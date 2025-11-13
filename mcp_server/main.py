"""
Secure Hospital MCP Server (JWT + RBAC + Redaction)
---------------------------------------------------
This server is a Medical Compliance Proxy (MCP) that:
- Authenticates requests using Django SimpleJWT tokens (HS256 by default).
- Enforces RBAC for each tool/action.
- Redacts PHI before returning to the LLM.
- Writes immutable audit events.

LLM clients (or your Django frontend proxy) POST JSON-RPC payloads to /mcp/.
"""

import os
import json
import datetime as dt
from typing import Any, Dict, Optional, Tuple

# Ensure Django is configured (db clients may import Django models or settings)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "secure_hospital_ai.settings")

import django
django.setup()

import jwt  # PyJWT
from fastapi import FastAPI, Request, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from mcp_server.rbac import is_allowed  # your RBAC checker: (model, action, role, user_id, row_context) -> bool
from mcp_server.db_client import (
    get_patient_overview,
    get_patient_phi,
    get_admissions_for_patient,
    get_appointments_for_patient,
    get_medical_records_for_patient,
    get_shifts_for_staff,
)
from mcp_server.redaction import redact_phi, isoformat_datetimes
from mcp_server.audit_logger import log_audit

# -----------------------------------------------
# Environment (configure in production)
# -----------------------------------------------
JWT_ALG = os.getenv("JWT_ALG", "HS256")
JWT_SECRET = os.getenv("JWT_SECRET")
JWT_ISSUER = os.getenv("JWT_ISSUER")  # optional
JWT_AUDIENCE = os.getenv("JWT_AUD")   # optional
ALLOW_CLOCK_SKEW = int(os.getenv("JWT_LEEWAY_SECS", "60"))  # seconds

if not JWT_SECRET:
    # Fail fast in production so we never run without verification.
    # For local demos, you can set JWT_SECRET in your shell or .env.
    raise RuntimeError("JWT_SECRET is required for MCP to validate tokens.")

# -----------------------------------------------
# FastAPI setup
# -----------------------------------------------
app = FastAPI(
    title="Secure Hospital MCP Server",
    description="Acts as a medical compliance proxy (MCP) for LLM-based hospital systems",
    version="2.0.0",
)


# -----------------------------------------------
# Models for incoming JSON-RPC
# -----------------------------------------------
class JsonRpcParams(BaseModel):
    name: str
    arguments: Dict[str, Any] = {}


class JsonRpcRequest(BaseModel):
    jsonrpc: str = "2.0"
    id: Optional[int] = 1
    method: str
    params: Optional[JsonRpcParams] = None


# -----------------------------------------------
# Identity extraction (JWT validation)
# -----------------------------------------------
class Identity(BaseModel):
    user_id: str
    role: str
    raw_claims: Dict[str, Any]


JWT_SECRET = os.getenv("JWT_SECRET")
JWT_ALG = os.getenv("JWT_ALG", "HS256")

def _decode_jwt_or_401(token: str):
    """
    Decodes a JWT and raises HTTP 401 if invalid or expired.
    """
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing Authorization token")

    try:
        # ✅ Correct usage: first positional argument is the JWT string
        decoded = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
        return decoded

    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired")
    except jwt.InvalidTokenError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"Invalid token: {e}")
    
    
async def get_identity(request: Request) -> Identity:
    """
    Authenticate using Bearer token; return Identity(user_id, role, raw_claims).
    The Django proxy should mint tokens with a `user_id` and `role` claim.
    """
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing Bearer token")

    token = auth.split(" ", 1)[1]
    claims = _decode_jwt_or_401(token)

    # Django SimpleJWT default includes "user_id". We add "role" in minting step.
    user_id = str(claims.get("user_id") or claims.get("sub") or "")
    role = str(claims.get("role") or "Auditor")

    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token missing user_id")

    return Identity(user_id=user_id, role=role, raw_claims=claims)


