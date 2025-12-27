# frontend/rbac.py
"""
Centralized RBAC Configuration for SecureHospital AI
====================================================
This module defines the Role-Based Access Control matrix used by ALL THREE security layers:
- Layer 1: Django/Frontend (pre-flight check before LLM)
- Layer 2: LLM System Prompt (guides AI behavior)
- Layer 3: MCP Server (final enforcement with redaction)

ROLES:
------
- Admin: Full system access, can see all data and manage users
- Doctor: Full clinical access, full PHI for patient care
- Nurse: Clinical access, REDACTED PHI (no SSN, masked address/phone)
- Auditor: Read-only access to everything (compliance/audit purposes)
- Reception: Patient overview + appointments only, NO PHI or medical records
- Billing: Patient overview + insurance info only, NO clinical data

PHI LEVELS:
-----------
- FULL: All PHI fields visible (Admin, Doctor, Auditor)
- REDACTED: Sensitive fields masked (Nurse) - SSN: ***-**-1234, Address: [REDACTED]
- INSURANCE_ONLY: Only insurance fields visible (Billing)
- NONE: No PHI access (Reception)
"""

from typing import Dict, List, Optional, Set
from enum import Enum


class PHIAccessLevel(Enum):
    """PHI access levels for different roles."""
    FULL = "full"              # All PHI visible
    REDACTED = "redacted"      # Sensitive fields masked
    INSURANCE_ONLY = "insurance"  # Only insurance info
    NONE = "none"              # No PHI access


# ======================================================
# MASTER RBAC CONFIGURATION
# ======================================================

ROLES = ["Admin", "Doctor", "Nurse", "Auditor", "Reception", "Billing"]

# Tool permissions: tool_name -> list of allowed roles
TOOL_PERMISSIONS: Dict[str, List[str]] = {
    "get_patient_overview": ["Admin", "Doctor", "Nurse", "Auditor", "Reception", "Billing"],
    "get_medical_records": ["Admin", "Doctor", "Nurse", "Auditor"],
    "get_patient_phi": ["Admin", "Doctor", "Nurse", "Auditor", "Billing"],  # With different access levels
    "get_appointments": ["Admin", "Doctor", "Nurse", "Auditor", "Reception"],
    "get_admissions": ["Admin", "Doctor", "Nurse", "Auditor"],
    "get_my_shifts": ["Admin", "Doctor", "Nurse", "Auditor", "Reception", "Billing"],
    "get_shifts": ["Admin", "Auditor"],  # Department-wide shifts
}

# PHI access levels by role
PHI_ACCESS_LEVELS: Dict[str, PHIAccessLevel] = {
    "Admin": PHIAccessLevel.FULL,
    "Doctor": PHIAccessLevel.FULL,
    "Auditor": PHIAccessLevel.FULL,
    "Nurse": PHIAccessLevel.REDACTED,
    "Billing": PHIAccessLevel.INSURANCE_ONLY,
    "Reception": PHIAccessLevel.NONE,
}

# Human-readable descriptions for UI
ROLE_DESCRIPTIONS: Dict[str, str] = {
    "Admin": "Full system access - manage users, view all data, system configuration",
    "Doctor": "Full clinical access - patient records, PHI, prescriptions, diagnoses",
    "Nurse": "Clinical care access - patient records, redacted PHI, medications",
    "Auditor": "Read-only compliance access - audit trails, all records (no modifications)",
    "Reception": "Front desk access - patient check-in, appointments, basic demographics",
    "Billing": "Financial access - insurance information, billing records only",
}

# RBAC Matrix for display (tool x role)
RBAC_MATRIX = {
    "get_patient_overview": {
        "Admin": "✅ Full",
        "Doctor": "✅ Full",
        "Nurse": "✅ Full",
        "Auditor": "✅ Read",
        "Reception": "✅ Basic",
        "Billing": "✅ Basic",
    },
    "get_medical_records": {
        "Admin": "✅ Full",
        "Doctor": "✅ Full",
        "Nurse": "✅ Full",
        "Auditor": "✅ Read",
        "Reception": "❌ Denied",
        "Billing": "❌ Denied",
    },
    "get_patient_phi": {
        "Admin": "✅ Full PHI",
        "Doctor": "✅ Full PHI",
        "Nurse": "⚠️ Redacted",
        "Auditor": "✅ Full PHI",
        "Reception": "❌ Denied",
        "Billing": "💳 Insurance Only",
    },
    "get_appointments": {
        "Admin": "✅ Full",
        "Doctor": "✅ Full",
        "Nurse": "✅ Full",
        "Auditor": "✅ Read",
        "Reception": "✅ Full",
        "Billing": "❌ Denied",
    },
    "get_admissions": {
        "Admin": "✅ Full",
        "Doctor": "✅ Full",
        "Nurse": "✅ Full",
        "Auditor": "✅ Read",
        "Reception": "❌ Denied",
        "Billing": "❌ Denied",
    },
    "get_my_shifts": {
        "Admin": "✅ Own",
        "Doctor": "✅ Own",
        "Nurse": "✅ Own",
        "Auditor": "✅ Own",
        "Reception": "✅ Own",
        "Billing": "✅ Own",
    },
    "get_shifts": {
        "Admin": "✅ All Staff",
        "Doctor": "❌ Denied",
        "Nurse": "❌ Denied",
        "Auditor": "✅ All Staff",
        "Reception": "❌ Denied",
        "Billing": "❌ Denied",
    },
}


