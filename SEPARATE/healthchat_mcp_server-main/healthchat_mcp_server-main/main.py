# mcp_server/main.py - STANDALONE MCP SERVER (No Django)
"""
MCP Server - Standalone Deployment
==================================
This is a completely standalone MCP server that can be deployed independently.
No Django dependencies - uses direct SQL for all database operations.

Features:
- JWT authentication (via middleware)
- Three-layer RBAC
- PHI redaction
- Comprehensive audit logging via SQL
"""

import os
import time
import json
from datetime import datetime
from typing import Optional, Any, Dict, List, Union
from uuid import uuid4

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import traceback

# Local imports
from db_client import (
    get_db_cursor,
    get_patient_overview,
    get_patient_phi,
    get_admissions_for_patient,
    get_appointments_for_patient,
    get_medical_records_for_patient,
    get_shifts_for_staff,
    get_all_shifts,
    get_staff_id_for_user,
)
from auth_middleware import auth_middleware

# ======================================================
# FASTAPI APP SETUP
# ======================================================

app = FastAPI(title="SecureHospital MCP Server")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify exact origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# JWT Authentication Middleware
app.middleware("http")(auth_middleware)


# ======================================================
# IP & USER AGENT HELPERS
# ======================================================

def get_client_ip(request: Request) -> Optional[str]:
    """Extract client IP from request, checking for proxy headers."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    
    real_ip = request.headers.get("x-real-ip")
    if real_ip:
        return real_ip
    
    return request.client.host if request.client else None


def get_user_agent(request: Request) -> Optional[str]:
    return request.headers.get("user-agent")


# ======================================================
# AUDIT LOGGING
# ======================================================

async def create_audit_log(
    *,
    user,
    action: str,
    table_name: str = "",
    record_id: Optional[str] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
    is_phi_access: bool = False,
    tool_name: Optional[str] = None,
    tool_parameters: Optional[Dict[str, Any]] = None,
    tool_result_summary: Optional[str] = None,
    access_granted: bool = True,
    denial_reason: Optional[str] = None,
    duration_ms: Optional[int] = None,
    action_details: Optional[str] = None,
):
    """
    Create audit log entry in Django audit_auditlog table using direct SQL.
    Matches Django AuditLog model schema exactly.
    
    Action types should be one of:
    - TOOL_CALL, TOOL_SUCCESS, TOOL_FAILURE
    - ACCESS_GRANTED, ACCESS_DENIED
    - PHI_READ, PHI_WRITE, PHI_DENIED
    - LOGIN, LOGOUT, SESSION_CREATE
    - ERROR, SECURITY_EVENT
    """
    try:
        user_id = getattr(user, "id", None)
        username = getattr(user, "username", "unknown")

        with get_db_cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO audit_auditlog (
                    audit_id,
                    user_id,
                    action,
                    action_details,
                    table_name,
                    record_id,
                    tool_name,
                    tool_parameters,
                    tool_result_summary,
                    access_granted,
                    denial_reason,
                    timestamp,
                    duration_ms,
                    ip_address,
                    user_agent,
                    is_phi_access,
                    is_suspicious,
                    risk_score,
                    country,
                    region,
                    city,
                    latitude,
                    longitude
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    str(uuid4()),
                    user_id,
                    action,
                    action_details or "",
                    table_name or "",
                    record_id,
                    tool_name or "",
                    json.dumps(tool_parameters) if tool_parameters else None,
                    tool_result_summary or "",
                    access_granted,
                    denial_reason or "",
                    datetime.utcnow(),
                    duration_ms,
                    ip_address,
                    user_agent or "",
                    is_phi_access,
                    False,  # is_suspicious - could be calculated based on patterns
                    0,      # risk_score - could be calculated
                    "",     # country - could be populated with GeoIP lookup
                    "",     # region
                    "",     # city
                    None,   # latitude
                    None,   # longitude
                ),
            )

        status = "✅" if access_granted else "❌"
        action_str = f"{action}:{tool_name}" if tool_name else action
        print(
            f"📝 Audit {status} | {action_str} | "
            f"User={username} | Table={table_name} | IP={ip_address}"
        )

    except Exception as e:
        print("⚠️ MCP audit logging failed (non-blocking):", e)
        traceback.print_exc()


# ======================================================
# PHI REDACTION
# ======================================================

def apply_phi_redaction(data: dict, role: str) -> dict:
    """
    Apply role-based PHI redaction.

    Roles allowed full PHI access:
    - Admin
    - Doctor
    - Nurse
    - Auditor

    Roles with limited PHI access:
    - Billing: Redacts clinical notes
    - Reception: Redacts everything except contact info
    """
    PHI_FULL_ACCESS = ["Admin", "Doctor", "Nurse", "Auditor"]

    if role in PHI_FULL_ACCESS:
        return data

    redacted = data.copy()

    if role == "Billing":
        redacted["diagnosis"] = "[REDACTED]"
        redacted["treatment"] = "[REDACTED]"
        redacted["notes"] = "[REDACTED]"
    elif role == "Reception":
        # Reception can only see scheduling info
        for key in list(redacted.keys()):
            if key not in ["patient_id", "appointment_id", "appointment_date", "status"]:
                redacted[key] = "[REDACTED]"

    return redacted


# ======================================================
# RBAC ENFORCEMENT
# ======================================================

PHI_TOOLS = [
    "get_patient_phi",
    "get_medical_records",
]

ALLOWED_ROLES_FOR_PHI = ["Admin", "Doctor", "Nurse", "Auditor"]


def check_rbac(role: str, tool_name: str) -> tuple[bool, Optional[str]]:
    """
    Check if user has permission to execute tool.
    Returns (allowed, denial_reason).
    """
    if tool_name in PHI_TOOLS:
        if role not in ALLOWED_ROLES_FOR_PHI:
            return False, f"Role '{role}' not authorized for PHI access"

    return True, None


# ======================================================
# DATETIME FORMATTING
# ======================================================

def isoformat_datetimes(data):
    """Convert datetime objects to ISO format strings for JSON serialization."""
    if isinstance(data, dict):
        return {k: isoformat_datetimes(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [isoformat_datetimes(item) for item in data]
    elif isinstance(data, datetime):
        return data.isoformat()
    return data


# ======================================================
# MCP RPC PROTOCOL
# ======================================================

class MCPRequest(BaseModel):
    jsonrpc: str = "2.0"
    id: Optional[Union[int, str]] = None  # JSON-RPC 2.0 allows string, number, or null
    method: str
    params: Optional[Dict[str, Any]] = None


def rpc_success(id: Optional[Union[int, str]], result: Any, message: Optional[str] = None, is_empty: bool = False):
    """Standard JSON-RPC success response."""
    response = {"jsonrpc": "2.0", "id": id, "result": result}
    if message:
        response["message"] = message
    if is_empty:
        response["is_empty"] = True
    return response


def rpc_error(id: Optional[Union[int, str]], code: int, message: str):
    """Standard JSON-RPC error response."""
    return {"jsonrpc": "2.0", "id": id, "error": {"code": code, "message": message}}


# ======================================================
# ENDPOINTS
# ======================================================

@app.get("/health")
async def health_check():
    """Health check endpoint for monitoring."""
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}


@app.post("/mcp/")
async def handle_rpc(payload: MCPRequest, request: Request):
    """
    Main MCP endpoint - handles all tool calls with:
    - JWT authentication (via middleware)
    - RBAC enforcement
    - Audit logging
    - PHI redaction
    """
    start_time = time.time()

    # Get user context from auth middleware
    user = getattr(request.state, "user", None)
    role = getattr(request.state, "role", "unknown")
    user_id = getattr(request.state, "user_id", None)

    # Get request metadata
    ip = get_client_ip(request)
    user_agent = get_user_agent(request)

    print(f"\n{'='*60}")
    print(f"🔧 Tool: {payload.method}")
    print(f"👤 User: {user} | Role: {role}")
    print(f"🌐 IP: {ip}")
    print(f"📋 Params: {payload.params}")

    # ==============================
    # METHOD ROUTING
    # ==============================

    try:
        # ======================================
        # INITIALIZE / LIST TOOLS
        # ======================================
        if payload.method == "initialize":
            await create_audit_log(
                user=user,
                action="SESSION_CREATE",
                table_name="session",
                ip_address=ip,
                user_agent=user_agent,
                tool_name="initialize",
                tool_result_summary="MCP session initialized"
            )

            return rpc_success(payload.id, {
                "protocolVersion": "2024-11-05",
                "capabilities": {
                    "tools": {},
                },
                "serverInfo": {
                    "name": "SecureHospital-MCP",
                    "version": "1.0.0"
                }
            })

        elif payload.method == "tools/list":
            tools_list = [
                {
                    "name": "get_patient_overview",
                    "description": "Get patient demographics (non-PHI)",
                    "inputSchema": {
                        "type": "object",
                        "properties": {"patient_id": {"type": "string"}},
                        "required": ["patient_id"]
                    }
                },
                {
                    "name": "get_patient_phi",
                    "description": "Get Protected Health Information - Admin/Doctor/Nurse/Auditor only",
                    "inputSchema": {
                        "type": "object",
                        "properties": {"patient_id": {"type": "string"}},
                        "required": ["patient_id"]
                    }
                },
                {
                    "name": "get_medical_records",
                    "description": "Get medical records (PHI) - Admin/Doctor/Nurse/Auditor only",
                    "inputSchema": {
                        "type": "object",
                        "properties": {"patient_id": {"type": "string"}},
                        "required": ["patient_id"]
                    }
                },
                {
                    "name": "get_admissions",
                    "description": "Get hospital admissions for patient",
                    "inputSchema": {
                        "type": "object",
                        "properties": {"patient_id": {"type": "string"}},
                        "required": ["patient_id"]
                    }
                },
                {
                    "name": "get_appointments",
                    "description": "Get appointments for patient",
                    "inputSchema": {
                        "type": "object",
                        "properties": {"patient_id": {"type": "string"}},
                        "required": ["patient_id"]
                    }
                },
                {
                    "name": "get_my_shifts",
                    "description": "Get shifts for current staff member",
                    "inputSchema": {"type": "object", "properties": {}}
                },
                {
                    "name": "get_shifts",
                    "description": "Get all shifts (Admin only) - optionally filter by department",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "department": {"type": "string", "description": "Optional department filter"}
                        }
                    }
                },
            ]
            return rpc_success(payload.id, {"tools": tools_list})

        # ======================================
        # TOOL EXECUTION
        # ======================================
        elif payload.method == "tools/call" or payload.method == "tools.call":
            args = payload.params.get("arguments", {}) if payload.params else {}
            tool = payload.params.get("name") if payload.params else None

            if not tool:
                return rpc_error(payload.id, -32602, "Missing tool name")

            # ==============================
            # RBAC CHECK
            # ==============================
            allowed, denial_reason = check_rbac(role, tool)
            if not allowed:
                print(f"❌ Access denied: {denial_reason}")
                
                await create_audit_log(
                    user=user,
                    action="ACCESS_DENIED",
                    table_name="rbac",
                    ip_address=ip,
                    user_agent=user_agent,
                    tool_name=tool,
                    tool_parameters=args,
                    access_granted=False,
                    denial_reason=denial_reason,
                    is_phi_access=(tool in PHI_TOOLS)
                )

                return rpc_error(payload.id, -32003, denial_reason)

            # ======================================
            # TOOL IMPLEMENTATIONS
            # ======================================

            # -----------------------------------
            # get_patient_overview (Non-PHI)
            # -----------------------------------
            if tool == "get_patient_overview":
                patient_id = args.get("patient_id")
                if not patient_id:
                    return rpc_error(payload.id, -32602, "Missing patient_id")

                data = get_patient_overview(patient_id)
                duration_ms = int((time.time() - start_time) * 1000)

                await create_audit_log(
                    user=user,
                    action="TOOL_SUCCESS",
                    table_name="ehr_patient",
                    record_id=patient_id,
                    ip_address=ip,
                    user_agent=user_agent,
                    is_phi_access=False,
                    tool_name=tool,
                    tool_parameters=args,
                    tool_result_summary=f"Found patient" if data else "No patient found",
                    access_granted=True,
                    duration_ms=duration_ms,
                )

                if not data:
                    print(f"⚠️ Patient not found: {patient_id}")
                    return rpc_success(payload.id, None, f"No patient found with ID {patient_id}", is_empty=True)

                data = isoformat_datetimes(data)
                print(f"✅ Patient overview retrieved: {patient_id}")
                return rpc_success(payload.id, data)

            # -----------------------------------
            # get_medical_records (PHI)
            # -----------------------------------
            elif tool == "get_medical_records":
                patient_id = args.get("patient_id")
                if not patient_id:
                    return rpc_error(payload.id, -32602, "Missing patient_id")

                data = get_medical_records_for_patient(patient_id)
                duration_ms = int((time.time() - start_time) * 1000)

                await create_audit_log(
                    user=user,
                    action="PHI_READ",
                    table_name="ehr_medicalrecord",
                    record_id=patient_id,
                    ip_address=ip,
                    user_agent=user_agent,
                    is_phi_access=True,
                    tool_name=tool,
                    tool_parameters=args,
                    tool_result_summary=f"Retrieved {len(data) if data else 0} records",
                    access_granted=True,
                    duration_ms=duration_ms,
                )

                if not data:
                    print(f"⚠️ No medical records: {patient_id}")
                    return rpc_success(payload.id, [], f"No medical records for {patient_id}", is_empty=True)

                # Apply PHI redaction based on role
                redacted_data = [apply_phi_redaction(record, role) for record in data]
                redacted_data = isoformat_datetimes(redacted_data)

                print(f"✅ Medical records retrieved: {len(data)} records")
                return rpc_success(payload.id, redacted_data)

            # -----------------------------------
            # get_patient_phi (PHI)
            # -----------------------------------
            elif tool == "get_patient_phi":
                patient_id = args.get("patient_id")
                if not patient_id:
                    return rpc_error(payload.id, -32602, "Missing patient_id")

                data = get_patient_phi(patient_id)
                duration_ms = int((time.time() - start_time) * 1000)

                await create_audit_log(
                    user=user,
                    action="PHI_READ",
                    table_name="ehr_phidemographics",
                    record_id=patient_id,
                    ip_address=ip,
                    user_agent=user_agent,
                    is_phi_access=True,
                    tool_name=tool,
                    tool_parameters=args,
                    tool_result_summary="PHI retrieved" if data else "No PHI found",
                    access_granted=True,
                    duration_ms=duration_ms,
                )

                if not data:
                    print(f"⚠️ PHI not found: {patient_id}")
                    return rpc_success(payload.id, None, f"No PHI found for {patient_id}", is_empty=True)

                data = isoformat_datetimes(data)
                print(f"✅ PHI retrieved: {patient_id}")
                return rpc_success(payload.id, data)

            # -----------------------------------
            # get_admissions
            # -----------------------------------
            elif tool == "get_admissions":
                patient_id = args.get("patient_id")
                if not patient_id:
                    return rpc_error(payload.id, -32602, "Missing patient_id")

                data = get_admissions_for_patient(patient_id)
                duration_ms = int((time.time() - start_time) * 1000)

                await create_audit_log(
                    user=user,
                    action="TOOL_SUCCESS",
                    table_name="ehr_admission",
                    record_id=patient_id,
                    ip_address=ip,
                    user_agent=user_agent,
                    tool_name=tool,
                    tool_parameters=args,
                    tool_result_summary=f"Retrieved {len(data)} admissions",
                    duration_ms=duration_ms,
                )

                data = isoformat_datetimes(data)
                print(f"✅ Admissions retrieved: {len(data)}")
                return rpc_success(payload.id, data)

            # -----------------------------------
            # get_appointments
            # -----------------------------------
            elif tool == "get_appointments":
                patient_id = args.get("patient_id")
                if not patient_id:
                    return rpc_error(payload.id, -32602, "Missing patient_id")

                data = get_appointments_for_patient(patient_id)
                duration_ms = int((time.time() - start_time) * 1000)

                await create_audit_log(
                    user=user,
                    action="TOOL_SUCCESS",
                    table_name="ehr_appointment",
                    record_id=patient_id,
                    ip_address=ip,
                    user_agent=user_agent,
                    tool_name=tool,
                    tool_parameters=args,
                    tool_result_summary=f"Retrieved {len(data)} appointments",
                    duration_ms=duration_ms,
                )

                data = isoformat_datetimes(data)
                print(f"✅ Appointments retrieved: {len(data)}")
                return rpc_success(payload.id, data)

            # -----------------------------------
            # get_my_shifts
            # -----------------------------------
            elif tool == "get_my_shifts":
                staff_id = get_staff_id_for_user(user_id)
                if not staff_id:
                    return rpc_error(payload.id, -32002, "Staff ID not found for current user")

                data = get_shifts_for_staff(staff_id)
                duration_ms = int((time.time() - start_time) * 1000)

                await create_audit_log(
                    user=user,
                    action="TOOL_SUCCESS",
                    table_name="ehr_shift",
                    record_id=staff_id,
                    ip_address=ip,
                    user_agent=user_agent,
                    tool_name=tool,
                    tool_parameters={"staff_id": staff_id},
                    tool_result_summary=f"Retrieved {len(data)} shifts",
                    duration_ms=duration_ms,
                )

                data = isoformat_datetimes(data)
                print(f"✅ Staff shifts retrieved: {len(data)}")
                return rpc_success(payload.id, data)

            # -----------------------------------
            # get_shifts (Admin only)
            # -----------------------------------
            elif tool == "get_shifts":
                if role != "Admin":
                    await create_audit_log(
                        user=user,
                        action="ACCESS_DENIED",
                        table_name="ehr_shift",
                        ip_address=ip,
                        user_agent=user_agent,
                        tool_name=tool,
                        tool_parameters=args,
                        access_granted=False,
                        denial_reason="Admin role required"
                    )
                    return rpc_error(payload.id, -32003, "Admin role required for get_shifts")

                department = args.get("department")
                data = get_all_shifts(department=department)
                duration_ms = int((time.time() - start_time) * 1000)

                await create_audit_log(
                    user=user,
                    action="TOOL_SUCCESS",
                    table_name="ehr_shift",
                    ip_address=ip,
                    user_agent=user_agent,
                    tool_name=tool,
                    tool_parameters=args,
                    tool_result_summary=f"Retrieved {len(data)} shifts",
                    duration_ms=duration_ms,
                )

                data = isoformat_datetimes(data)
                print(f"✅ All shifts retrieved: {len(data)}")
                return rpc_success(payload.id, data)

            # Unknown tool
            else:
                print(f"❌ Unknown tool: {tool}")
                return rpc_error(payload.id, -32601, f"Unknown tool: {tool}")

        else:
            return rpc_error(payload.id, -32601, f"Unknown method: {payload.method}")

    except Exception as e:
        print(f"❌ Error in tool {payload.method}: {e}")
        traceback.print_exc()

        duration_ms = int((time.time() - start_time) * 1000)
        await create_audit_log(
            user=user,
            action="TOOL_FAILURE",
            table_name="error",
            record_id=None,
            ip_address=ip,
            user_agent=user_agent,
            is_phi_access=False,
            tool_name=payload.params.get("name") if payload.params else None,
            access_granted=False,
            denial_reason=f"Internal error: {str(e)}",
            duration_ms=duration_ms,
        )

        return rpc_error(payload.id, -32603, f"Internal error: {str(e)}")


# ======================================================
# MAIN
# ======================================================

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8001))
    print(f"🚀 Starting SecureHospital MCP Server on port {port}")
    uvicorn.run(app, host="0.0.0.0", port=port)