# -----------------------------------------------
# Helpers
# -----------------------------------------------
def _rpc_error(id_: Optional[int], message: str, code: int = -32600) -> JSONResponse:
    """JSON-RPC error response."""
    return JSONResponse(
        status_code=400 if code == -32600 else 500,
        content={"jsonrpc": "2.0", "id": id_, "error": {"code": code, "message": message}},
    )


def _rpc_result(id_: Optional[int], result: Dict[str, Any]) -> JSONResponse:
    """JSON-RPC success response."""
    return JSONResponse(content={"jsonrpc": "2.0", "id": id_, "result": result})


def _audit_ok(user_id: str, action: str, table: str, is_phi: bool, ip: Optional[str]):
    """Log audit event; never crash the request on audit failure."""
    try:
        log_audit(
            action=action,
            table_name=table,
            is_phi_access=is_phi,
            ip_address=ip,
            # Optionally, you could pass record_id if you have a specific PK.
        )
    except Exception as e:
        # Don't leak internal details; print to server logs instead.
        print(f"⚠️  Audit log failed: {e}")


# -----------------------------------------------
# Routes
# -----------------------------------------------
@app.get("/")
async def home():
    return {"ok": True, "service": "Secure Hospital MCP", "version": "2.0.0"}


@app.get("/mcp/")
async def mcp_info():
    return {"message": "Welcome to the Secure Hospital MCP API. POST JSON-RPC to this path."}


