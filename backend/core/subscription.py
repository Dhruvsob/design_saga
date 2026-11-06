"""Tenant subscription state and read-only mode.

A tenant is read-only only when the platform owner has explicitly set its
subscription: status "expired", or status "trial" with a trial end date that
has passed. Tenants without a subscription record are never restricted, so
existing workspaces are unaffected until the owner configures them.

Read-only means: everything can be viewed, downloaded and printed; nothing can
be created, changed or deleted. Sign-in, sign-out, PIN lock/unlock and
marking notifications read keep working. Super Admins are never blocked.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import HTTPException

STATUSES = ("trial", "active", "expired")
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
# writes that must keep working in read-only mode
EXEMPT_PREFIXES = ("/api/auth/", "/api/notifications")

READ_ONLY_MESSAGE = (
    "Read-only mode: the subscription for this workspace has ended. Your work is "
    "preserved, but editing is paused. Ask your studio owner to renew the plan."
)


def _today() -> date:
    from core.helpers import business_today
    return business_today()


def subscription_state(org: Optional[dict], today: Optional[date] = None) -> dict:
    sub = (org or {}).get("subscription") or {}
    status = sub.get("status") if sub.get("status") in STATUSES else None
    trial_end = sub.get("trial_ends_on")
    today = today or _today()
    days_left = None
    expired_trial = False
    if status == "trial" and trial_end:
        try:
            end = date.fromisoformat(str(trial_end)[:10])
            days_left = (end - today).days
            expired_trial = days_left < 0
        except ValueError:
            pass
    read_only = status == "expired" or expired_trial
    return {
        "status": "expired" if expired_trial else status,
        "trial_ends_on": trial_end,
        "days_left": max(days_left, 0) if days_left is not None else None,
        "read_only": read_only,
        "ended_on": trial_end if expired_trial else sub.get("ended_on"),
        "message": READ_ONLY_MESSAGE if read_only else None,
    }


async def enforce_writable(request, user: dict) -> None:
    """Refuse changes for a read-only tenant (called from require_user)."""
    if request is None or request.method.upper() in SAFE_METHODS:
        return
    path = request.url.path
    if path.startswith(EXEMPT_PREFIXES):
        return
    from core.tenancy import get_org, is_super_admin
    if is_super_admin(user):
        return
    org_id = user.get("org_id")
    if not org_id:
        return
    org = await get_org(org_id)
    if subscription_state(org)["read_only"]:
        raise HTTPException(status_code=403, detail=READ_ONLY_MESSAGE)
