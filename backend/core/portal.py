"""Client portal links.

Two kinds of link open `/portal/<token>`:

* the project's **shared link** (`projects.share_token`): read-only, anyone
  holding it sees the project, shared files and invoices;
* a **personal link** (`portal_access`): issued by the studio to one named
  client contact. It shows the same portal and also lets that person approve
  or send back what the studio asked them to sign off, so every decision is
  attributable to a named person.

Personal tokens are 256-bit, stored only as a SHA-256 hash, shown once when
issued, revocable, and stop working with the tenant (suspended or inactive
workspace) like the shared link does.

Every lookup here is unscoped (no signed-in user) and therefore filters by the
token owner's org explicitly. Callers pass the database handle so the public
routes and their tests use the same one.
"""
import hashlib
import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import HTTPException

from core.tenancy import DEFAULT_ORG_ID

_LEGACY = re.compile(r"[a-f0-9]{12}")
_TOKEN = re.compile(r"[A-Za-z0-9_-]{32,64}")
_TOUCH_EVERY = timedelta(minutes=10)


def token_hash(token: str) -> str:
    return hashlib.sha256((token or "").encode("utf-8")).hexdigest()


def new_personal_token() -> str:
    return secrets.token_urlsafe(32)


def valid_format(token: str) -> bool:
    return bool(_LEGACY.fullmatch(token or "") or _TOKEN.fullmatch(token or ""))


async def resolve(database, token: str) -> dict:
    """Return {project, org_id, org, contact} for a live link, else 404.

    `contact` is the personal-link row (None for the shared link).
    """
    if not valid_format(token):
        raise HTTPException(status_code=404, detail="Invalid link")
    contact = None
    project = await database.projects.find_one({"share_token": token}, {"_id": 0})
    if not project and _TOKEN.fullmatch(token):
        contact = await database.portal_access.find_one(
            {"token_hash": token_hash(token), "revoked_at": None}, {"_id": 0})
        if contact:
            project = await database.projects.find_one(
                {"id": contact.get("project_id"), "org_id": contact.get("org_id")}, {"_id": 0})
    if not project:
        raise HTTPException(status_code=404, detail="Invalid link")
    org_id = project.get("org_id") or DEFAULT_ORG_ID
    if contact and contact.get("org_id") != org_id:
        raise HTTPException(status_code=404, detail="Invalid link")
    owner = await database.organizations.find_one({
        "org_id": org_id,
        "is_active": {"$ne": False},
        "is_suspended": {"$ne": True},
    }, {"_id": 0, "org_id": 1, "name": 1, "display_name": 1, "branding": 1})
    if not owner:
        raise HTTPException(status_code=404, detail="Invalid link")
    return {"project": project, "org_id": org_id, "org": owner, "contact": contact}


async def touch(database, contact: Optional[dict]) -> None:
    """Record when a personal link was last opened (at most every 10 min)."""
    if not contact:
        return
    now = datetime.now(timezone.utc)
    last = contact.get("last_used_at")
    try:
        last_dt = datetime.fromisoformat(str(last)) if last else None
    except ValueError:
        last_dt = None
    if last_dt and last_dt.tzinfo is None:
        last_dt = last_dt.replace(tzinfo=timezone.utc)
    if last_dt and now - last_dt < _TOUCH_EVERY:
        return
    await database.portal_access.update_one(
        {"id": contact["id"], "org_id": contact["org_id"]},
        {"$set": {"last_used_at": now.isoformat()}})


def viewer(contact: Optional[dict]) -> dict:
    if not contact:
        return {"kind": "shared", "name": None, "can_decide": False}
    return {"kind": "personal", "name": contact.get("name"), "can_decide": True}


def contact_view(row: dict) -> dict:
    """Studio-side projection of a personal link (never the hash)."""
    return {k: row.get(k) for k in ("id", "project_id", "name", "email", "phone", "created_at",
                                    "created_by_name", "last_used_at", "link_issued_at")}