@app.post("/mcp/")
async def handle_mcp(request: Request, ident: Identity = Depends(get_identity)):
    """
    Entry point for all LLM MCP tool calls (JSON-RPC 2.0).
    The `ident` is the authenticated user (from JWT).
    """
    try:
        body = await request.json()
    except Exception:
        return _rpc_error(None, "Invalid JSON")

    try:
        rpc = JsonRpcRequest(**body)
    except Exception as e:
        return _rpc_error(body.get("id") if isinstance(body, dict) else None, f"Bad RPC schema: {e}")

    if rpc.method != "tools.call" or not rpc.params:
        return _rpc_error(rpc.id, "Invalid method or missing params")

    tool = rpc.params.name
    args = rpc.params.arguments or {}
    user_role = ident.role
    user_id = ident.user_id
    client_ip = request.client.host if request.client else None

    # -------------------------
    # Tool router
    # -------------------------
    try:
        # 1) Patient “overview” (non-PHI + summary pointers)
        if tool == "get_patient_overview":
            pid = args.get("patient_id")
            if not pid:
                return _rpc_error(rpc.id, "Missing patient_id")

            # RBAC: Patient (basic)
            if not is_allowed(model="Patient", action="read_basic", role=user_role, user_id=user_id, row_context={"patient_id": pid}):
                raise HTTPException(status_code=403, detail="Forbidden: Patient basic info")

            data = get_patient_overview(pid)  # non-PHI identifiers and safe joined info
            data = isoformat_datetimes(data)
            _audit_ok(user_id, "MCP_READ_PATIENT_OVERVIEW", "Patient", False, client_ip)
            return _rpc_result(rpc.id, {"data": data, "meta": {"redacted": False, "source": "mcp"}})

        # 2) Patient PHI (strictly limited)
        elif tool == "get_patient_phi":
            pid = args.get("patient_id")
            scope = args.get("scope", "full")  # "full" | "insurance"
            if not pid:
                return _rpc_error(rpc.id, "Missing patient_id")

            # RBAC for PHI
            if scope == "insurance":
                permitted = is_allowed(model="PHI", action="read_insurance", role=user_role, user_id=user_id, row_context={"patient_id": pid})
            else:
                permitted = is_allowed(model="PHI", action="read_full", role=user_role, user_id=user_id, row_context={"patient_id": pid})

            if not permitted:
                raise HTTPException(status_code=403, detail="Forbidden: PHI access")

            raw = get_patient_phi(pid)
            # Apply redaction according to scope and role
            redacted = redact_phi(raw, role=user_role, scope=scope)
            redacted = isoformat_datetimes(redacted)
            _audit_ok(user_id, "MCP_READ_PHI", "PHIDemographics", True, client_ip)
            return _rpc_result(rpc.id, {"data": redacted, "meta": {"redacted": True, "scope": scope, "source": "mcp"}})

        # 3) Admissions for patient
        elif tool == "get_admissions":
            pid = args.get("patient_id")
            if not pid:
                return _rpc_error(rpc.id, "Missing patient_id")

            if not is_allowed(model="Admission", action="read", role=user_role, user_id=user_id, row_context={"patient_id": pid}):
                raise HTTPException(status_code=403, detail="Forbidden: Admissions")

            rows = get_admissions_for_patient(pid)
            rows = isoformat_datetimes(rows)
            _audit_ok(user_id, "MCP_READ_ADMISSIONS", "Admission", False, client_ip)
            return _rpc_result(rpc.id, {"data": rows, "meta": {"redacted": False, "source": "mcp"}})

        # 4) Appointments
        elif tool == "get_appointments":
            pid = args.get("patient_id")
            if not pid:
                return _rpc_error(rpc.id, "Missing patient_id")

            if not is_allowed(model="Appointment", action="read", role=user_role, user_id=user_id, row_context={"patient_id": pid}):
                raise HTTPException(status_code=403, detail="Forbidden: Appointments")

            rows = get_appointments_for_patient(pid)
            rows = isoformat_datetimes(rows)
            _audit_ok(user_id, "MCP_READ_APPOINTMENTS", "Appointment", False, client_ip)
            return _rpc_result(rpc.id, {"data": rows, "meta": {"redacted": False, "source": "mcp"}})

        # 5) Medical records (clinical notes)
        elif tool == "get_medical_records":
            pid = args.get("patient_id")
            if not pid:
                return _rpc_error(rpc.id, "Missing patient_id")

            if not is_allowed(model="MedicalRecord", action="read", role=user_role, user_id=user_id, row_context={"patient_id": pid}):
                raise HTTPException(status_code=403, detail="Forbidden: MedicalRecords")

            rows = get_medical_records_for_patient(pid)
            # Even for permitted roles, we can redact names/SSN if accidentally joined
            rows = [redact_phi(r, role=user_role, scope="clinical") for r in rows]
            rows = isoformat_datetimes(rows)
            _audit_ok(user_id, "MCP_READ_MEDICAL_RECORDS", "MedicalRecord", True, client_ip)
            return _rpc_result(rpc.id, {"data": rows, "meta": {"redacted": True, "source": "mcp"}})

        # 6) Shifts for a staff member (self or read-only roles)
        elif tool == "get_shifts":
            staff_id = args.get("staff_id")
            if not staff_id:
                return _rpc_error(rpc.id, "Missing staff_id")

            if not is_allowed(model="Shift", action="read", role=user_role, user_id=user_id, row_context={"staff_id": staff_id}):
                raise HTTPException(status_code=403, detail="Forbidden: Shifts")

            rows = get_shifts_for_staff(staff_id)
            rows = isoformat_datetimes(rows)
            _audit_ok(user_id, "MCP_READ_SHIFTS", "Shift", False, client_ip)
            return _rpc_result(rpc.id, {"data": rows, "meta": {"redacted": False, "source": "mcp"}})

        else:
            return _rpc_error(rpc.id, f"Unknown tool: {tool}")

    except HTTPException as he:
        # Convert to JSON-RPC error with 403/401 mapping
        return JSONResponse(
            status_code=he.status_code,
            content={"jsonrpc": "2.0", "id": rpc.id, "error": {"code": -32000, "message": he.detail}},
        )
    except Exception as e:
        # Catch-all to avoid leaking internals
        print(f"❌ MCP internal error: {e}")
        return JSONResponse(
            status_code=500,
            content={"jsonrpc": "2.0", "id": rpc.id, "error": {"code": -32001, "message": "Internal Server Error"}},
        )
