# mcp_server/main.py - COMPLETE THREE-LAYER RBAC IMPLEMENTATION
"""
MCP Server - Layer 3 Security (Final Enforcement)
=================================================
This is the FINAL security gate. Even if Layer 1 (Django) and Layer 2 (LLM) 
fail, this layer MUST enforce RBAC correctly.

Features:
- Uses redaction.py for PHI field masking
- Complete audit logging with all fields
- FastAPI-compatible IP extraction
- Proper async/sync handling for Django ORM
"""

import os
import sys
import time
import json
from pathlib import Path
from datetime import datetime
from typing import Optional, Any, Dict

# Load .env FIRST
BASE_DIR = Path(__file__).resolve().parent.parent
env_path = BASE_DIR / ".env"

try:
    from dotenv import load_dotenv
    load_dotenv(env_path)
except Exception:
    pass

# Django setup
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "secure_hospital_ai.settings")

import django
django.setup()

from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from asgiref.sync import sync_to_async

from mcp_server.auth_middleware import auth_middleware
from mcp_server.db_client import (
    get_patient_overview,
    get_patient_phi,
    get_admissions_for_patient,
    get_appointments_for_patient,
    get_medical_records_for_patient,
    get_shifts_for_staff,
)
from mcp_server.redaction import redact_phi, isoformat_datetimes

app = FastAPI(title="SecureHospital MCP Server")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.middleware("http")(auth_middleware)


# ======================================================
# RBAC CONFIGURATION (Layer 3 - Final Enforcement)
# ======================================================

ROLES = ["Admin", "Doctor", "Nurse", "Auditor", "Reception", "Billing"]

# Tool -> Allowed Roles
TOOL_PERMISSIONS = {
    "get_patient_overview": ["Admin", "Doctor", "Nurse", "Auditor", "Reception", "Billing"],
    "get_medical_records": ["Admin", "Doctor", "Nurse", "Auditor"],
    "get_patient_phi": ["Admin", "Doctor", "Nurse", "Auditor", "Billing"],  # Different access levels
    "get_appointments": ["Admin", "Doctor", "Nurse", "Auditor", "Reception"],
    "get_admissions": ["Admin", "Doctor", "Nurse", "Auditor"],
    "get_my_shifts": ["Admin", "Doctor", "Nurse", "Auditor", "Reception", "Billing"],
    "get_shifts": ["Admin", "Auditor"],
}

# PHI Access Levels
PHI_FULL_ACCESS = ["Admin", "Doctor", "Auditor"]
PHI_REDACTED_ACCESS = ["Nurse"]
PHI_INSURANCE_ONLY = ["Billing"]
PHI_NO_ACCESS = ["Reception"]


# ======================================================
# AUDIT LOGGING (Fixed for FastAPI)
# ======================================================

def get_client_ip(request: Request) -> Optional[str]:
    """Extract client IP from FastAPI Request."""
    # Check proxy headers first
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    
    real_ip = request.headers.get("x-real-ip")
    if real_ip:
        return real_ip
    
    # Direct connection
    if request.client:
        return request.client.host
    return None


def get_user_agent(request: Request) -> Optional[str]:
    """Extract user agent from request."""
    return request.headers.get("user-agent")


@sync_to_async
def create_audit_log(
    user,
    action: str,
    table_name: str,
    record_id: str = None,
    ip_address: str = None,
    user_agent: str = None,
    is_phi_access: bool = False,
    tool_name: str = None,
    tool_arguments: dict = None,
    tool_result: str = None,
    access_granted: bool = True,
    denial_reason: str = None,
    duration_ms: int = None,
):
    """Create audit log entry in database."""
    try:
        from audit.models import AuditLog
        from django.utils import timezone
        from django.contrib.auth import get_user_model
        
        User = get_user_model()
        
        # Get real Django User instance
        # The auth middleware passes an AuthUser object, not a real User
        real_user = None
        if user:
            user_id = getattr(user, 'id', None)
            if user_id:
                try:
                    real_user = User.objects.get(id=user_id)
                except User.DoesNotExist:
                    print(f"⚠️ User {user_id} not found in database")
        
        # Build action string with tool info
        full_action = action
        if tool_name and action not in ["ACCESS_DENIED", "PHI_ACCESS_DENIED"]:
            full_action = f"{action}:{tool_name}"
        
        # Create audit log - only use fields that exist in the model
        AuditLog.objects.create(
            user=real_user,
            action=full_action,
            table_name=table_name,
            record_id=str(record_id) if record_id else None,
            timestamp=timezone.now(),
            ip_address=ip_address,
            is_phi_access=is_phi_access,
        )
        
        username = getattr(user, 'username', 'unknown')
        status = "✅" if access_granted else "❌"
        print(f"📝 Audit: {status} {full_action} | {table_name} | User: {username} | IP: {ip_address}")
        
    except Exception as e:
        print(f"⚠️ Audit log error: {e}")
        import traceback
        traceback.print_exc()