# ======================================================
# RBAC CHECK FUNCTIONS (Layer 1 - Django)
# ======================================================

def can_access_tool(role: str, tool_name: str) -> bool:
    """
    Check if a role can access a specific tool.
    This is the Layer 1 (Django) pre-flight check.
    """
    if role not in ROLES:
        return False
    allowed_roles = TOOL_PERMISSIONS.get(tool_name, [])
    return role in allowed_roles


def get_phi_access_level(role: str) -> PHIAccessLevel:
    """Get the PHI access level for a role."""
    return PHI_ACCESS_LEVELS.get(role, PHIAccessLevel.NONE)


def can_access_phi(role: str) -> bool:
    """Check if role has any PHI access (even redacted)."""
    level = get_phi_access_level(role)
    return level != PHIAccessLevel.NONE


def get_allowed_tools(role: str) -> List[str]:
    """Get list of tools a role can access."""
    return [tool for tool, roles in TOOL_PERMISSIONS.items() if role in roles]


def get_denied_tools(role: str) -> List[str]:
    """Get list of tools a role cannot access."""
    return [tool for tool, roles in TOOL_PERMISSIONS.items() if role not in roles]


def check_tool_access(user, tool_name: str) -> tuple:
    """
    Full access check for a user attempting to use a tool.
    Returns: (allowed: bool, reason: str, phi_level: PHIAccessLevel)
    """
    role = getattr(user, 'role', None)
    
    if not role:
        return False, "User has no role assigned", PHIAccessLevel.NONE
    
    if role not in ROLES:
        return False, f"Unknown role: {role}", PHIAccessLevel.NONE
    
    if not can_access_tool(role, tool_name):
        return False, f"Role '{role}' is not authorized for {tool_name}", PHIAccessLevel.NONE
    
    phi_level = get_phi_access_level(role)
    return True, "Access granted", phi_level


# ======================================================
# RBAC MATRIX FOR API/UI
# ======================================================

def get_rbac_matrix_for_display() -> Dict:
    """
    Returns RBAC matrix formatted for UI display.
    Used by landing page and API.
    """
    tools = [
        {"id": "get_patient_overview", "name": "Patient Overview", "description": "Basic demographics"},
        {"id": "get_medical_records", "name": "Medical Records", "description": "Clinical notes, diagnoses"},
        {"id": "get_patient_phi", "name": "PHI Access", "description": "SSN, address, insurance"},
        {"id": "get_appointments", "name": "Appointments", "description": "Patient appointments"},
        {"id": "get_admissions", "name": "Admissions", "description": "Hospital admissions"},
        {"id": "get_my_shifts", "name": "My Shifts", "description": "Own schedule"},
        {"id": "get_shifts", "name": "All Shifts", "description": "Department schedules"},
    ]
    
    roles_info = [
        {"id": role, "description": ROLE_DESCRIPTIONS[role]} 
        for role in ROLES
    ]
    
    matrix = []
    for tool in tools:
        row = {
            "tool": tool,
            "permissions": {}
        }
        for role in ROLES:
            row["permissions"][role] = RBAC_MATRIX.get(tool["id"], {}).get(role, "❌ Denied")
        matrix.append(row)
    
    return {
        "roles": roles_info,
        "tools": tools,
        "matrix": matrix,
        "phi_levels": {
            role: level.value for role, level in PHI_ACCESS_LEVELS.items()
        }
    }


# ======================================================
# LLM SYSTEM PROMPT RBAC SECTION
# ======================================================

def get_rbac_prompt_for_role(role: str) -> str:
    """
    Generate RBAC instructions for LLM system prompt.
    This is Layer 2 - tells the AI what the user can/cannot do.
    """
    if role not in ROLES:
        return "ERROR: Unknown role. Deny all data access requests."
    
    allowed = get_allowed_tools(role)
    denied = get_denied_tools(role)
    phi_level = get_phi_access_level(role)
    
    prompt = f"""
## RBAC RESTRICTIONS FOR CURRENT USER
Role: {role}
PHI Access Level: {phi_level.value}

### ALLOWED OPERATIONS:
{chr(10).join(f'- {tool}' for tool in allowed)}

### DENIED OPERATIONS (Do not attempt these):
{chr(10).join(f'- {tool}' for tool in denied) if denied else '- None (full access)'}

### PHI HANDLING:
"""
    
    if phi_level == PHIAccessLevel.FULL:
        prompt += "- You may retrieve and display full PHI including SSN, addresses, phone numbers.\n"
    elif phi_level == PHIAccessLevel.REDACTED:
        prompt += """- PHI will be automatically redacted by the system.
- SSN will show as ***-**-XXXX (last 4 digits only)
- Addresses will be hidden
- Phone numbers will be partially masked
- Inform the user if they need full PHI to contact an Admin or Doctor.
"""
    elif phi_level == PHIAccessLevel.INSURANCE_ONLY:
        prompt += """- You can only access insurance information (provider, policy number).
- All other PHI fields are blocked.
- Do NOT attempt to retrieve SSN, addresses, or phone numbers.
"""
    else:
        prompt += """- You have NO PHI access.
- Do NOT attempt to call get_patient_phi.
- If user asks for PHI, explain they need a clinical role for that information.
"""
    
    prompt += """
### IMPORTANT:
- NEVER attempt to call tools you don't have permission for.
- If access is denied by the MCP server, apologize and explain the role limitation.
- Do not try to work around RBAC restrictions.
"""
    
    return prompt