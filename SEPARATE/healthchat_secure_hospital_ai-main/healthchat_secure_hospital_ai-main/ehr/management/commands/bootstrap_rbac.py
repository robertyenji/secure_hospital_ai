"""
Management command to bootstrap Role-Based Access Control (RBAC)
for the Secure Hospital AI System.

Creates Django Groups:
- Admin
- Doctor
- Nurse
- Billing
- Reception
- Auditor

Assigns each group relevant model permissions based on least privilege.
Optionally attaches users whose role matches the group name.
"""

from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.contrib.auth import get_user_model
from ehr.models import (
    Staff,
    Patient,
    PHIDemographics,
    Admission,
    AdmissionStaff,
    Appointment,
    MedicalRecord,
    Shift,
)
from audit.models import AuditLog, UserRole


class Command(BaseCommand):
    help = "Bootstrap Role-Based Access Control (RBAC) groups and permissions."

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset", action="store_true", help="Delete and recreate all RBAC groups."
        )
        parser.add_argument(
            "--attach-users",
            action="store_true",
            help="Attach users to groups based on their role.",
        )

    def handle(self, *args, **options):
        if options["reset"]:
            self.stdout.write(self.style.WARNING("Deleting existing groups..."))
            Group.objects.all().delete()

        self.stdout.write(self.style.SUCCESS("Bootstrapping RBAC groups..."))

        # Mapping of group → permissions
        rbac_matrix = {
            UserRole.ADMIN: {
                "ehr": [
                    "add_", "change_", "delete_", "view_"
                ],
                "audit": ["view_auditlog"],
            },
            UserRole.DOCTOR: {
                "ehr": [
                    "view_patient",
                    "view_medicalrecord",
                    "add_medicalrecord",
                    "change_medicalrecord",
                    "view_appointment",
                    "add_appointment",
                    "change_appointment",
                    "view_admission",
                ],
            },
            UserRole.NURSE: {
                "ehr": [
                    "view_patient",
                    "view_admission",
                    "view_shift",
                    "view_medicalrecord",
                ],
            },
            UserRole.BILLING: {
                "ehr": [
                    "view_patient",
                    "view_phidemographics",
                    "view_appointment",
                ],
            },
            UserRole.RECEPTION: {
                "ehr": [
                    "view_patient",
                    "add_patient",
                    "view_appointment",
                    "add_appointment",
                    "change_appointment",
                ],
            },
            UserRole.AUDITOR: {
                "ehr": [
                    "view_patient",
                    "view_medicalrecord",
                    "view_phidemographics",
                    "view_admission",
                    "view_staff",
                ],
                "audit": ["view_auditlog"],
            },
        }

        # Create Groups and assign permissions
        for role, app_perms in rbac_matrix.items():
            group, created = Group.objects.get_or_create(name=role)
            if created:
                self.stdout.write(f"Created group: {role}")
            else:
                self.stdout.write(f"Updating group: {role}")
            group.permissions.clear()

            for app_label, perms in app_perms.items():
                for perm_code in perms:
                    # If wildcard (add_, change_, etc.)
                    if perm_code.endswith("_"):
                        content_types = ContentType.objects.filter(app_label=app_label)
                        for ct in content_types:
                            for p in Permission.objects.filter(content_type=ct, codename__startswith=perm_code):
                                group.permissions.add(p)
                    else:
                        try:
                            p = Permission.objects.get(codename=perm_code)
                            group.permissions.add(p)
                        except Permission.DoesNotExist:
                            self.stdout.write(self.style.WARNING(f"Permission not found: {perm_code}"))

            self.stdout.write(self.style.SUCCESS(f"✔ {role} permissions updated."))

        # Optionally attach users to their group
        if options["attach_users"]:
            User = get_user_model()
            for user in User.objects.all():
                if user.role in rbac_matrix:
                    group = Group.objects.get(name=user.role)
                    user.groups.clear()
                    user.groups.add(group)
                    self.stdout.write(f"Attached {user.username} → {group.name}")

        self.stdout.write(self.style.SUCCESS("✅ RBAC bootstrap complete."))
