"""Tenant subscription state and read-only mode.

A tenant is read-only only when the platform owner has explicitly set its
subscription: status "expired", or status "trial" with a trial end date that
has passed. Tenants without a subscription record are never restricted, so
existing workspaces are unaffected until the owner configures them.

Paid subscriptions (P1.3, decision G7): an "active" subscription with a
``paid_through`` date (set when a GAMAA invoice is paid) runs on its own:
after that date comes a GRACE_DAYS grace period (everything still works, with
a warning), then read-only. READ_ONLY_DAYS after that the workspace is marked
"lapsed" for the platform owner to decide on suspension; nothing is suspended
or deleted automatically. Paying the next invoice restores it immediately.

Read-only means: everything can be viewed, downloaded and printed; nothing can
be created, changed or deleted. Sign-in, sign-out, PIN lock/unlock and
marking notifications read keep working. Super Admins are never blocked.
"""
from __future__ import annotations

from datetime import date, timedelta
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


GRACE_DAYS = 7
READ_ONLY_DAYS = 30


def _date(value) -> Optional[date]:
    try:
        return date.fromisoformat(str(value)[:10]) if value else None
    except ValueError:
        return None


def subscription_state(org: Optional[dict], today: Optional[date] = None) -> dict:
    sub = (org or {}).get("subscription") or {}
    status = sub.get("status") if sub.get("status") in STATUSES else None
    trial_end = sub.get("trial_ends_on")
    today = today or _today()
    days_left = None
    expired_trial = False
    if status == "trial" and trial_end:
        end = _date(trial_end)
        if end:
            days_left = (end - today).days
            expired_trial = days_left < 0
    paid_through = _date(sub.get("paid_through")) if status == "active" else None
    grace_ends = lapses = None
    in_grace = lapsed_paid = lapsed = False
    if paid_through:
        grace_ends = paid_through + timedelta(days=GRACE_DAYS)
        lapses = grace_ends + timedelta(days=READ_ONLY_DAYS)
        days_left = (paid_through - today).days
        in_grace = paid_through < today <= grace_ends
        lapsed_paid = today > grace_ends
        lapsed = today > lapses
    read_only = status == "expired" or expired_trial or lapsed_paid
    if expired_trial or lapsed_paid:
        shown = "expired"
    elif in_grace:
        shown = "grace"
    else:
        shown = status
    ended_on = (trial_end if expired_trial
                else grace_ends.isoformat() if lapsed_paid else sub.get("ended_on"))
    return {
        "status": shown,
        "trial_ends_on": trial_end,
        "paid_through": paid_through.isoformat() if paid_through else None,
        "grace_ends_on": grace_ends.isoformat() if grace_ends else None,
        "days_left": max(days_left, 0) if days_left is not None else None,
        "read_only": read_only,
        "lapsed": lapsed,          # read-only for READ_ONLY_DAYS: owner decides on suspension
        "ended_on": ended_on,
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
