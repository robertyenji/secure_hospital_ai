"""
Redaction utilities for Secure Hospital MCP
-------------------------------------------
- redact_phi: remove or limit PHI fields based on role/scope
- isoformat_datetimes: convert datetime values to ISO-8601 for JSON
"""

from datetime import datetime
from typing import Any, Dict, List, Union

# Fields that should never leave the system unredacted for non-privileged roles
PHI_FIELDS = [
    "address",
    "phone",
    "email",
    "social_security_number",
    "emergency_contact",
]

def redact_phi(
    data: Union[Dict[str, Any], List[Dict[str, Any]]],
    role: str,
    scope: str = "full",   # "full" | "insurance" | "clinical"
):
    """
    Redact sensitive fields based on role/scope.
    - Admin/Auditor: full visibility
    - Billing: insurance-only (insurance_provider, insurance_number, patient_id)
    - Doctor/Nurse: clinical view; removes identifying PHI fields
    - Reception/Other: strongly redacted
    """
    if not data:
        return data

    if isinstance(data, list):
        return [redact_phi(item, role, scope) for item in data]

    redacted = dict(data)

    # Admins & Auditors see everything
    if role in ("Admin", "Auditor"):
        return redacted

    # Billing (or insurance scope): only insurance fields + patient_id
    if role == "Billing" or scope == "insurance":
        for k in list(redacted.keys()):
            if k not in ("insurance_provider", "insurance_number", "patient_id"):
                redacted.pop(k, None)
        return redacted

    # Doctors/Nurses (or clinical scope): strip identifiers but keep clinical content
    if role in ("Doctor", "Nurse") or scope == "clinical":
        for f in PHI_FIELDS:
            redacted.pop(f, None)
        redacted.pop("insurance_provider", None)
        redacted.pop("insurance_number", None)
        return redacted

    # Reception/Other: remove PHI + insurance
    for f in PHI_FIELDS + ["insurance_provider", "insurance_number"]:
        redacted.pop(f, None)

    return redacted


def isoformat_datetimes(data: Union[Dict[str, Any], List[Dict[str, Any]]]) -> Any:
    """
    Convert datetime values in dict(s) to ISO-8601 strings so FastAPI can JSON-encode.
    Call this before returning data to the client.
    """
    def _conv(v):
        return v.isoformat() if isinstance(v, datetime) else v

    if isinstance(data, list):
        return [{k: _conv(v) for k, v in row.items()} for row in data]

    if isinstance(data, dict):
        return {k: _conv(v) for k, v in data.items()}

    return data
