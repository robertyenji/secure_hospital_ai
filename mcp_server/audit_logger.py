# mcp_server/audit_logger.py
"""
Audit logging helper.

- Designed to be called from async routes. If your DB driver is sync (Django ORM),
  keep the function 'async' and do the write using Django ORM inside — the event loop
  will hand it off without blocking for long, but for heavy loads you can switch
  to a background task/queue (Celery, Dramatiq, etc.).

- Takes a real User object for strong attribution.
"""

from typing import Optional
from django.utils import timezone
from audit.models import AuditLog, User


async def log_audit(action: str, table_name: str, is_phi_access: bool, ip_address: Optional[str], user: Optional[User]):
    try:
        AuditLog.objects.create(
            user=user,
            action=action,
            table_name=table_name,
            record_id=None,
            timestamp=timezone.now(),
            ip_address=ip_address,
            is_phi_access=is_phi_access,
        )
    except Exception:
        # Never fail the request because auditing hiccuped
        pass
