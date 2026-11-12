"""Platform (Super Admin) routes.

Super Admin owns the whole SaaS deployment. They can:
- Create / list / update / suspend / delete organisations (tenants)
- Create the first Company Admin for a new organisation
- Reset a Company Admin password
- View platform-wide analytics (orgs, users, revenue rollup)
- Impersonate an organisation for troubleshooting

All endpoints gated by `require_super_admin`.
"""
from fastapi import APIRouter, HTTPException, Request, Response, Cookie, Header
from fastapi.responses import StreamingResponse
from typing import Optional, List
from pydantic import BaseModel, EmailStr, StrictBool, field_validator
import datetime as _dt
import uuid
import re

from core.pdf_brand import BRAND_ACCENT, BRAND_PRIMARY
from core.employee_ids import derive_prefix, normalize_prefix
from core.limits import MAX_LIST_ROWS
from core.db import db
from core.helpers import business_today, iso_now, now_utc, new_id
from core.tenancy import (
    require_super_admin, get_org, DEFAULT_ORG_ID, DEFAULT_ORG_SLUG,
    SUPER_ADMIN_EMAILS,
)
from core.rbac import normalize_role, expand_permissions
from core.audit import audit
from models.organization import (
    MODULE_KEYS, OrgCreateIn, OrgUpdateIn, OrgStatusIn, DEFAULT_FEATURES,
    features_for_mode,
)


router = APIRouter(prefix="/platform")


from core.tenant_registry import (  # noqa: E402
    EXPORT_REDACTED_FIELDS, EXPORT_SKIPPED, TENANT_COLLECTIONS,
)

TENANT_PURGE_COLLECTIONS = TENANT_COLLECTIONS


