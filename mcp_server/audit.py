# mcp_server/audit.py

from typing import Optional
from mcp_server.audit_logger import log_audit as _log
from audit.models import User
from asgiref.sync import sync_to_async
from dotenv import load_dotenv
load_dotenv()


async def audit(
    user: User,
    action: str,
    table_name: str,
    is_phi: bool = False,
    ip: Optional[str] = None
):
    try:
        await sync_to_async(_log)(
            action=action,
            table_name=table_name,
            is_phi_access=is_phi,
            ip_address=ip,
            user=user,
        )
    except Exception:
        pass
