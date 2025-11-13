"""
Audit & Auth Models – Secure Hospital System
--------------------------------------------
- Custom User with role (Admin, Doctor, Nurse, Billing, Reception, Auditor)
- Immutable AuditLog for compliance & traceability

Notes:
- Do NOT declare custom 'view_*' permissions that Django already auto-creates.
- Django auto-adds: add_<model>, change_<model>, delete_<model>, view_<model>.
"""

from django.db import models
from django.contrib.auth.models import AbstractUser
import uuid


# ================================================================
# ROLES (used across RBAC)
# ================================================================
class UserRole(models.TextChoices):
    ADMIN = 'Admin', 'Admin'
    DOCTOR = 'Doctor', 'Doctor'
    NURSE = 'Nurse', 'Nurse'
    BILLING = 'Billing', 'Billing'
    RECEPTION = 'Reception', 'Reception'     # Front Desk
    AUDITOR = 'Auditor', 'Auditor'


# ================================================================
# CUSTOM USER
# ================================================================
class User(AbstractUser):
    """
    Custom user model with UUID PK and role field.

    RBAC Access:
    - Admin: full management
    - Auditor: read-only (no mutations)
    - Others: scoped by app policies/groups
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    role = models.CharField(max_length=20, choices=UserRole.choices)
    email = models.EmailField(unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        # Keep only truly custom permissions (no conflict with built-ins).
        # Built-ins already include: add_user, change_user, delete_user, view_user
        permissions = [
            ("manage_users", "Can create/edit/delete users"),  # optional custom umbrella perm
            # If you want a custom read perm distinct from built-in view_user:
            # ("view_users_dashboard", "Can view the users dashboard"),
        ]
        ordering = ["date_joined"]

    def __str__(self):
        return f"{self.username} ({self.role})"


# ================================================================
# AUDIT LOG (immutable compliance trail)
# ================================================================
class AuditLog(models.Model):
    """
    Captures who did what, when, and from where.

    RBAC Access:
    - Admin: full read
    - Auditor: full read (no edit)
    - Others: no direct access
    """
    audit_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    action = models.CharField(max_length=255)              # e.g., "MCP_GET_SECURE_PATIENT_DATA"
    table_name = models.CharField(max_length=100)          # e.g., "Patient", "PHIDemographics"
    record_id = models.UUIDField(null=True, blank=True)    # optional related row ID
    timestamp = models.DateTimeField(auto_now_add=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    is_phi_access = models.BooleanField(default=False)

    class Meta:
        # IMPORTANT: Do NOT add ("view_auditlog", "…") here — Django auto-creates it
        ordering = ["-timestamp"]

    def __str__(self):
        who = self.user.username if self.user else "system"
        return f"{self.timestamp:%Y-%m-%d %H:%M} • {who} • {self.action} • {self.table_name}"
