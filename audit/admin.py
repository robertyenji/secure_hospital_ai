from django.contrib import admin
from .models import User, AuditLog

@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    """
    Admin configuration for the custom User model.
    Displays user roles, creation timestamps, and allows search/filter.
    """
    list_display = ("username", "email", "role", "is_active", "is_staff", "created_at")
    list_filter = ("role", "is_active", "is_staff")
    search_fields = ("username", "email")
    ordering = ("-created_at",)
    readonly_fields = ("created_at",)
    fieldsets = (
        ("Account Information", {
            "fields": ("username", "email", "password", "role")
        }),
        ("Permissions", {
            "fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")
        }),
        ("Timestamps", {
            "fields": ("created_at",)
        }),
    )


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    """
    Read-only admin view for security and compliance auditing.
    Shows who performed what action, on which table, and when.
    """
    list_display = ("user", "action", "table_name", "timestamp", "ip_address", "is_phi_access")
    list_filter = ("is_phi_access", "table_name", "timestamp")
    search_fields = ("user__username", "action", "table_name", "ip_address")
    ordering = ("-timestamp",)
    readonly_fields = ("audit_id", "user", "action", "table_name", "record_id", "timestamp", "ip_address", "is_phi_access")

    def has_add_permission(self, request):
        """Prevents manual log creation — logs are system-generated."""
        return False

    def has_change_permission(self, request, obj=None):
        """Prevents tampering with audit records."""
        return False
