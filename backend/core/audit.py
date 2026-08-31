"""Append-only audit log for critical actions (approvals, deletes,
password resets, org status changes, loan payments, etc).

Usage:
    from core.audit import audit
    await audit(user, action="org.suspend", target=org_id, meta={...})

Reads via /api/audit-log (Admin scoped by org, SuperAdmin sees all).
"""
from typing import Optional
from .db import db
from .helpers import iso_now, new_id


async def audit(actor: Optional[dict], action: str, target: str = "",
                target_type: str = "", meta: Optional[dict] = None,
                org_id: Optional[str] = None):
    """Append one row. Never raises — audit failures shouldn't break flows."""
    try:
        doc = {
            "id": new_id("aud_"),
            "at": iso_now(),
            "action": action,
            "target": target,
            "target_type": target_type,
            "actor_id": (actor or {}).get("user_id"),
            "actor_email": (actor or {}).get("email"),
            "actor_role": (actor or {}).get("role"),
            "org_id": org_id or (actor or {}).get("org_id"),
            "meta": meta or {},
        }
        await db.audit_log.insert_one(doc)
    except Exception:
        pass