# ======================================================
# PHI REDACTION (Uses redaction.py)
# ======================================================

def apply_phi_redaction(data: dict, role: str) -> dict:
    """
    Apply role-based PHI redaction using redaction.py.
    
    - Admin/Doctor/Auditor: Full PHI (use 'full' scope)
    - Nurse: Clinical view (strips identifiers)
    - Billing: Insurance only
    - Reception: No PHI (should not reach here)
    """
    if not data:
        return data
    
    if role in PHI_FULL_ACCESS:
        # Full access - no redaction needed
        return data
    
    elif role in PHI_REDACTED_ACCESS:
        # Nurse: Clinical scope - strips identifying info
        redacted = redact_phi(data, role, scope="clinical")
        redacted["_access_level"] = "redacted"
        redacted["_note"] = "Some PHI fields redacted for Nurse role. Contact Admin for full access."
        return redacted
    
    elif role in PHI_INSURANCE_ONLY:
        # Billing: Insurance only
        redacted = redact_phi(data, role, scope="insurance")
        redacted["_access_level"] = "insurance_only"
        redacted["_note"] = "Only insurance information visible for Billing role."
        return redacted
    
    else:
        # No access - return empty
        return {
            "error": "PHI access denied for your role",
            "_access_level": "denied"
        }


# ======================================================
# REQUEST/RESPONSE MODELS
# ======================================================

class RPCRequest(BaseModel):
    jsonrpc: str
    id: Optional[Any] = None
    method: str
    params: Optional[Dict[str, Any]] = None

    class Config:
        extra = "allow"


def rpc_success(request_id, data, message: str = None, is_empty: bool = False):
    """Standard success response."""
    result = {"data": data}
    if message:
        result["message"] = message
    if is_empty:
        result["is_empty"] = True
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def rpc_error(request_id, code: int, message: str):
    """Standard error response."""
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def rpc_denied(request_id, reason: str):
    """Access denied response."""
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "result": {
            "data": None,
            "error": f"Access denied: {reason}",
            "access_denied": True
        }
    }


# ======================================================
# RBAC CHECK
# ======================================================

def check_permission(role: str, tool: str) -> tuple:
    """
    Check if role has permission for tool.
    Returns: (allowed: bool, reason: str)
    """
    if role not in ROLES:
        return False, f"Unknown role: {role}"
    
    allowed_roles = TOOL_PERMISSIONS.get(tool, [])
    if role not in allowed_roles:
        return False, f"Role '{role}' is not authorized for {tool}"
    
    return True, None


# ======================================================
# MAIN RPC HANDLER
# ======================================================

