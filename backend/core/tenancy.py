"""Multi-tenant tenancy helpers.

Design
------
Every business collection carries an `org_id` field. Requests are
scoped by the current user's org via `tenant_filter(user)` which returns
a Mongo filter dict.

Special roles
-------------
- **SuperAdmin**  → platform-level. `org_id = None`. Bypasses tenant
  filter and can see every org. Managed via `SUPER_ADMIN_EMAILS` env.
- **Admin (Company Admin)** → belongs to exactly one org, has `*.*`
  within that org.

`stamp_org(doc, user)` — call before Mongo insert to attach org_id.
`ensure_org_match(doc, user)` — assert an existing doc belongs to the
user's org (raises 404 otherwise, mimicking "not found").
"""
from typing import Optional
from fastapi import HTTPException, Request, Cookie, Header
import os

from .db import db
from .deps import require_user
from .helpers import now_utc, iso_now


DEFAULT_ORG_ID = "org_default"                 # existing data lives here
DEFAULT_ORG_SLUG = "design-saga"


SUPER_ADMIN_EMAILS = {
    e.strip().lower()
    for e in os.environ.get("SUPER_ADMIN_EMAILS", "designsaga10@gmail.com").split(",")
    if e.strip()
}


def is_super_admin(user: Optional[dict]) -> bool:
    if not user:
        return False
    if user.get("is_super_admin") is True:
        return True
    email = (user.get("email") or "").strip().lower()
    return email in SUPER_ADMIN_EMAILS


def user_org_id(user: Optional[dict]) -> Optional[str]:
    if not user:
        return None
    return user.get("org_id") or DEFAULT_ORG_ID


def tenant_filter(user: dict) -> dict:
    """Return a Mongo filter that scopes queries to the user's org.

    Super admins get an empty filter (see everything). Regular users
    get `{"org_id": <their-org>}` — plus we include legacy documents
    that have no org_id and match the default org for zero-downtime
    migration.
    """
    if is_super_admin(user):
        return {}
    oid = user_org_id(user)
    if oid == DEFAULT_ORG_ID:
        return {"$or": [{"org_id": DEFAULT_ORG_ID}, {"org_id": {"$exists": False}}, {"org_id": None}]}
    return {"org_id": oid}


def stamp_org(doc: dict, user: dict) -> dict:
    """Attach `org_id` to a document before insert. Mutates & returns."""
    if "org_id" not in doc or not doc["org_id"]:
        doc["org_id"] = user_org_id(user)
    return doc


async def require_org_context(
    request: Request,
    session_token: Optional[str] = Cookie(default=None),
    authorization: Optional[str] = Header(default=None),
):
    """Dependency: authenticated user + must belong to an org (blocks Super
    Admins from company-scoped routes when they don't impersonate a tenant)."""
    user = await require_user(request, session_token, authorization)
    if is_super_admin(user) and not user.get("org_id"):
        raise HTTPException(
            status_code=400,
            detail="Super Admin: switch into an organisation to access this endpoint.",
        )
    return user


async def require_super_admin(
    request: Request,
    session_token: Optional[str] = Cookie(default=None),
    authorization: Optional[str] = Header(default=None),
):
    user = await require_user(request, session_token, authorization)
    if not is_super_admin(user):
        raise HTTPException(status_code=403, detail="Super Admin only")
    return user


async def get_org(org_id: str) -> Optional[dict]:
    if not org_id:
        return None
    return await db.organizations.find_one({"org_id": org_id}, {"_id": 0})


async def ensure_org_active(org_id: str):
    """Raise 403 if the org is suspended or deactivated."""
    if not org_id or org_id == DEFAULT_ORG_ID:
        # default org is always active during bootstrap
        pass
    org = await get_org(org_id)
    if not org:
        return
    if org.get("is_active") is False:
        raise HTTPException(status_code=403, detail="Your workspace has been deactivated.")
    if org.get("is_suspended") is True:
        raise HTTPException(status_code=403, detail="Your workspace has been suspended.")
