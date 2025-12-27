# audit/models.py - Enhanced Audit Log

from django.db import models
from django.contrib.auth.models import AbstractUser
import uuid


class UserRole(models.TextChoices):
    ADMIN = 'Admin', 'Admin'
    DOCTOR = 'Doctor', 'Doctor'
    NURSE = 'Nurse', 'Nurse'
    BILLING = 'Billing', 'Billing'
    RECEPTION = 'Reception', 'Reception'
    AUDITOR = 'Auditor', 'Auditor'


class User(AbstractUser):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    role = models.CharField(max_length=20, choices=UserRole.choices)
    email = models.EmailField(unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        permissions = [
            ("manage_users", "Can create/edit/delete users"),
        ]
        ordering = ["date_joined"]

    def __str__(self):
        return f"{self.username} ({self.role})"


class AuditLog(models.Model):
    """
    Enhanced audit log capturing ALL tool calls, access decisions, and user activity.
    Immutable for compliance.
    """
    
    ACTION_TYPES = [
        # Tool Calls
        ('TOOL_CALL', 'Tool Call'),
        ('TOOL_SUCCESS', 'Tool Success'),
        ('TOOL_FAILURE', 'Tool Failure'),
        
        # Access Control
        ('ACCESS_GRANTED', 'Access Granted'),
        ('ACCESS_DENIED', 'Access Denied'),
        
        # PHI Access
        ('PHI_READ', 'PHI Read'),
        ('PHI_WRITE', 'PHI Write'),
        ('PHI_DENIED', 'PHI Access Denied'),
        
        # Session Events
        ('LOGIN', 'User Login'),
        ('LOGOUT', 'User Logout'),
        ('SESSION_CREATE', 'Session Created'),
        
        # System Events
        ('ERROR', 'System Error'),
        ('SECURITY_EVENT', 'Security Event'),
    ]
    
    audit_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    
    # Action details
    action = models.CharField(max_length=50, choices=ACTION_TYPES)
    action_details = models.TextField(blank=True)  # JSON string for extra details
    
    # Resource accessed
    table_name = models.CharField(max_length=100)
    record_id = models.CharField(max_length=100, null=True, blank=True)
    
    # Tool call specifics
    tool_name = models.CharField(max_length=100, blank=True)
    tool_parameters = models.JSONField(null=True, blank=True)
    tool_result_summary = models.TextField(blank=True)
    
    # Access decision
    access_granted = models.BooleanField(default=True)
    denial_reason = models.TextField(blank=True)
    
    # Timestamps
    timestamp = models.DateTimeField(auto_now_add=True)
    duration_ms = models.IntegerField(null=True, blank=True)  # How long the operation took
    
    # Network & Location
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    
    # Geolocation (populated from IP)
    country = models.CharField(max_length=100, blank=True)
    region = models.CharField(max_length=100, blank=True)
    city = models.CharField(max_length=100, blank=True)
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    
    # Security flags
    is_phi_access = models.BooleanField(default=False)
    is_suspicious = models.BooleanField(default=False)
    risk_score = models.IntegerField(default=0)  # 0-100, higher = more suspicious

    class Meta:
        ordering = ["-timestamp"]
        indexes = [
            models.Index(fields=['user', 'timestamp']),
            models.Index(fields=['action', 'timestamp']),
            models.Index(fields=['is_phi_access', 'timestamp']),
            models.Index(fields=['ip_address', 'timestamp']),
            models.Index(fields=['tool_name', 'timestamp']),
            models.Index(fields=['access_granted']),
        ]
        verbose_name = "Audit Log Entry"
        verbose_name_plural = "Audit Log Entries"

    def __str__(self):
        who = self.user.username if self.user else "system"
        status = "✓" if self.access_granted else "✗"
        return f"{status} {self.timestamp:%Y-%m-%d %H:%M} • {who} • {self.action} • {self.tool_name or self.table_name}"