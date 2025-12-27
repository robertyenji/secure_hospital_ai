# mcp_server/rbac.py
from typing import Dict, Any
from mcp_server.audit_logger import log_audit  # sync logger

RBAC_MATRIX = {
    "Staff": {
        "Admin": ["read", "write"],
        "Auditor": ["read"],
        "Doctor": ["read_self"],
        "Nurse": ["read_self"],
        "Billing": ["read"],
        "Reception": ["read"],
    },
    "Patient": {
        "Admin": ["read_basic", "write"],
        "Auditor": ["read_basic"],
        "Doctor": ["read_basic", "write"],
        "Nurse": ["read_basic", "write"],
        "Billing": ["read_basic"],
        "Reception": ["read_basic", "write"],
    },
    "PHI": {
        "Admin": ["read_full", "write"],
        "Auditor": ["read_full"],
        "Doctor": [],
        "Nurse": [],
        "Billing": ["read_insurance"],
        "Reception": [],
    },
    "Admission": {
        "Admin": ["read", "write"],
        "Auditor": ["read"],
        "Doctor": ["read", "write_assigned"],
        "Nurse": ["read"],
        "Billing": ["read"],
        "Reception": ["read", "write"],
    },
    "AdmissionStaff": {
        "Admin": ["read", "write"],
        "Auditor": ["read"],
        "Doctor": ["read", "write_assigned"],
        "Nurse": ["read"],
        "Billing": ["read"],
        "Reception": ["read"],
    },
    "Appointment": {
        "Admin": ["read", "write"],
        "Auditor": ["read"],
        "Doctor": ["read", "write"],
        "Nurse": ["read", "write"],
        "Billing": ["read"],
        "Reception": ["read", "write"],
    },
    "MedicalRecord": {
        "Admin": ["read", "write"],
        "Auditor": ["read"],
        "Doctor": ["read", "write"],
        "Nurse": ["read"],
        "Billing": [],
        "Reception": [],
    },
    "Shift": {
        "Admin": ["read", "write"],
        "Auditor": ["read"],
        "Doctor": ["read"],
        "Nurse": ["read"],
        "Billing": [],
        "Reception": ["read"],
    },
}

def is_allowed(model: str, action: str, role: str, user_id: str, row_context: Dict[str, Any]) -> bool:
    """
    Returns True if permitted by RBAC. Logs ACCESS_DENIED to audit when blocked.
    """
    perms = RBAC_MATRIX.get(model, {}).get(role, [])
    allowed = False

    if action in perms:
        allowed = True
    elif "read_self" in perms and row_context.get("staff_id") == user_id:
        allowed = True
    elif "write_assigned" in perms and row_context.get("assigned_doctor_id") == user_id:
        allowed = True

    if not allowed:
        # Fire-and-forget audit log for denied access
        try:
            log_audit(
                action="ACCESS_DENIED",
                table_name=model,
                is_phi_access=(model == "PHI"),
                ip_address=row_context.get("ip"),
            )
        except Exception:
            # Never break the request on audit failures
            pass

    return allowed