# ------------------------------------------------------------------
# helpers
# ------------------------------------------------------------------
def _slugify(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return s or "org"



async def _unique_slug(base: str) -> str:
    slug = base
    i = 1
    while await db.organizations.find_one({"slug": slug}, {"_id": 0, "org_id": 1}):
        i += 1
        slug = f"{base}-{i}"
    return slug


def _sanitize_org(o: dict) -> dict:
    return {k: v for k, v in (o or {}).items() if k != "_id"}


def _current_session_filter(session_token: Optional[str], authorization: Optional[str]) -> dict:
    from core.helpers import session_lookup_values
    token = session_token
    if not token and authorization and authorization.startswith("Bearer "):
        token = authorization.split(" ", 1)[1]
    if not token:
        raise HTTPException(401, "Not authenticated")
    return {"session_token": {"$in": session_lookup_values(token)}}


# ------------------------------------------------------------------
# ORGANISATIONS CRUD
# ------------------------------------------------------------------
@router.get("/orgs")
async def list_orgs(user=None, request: Request = None,
                    session_token: Optional[str] = Cookie(default=None),
                    authorization: Optional[str] = Header(default=None)):
    await require_super_admin(request, session_token, authorization)
    rows = await db.organizations.find({}, {"_id": 0}).sort("created_at", -1).to_list(MAX_LIST_ROWS)
    # Attach quick stats per org
    out = []
    for o in rows:
        oid = o["org_id"]
        users_n = await db.users.count_documents({"org_id": oid})
        projects_n = await db.projects.count_documents({"org_id": oid})
        clients_n = await db.clients.count_documents({"org_id": oid})
        # legacy default org counts records without org_id too
        if oid == DEFAULT_ORG_ID:
            users_n += await db.users.count_documents({"org_id": {"$exists": False}})
            projects_n += await db.projects.count_documents({"org_id": {"$exists": False}})
            clients_n += await db.clients.count_documents({"org_id": {"$exists": False}})
        # Tenant owner = manual override, else the earliest active Admin.
        owner = (o.get("billing") or {}).get("owner_override")
        owner_email = None
        if not owner:
            admin = await db.users.find_one(
                {"org_id": oid, "role": {"$in": ["Admin", "Director"]}},
                {"_id": 0, "name": 1, "email": 1}, sort=[("created_at", 1)])
            if admin:
                owner = admin.get("name") or admin.get("email")
                owner_email = admin.get("email")
        out.append({
            **o,
            "owner": owner,
            "owner_email": owner_email,
            "stats": {"users": users_n, "projects": projects_n, "clients": clients_n},
        })
    return out


@router.get("/orgs/{org_id}")
async def get_one_org(org_id: str, request: Request,
                     session_token: Optional[str] = Cookie(default=None),
                     authorization: Optional[str] = Header(default=None)):
    await require_super_admin(request, session_token, authorization)
    o = await get_org(org_id)
    if not o:
        raise HTTPException(404, "Organisation not found")
    return o


@router.post("/orgs")
async def create_org(payload: OrgCreateIn, request: Request,
                     session_token: Optional[str] = Cookie(default=None),
                     authorization: Optional[str] = Header(default=None)):
    sa = await require_super_admin(request, session_token, authorization)

    # Reject duplicate admin_email
    email = payload.admin_email.lower().strip()
    if await db.users.find_one({"email": email}):
        raise HTTPException(409, "Admin email already registered")

    org_id = "org_" + uuid.uuid4().hex[:12]
    base_slug = payload.slug or _slugify(payload.name)
    slug = await _unique_slug(_slugify(base_slug))
    now = iso_now()

    org_doc = {
        "org_id": org_id,
        "slug": slug,
        "name": payload.name.strip(),
        "display_name": payload.display_name or payload.name.strip(),
        "employee_id_prefix": (normalize_prefix(payload.employee_id_prefix)
                               or derive_prefix(payload.name)),
        "business_mode": payload.business_mode,
        "phone": payload.phone,
        "website": payload.website,
        "gstin": payload.gstin,
        "pan": payload.pan,
        "industry": payload.industry or "Architecture & Interior Design",
        "plan": payload.plan or "starter",
        "address": payload.address.dict() if payload.address else {},
        "branding": (payload.branding.dict() if payload.branding
                     else {"primary_color": BRAND_PRIMARY, "accent_color": BRAND_ACCENT}),
        "billing": payload.billing.dict() if payload.billing else {},
        "features": {
            "modules": features_for_mode(payload.business_mode),
            "limits": DEFAULT_FEATURES["limits"],
        },
        "is_active": True,
        "is_suspended": False,
        "notes": payload.notes,
        "created_at": now,
        "created_by": sa["user_id"],
    }
    await db.organizations.insert_one(dict(org_doc))

    # Create first Company Admin
    admin_uid = "user_" + uuid.uuid4().hex[:12]
    admin_doc = {
        "user_id": admin_uid,
        "org_id": org_id,
        "employee_id": f"{org_doc['employee_id_prefix']}0001",   # per-org sequence
        "email": email,
        "name": payload.admin_name.strip(),
        "role": "Admin",
        # No password: the owner sets their own from a one-time link, so
        # platform staff never choose or know it.
        "is_active": True,
        "approval_status": "approved",
        "auth_type": "password",
        "created_at": now,
        "created_by": sa["user_id"],
    }
    try:
        await db.users.insert_one(dict(admin_doc))
    except Exception:
        # Do not leave an unusable tenant behind if its first login cannot be created.
        await db.organizations.delete_one({"org_id": org_id})
        raise
    from core.invites import issue_set_password_link
    invite_path = await issue_set_password_link(admin_doc, "invite", sa["user_id"])
    await audit(sa, "org.create", target=org_id, target_type="org",
                meta={"admin_user_id": admin_uid, "plan": org_doc["plan"]})
    return {"org": org_doc, "admin_user_id": admin_uid, "invite_path": invite_path}


@router.patch("/orgs/{org_id}")
async def update_org(org_id: str, payload: OrgUpdateIn, request: Request,
                     session_token: Optional[str] = Cookie(default=None),
                     authorization: Optional[str] = Header(default=None)):
    sa = await require_super_admin(request, session_token, authorization)
    org = await get_org(org_id)
    if not org:
        raise HTTPException(404, "Organisation not found")
    up = {k: v for k, v in payload.dict(exclude_unset=True).items() if v is not None}
    if "employee_id_prefix" in up:
        up["employee_id_prefix"] = normalize_prefix(up["employee_id_prefix"])
    # Convert nested pydantic to dict
    if "address" in up and hasattr(up["address"], "dict"):
        up["address"] = up["address"].dict()
    if "branding" in up and hasattr(up["branding"], "dict"):
        up["branding"] = up["branding"].dict()
    if "billing" in up:
        # Merge with existing billing so partial edits don't wipe other fields.
        new_billing = up["billing"].dict(exclude_unset=True) if hasattr(up["billing"], "dict") else dict(up["billing"])
        up["billing"] = {**(org.get("billing") or {}), **new_billing}
    # If business_mode changes, re-derive the module feature flags
    if "business_mode" in up and up["business_mode"] != org.get("business_mode"):
        new_modules = features_for_mode(up["business_mode"])
        prev = (org.get("features") or {}).get("modules") or {}
        # Preserve any admin-toggled overrides that don't conflict with the preset
        up["features"] = {
            "modules": {**prev, **new_modules},
            "limits": (org.get("features") or {}).get("limits", DEFAULT_FEATURES["limits"]),
        }
    up["updated_at"] = iso_now()
    await db.organizations.update_one({"org_id": org_id}, {"$set": up})
    await audit(sa, "org.update", target=org_id, target_type="org",
                meta={"fields": sorted(k for k in up if k != "updated_at")})
    return await get_org(org_id)


@router.post("/orgs/{org_id}/status")
async def change_org_status(org_id: str, payload: OrgStatusIn, request: Request,
                            session_token: Optional[str] = Cookie(default=None),
                            authorization: Optional[str] = Header(default=None)):
    sa = await require_super_admin(request, session_token, authorization)
    org = await get_org(org_id)
    if not org:
        raise HTTPException(404, "Organisation not found")
    if org_id == DEFAULT_ORG_ID:
        raise HTTPException(400, "Default organisation cannot be deactivated/suspended")

    action = payload.action.lower()
    updates = {"updated_at": iso_now(), "status_by": sa["user_id"]}
    if action == "activate":
        updates.update({"is_active": True, "is_suspended": False})
    elif action == "suspend":
        updates.update({"is_suspended": True})
        # Kill sessions of all users in this org so they get logged out
        user_ids = [u["user_id"] async for u in db.users.find({"org_id": org_id}, {"_id": 0, "user_id": 1})]
        if user_ids:
            await db.user_sessions.delete_many({"user_id": {"$in": user_ids}})
    elif action == "deactivate":
        updates.update({"is_active": False})
        user_ids = [u["user_id"] async for u in db.users.find({"org_id": org_id}, {"_id": 0, "user_id": 1})]
        if user_ids:
            await db.user_sessions.delete_many({"user_id": {"$in": user_ids}})
    else:
        raise HTTPException(400, "action must be activate|suspend|deactivate")
    await db.organizations.update_one({"org_id": org_id}, {"$set": updates})
    await audit(sa, f"org.{action}", target=org_id, target_type="org",
                meta={"org_name": org.get("name")})
    return await get_org(org_id)


class OrgSubscriptionIn(BaseModel):
    status: Optional[str] = None          # trial | active | expired | None (no restriction)
    trial_ends_on: Optional[str] = None   # YYYY-MM-DD, used with status "trial"


@router.patch("/orgs/{org_id}/subscription")
async def set_org_subscription(org_id: str, payload: OrgSubscriptionIn, request: Request,
                               session_token: Optional[str] = Cookie(default=None),
                               authorization: Optional[str] = Header(default=None)):
    """Platform owner sets a tenant's trial/active/expired state (read-only mode)."""
    from datetime import date as _d
    from core.subscription import STATUSES, subscription_state
    sa = await require_super_admin(request, session_token, authorization)
    org = await get_org(org_id)
    if not org:
        raise HTTPException(404, "Organisation not found")
    if payload.status is not None and payload.status not in STATUSES:
        raise HTTPException(400, "status must be trial, active or expired")
    if payload.status == "trial":
        try:
            _d.fromisoformat(payload.trial_ends_on or "")
        except ValueError:
            raise HTTPException(400, "trial_ends_on (YYYY-MM-DD) is required for a trial")
    sub = {"status": payload.status, "trial_ends_on": payload.trial_ends_on if payload.status == "trial" else None,
           "updated_at": iso_now(), "updated_by": sa["user_id"]}
    if payload.status == "expired":
        sub["ended_on"] = business_today().isoformat()
    await db.organizations.update_one({"org_id": org_id}, {"$set": {"subscription": sub, "updated_at": iso_now()}})
    await audit(sa, "org.subscription", target=org_id, target_type="org",
                meta={"status": payload.status, "trial_ends_on": sub["trial_ends_on"]})
    fresh = await get_org(org_id)
    return {"org_id": org_id, "subscription": sub, "state": subscription_state(fresh)}


# ------------------------------------------------------------------
# MODULE TOGGLES
# ------------------------------------------------------------------
class OrgModulesIn(BaseModel):
    modules: dict[str, StrictBool]  # e.g. {"accounting": False, "crm": True}

    @field_validator("modules")
    @classmethod
    def known_modules_only(cls, value: dict[str, bool]) -> dict[str, bool]:
        unknown = sorted(set(value) - MODULE_KEYS)
        if unknown:
            raise ValueError(f"Unknown module key(s): {', '.join(unknown)}")
        return value


@router.patch("/orgs/{org_id}/modules")
async def set_org_modules(org_id: str, payload: OrgModulesIn, request: Request,
                          session_token: Optional[str] = Cookie(default=None),
                          authorization: Optional[str] = Header(default=None)):
    """Platform owner toggles individual ERP modules on/off for a tenant."""
    sa = await require_super_admin(request, session_token, authorization)
    org = await get_org(org_id)
    if not org:
        raise HTTPException(404, "Organisation not found")
    current_modules = (org.get("features") or {}).get("modules") or {}
    new_modules = {**current_modules, **payload.modules}
    await db.organizations.update_one(
        {"org_id": org_id},
        {"$set": {"features.modules": new_modules, "updated_at": iso_now()}}
    )
    await audit(sa, "org.modules_update", target=org_id, target_type="org",
                meta={"changes": {k: v for k, v in payload.modules.items()}})
    return {"ok": True, "modules": new_modules}


@router.get("/contact-requests")
async def list_contact_requests(request: Request, limit: int = 50,
                                status: Optional[str] = None,
                                session_token: Optional[str] = Cookie(default=None),
                                authorization: Optional[str] = Header(default=None)):
    """Recent public demo requests, visible only to the platform owner."""
    await require_super_admin(request, session_token, authorization)
    if status not in (None, "new", "contacted", "closed"):
        raise HTTPException(400, "Invalid contact request status")
    query = {"status": status} if status else {}
    safe_limit = min(max(int(limit or 50), 1), 200)
    return await db.contact_requests.find(
        query, {"_id": 0, "website": 0},
    ).sort("created_at", -1).limit(safe_limit).to_list(safe_limit)


def _tenant_file_dirs(org_id: str) -> list:
    """Upload and branding folders that belong to one tenant."""
    from services import local_files
    safe = re.sub(r"[^A-Za-z0-9_-]", "_", org_id)[:64]
    root = local_files.STORAGE_ROOT
    branding = root / "branding" / "designsaga-erp"
    return [root / safe, branding / "org-logos" / safe, branding / "org-signatures" / safe]


class _ZipSink:
    """Write-only target for a streamed zip; drained after each chunk."""

    def __init__(self):
        self.buf = bytearray()

    def write(self, data) -> int:
        self.buf += data
        return len(data)

    def flush(self):
        pass

    def drain(self) -> bytes:
        out = bytes(self.buf)
        self.buf.clear()
        return out


@router.get("/orgs/{org_id}/export")
async def export_org(org_id: str, request: Request,
                     session_token: Optional[str] = Cookie(default=None),
                     authorization: Optional[str] = Header(default=None)):
    """Complete workspace export: every tenant record (JSON lines per collection,
    secrets removed) plus uploaded and branding files, streamed as one zip."""
    sa = await require_super_admin(request, session_token, authorization)
    org = await get_org(org_id)
    if not org:
        raise HTTPException(404, "Organisation not found")

    async def stream():
        import json
        import zipfile
        sink = _ZipSink()
        zf = zipfile.ZipFile(sink, "w", zipfile.ZIP_DEFLATED)
        manifest = {"org_id": org_id, "name": org.get("name"), "exported_at": iso_now(),
                    "collections": {}, "files": 0}
        zf.writestr("organization.json", json.dumps(org, default=str, indent=1))
        for coll in TENANT_COLLECTIONS:
            if coll in EXPORT_SKIPPED:
                continue
            projection = {"_id": 0, **{f: 0 for f in EXPORT_REDACTED_FIELDS.get(coll, ())}}
            count = 0
            with zf.open(f"data/{coll}.jsonl", "w", force_zip64=True) as entry:
                async for row in db[coll].find({"org_id": org_id}, projection):
                    entry.write((json.dumps(row, default=str) + "\n").encode("utf-8"))
                    count += 1
                    if len(sink.buf) > 1 << 20:
                        yield sink.drain()
            manifest["collections"][coll] = count
            yield sink.drain()
        from services import local_files
        for folder in _tenant_file_dirs(org_id):
            if not folder.exists():
                continue
            for path in sorted(p for p in folder.rglob("*") if p.is_file()):
                rel = path.relative_to(local_files.STORAGE_ROOT)
                with zf.open(f"files/{rel.as_posix()}", "w", force_zip64=True) as entry, \
                        path.open("rb") as src:
                    for chunk in iter(lambda: src.read(1 << 20), b""):
                        entry.write(chunk)
                        yield sink.drain()
                manifest["files"] += 1
        zf.writestr("manifest.json", json.dumps(manifest, indent=1))
        zf.close()
        yield sink.drain()
        # Recorded only when the whole archive was produced.
        await db.organizations.update_one({"org_id": org_id}, {"$set": {"exported_at": iso_now()}})
        await audit(sa, "org.export", target=org_id, target_type="org",
                    meta={"org_name": org.get("name"), "records": sum(manifest["collections"].values()),
                          "files": manifest["files"]})

    filename = f"{org.get('slug') or org_id}-export-{business_today().isoformat()}.zip"
    return StreamingResponse(stream(), media_type="application/zip",
                             headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.delete("/orgs/{org_id}")
async def delete_org(org_id: str, request: Request,
                     purge: bool = False,
                     confirm: Optional[str] = None,
                     session_token: Optional[str] = Cookie(default=None),
                     authorization: Optional[str] = Header(default=None)):
    """Deactivate an org (default). `?purge=true` permanently deletes it and all its
    data, and only for a deactivated workspace that has been exported, with the
    workspace slug typed in `confirm`."""
    sa = await require_super_admin(request, session_token, authorization)
    if org_id == DEFAULT_ORG_ID:
        raise HTTPException(400, "Default organisation cannot be deleted")
    org = await get_org(org_id)
    if not org:
        raise HTTPException(404, "Organisation not found")

    if purge:
        if org.get("is_active") is not False:
            raise HTTPException(409, "Deactivate the workspace before deleting it permanently")
        if not org.get("exported_at"):
            raise HTTPException(409, "Download the workspace export before deleting it permanently")
        if (confirm or "").strip().lower() != str(org.get("slug") or "").lower():
            raise HTTPException(400, "Type the workspace's short name exactly to confirm")

    if not purge:
        await db.organizations.update_one({"org_id": org_id},
                                          {"$set": {"is_active": False,
                                                    "deleted_at": iso_now()}})
        tenant_user_ids = [
            row["user_id"] async for row in db.users.find(
                {"org_id": org_id}, {"_id": 0, "user_id": 1})
            if row.get("user_id")
        ]
        if tenant_user_ids:
            await db.user_sessions.delete_many({"user_id": {"$in": tenant_user_ids}})
        await audit(sa, "org.deactivate", target=org_id, target_type="org",
                    meta={"org_name": org.get("name"),
                          "sessions_revoked": len(tenant_user_ids)})
        return {"ok": True, "purged": False}

    # Sessions and login-attempt rows do not carry org_id, so remove them via
    # the tenant's user identities before deleting the users themselves.
    tenant_users = await db.users.find(
        {"org_id": org_id},
        {"_id": 0, "user_id": 1, "email": 1, "employee_id": 1},
    ).to_list(10000)
    user_ids = [u["user_id"] for u in tenant_users if u.get("user_id")]
    login_identifiers = {
        str(value).strip().lower()
        for user in tenant_users
        for value in (user.get("email"), user.get("employee_id"), user.get("user_id"))
        if value and str(value).strip()
    }
    if user_ids:
        await db.user_sessions.delete_many({"user_id": {"$in": user_ids}})
        await db.user_app_locks.delete_many({"user_id": {"$in": user_ids}})
    if login_identifiers:
        await db.login_attempts.delete_many(
            {"identifier": {"$in": sorted(login_identifiers)}})

    # Purge every collection that owns tenant-scoped records. Keep this list
    # explicit so global scheduler/config collections cannot be erased.
    for coll in TENANT_PURGE_COLLECTIONS:
        await db[coll].delete_many({"org_id": org_id})
    await db.audit_chain.delete_one({"chain": org_id})
    await db.organizations.delete_one({"org_id": org_id})
    import shutil
    for folder in _tenant_file_dirs(org_id):
        shutil.rmtree(folder, ignore_errors=True)
    await audit(sa, "org.purge", target=org_id, target_type="org",
                meta={"org_name": org.get("name")})
    return {"ok": True, "purged": True}


# ------------------------------------------------------------------
# ORG ADMINS / USERS management
# ------------------------------------------------------------------
@router.get("/orgs/{org_id}/users")
async def list_org_users(org_id: str, request: Request,
                         session_token: Optional[str] = Cookie(default=None),
                         authorization: Optional[str] = Header(default=None)):
    await require_super_admin(request, session_token, authorization)
    rows = await db.users.find({"org_id": org_id}, {"_id": 0, "password_hash": 0}) \
                         .sort("created_at", 1).to_list(MAX_LIST_ROWS)
    return rows


class OrgAdminInviteIn(BaseModel):
    email: EmailStr
    name: str
    phone: Optional[str] = None


@router.post("/orgs/{org_id}/admins")
async def add_org_admin(org_id: str, payload: OrgAdminInviteIn, request: Request,
                        session_token: Optional[str] = Cookie(default=None),
                        authorization: Optional[str] = Header(default=None)):
    """Add a workspace admin; they set their own password from the returned link."""
    sa = await require_super_admin(request, session_token, authorization)
    org = await get_org(org_id)
    if not org:
        raise HTTPException(404, "Organisation not found")
    email = payload.email.lower().strip()
    if not payload.name.strip():
        raise HTTPException(400, "Name is required")
    if await db.users.find_one({"email": email}):
        raise HTTPException(409, "This email cannot be used. Choose another address.")
    from routes.auth import _next_employee_id  # local import: routes.auth imports core modules only
    uid = "user_" + uuid.uuid4().hex[:12]
    doc = {
        "user_id": uid, "org_id": org_id,
        "employee_id": await _next_employee_id(org_id),
        "email": email, "name": payload.name.strip(),
        "phone": payload.phone,
        "role": "Admin",
        "is_active": True, "approval_status": "approved",
        "auth_type": "password",
        "created_at": iso_now(), "created_by": sa["user_id"],
    }
    await db.users.insert_one(dict(doc))
    from core.invites import issue_set_password_link
    invite_path = await issue_set_password_link(doc, "invite", sa["user_id"])
    await audit(sa, "user.create", target=uid, target_type="user",
                meta={"role": "Admin", "via": "invite_link"}, org_id=org_id)
    return {**doc, "invite_path": invite_path}


@router.post("/orgs/{org_id}/users/{user_id}/reset-link")
async def reset_org_user_link(org_id: str, user_id: str, request: Request,
                              session_token: Optional[str] = Cookie(default=None),
                              authorization: Optional[str] = Header(default=None)):
    """A one-time link with which the user chooses a new password themselves.
    Their current password keeps working until the link is used."""
    sa = await require_super_admin(request, session_token, authorization)
    user = await db.users.find_one({"user_id": user_id, "org_id": org_id}, {"_id": 0})
    if not user:
        raise HTTPException(404, "User not found in this org")
    from core.invites import issue_set_password_link
    path = await issue_set_password_link(user, "reset", sa["user_id"])
    await audit(sa, "user.password_reset_link", target=user_id, target_type="user",
                org_id=org_id)
    return {"ok": True, "invite_path": path}


# ------------------------------------------------------------------
# UNASSIGNED / PENDING SIGNUPS — Google users with no domain match
# ------------------------------------------------------------------
@router.get("/pending-signups")
async def pending_signups(request: Request,
                          session_token: Optional[str] = Cookie(default=None),
                          authorization: Optional[str] = Header(default=None)):
    """Google sign-ins waiting for platform-level org assignment."""
    await require_super_admin(request, session_token, authorization)
    rows = await db.users.find(
        {"approval_status": "pending", "auth_type": {"$ne": "password"}},
        {"_id": 0, "password_hash": 0},
    ).sort("created_at", -1).to_list(200)
    return rows


class ReassignOrgIn(BaseModel):
    org_id: str
    role: Optional[str] = "Employee"
    approve: Optional[bool] = True


@router.post("/users/{user_id}/reassign-org")
async def reassign_org(user_id: str, payload: ReassignOrgIn, request: Request,
                       session_token: Optional[str] = Cookie(default=None),
                       authorization: Optional[str] = Header(default=None)):
    """Platform Owner moves an unassigned/pending user into a target org."""
    sa = await require_super_admin(request, session_token, authorization)
    target = await db.users.find_one({"user_id": user_id}, {"_id": 0})
    if not target:
        raise HTTPException(404, "User not found")
    org = await get_org(payload.org_id)
    if not org:
        raise HTTPException(404, "Target organisation not found")
    role = normalize_role(payload.role or "Employee")
    if role == "SuperAdmin":
        raise HTTPException(400, "A tenant user cannot be assigned the SuperAdmin role")
    updates = {
        "org_id": payload.org_id,
        "role": role,
        "reassigned_at": iso_now(),
        "reassigned_by": sa["user_id"],
    }
    if payload.approve:
        updates.update({"approval_status": "approved", "is_active": True})
    await db.users.update_one({"user_id": user_id}, {"$set": updates})
    await db.user_sessions.delete_many({"user_id": user_id})
    await audit(sa, "user.reassign_org", target=user_id, target_type="user",
                meta={"from_org_id": target.get("org_id"), "to_org_id": payload.org_id,
                      "role": role, "sessions_revoked": True}, org_id=payload.org_id)
    return await db.users.find_one({"user_id": user_id}, {"_id": 0, "password_hash": 0})


# ------------------------------------------------------------------
# PLATFORM ANALYTICS
# ------------------------------------------------------------------
@router.get("/analytics")
async def platform_analytics(request: Request,
                             session_token: Optional[str] = Cookie(default=None),
                             authorization: Optional[str] = Header(default=None)):
    await require_super_admin(request, session_token, authorization)
    orgs_total = await db.organizations.count_documents({})
    orgs_active = await db.organizations.count_documents({"is_active": True, "is_suspended": {"$ne": True}})
    orgs_suspended = await db.organizations.count_documents({"is_suspended": True})
    orgs_inactive = await db.organizations.count_documents({"is_active": False})

    users_total = await db.users.count_documents({})
    users_active = await db.users.count_documents({"is_active": True})
    projects_total = await db.projects.count_documents({})
    tasks_total = await db.tasks.count_documents({})

    # Commercial metadata only. A tenant's own accounting (journals, invoices,
    # receipts) is that customer's business and is never read for platform figures.
    from core.subscription import subscription_state
    today = business_today()
    by_plan: dict = {}
    by_status: dict = {}
    trials_ending, renewals_due = [], []
    async for o in db.organizations.find(
            {}, {"_id": 0, "org_id": 1, "name": 1, "plan": 1, "subscription": 1,
                 "billing": 1, "is_active": 1}):
        if o.get("is_active") is False:
            continue
        plan = o.get("plan") or "starter"
        by_plan[plan] = by_plan.get(plan, 0) + 1
        state = subscription_state(o, today)
        status = state["status"] or "not_set"
        by_status[status] = by_status.get(status, 0) + 1
        if state["status"] == "trial" and state["days_left"] is not None and state["days_left"] <= 14:
            trials_ending.append({"org_id": o["org_id"], "name": o.get("name"),
                                  "trial_ends_on": state["trial_ends_on"], "days_left": state["days_left"]})
        renewal = str((o.get("billing") or {}).get("renewal_date") or "")[:10]
        try:
            days = (_dt.date.fromisoformat(renewal) - today).days if renewal else None
        except ValueError:
            days = None
        if days is not None and days <= 30:
            renewals_due.append({"org_id": o["org_id"], "name": o.get("name"),
                                 "renewal_date": renewal, "days_left": days,
                                 "plan": plan})
    renewals_due.sort(key=lambda r: r["days_left"])
    trials_ending.sort(key=lambda r: r["days_left"])
    open_enquiries = await db.contact_requests.count_documents({"status": "new"})

    return {
        "orgs": {"total": orgs_total, "active": orgs_active,
                 "suspended": orgs_suspended, "inactive": orgs_inactive},
        "users": {"total": users_total, "active": users_active},
        "projects": projects_total,
        "tasks": tasks_total,
        "plans": by_plan,
        "subscriptions": by_status,
        "trials_ending": trials_ending,
        "renewals_due": renewals_due,
        "open_enquiries": open_enquiries,
    }


# ------------------------------------------------------------------
# IMPERSONATION — Super Admin steps into an org context
# ------------------------------------------------------------------
# ------------------------------------------------------------------
# Tenant health + platform isolation verification
# ------------------------------------------------------------------
_HEALTH_COLLECTIONS = [
    "users", "employees", "clients", "leads", "projects", "tasks",
    "invoices", "quotations_adv", "vendors_acc", "vendor_bills",
    "journal_entries", "accounts", "payment_milestones", "expenses",
    "purchase_orders", "attendance", "notifications", "calendar_events",
    "holidays", "files",
]


@router.get("/orgs/{org_id}/health")
async def org_health(org_id: str, request: Request,
                     session_token: Optional[str] = Cookie(default=None),
                     authorization: Optional[str] = Header(default=None)):
    """Per-tenant health snapshot: record counts, plan usage vs limits,
    latest activity, and admin coverage — for the SuperAdmin panel."""
    await require_super_admin(request, session_token, authorization)
    org = await get_org(org_id)
    if not org:
        raise HTTPException(404, "Organisation not found")
    counts = {}
    for coll in _HEALTH_COLLECTIONS:
        try:
            counts[coll] = await db[coll].count_documents({"org_id": org_id})
        except Exception:
            counts[coll] = None
    limits = ((org.get("features") or {}).get("limits")
              or {"max_users": 25, "max_projects": 200, "storage_mb": 1024})
    active_users = await db.users.count_documents(
        {"org_id": org_id, "is_active": {"$ne": False}})
    admins = await db.users.count_documents(
        {"org_id": org_id, "role": {"$in": ["Admin", "Director"]},
         "is_active": {"$ne": False}})
    # Latest activity — newest audit row or user login for this org
    last_login = None
    async for u in db.users.find({"org_id": org_id, "last_login": {"$ne": None}},
                                 {"_id": 0, "last_login": 1}).sort("last_login", -1).limit(1):
        last_login = u["last_login"]
    warnings = []
    if admins == 0:
        warnings.append("No active Admin — tenant cannot self-manage")
    if limits.get("max_users") and active_users >= limits["max_users"]:
        warnings.append(f"User limit reached ({active_users}/{limits['max_users']})")
    if limits.get("max_projects") and (counts.get("projects") or 0) >= limits["max_projects"]:
        warnings.append(f"Project limit reached ({counts['projects']}/{limits['max_projects']})")
    return {
        "org_id": org_id,
        "name": org.get("name"),
        "status": ("suspended" if org.get("is_suspended")
                   else "inactive" if org.get("is_active") is False else "active"),
        "plan": org.get("plan"),
        "business_mode": org.get("business_mode"),
        "counts": counts,
        "usage": {
            "users": {"used": active_users, "limit": limits.get("max_users")},
            "projects": {"used": counts.get("projects") or 0,
                         "limit": limits.get("max_projects")},
        },
        "admins": admins,
        "last_login": last_login,
        "warnings": warnings,
    }


@router.get("/isolation-check")
async def isolation_check(request: Request,
                          session_token: Optional[str] = Cookie(default=None),
                          authorization: Optional[str] = Header(default=None)):
    """Automated tenant-isolation verification. Scans business collections
    for documents with a missing/unknown org_id. PASS = every document is
    attributable to a real organisation."""
    await require_super_admin(request, session_token, authorization)
    valid_orgs = {o["org_id"] async for o in
                  db.organizations.find({}, {"_id": 0, "org_id": 1})}
    problems = []
    checked = 0
    for coll in _HEALTH_COLLECTIONS:
        if coll == "users":
            # SuperAdmins legitimately have no org_id
            missing = await db.users.count_documents(
                {"$or": [{"org_id": {"$exists": False}}, {"org_id": None}],
                 "is_super_admin": {"$ne": True}, "role": {"$ne": "SuperAdmin"}})
        else:
            missing = await db[coll].count_documents(
                {"$or": [{"org_id": {"$exists": False}}, {"org_id": None}]})
        orphan_org = 0
        if valid_orgs:
            orphan_org = await db[coll].count_documents(
                {"org_id": {"$nin": list(valid_orgs) + [None]}})
        checked += 1
        if missing or orphan_org:
            problems.append({"collection": coll,
                             "missing_org_id": missing,
                             "unknown_org_id": orphan_org})
    return {
        "status": "PASS" if not problems else "FAIL",
        "collections_checked": checked,
        "organisations": len(valid_orgs),
        "problems": problems,
        "checked_at": iso_now(),
    }


@router.patch("/orgs/{org_id}/limits")
async def update_org_limits(org_id: str, payload: dict, request: Request,
                            session_token: Optional[str] = Cookie(default=None),
                            authorization: Optional[str] = Header(default=None)):
    """Update plan limits for a tenant (max_users / max_projects / storage_mb)."""
    sa = await require_super_admin(request, session_token, authorization)
    org = await get_org(org_id)
    if not org:
        raise HTTPException(404, "Organisation not found")
    allowed = {}
    for k in ("max_users", "max_projects", "storage_mb"):
        if k in payload:
            try:
                v = int(payload[k])
            except (TypeError, ValueError):
                raise HTTPException(400, f"{k} must be an integer")
            if v < 1:
                raise HTTPException(400, f"{k} must be >= 1")
            allowed[f"features.limits.{k}"] = v
    if "plan" in payload:
        if payload["plan"] not in ("starter", "pro", "enterprise"):
            raise HTTPException(400, "plan must be starter|pro|enterprise")
        allowed["plan"] = payload["plan"]
    if not allowed:
        raise HTTPException(400, "Nothing to update")
    allowed["updated_at"] = iso_now()
    await db.organizations.update_one({"org_id": org_id}, {"$set": allowed})
    await audit(sa, "org.limits_update", target=org_id, target_type="org",
                meta={"changes": {k: v for k, v in allowed.items() if k != "updated_at"}})
    return await get_org(org_id)


class SupportAccessIn(BaseModel):
    reason: str
    mode: str = "read"            # read | write
    minutes: int = 60

    @field_validator("reason")
    @classmethod
    def _reason(cls, value: str) -> str:
        value = (value or "").strip()
        if len(value) < 10:
            raise ValueError("Give a reason of at least 10 characters (for example the support ticket)")
        return value[:300]

    @field_validator("mode")
    @classmethod
    def _mode(cls, value: str) -> str:
        if value not in ("read", "write"):
            raise ValueError("mode must be read or write")
        return value

    @field_validator("minutes")
    @classmethod
    def _minutes(cls, value: int) -> int:
        if not 5 <= value <= 240:
            raise ValueError("Support access lasts between 5 and 240 minutes")
        return value


@router.post("/impersonate/{org_id}")
async def impersonate_org(org_id: str, payload: SupportAccessIn, request: Request,
                          session_token: Optional[str] = Cookie(default=None),
                          authorization: Optional[str] = Header(default=None)):
    """Time-limited support access to one workspace for this Super Admin session only.
    Read-only unless write is requested; recorded in the customer's own audit log."""
    sa = await require_super_admin(request, session_token, authorization)
    org = await get_org(org_id)
    if not org:
        raise HTTPException(404, "Organisation not found")
    expires_at = now_utc() + _dt.timedelta(minutes=payload.minutes)
    session_filter = _current_session_filter(session_token, authorization)
    await db.user_sessions.update_one(session_filter, {"$set": {
        "impersonated_org_id": org_id, "impersonation_mode": payload.mode,
        "impersonation_reason": payload.reason, "impersonation_expires_at": expires_at,
    }})
    # Remove legacy account-wide state left by older deployments.
    await db.users.update_one({"user_id": sa["user_id"]},
                              {"$unset": {"org_id": "", "impersonating": ""}})
    meta = {"mode": payload.mode, "reason": payload.reason, "minutes": payload.minutes,
            "by": sa.get("email")}
    platform_actor = {**sa, "org_id": None}
    await audit(platform_actor, "platform.impersonation_start", target=org_id,
                target_type="org", meta=meta)
    # The customer sees every support access in their own audit log.
    await audit(platform_actor, "support.access_granted", target=org_id,
                target_type="org", meta=meta, org_id=org_id)
    return {"ok": True, "org_id": org_id, "org": org, "mode": payload.mode,
            "expires_at": expires_at.isoformat()}


@router.post("/exit-impersonation")
async def exit_impersonation(request: Request,
                             session_token: Optional[str] = Cookie(default=None),
                             authorization: Optional[str] = Header(default=None)):
    sa = await require_super_admin(request, session_token, authorization)
    previous_org_id = sa.get("org_id")
    session_filter = _current_session_filter(session_token, authorization)
    await db.user_sessions.update_one(session_filter, {"$unset": {
        "impersonated_org_id": "", "impersonation_mode": "", "impersonation_reason": "",
        "impersonation_expires_at": "",
    }})
    await db.users.update_one({"user_id": sa["user_id"]},
                              {"$unset": {"org_id": "", "impersonating": ""}})
    platform_actor = {**sa, "org_id": None}
    await audit(platform_actor, "platform.impersonation_end",
                target=previous_org_id or "", target_type="org")
    if previous_org_id:
        await audit(platform_actor, "support.access_ended", target=previous_org_id,
                    target_type="org", org_id=previous_org_id)
    return {"ok": True}