@app.post("/mcp/")
async def handle_rpc(request: Request, payload: RPCRequest):
    """Main RPC handler with three-layer RBAC enforcement."""
    
    start_time = time.time()
    
    print(f"\n{'='*60}")
    print(f"📥 MCP Request: {payload.method}")
    print(f"{'='*60}")
    
    # Only handle tools.call
    if payload.method != "tools.call":
        return rpc_error(payload.id, -32601, f"Unknown method: {payload.method}")

    params = payload.params or {}
    tool = params.get("name")
    args = params.get("arguments", {}) or {}

    if not tool:
        return rpc_error(payload.id, -32602, "Missing tool name")

    # Get user context from auth middleware
    user = getattr(request.state, "user", None)
    role = getattr(request.state, "role", "unknown")
    user_id = getattr(request.state, "user_id", None)
    
    # Get request metadata
    ip = get_client_ip(request)
    user_agent = get_user_agent(request)
    
    print(f"🔧 Tool: {tool}")
    print(f"👤 User: {user} | Role: {role}")
    print(f"🌐 IP: {ip}")
    print(f"📋 Args: {args}")

    # ===================================
    # LAYER 3 RBAC CHECK
    # ===================================
    allowed, denial_reason = check_permission(role, tool)
    
    if not allowed:
        duration_ms = int((time.time() - start_time) * 1000)
        
        await create_audit_log(
            user=user,
            action="ACCESS_DENIED",
            table_name="rbac",
            ip_address=ip,
            user_agent=user_agent,
            is_phi_access=False,
            tool_name=tool,
            tool_arguments=args,
            access_granted=False,
            denial_reason=denial_reason,
            duration_ms=duration_ms,
        )
        
        print(f"❌ RBAC DENIED: {denial_reason}")
        return rpc_denied(payload.id, denial_reason)

    # ===================================
    # TOOL HANDLERS
    # ===================================
    
    try:
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
                action="TOOL_CALL",
                table_name="patients",
                record_id=patient_id,
                ip_address=ip,
                user_agent=user_agent,
                is_phi_access=False,
                tool_name=tool,
                tool_arguments=args,
                tool_result=f"Found patient" if data else "No patient found",
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
                action="PHI_ACCESS",
                table_name="medical_records",
                record_id=patient_id,
                ip_address=ip,
                user_agent=user_agent,
                is_phi_access=True,
                tool_name=tool,
                tool_arguments=args,
                tool_result=f"Retrieved {len(data) if data else 0} records",
                access_granted=True,
                duration_ms=duration_ms,
            )
            
            if not data:
                print(f"⚠️ No medical records: {patient_id}")
                return rpc_success(payload.id, [], f"No medical records for {patient_id}", is_empty=True)
            
            data = isoformat_datetimes(data)
            print(f"✅ Medical records retrieved: {len(data)} records")
            return rpc_success(payload.id, data)

        # -----------------------------------
        # get_patient_phi (PHI with redaction)
        # -----------------------------------
        elif tool == "get_patient_phi":
            patient_id = args.get("patient_id")
            if not patient_id:
                return rpc_error(payload.id, -32602, "Missing patient_id")
            
            # Special handling for roles with no PHI access
            if role in PHI_NO_ACCESS:
                duration_ms = int((time.time() - start_time) * 1000)
                
                await create_audit_log(
                    user=user,
                    action="PHI_ACCESS_DENIED",
                    table_name="patient_phi",
                    record_id=patient_id,
                    ip_address=ip,
                    user_agent=user_agent,
                    is_phi_access=True,
                    tool_name=tool,
                    tool_arguments=args,
                    access_granted=False,
                    denial_reason=f"Role '{role}' has no PHI access",
                    duration_ms=duration_ms,
                )
                
                print(f"❌ PHI access denied for {role}")
                return rpc_denied(payload.id, f"Role '{role}' does not have PHI access")
            
            # Get PHI data
            data = get_patient_phi(patient_id)
            
            if not data:
                duration_ms = int((time.time() - start_time) * 1000)
                await create_audit_log(
                    user=user,
                    action="PHI_ACCESS",
                    table_name="patient_phi",
                    record_id=patient_id,
                    ip_address=ip,
                    user_agent=user_agent,
                    is_phi_access=True,
                    tool_name=tool,
                    tool_arguments=args,
                    tool_result="No PHI found",
                    access_granted=True,
                    duration_ms=duration_ms,
                )
                print(f"⚠️ No PHI found: {patient_id}")
                return rpc_success(payload.id, None, f"No PHI found for {patient_id}", is_empty=True)
            
            # Apply role-based redaction
            access_level = "full"
            if role in PHI_REDACTED_ACCESS:
                access_level = "redacted"
                data = apply_phi_redaction(data, role)
                print(f"⚠️ PHI redacted for {role}")
            elif role in PHI_INSURANCE_ONLY:
                access_level = "insurance_only"
                data = apply_phi_redaction(data, role)
                print(f"💳 Insurance-only PHI for {role}")
            else:
                print(f"✅ Full PHI access for {role}")
            
            duration_ms = int((time.time() - start_time) * 1000)
            
            await create_audit_log(
                user=user,
                action="PHI_ACCESS",
                table_name="patient_phi",
                record_id=patient_id,
                ip_address=ip,
                user_agent=user_agent,
                is_phi_access=True,
                tool_name=tool,
                tool_arguments=args,
                tool_result=f"PHI retrieved (access_level: {access_level})",
                access_granted=True,
                duration_ms=duration_ms,
            )
            
            data = isoformat_datetimes(data)
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
                action="TOOL_CALL",
                table_name="appointments",
                record_id=patient_id,
                ip_address=ip,
                user_agent=user_agent,
                is_phi_access=False,
                tool_name=tool,
                tool_arguments=args,
                tool_result=f"Retrieved {len(data) if data else 0} appointments",
                access_granted=True,
                duration_ms=duration_ms,
            )
            
            if not data:
                return rpc_success(payload.id, [], f"No appointments for {patient_id}", is_empty=True)
            
            data = isoformat_datetimes(data)
            print(f"📅 Appointments retrieved: {len(data)}")
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
                action="TOOL_CALL",
                table_name="admissions",
                record_id=patient_id,
                ip_address=ip,
                user_agent=user_agent,
                is_phi_access=False,
                tool_name=tool,
                tool_arguments=args,
                tool_result=f"Retrieved {len(data) if data else 0} admissions",
                access_granted=True,
                duration_ms=duration_ms,
            )
            
            if not data:
                return rpc_success(payload.id, [], f"No admissions for {patient_id}", is_empty=True)
            
            data = isoformat_datetimes(data)
            print(f"🏥 Admissions retrieved: {len(data)}")
            return rpc_success(payload.id, data)

        # -----------------------------------
        # get_my_shifts
        # -----------------------------------
        elif tool == "get_my_shifts":
            staff_id = args.get("staff_id")
            
            # Try to get staff_id from user if not provided
            if not staff_id and user:
                try:
                    from ehr.models import Staff
                    # Get user_id from the AuthUser object
                    auth_user_id = getattr(user, 'id', None)
                    if auth_user_id:
                        @sync_to_async
                        def get_staff_id_for_user(uid):
                            staff = Staff.objects.filter(user_id=uid).first()
                            return str(staff.staff_id) if staff else None
                        
                        staff_id = await get_staff_id_for_user(auth_user_id)
                except Exception as e:
                    print(f"Could not get staff_id: {e}")
            
            if not staff_id:
                return rpc_error(payload.id, -32602, "Missing staff_id")
            
            data = get_shifts_for_staff(staff_id)
            duration_ms = int((time.time() - start_time) * 1000)
            
            await create_audit_log(
                user=user,
                action="TOOL_CALL",
                table_name="shifts",
                record_id=staff_id,
                ip_address=ip,
                user_agent=user_agent,
                is_phi_access=False,
                tool_name=tool,
                tool_arguments={"staff_id": staff_id},
                tool_result=f"Retrieved {len(data) if data else 0} shifts",
                access_granted=True,
                duration_ms=duration_ms,
            )
            
            if not data:
                return rpc_success(payload.id, [], f"No shifts for staff {staff_id}", is_empty=True)
            
            data = isoformat_datetimes(data)
            print(f"📅 My shifts retrieved: {len(data)}")
            return rpc_success(payload.id, data)

        # -----------------------------------
        # get_shifts (all department shifts)
        # -----------------------------------
        elif tool == "get_shifts":
            department = args.get("department")
            
            from ehr.models import Shift
            
            # Use a sync function to fetch shifts with related staff data
            @sync_to_async
            def fetch_shifts(dept=None):
                if dept:
                    shifts = list(
                        Shift.objects.select_related('staff')
                        .filter(staff__department__icontains=dept)
                        .order_by('-start_time')[:50]
                    )
                else:
                    shifts = list(
                        Shift.objects.select_related('staff')
                        .order_by('-start_time')[:50]
                    )
                
                result = []
                for s in shifts:
                    staff_dept = None
                    if s.staff:
                        staff_dept = getattr(s.staff, 'department', None)
                    
                    result.append({
                        "shift_id": str(s.shift_id),
                        "staff_id": str(s.staff_id) if s.staff_id else None,
                        "start_time": s.start_time.isoformat() if s.start_time else None,
                        "end_time": s.end_time.isoformat() if s.end_time else None,
                        "department": staff_dept,
                    })
                return result
            
            data = await fetch_shifts(department)
            
            duration_ms = int((time.time() - start_time) * 1000)
            
            await create_audit_log(
                user=user,
                action="TOOL_CALL",
                table_name="shifts",
                record_id=department or "all",
                ip_address=ip,
                user_agent=user_agent,
                is_phi_access=False,
                tool_name=tool,
                tool_arguments=args,
                tool_result=f"Retrieved {len(data)} shifts",
                access_granted=True,
                duration_ms=duration_ms,
            )
            
            if not data:
                return rpc_success(payload.id, [], "No shifts found", is_empty=True)
            
            print(f"📅 All shifts retrieved: {len(data)}")
            return rpc_success(payload.id, data)

        # -----------------------------------
        # Unknown tool
        # -----------------------------------
        else:
            print(f"❌ Unknown tool: {tool}")
            return rpc_error(payload.id, -32601, f"Unknown tool: {tool}")

    except Exception as e:
        print(f"❌ Error in tool {tool}: {e}")
        import traceback
        traceback.print_exc()
        
        duration_ms = int((time.time() - start_time) * 1000)
        
        await create_audit_log(
            user=user,
            action="TOOL_ERROR",
            table_name="error",
            ip_address=ip,
            user_agent=user_agent,
            is_phi_access=False,
            tool_name=tool,
            tool_arguments=args,
            tool_result=str(e),
            access_granted=False,
            denial_reason=f"Internal error: {str(e)}",
            duration_ms=duration_ms,
        )
        
        return rpc_error(payload.id, -32603, f"Internal error: {str(e)}")


