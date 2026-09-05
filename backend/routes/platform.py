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
from typing import Optional, List
from pydantic import BaseModel
import uuid
import re

from core.db import db
from core.helpers import iso_now, now_utc, new_id
from core.tenancy import (
    require_super_admin, get_org, DEFAULT_ORG_ID, DEFAULT_ORG_SLUG,
    SUPER_ADMIN_EMAILS,
)
from core.rbac import normalize_role, expand_permissions
from core.audit import audit
from models.organization import (
    OrgCreateIn, OrgUpdateIn, OrgStatusIn, DEFAULT_FEATURES, features_for_mode,
)
from models.user import RegisterIn, ResetPasswordIn
from passlib.hash import bcrypt


router = APIRouter(prefix="/platform")


# ------------------------------------------------------------------
# helpers
# ------------------------------------------------------------------
def _slugify(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return s or "org"


def _hash(pw: str) -> str:
    return bcrypt.hash(pw)


async def _unique_slug(base: str) -> str:
    slug = base
    i = 1
    while await db.organizations.find_one({"slug": slug}, {"_id": 0, "org_id": 1}):
        i += 1
        slug = f"{base}-{i}"
    return slug


def _sanitize_org(o: dict) -> dict:
    return {k: v for k, v in (o or {}).items() if k != "_id"}


# ------------------------------------------------------------------
# ORGANISATIONS CRUD
# ------------------------------------------------------------------
@router.get("/orgs")
async def list_orgs(user=None, request: Request = None,
                    session_token: Optional[str] = Cookie(default=None),
                    authorization: Optional[str] = Header(default=None)):
    await require_super_admin(request, session_token, authorization)
    rows = await db.organizations.find({}, {"_id": 0}).sort("created_at", -1).to_list(500)
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
        out.append({
            **o,
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
        "business_mode": payload.business_mode,
        "phone": payload.phone,
        "website": payload.website,
        "gstin": payload.gstin,
        "pan": payload.pan,
        "industry": payload.industry or "Architecture & Interior Design",
        "plan": payload.plan or "starter",
        "address": payload.address.dict() if payload.address else {},
        "branding": (payload.branding.dict() if payload.branding
                     else {"primary_color": "#002FA7", "accent_color": "#0A0A0A"}),
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
        "employee_id": "DS0001",   # per-org sequence
        "email": email,
        "name": payload.admin_name.strip(),
        "role": "Admin",
        "password_hash": _hash(payload.admin_password),
        "is_active": True,
        "approval_status": "approved",
        "auth_type": "password",
        "created_at": now,
        "created_by": sa["user_id"],
    }
    await db.users.insert_one(dict(admin_doc))
    return {"org": org_doc, "admin_user_id": admin_uid}


@router.patch("/orgs/{org_id}")
async def update_org(org_id: str, payload: OrgUpdateIn, request: Request,
                     session_token: Optional[str] = Cookie(default=None),
                     authorization: Optional[str] = Header(default=None)):
    await require_super_admin(request, session_token, authorization)
    org = await get_org(org_id)
    if not org:
        raise HTTPException(404, "Organisation not found")
    up = {k: v for k, v in payload.dict(exclude_unset=True).items() if v is not None}
    # Convert nested pydantic to dict
    if "address" in up and hasattr(up["address"], "dict"):
        up["address"] = up["address"].dict()
    if "branding" in up and hasattr(up["branding"], "dict"):
        up["branding"] = up["branding"].dict()
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


@router.delete("/orgs/{org_id}")
async def delete_org(org_id: str, request: Request,
                     purge: bool = False,
                     session_token: Optional[str] = Cookie(default=None),
                     authorization: Optional[str] = Header(default=None)):
    """Delete an org. By default just marks inactive. `?purge=true`
    hard-deletes the org AND all its data (dangerous)."""
    await require_super_admin(request, session_token, authorization)
    if org_id == DEFAULT_ORG_ID:
        raise HTTPException(400, "Default organisation cannot be deleted")
    org = await get_org(org_id)
    if not org:
        raise HTTPException(404, "Organisation not found")

    if not purge:
        await db.organizations.update_one({"org_id": org_id},
                                          {"$set": {"is_active": False,
                                                    "deleted_at": iso_now()}})
        await audit({"user_id": "sa", "email": "sa", "role": "SuperAdmin"},
                    "org.deactivate", target=org_id, target_type="org",
                    meta={"org_name": org.get("name")})
        return {"ok": True, "purged": False}

    # Purge — drop every scoped collection's docs for this org
    scoped = [
        "users", "user_sessions", "leads", "clients", "projects", "tasks",
        "vendors_acc", "vendor_bills", "vendor_payments", "vendor_commissions",
        "invoices", "quotations", "quotations_adv", "employees",
        "attendance", "leave_applications", "leave_rules",
        "journal_entries", "accounts", "payroll_runs",
        "notifications", "files", "documents", "milestones",
    ]
    for coll in scoped:
        await db[coll].delete_many({"org_id": org_id})
    await db.organizations.delete_one({"org_id": org_id})
    await audit({"user_id": "sa", "email": "sa", "role": "SuperAdmin"},
                "org.purge", target=org_id, target_type="org",
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
                         .sort("created_at", 1).to_list(500)
    return rows


@router.post("/orgs/{org_id}/admins")
async def add_org_admin(org_id: str, payload: RegisterIn, request: Request,
                        session_token: Optional[str] = Cookie(default=None),
                        authorization: Optional[str] = Header(default=None)):
    sa = await require_super_admin(request, session_token, authorization)
    org = await get_org(org_id)
    if not org:
        raise HTTPException(404, "Organisation not found")
    email = payload.email.lower().strip()
    if await db.users.find_one({"email": email}):
        raise HTTPException(409, "Email already registered")
    uid = "user_" + uuid.uuid4().hex[:12]
    doc = {
        "user_id": uid, "org_id": org_id,
        "email": email, "name": payload.name.strip(),
        "phone": payload.phone,
        "role": "Admin",
        "password_hash": _hash(payload.password),
        "is_active": True, "approval_status": "approved",
        "auth_type": "password",
        "created_at": iso_now(), "created_by": sa["user_id"],
    }
    await db.users.insert_one(dict(doc))
    doc.pop("password_hash", None)
    return doc


@router.post("/orgs/{org_id}/users/{user_id}/reset-password")
async def reset_org_user_password(org_id: str, user_id: str, payload: ResetPasswordIn,
                                  request: Request,
                                  session_token: Optional[str] = Cookie(default=None),
                                  authorization: Optional[str] = Header(default=None)):
    sa = await require_super_admin(request, session_token, authorization)
    user = await db.users.find_one({"user_id": user_id, "org_id": org_id}, {"_id": 0})
    if not user:
        raise HTTPException(404, "User not found in this org")
    await db.users.update_one(
        {"user_id": user_id},
        {"$set": {"password_hash": _hash(payload.new_password),
                  "password_updated_at": iso_now(),
                  "password_reset_by": sa["user_id"]}}
    )
    await db.user_sessions.delete_many({"user_id": user_id})
    return {"ok": True}


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
    updates = {
        "org_id": payload.org_id,
        "role": normalize_role(payload.role or "Employee"),
        "reassigned_at": iso_now(),
        "reassigned_by": sa["user_id"],
    }
    if payload.approve:
        updates.update({"approval_status": "approved", "is_active": True})
    await db.users.update_one({"user_id": user_id}, {"$set": updates})
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

    # Revenue rollup across all orgs (from journal_entries.income lines)
    revenue = 0.0
    async for je in db.journal_entries.find({}, {"_id": 0, "lines": 1}):
        for l in je.get("lines", []):
            if l.get("account_type") == "income":
                revenue += float(l.get("credit", 0)) - float(l.get("debit", 0))

    # Per-org revenue leaderboard (top 5)
    per_org_rev = {}
    async for je in db.journal_entries.find({}, {"_id": 0, "org_id": 1, "lines": 1}):
        oid = je.get("org_id") or DEFAULT_ORG_ID
        for l in je.get("lines", []):
            if l.get("account_type") == "income":
                per_org_rev[oid] = per_org_rev.get(oid, 0.0) + float(l.get("credit", 0)) - float(l.get("debit", 0))
    leaderboard_ids = sorted(per_org_rev.items(), key=lambda x: -x[1])[:5]
    leaderboard = []
    for oid, amt in leaderboard_ids:
        o = await get_org(oid)
        leaderboard.append({"org_id": oid, "name": o["name"] if o else "Default",
                           "revenue": round(amt, 2)})

    return {
        "orgs": {"total": orgs_total, "active": orgs_active,
                 "suspended": orgs_suspended, "inactive": orgs_inactive},
        "users": {"total": users_total, "active": users_active},
        "projects": projects_total,
        "tasks": tasks_total,
        "revenue_total": round(revenue, 2),
        "leaderboard": leaderboard,
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


@router.post("/impersonate/{org_id}")
async def impersonate_org(org_id: str, request: Request,
                          session_token: Optional[str] = Cookie(default=None),
                          authorization: Optional[str] = Header(default=None)):
    """Super Admin picks an org context to operate in. Sets user.org_id
    for the duration of the session (writes to the user doc)."""
    sa = await require_super_admin(request, session_token, authorization)
    if org_id == "":
        # exit impersonation
        await db.users.update_one({"user_id": sa["user_id"]},
                                  {"$unset": {"org_id": "", "impersonating": ""}})
        return {"ok": True, "org_id": None}
    org = await get_org(org_id)
    if not org:
        raise HTTPException(404, "Organisation not found")
    await db.users.update_one({"user_id": sa["user_id"]},
                              {"$set": {"org_id": org_id, "impersonating": True}})
    return {"ok": True, "org_id": org_id, "org": org}


@router.post("/exit-impersonation")
async def exit_impersonation(request: Request,
                             session_token: Optional[str] = Cookie(default=None),
                             authorization: Optional[str] = Header(default=None)):
    sa = await require_super_admin(request, session_token, authorization)
    await db.users.update_one({"user_id": sa["user_id"]},
                              {"$unset": {"org_id": "", "impersonating": ""}})
    return {"ok": True}