# ======================================================
# UTILITY ENDPOINTS
# ======================================================

@app.get("/health")
async def health():
    return {"status": "ok", "service": "mcp-server", "version": "2.0"}


@app.get("/tools")
async def list_tools():
    """List available tools with RBAC info."""
    return {
        "tools": [
            {
                "name": "get_patient_overview",
                "description": "Get basic patient demographics",
                "allowed_roles": TOOL_PERMISSIONS["get_patient_overview"],
                "phi_level": "none"
            },
            {
                "name": "get_medical_records",
                "description": "Get patient medical records",
                "allowed_roles": TOOL_PERMISSIONS["get_medical_records"],
                "phi_level": "clinical"
            },
            {
                "name": "get_patient_phi",
                "description": "Get Protected Health Information",
                "allowed_roles": TOOL_PERMISSIONS["get_patient_phi"],
                "phi_level": "varies_by_role",
                "phi_notes": {
                    "Admin/Doctor/Auditor": "Full PHI",
                    "Nurse": "Redacted (no SSN/address)",
                    "Billing": "Insurance only",
                    "Reception": "Denied"
                }
            },
            {
                "name": "get_appointments",
                "description": "Get patient appointments",
                "allowed_roles": TOOL_PERMISSIONS["get_appointments"],
                "phi_level": "none"
            },
            {
                "name": "get_admissions",
                "description": "Get patient hospital admissions",
                "allowed_roles": TOOL_PERMISSIONS["get_admissions"],
                "phi_level": "none"
            },
            {
                "name": "get_my_shifts",
                "description": "Get current user's shifts",
                "allowed_roles": TOOL_PERMISSIONS["get_my_shifts"],
                "phi_level": "none"
            },
            {
                "name": "get_shifts",
                "description": "Get all department shifts",
                "allowed_roles": TOOL_PERMISSIONS["get_shifts"],
                "phi_level": "none"
            },
        ],
        "roles": ROLES,
        "phi_access_levels": {
            "full": PHI_FULL_ACCESS,
            "redacted": PHI_REDACTED_ACCESS,
            "insurance_only": PHI_INSURANCE_ONLY,
            "none": PHI_NO_ACCESS,
        }
    }


@app.get("/rbac")
async def get_rbac():
    """Get RBAC matrix for UI display."""
    return {
        "permissions": TOOL_PERMISSIONS,
        "phi_levels": {
            "full": PHI_FULL_ACCESS,
            "redacted": PHI_REDACTED_ACCESS,
            "insurance_only": PHI_INSURANCE_ONLY,
            "none": PHI_NO_ACCESS,
        }
    }