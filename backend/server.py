"""
Design Saga - SaaS platform for architecture/interior design firms
FastAPI backend with Google Auth, CRM, Projects, Tasks, Invoices, AI Assistant, Client Portal
"""
from fastapi import FastAPI, APIRouter, HTTPException, Request, Response, Cookie, Header
from fastapi.responses import StreamingResponse
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pathlib import Path
from pydantic import BaseModel, Field
from typing import List, Optional, Literal
from datetime import datetime, timezone, timedelta
import os
import asyncio
import uuid
import logging
import io
import httpx

from fpdf import FPDF
from emergentintegrations.llm.chat import LlmChat, UserMessage

# ============================================================
# Setup
# ============================================================
ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

mongo_url = os.environ["MONGO_URL"]
db_name = os.environ["DB_NAME"]
client = AsyncIOMotorClient(mongo_url)
db = client[db_name]

# Tenant-scoped proxy — use `sdb.<coll>.` in place of `db.<coll>.` for
# any business collection so reads/writes auto-filter by org_id.
from core.scoped_db import sdb  # noqa: E402
from core.audit import audit as audit_log  # noqa: E402

EMERGENT_LLM_KEY = os.environ.get("EMERGENT_LLM_KEY")
EMERGENT_AUTH_BASE = "https://demobackend.emergentagent.com/auth/v1/env/oauth/session-data"

# Super-admins: emails in this set are ALWAYS elevated to role="Admin" on every
# sign-in and can never be demoted (RBAC endpoint also blocks demotion below).
SUPER_ADMIN_EMAILS = {
    e.strip().lower()
    for e in os.environ.get("SUPER_ADMIN_EMAILS", "designsaga10@gmail.com").split(",")
    if e.strip()
}


def _is_super_admin(email: Optional[str]) -> bool:
    return bool(email) and email.strip().lower() in SUPER_ADMIN_EMAILS

app = FastAPI(title="Design Saga API")
api = APIRouter(prefix="/api")

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


# ============================================================
# Helpers
# ============================================================
def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime) -> str:
    return dt.isoformat()


def new_id(prefix: str = "") -> str:
    return f"{prefix}{uuid.uuid4().hex[:12]}" if prefix else uuid.uuid4().hex[:12]


async def get_current_user(
    request: Request,
    session_token: Optional[str] = Cookie(default=None),
    authorization: Optional[str] = Header(default=None),
):
    """Resolve user from cookie first, then Authorization header. Returns user dict or None."""
    from core.scoped_db import set_scope_from_user, clear_scope
    token = session_token
    if not token and authorization and authorization.startswith("Bearer "):
        token = authorization.split(" ", 1)[1]
    if not token:
        clear_scope()
        return None

    session = await db.user_sessions.find_one({"session_token": token}, {"_id": 0})
    if not session:
        clear_scope()
        return None

    expires_at = session.get("expires_at")
    if isinstance(expires_at, str):
        expires_at = datetime.fromisoformat(expires_at)
    if expires_at and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at and expires_at < now_utc():
        clear_scope()
        return None

    user = await db.users.find_one({"user_id": session["user_id"]}, {"_id": 0})
    if user:
        # Attach EFFECTIVE (per-tenant override-aware) permissions so that
        # has_permission() and _user_with_perms() both honour any role
        # customisation an Admin made via the Team & Roles matrix. Without this
        # a revoked permission (e.g. Designer -> employees.read) would silently
        # fall back to the static role default and stay granted.
        try:
            from core.deps import resolve_permissions as _resolve_perms
            from core.tenancy import user_org_id as _uoid
            user["permissions"] = await _resolve_perms(user.get("role"), _uoid(user))
        except Exception:
            pass
    set_scope_from_user(user)
    return user


async def require_user(request: Request, session_token: Optional[str] = Cookie(default=None),
                       authorization: Optional[str] = Header(default=None)):
    user = await get_current_user(request, session_token, authorization)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    # Approval / active gates — pending or rejected users cannot use protected routes.
    status = user.get("approval_status")
    if status == "pending":
        raise HTTPException(status_code=403,
                            detail="Your account is awaiting Admin approval.")
    if status == "rejected" or user.get("is_active") is False:
        raise HTTPException(status_code=403,
                            detail="Your account has been deactivated. Contact an Admin.")
    return user


# ============================================================
# RBAC – Roles, Permissions, Guards
# ============================================================
# NOTE: Roles + permissions live in `core/rbac.py` (single source of truth).
# We re-export names here so the rest of server.py doesn't need to be rewritten.
# ============================================================
from core.rbac import (
    ROLES,
    ROLE_PERMISSIONS,
    LEGACY_ROLE_MAP as _LEGACY_ROLE_MAP,
    normalize_role as _normalize_role,
    expand_permissions as _expand_permissions,
    has_permission,
    PERMISSION_CATALOG,
    PROTECTED_ROLES,
    valid_permission_keys,
)


def require_permission(perm: str):
    """FastAPI dependency factory — raises 403 if user lacks perm."""
    async def _dep(request: Request,
                   session_token: Optional[str] = Cookie(default=None),
                   authorization: Optional[str] = Header(default=None)):
        user = await require_user(request, session_token, authorization)
        if not has_permission(user, perm):
            raise HTTPException(status_code=403,
                                detail=f"Missing permission: {perm}")
        return user
    return _dep


def _user_with_perms(user: dict) -> dict:
    """Attach normalised role + expanded permissions for wire output.
    Always strips `password_hash` — never leak the bcrypt digest."""
    if not user:
        return user
    out = {k: v for k, v in user.items() if k != "password_hash"}
    out["role"] = _normalize_role(user.get("role"))
    if isinstance(user.get("permissions"), list) and user.get("permissions"):
        out["permissions"] = list(user["permissions"])
    else:
        out["permissions"] = _expand_permissions(out["role"])
    # Multi-tenant: expose org_id and super-admin flag
    from core.tenancy import DEFAULT_ORG_ID, SUPER_ADMIN_EMAILS as _SA_EMAILS
    if out["role"] == "SuperAdmin" and not out.get("impersonating"):
        # Super admins always live outside any tenant (unless impersonating).
        out["org_id"] = None
    else:
        out.setdefault("org_id", DEFAULT_ORG_ID)
    out["is_super_admin"] = (
        out["role"] == "SuperAdmin"
        or (out.get("email") or "").strip().lower() in _SA_EMAILS
    )
    return out


# ============================================================
# Models
# ============================================================
PIPELINE_STAGES = ["New", "Qualified", "Proposal", "Negotiation", "Won", "Lost"]
PROJECT_STAGES = [
    "Requirement", "Concept", "Design Dev", "Tech Drawings",
    "Review", "Signoff", "Procurement", "Execution", "Handover"
]
TASK_STATUSES = ["todo", "in_progress", "review", "done"]

# ----- Extended task model (backward compatible) -----
TASK_TYPES = ["employee", "vendor"]
TASK_STATUS_DETAIL = [
    "Pending", "Selection Required", "Reference Required", "Vendor Required",
    "Quotation Requested", "Quotation Received", "Ordered",
    "Work Started", "In Progress", "On Hold",
    "Inspection Pending", "Completed", "Cancelled",
]
TASK_PRIORITIES_EXT = ["low", "medium", "high", "urgent", "critical"]
STATUS_TO_LANE = {
    "Pending": "todo", "Selection Required": "todo", "Reference Required": "todo",
    "Vendor Required": "todo", "Quotation Requested": "todo",
    "Quotation Received": "in_progress", "Ordered": "in_progress",
    "Work Started": "in_progress", "In Progress": "in_progress",
    "On Hold": "review", "Inspection Pending": "review",
    "Completed": "done", "Cancelled": "done",
}
LANE_TO_DEFAULT_STATUS = {"todo": "Pending", "in_progress": "In Progress",
                          "review": "Inspection Pending", "done": "Completed"}
TASK_AREAS = [
    "Entrance", "Foyer", "Living Room", "Drawing Room", "Dining Room", "Kitchen",
    "Utility", "Store Room", "Pooja Room", "Parents Bedroom", "Master Bedroom",
    "Kids Bedroom", "Guest Bedroom", "Children's Bedroom", "Walk-in Closet",
    "Master Bathroom", "Common Bathroom", "Powder Room", "Balcony", "Terrace",
    "Home Office", "Study Room", "Family Lounge", "Staircase", "Lift Lobby",
    "Basement", "Parking", "Garden", "Outdoor Area",
]
TASK_CATEGORIES = [
    "Furniture", "Lighting", "Decor", "Wall Feature", "Flooring", "Ceiling",
    "Painting", "Wallpaper", "Curtains", "Blinds", "Hardware", "Doors", "Windows",
    "Wardrobe", "TV Unit", "Kitchen", "Vanity", "Bathroom Accessories",
    "Electrical", "Plumbing", "HVAC", "False Ceiling", "Marble", "Granite",
    "Tiles", "Glass", "Mirror", "Metal Work", "Fabrication", "Landscape",
    "Civil Work", "Automation", "Accessories", "Others",
]
REMINDER_FREQUENCIES = ["one_time", "daily", "weekly", "monthly", "custom"]
INVOICE_STATUSES = ["draft", "sent", "paid", "overdue"]


class LeadIn(BaseModel):
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    source: Optional[str] = "Website"
    project_type: Optional[str] = "Residential"
    budget: Optional[float] = 0
    location: Optional[str] = None
    timeline: Optional[str] = None
    stage: Optional[str] = "New"
    notes: Optional[str] = None


class LeadStageUpdate(BaseModel):
    stage: str


class LeadUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    source: Optional[str] = None
    project_type: Optional[str] = None
    budget: Optional[float] = None
    location: Optional[str] = None
    timeline: Optional[str] = None
    notes: Optional[str] = None


class ClientIn(BaseModel):
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    company: Optional[str] = None
    address: Optional[str] = None
    client_type: Optional[str] = None
    notes: Optional[str] = None


class ClientUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    company: Optional[str] = None
    address: Optional[str] = None
    client_type: Optional[str] = None
    notes: Optional[str] = None


class ProjectIn(BaseModel):
    name: str
    client_id: Optional[str] = None
    project_type: Optional[str] = "Residential"        # Residential | Commercial | Retail ...
    engagement_type: Optional[str] = None              # consultancy | turnkey  (Hybrid-org only)
    budget: Optional[float] = 0
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    stage: Optional[str] = "Requirement"
    description: Optional[str] = None


class ProjectStageUpdate(BaseModel):
    stage: str


class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    client_id: Optional[str] = None
    project_type: Optional[str] = None
    engagement_type: Optional[str] = None
    budget: Optional[float] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    description: Optional[str] = None
    project_manager_id: Optional[str] = None
    team_ids: Optional[List[str]] = None
    site_address: Optional[str] = None
    site_area_sqft: Optional[float] = None


class VendorContact(BaseModel):
    vendor_name: Optional[str] = ""
    contact_person: Optional[str] = ""
    phone: Optional[str] = ""
    email: Optional[str] = ""
    whatsapp: Optional[str] = ""
    company_name: Optional[str] = ""


class FollowUpIn(BaseModel):
    follow_up_date: Optional[str] = None
    reminder_date: Optional[str] = None
    reminder_time: Optional[str] = None
    reminder_frequency: Optional[str] = "one_time"
    assigned_employee: Optional[str] = None
    notes: Optional[str] = ""
    next_follow_up_date: Optional[str] = None


class TaskIn(BaseModel):
    title: str
    description: Optional[str] = None
    project_id: Optional[str] = None
    assignee_id: Optional[str] = None
    assignee_name: Optional[str] = None
    priority: Optional[str] = "medium"
    status: Optional[str] = "todo"
    due_date: Optional[str] = None
    # Extended (all optional, backward compatible):
    task_type: Optional[str] = "employee"       # employee | vendor
    area: Optional[str] = None
    category: Optional[str] = None
    item_description: Optional[str] = None
    quantity: Optional[float] = None
    status_detail: Optional[str] = None
    remarks: Optional[str] = None
    vendor_contact: Optional[VendorContact] = None
    reference_links: Optional[List[str]] = None
    attachments: Optional[List[dict]] = None    # [{label, url, type}]
    assignees: Optional[List[str]] = None       # multi-assign (employee ids)


class TaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    project_id: Optional[str] = None
    priority: Optional[str] = None
    status: Optional[str] = None
    due_date: Optional[str] = None
    task_type: Optional[str] = None
    area: Optional[str] = None
    category: Optional[str] = None
    item_description: Optional[str] = None
    quantity: Optional[float] = None
    status_detail: Optional[str] = None
    remarks: Optional[str] = None
    vendor_contact: Optional[VendorContact] = None
    reference_links: Optional[List[str]] = None
    attachments: Optional[List[dict]] = None
    assignees: Optional[List[str]] = None
    follow_up: Optional[FollowUpIn] = None


class TaskStatusUpdate(BaseModel):
    status: Optional[str] = None
    status_detail: Optional[str] = None


class InvoiceItem(BaseModel):
    description: str
    quantity: float = 1
    rate: float = 0
    amount: float = 0


class InvoiceIn(BaseModel):
    client_id: Optional[str] = None
    client_name: Optional[str] = None
    project_id: Optional[str] = None
    project_name: Optional[str] = None
    items: List[InvoiceItem] = []
    tax_rate: float = 0
    notes: Optional[str] = None
    due_date: Optional[str] = None
    status: Optional[str] = "draft"
    doc_type: Optional[Literal["invoice", "quotation"]] = "invoice"


class InvoiceStatusUpdate(BaseModel):
    status: str


class InvoiceUpdate(BaseModel):
    client_id: Optional[str] = None
    project_id: Optional[str] = None
    items: Optional[List[InvoiceItem]] = None
    tax_rate: Optional[float] = None
    notes: Optional[str] = None
    due_date: Optional[str] = None


class AIChatIn(BaseModel):
    message: str
    session_id: Optional[str] = None
    context: Optional[str] = None


class FileIn(BaseModel):
    project_id: str
    name: str
    url: str
    stage: Optional[str] = None
    version: Optional[int] = 1


# ============================================================
# Auth Routes (Emergent Google)
# ============================================================
@api.post("/auth/session")
async def create_session(request: Request, response: Response):
    """Called by frontend AuthCallback after Google redirect. Accepts session_id in body or X-Session-ID header."""
    body = {}
    try:
        body = await request.json()
    except Exception:
        body = {}
    session_id = body.get("session_id") or request.headers.get("X-Session-ID")
    if not session_id:
        raise HTTPException(status_code=400, detail="Missing session_id")

    async with httpx.AsyncClient(timeout=15) as http:
        r = await http.get(EMERGENT_AUTH_BASE, headers={"X-Session-ID": session_id})
    if r.status_code != 200:
        raise HTTPException(status_code=401, detail="Invalid session")
    data = r.json()

    email = data.get("email")
    name = data.get("name") or email
    picture = data.get("picture")
    session_token = data.get("session_token")

    # Upsert user
    existing = await db.users.find_one({"email": email}, {"_id": 0})
    if existing:
        user_id = existing["user_id"]
        update_set = {"name": name, "picture": picture, "last_login": iso(now_utc())}
        # Super-admin guarantee: force-elevate to SuperAdmin on every sign-in
        if _is_super_admin(email):
            if _normalize_role(existing.get("role")) != "SuperAdmin":
                update_set["role"] = "SuperAdmin"
            update_set["approval_status"] = "approved"
            update_set["is_active"] = True
        await db.users.update_one({"user_id": user_id}, {"$set": update_set})
        user = await db.users.find_one({"user_id": user_id}, {"_id": 0})
    else:
        user_id = f"user_{uuid.uuid4().hex[:12]}"
        user_count = await db.users.count_documents({})
        # First-ever user OR whitelisted super-admin = auto-approved SuperAdmin.
        # Every other Google sign-up lands in `pending` and must be approved.
        is_privileged = _is_super_admin(email) or user_count == 0
        from core.tenancy import DEFAULT_ORG_ID
        # Try to match a company by email domain (@acme.com → Acme Interiors)
        assigned_org_id = None
        if not is_privileged and email and "@" in email:
            domain = email.split("@", 1)[1].lower()
            match = await db.organizations.find_one(
                {"$or": [{"email_domains": domain}, {"email_domain": domain}]},
                {"_id": 0, "org_id": 1},
            )
            if match:
                assigned_org_id = match["org_id"]
        user = {
            "user_id": user_id,
            "org_id": (None if is_privileged
                       else (assigned_org_id or DEFAULT_ORG_ID)),
            "email": email,
            "name": name,
            "picture": picture,
            "role": "SuperAdmin" if is_privileged else "Employee",
            "approval_status": "approved" if is_privileged else "pending",
            "is_active": True if is_privileged else False,
            "auth_type": "google",
            "created_at": iso(now_utc()),
            "last_login": iso(now_utc()),
        }
        await db.users.insert_one(dict(user))

    # Store session
    expires_at = now_utc() + timedelta(days=7)
    await db.user_sessions.insert_one({
        "user_id": user_id,
        "session_token": session_token,
        "expires_at": expires_at,
        "created_at": now_utc(),
    })

    # httpOnly cookie
    response.set_cookie(
        key="session_token",
        value=session_token,
        httponly=True,
        secure=True,
        samesite="none",
        path="/",
        max_age=7 * 24 * 3600,
    )

    user_out = await db.users.find_one({"user_id": user_id}, {"_id": 0})
    try:
        from core.deps import resolve_permissions as _resolve_perms
        from core.tenancy import user_org_id as _uoid_sess
        user_out["permissions"] = await _resolve_perms(user_out.get("role"), _uoid_sess(user_out))
    except Exception:
        pass
    return {"user": _user_with_perms(user_out), "session_token": session_token}


@api.get("/auth/me")
async def auth_me(user=None, request: Request = None,
                  session_token: Optional[str] = Cookie(default=None),
                  authorization: Optional[str] = Header(default=None)):
    user = await get_current_user(request, session_token, authorization)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return _user_with_perms(user)


@api.post("/auth/logout")
async def logout(response: Response, session_token: Optional[str] = Cookie(default=None)):
    if session_token:
        await db.user_sessions.delete_many({"session_token": session_token})
    response.delete_cookie("session_token", path="/")
    return {"ok": True}


# ============================================================
# RBAC endpoints
# ============================================================
class RoleAssignIn(BaseModel):
    role: str


@api.get("/rbac/roles")
async def rbac_roles(request: Request,
                     session_token: Optional[str] = Cookie(default=None),
                     authorization: Optional[str] = Header(default=None)):
    """Role catalogue with EFFECTIVE (per-tenant override-aware) permissions,
    the static defaults, and the editable-permission catalogue for the UI."""
    user = await require_user(request, session_token, authorization)
    from core.deps import resolve_permissions as _resolve_perms
    from core.tenancy import user_org_id as _uoid
    org_id = _uoid(user)
    roles_out = []
    for r in ROLES:
        default_perms = ROLE_PERMISSIONS.get(r, [])
        if r in PROTECTED_ROLES:
            eff = default_perms
        else:
            eff = await _resolve_perms(r, org_id)
        roles_out.append({
            "name": r,
            "permissions": eff,
            "default_permissions": default_perms,
            "editable": r not in PROTECTED_ROLES,
            "customized": r not in PROTECTED_ROLES and sorted(eff) != sorted(default_perms),
        })
    return {"roles": roles_out, "catalog": PERMISSION_CATALOG}


class RolePermsIn(BaseModel):
    permissions: List[str]


@api.put("/rbac/roles/{role}/permissions")
async def set_role_permissions(role: str, payload: RolePermsIn, request: Request,
                               session_token: Optional[str] = Cookie(default=None),
                               authorization: Optional[str] = Header(default=None)):
    """Admin-only. Save a per-tenant permission override for a role."""
    actor = await require_user(request, session_token, authorization)
    if not (has_permission(actor, "*.*") or has_permission(actor, "rbac.manage")):
        raise HTTPException(status_code=403, detail="Only Admin can edit role permissions")
    role = _normalize_role(role)
    if role in PROTECTED_ROLES:
        raise HTTPException(status_code=400, detail=f"The {role} role's permissions are locked.")
    from core.tenancy import user_org_id as _uoid
    org_id = _uoid(actor)
    if not org_id:
        raise HTTPException(status_code=400, detail="No tenant context")
    valid = valid_permission_keys()
    perms = sorted({p for p in payload.permissions if p in valid})
    await db.role_permissions.update_one(
        {"org_id": org_id, "role": role},
        {"$set": {"org_id": org_id, "role": role, "permissions": perms,
                  "updated_at": datetime.now(timezone.utc).isoformat(), "updated_by": actor["user_id"]}},
        upsert=True)
    return {"ok": True, "role": role, "permissions": perms}


@api.post("/rbac/roles/{role}/reset-permissions")
async def reset_role_permissions(role: str, request: Request,
                                 session_token: Optional[str] = Cookie(default=None),
                                 authorization: Optional[str] = Header(default=None)):
    """Admin-only. Remove the tenant override → revert role to platform default."""
    actor = await require_user(request, session_token, authorization)
    if not (has_permission(actor, "*.*") or has_permission(actor, "rbac.manage")):
        raise HTTPException(status_code=403, detail="Only Admin can edit role permissions")
    role = _normalize_role(role)
    from core.tenancy import user_org_id as _uoid
    org_id = _uoid(actor)
    await db.role_permissions.delete_one({"org_id": org_id, "role": role})
    return {"ok": True, "role": role, "permissions": ROLE_PERMISSIONS.get(role, [])}


@api.get("/rbac/users")
async def rbac_users(request: Request,
                     session_token: Optional[str] = Cookie(default=None),
                     authorization: Optional[str] = Header(default=None)):
    """Admin or HR can list users."""
    user = await require_user(request, session_token, authorization)
    if not (has_permission(user, "users.read") or has_permission(user, "rbac.read")):
        raise HTTPException(status_code=403, detail="Missing permission: users.read")
    users = await db.users.find({}, {"_id": 0}).sort("created_at", 1).to_list(500)
    # Which identifiers are currently locked out (>=5 fails in the window)?
    from datetime import timedelta as _td
    cutoff = now_utc() - _td(minutes=15)
    locked_idents = set()
    try:
        agg = await db.login_attempts.aggregate([
            {"$match": {"at": {"$gte": cutoff}}},
            {"$group": {"_id": "$identifier", "n": {"$sum": 1}}},
            {"$match": {"n": {"$gte": 5}}},
        ]).to_list(1000)
        locked_idents = {a["_id"] for a in agg}
    except Exception:
        locked_idents = set()
    out = []
    for u in users:
        is_locked = ((u.get("email") or "").lower() in locked_idents) or \
                    ((str(u.get("employee_id") or "").lower()) in locked_idents)
        out.append({
            "user_id": u.get("user_id"),
            "email": u.get("email"),
            "name": u.get("name"),
            "picture": u.get("picture"),
            "role": _normalize_role(u.get("role")),
            "employee_id": u.get("employee_id"),
            "approval_status": u.get("approval_status", "approved"),
            "is_active": u.get("is_active", True),
            "is_locked": is_locked,
            "created_at": u.get("created_at"),
            "last_login": u.get("last_login"),
        })
    return out


@api.patch("/rbac/users/{user_id}/role")
async def rbac_assign_role(user_id: str, payload: RoleAssignIn, request: Request,
                           session_token: Optional[str] = Cookie(default=None),
                           authorization: Optional[str] = Header(default=None)):
    """Admin-only. Assign a role from the ROLES catalogue."""
    actor = await require_user(request, session_token, authorization)
    if not has_permission(actor, "rbac.manage") and not has_permission(actor, "*.*"):
        raise HTTPException(status_code=403, detail="Only Admin can change roles")
    new_role = _normalize_role(payload.role)
    if new_role not in ROLES:
        raise HTTPException(status_code=400, detail=f"Unknown role: {payload.role}")
    target = await db.users.find_one({"user_id": user_id}, {"_id": 0})
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    # Guard: super-admin emails can never be demoted.
    if _is_super_admin(target.get("email")) and new_role not in ("Admin", "SuperAdmin"):
        raise HTTPException(status_code=400,
                            detail="This account is a protected super-admin and cannot be demoted.")
    # Guard: never allow the last admin to demote themselves.
    if _normalize_role(target.get("role")) == "Admin" and new_role != "Admin":
        admin_count = 0
        # Count admins within the SAME org only — other tenants' admins
        # can't administer this workspace.
        _t_org = target.get("org_id")
        async for u in db.users.find({"org_id": _t_org} if _t_org else {}, {"_id": 0, "role": 1}):
            if _normalize_role(u.get("role")) == "Admin":
                admin_count += 1
        if admin_count <= 1:
            raise HTTPException(status_code=400,
                                detail="Cannot demote the last Admin")
    await db.users.update_one(
        {"user_id": user_id},
        {"$set": {"role": new_role, "role_updated_at": iso(now_utc()),
                  "role_updated_by": actor.get("user_id")}}
    )
    updated = await db.users.find_one({"user_id": user_id}, {"_id": 0})
    return _user_with_perms(updated)


# ============================================================
# Dashboard
# ============================================================
@api.get("/dashboard/stats")
async def dashboard_stats(request: Request, session_token: Optional[str] = Cookie(default=None),
                          authorization: Optional[str] = Header(default=None)):
    await require_user(request, session_token, authorization)

    active_projects = await sdb.projects.count_documents({"stage": {"$nin": ["Handover"]}})
    total_projects = await sdb.projects.count_documents({})

    # Revenue: sum from ACCOUNTING journal entries (income line credits) — single source
    # of truth. Falls back to zero if no journal exists yet. This matches the P&L report.
    revenue = 0.0
    async for je in sdb.journal_entries.find({}, {"_id": 0, "lines": 1}):
        for l in je.get("lines", []):
            if l.get("account_type") == "income":
                revenue += float(l.get("credit", 0)) - float(l.get("debit", 0))
    revenue = round(revenue, 2)

    # Collection due: sum of sent+overdue
    due_cursor = sdb.invoices.find({"status": {"$in": ["sent", "overdue"]}, "doc_type": "invoice"}, {"_id": 0})
    collection_due = 0.0
    async for inv in due_cursor:
        collection_due += float(inv.get("total", 0))

    # Overdue tasks
    today = now_utc().date().isoformat()
    overdue_tasks = await sdb.tasks.count_documents({
        "status": {"$ne": "done"},
        "due_date": {"$lt": today, "$ne": None}
    })

    # Pipeline funnel
    pipeline = []
    for stage in PIPELINE_STAGES:
        count = await sdb.leads.count_documents({"stage": stage})
        pipeline.append({"stage": stage, "count": count})

    # Lead sources
    sources = {}
    async for lead in sdb.leads.find({}, {"_id": 0, "source": 1}):
        s = lead.get("source", "Other")
        sources[s] = sources.get(s, 0) + 1
    source_list = [{"source": k, "count": v} for k, v in sources.items()]

    # Alerts
    alerts = []
    if overdue_tasks > 0:
        alerts.append({"level": "high", "message": f"{overdue_tasks} tasks overdue"})
    if collection_due > 0:
        alerts.append({"level": "medium", "message": f"₹{collection_due:,.0f} pending collection"})

    # Team utilization — real signal: weighted open tasks (urgent=3, high=2, medium=1, low=1)
    # per active employee. Not a percentage — a workload index the studio owner can eyeball.
    weight = {"urgent": 3, "critical": 3, "high": 2, "medium": 1, "low": 1}
    util = {}
    async for t in sdb.tasks.find({"status": {"$ne": "done"}},
                                 {"_id": 0, "assignee_name": 1, "priority": 1}):
        n = t.get("assignee_name") or "Unassigned"
        util[n] = util.get(n, 0) + weight.get((t.get("priority") or "medium").lower(), 1)
    utilization = sorted(
        [{"name": k, "load": v} for k, v in util.items()],
        key=lambda x: -x["load"],
    )

    return {
        "kpis": {
            "revenue": revenue,
            "active_projects": active_projects,
            "total_projects": total_projects,
            "overdue_tasks": overdue_tasks,
            "collection_due": collection_due,
        },
        "pipeline": pipeline,
        "sources": source_list,
        "alerts": alerts,
        "utilization": utilization,
    }


# ============================================================
# Leads (CRM)
# ============================================================
@api.get("/leads")
async def list_leads(request: Request, session_token: Optional[str] = Cookie(default=None),
                     authorization: Optional[str] = Header(default=None)):
    await require_user(request, session_token, authorization)
    leads = await sdb.leads.find({"archived": {"$ne": True}}, {"_id": 0}).sort("created_at", -1).to_list(1000)
    return leads


@api.post("/leads")
async def create_lead(payload: LeadIn, request: Request,
                      session_token: Optional[str] = Cookie(default=None),
                      authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    lead = payload.model_dump()
    lead["id"] = new_id("lead_")
    lead["created_at"] = iso(now_utc())
    lead["created_by"] = user["user_id"]
    lead["timeline"] = []
    await sdb.leads.insert_one(dict(lead))
    return await sdb.leads.find_one({"id": lead["id"]}, {"_id": 0})


@api.patch("/leads/{lead_id}")
async def update_lead(lead_id: str, payload: LeadUpdate, request: Request,
                      session_token: Optional[str] = Cookie(default=None),
                      authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    if not has_permission(user, "leads.update"):
        raise HTTPException(status_code=403, detail="Missing permission: leads.update")
    upd = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not upd:
        raise HTTPException(status_code=400, detail="Nothing to update")
    upd["updated_at"] = iso(now_utc())
    res = await sdb.leads.update_one(
        {"id": lead_id},
        {"$set": upd,
         "$push": {"timeline": {"event": "edited", "by": user.get("name"), "at": iso(now_utc())}}}
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Lead not found")
    return await sdb.leads.find_one({"id": lead_id}, {"_id": 0})


@api.patch("/leads/{lead_id}/stage")
async def update_lead_stage(lead_id: str, payload: LeadStageUpdate, request: Request,
                             session_token: Optional[str] = Cookie(default=None),
                             authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    from routes.master_data import get_values as _md_values
    valid_stages = await _md_values(user.get("org_id") or "org_default", "lead_stage", PIPELINE_STAGES)
    if payload.stage not in valid_stages and payload.stage not in PIPELINE_STAGES:
        raise HTTPException(status_code=400, detail="Invalid stage")
    res = await sdb.leads.update_one(
        {"id": lead_id},
        {"$set": {"stage": payload.stage, "updated_at": iso(now_utc())},
         "$push": {"timeline": {"event": "stage_change", "to": payload.stage, "at": iso(now_utc())}}}
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Lead not found")
    return await sdb.leads.find_one({"id": lead_id}, {"_id": 0})


@api.delete("/leads/{lead_id}")
async def delete_lead(lead_id: str, request: Request,
                      session_token: Optional[str] = Cookie(default=None),
                      authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    if not has_permission(user, "leads.delete"):
        raise HTTPException(status_code=403, detail="Missing permission: leads.delete")
    await sdb.leads.delete_one({"id": lead_id})
    return {"ok": True}


@api.post("/leads/{lead_id}/convert")
async def convert_lead_to_project(lead_id: str, request: Request,
                                   session_token: Optional[str] = Cookie(default=None),
                                   authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    lead = await sdb.leads.find_one({"id": lead_id}, {"_id": 0})
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    # create client
    client_id = new_id("cli_")
    client_doc = {
        "id": client_id,
        "name": lead.get("name"),
        "email": lead.get("email"),
        "phone": lead.get("phone"),
        "company": None,
        "address": lead.get("location"),
        "created_at": iso(now_utc()),
    }
    await sdb.clients.insert_one(dict(client_doc))

    project_id = new_id("prj_")
    project = {
        "id": project_id,
        "name": f"{lead.get('name')} - {lead.get('project_type', 'Project')}",
        "client_id": client_id,
        "client_name": lead.get("name"),
        "project_type": lead.get("project_type", "Residential"),
        "budget": lead.get("budget", 0),
        "stage": "Requirement",
        "share_token": new_id(),
        "created_at": iso(now_utc()),
        "created_by": user["user_id"],
    }
    await sdb.projects.insert_one(dict(project))
    await sdb.leads.update_one({"id": lead_id}, {"$set": {"stage": "Won", "converted_project_id": project_id}})
    await audit_log(user, "lead.convert", target=lead_id, target_type="lead",
                    meta={"project_id": project_id, "client_id": client_id})
    await audit_log(user, "project.create", target=project_id, target_type="project",
                    meta={"name": project.get("name"), "from_lead": lead_id})
    return {"project_id": project_id, "client_id": client_id}


# ============================================================
# Clients
# ============================================================
@api.get("/clients")
async def list_clients(request: Request, include_archived: bool = False,
                       session_token: Optional[str] = Cookie(default=None),
                       authorization: Optional[str] = Header(default=None)):
    await require_user(request, session_token, authorization)
    q = {} if include_archived else {"archived": {"$ne": True}}
    rows = await sdb.clients.find(q, {"_id": 0}).sort("created_at", -1).to_list(500)
    return rows


@api.post("/clients")
async def create_client(payload: ClientIn, request: Request,
                        session_token: Optional[str] = Cookie(default=None),
                        authorization: Optional[str] = Header(default=None)):
    await require_user(request, session_token, authorization)
    doc = payload.model_dump()
    doc["id"] = new_id("cli_")
    doc["created_at"] = iso(now_utc())
    await sdb.clients.insert_one(dict(doc))
    return await sdb.clients.find_one({"id": doc["id"]}, {"_id": 0})


@api.get("/clients/{client_id}")
async def get_client(client_id: str, request: Request,
                     session_token: Optional[str] = Cookie(default=None),
                     authorization: Optional[str] = Header(default=None)):
    await require_user(request, session_token, authorization)
    c = await sdb.clients.find_one({"id": client_id}, {"_id": 0})
    if not c:
        raise HTTPException(status_code=404, detail="Client not found")
    c["projects"] = await sdb.projects.find(
        {"client_id": client_id, "archived": {"$ne": True}}, {"_id": 0}).sort("created_at", -1).to_list(200)
    c["invoices"] = await sdb.invoices.find(
        {"client_id": client_id}, {"_id": 0}).sort("created_at", -1).to_list(200)
    invoiced = sum(i.get("total", 0) or 0 for i in c["invoices"] if i.get("doc_type") != "quotation")
    paid = sum(i.get("total", 0) or 0 for i in c["invoices"]
               if i.get("doc_type") != "quotation" and i.get("status") == "paid")
    c["summary"] = {
        "projects": len(c["projects"]),
        "total_invoiced": round(invoiced, 2),
        "total_paid": round(paid, 2),
        "outstanding": round(invoiced - paid, 2),
    }
    return c


@api.patch("/clients/{client_id}")
async def update_client(client_id: str, payload: ClientUpdate, request: Request,
                        session_token: Optional[str] = Cookie(default=None),
                        authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    if not has_permission(user, "clients.update"):
        raise HTTPException(status_code=403, detail="Missing permission: clients.update")
    upd = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not upd:
        raise HTTPException(status_code=400, detail="Nothing to update")
    upd["updated_at"] = iso(now_utc())
    res = await sdb.clients.update_one({"id": client_id}, {"$set": upd})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Client not found")
    # keep denormalised client_name in sync
    if upd.get("name"):
        await sdb.projects.update_many({"client_id": client_id}, {"$set": {"client_name": upd["name"]}})
        await sdb.invoices.update_many({"client_id": client_id}, {"$set": {"client_name": upd["name"]}})
    await audit_log(user, "client.update", target=client_id, target_type="client",
                    meta={"fields": [k for k in upd if k != "updated_at"]})
    return await sdb.clients.find_one({"id": client_id}, {"_id": 0})


@api.post("/clients/{client_id}/archive")
async def archive_client(client_id: str, request: Request,
                         session_token: Optional[str] = Cookie(default=None),
                         authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    if not has_permission(user, "clients.update"):
        raise HTTPException(status_code=403, detail="Missing permission: clients.update")
    res = await sdb.clients.update_one(
        {"id": client_id},
        {"$set": {"archived": True, "archived_at": iso(now_utc()), "archived_by": user.get("name")}})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Client not found")
    await audit_log(user, "client.archive", target=client_id, target_type="client")
    return {"ok": True, "archived": True}


@api.post("/clients/{client_id}/restore")
async def restore_client(client_id: str, request: Request,
                         session_token: Optional[str] = Cookie(default=None),
                         authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    if not has_permission(user, "clients.update"):
        raise HTTPException(status_code=403, detail="Missing permission: clients.update")
    res = await sdb.clients.update_one(
        {"id": client_id}, {"$set": {"archived": False}, "$unset": {"archived_at": "", "archived_by": ""}})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Client not found")
    return {"ok": True, "archived": False}


@api.delete("/clients/{client_id}")
async def delete_client(client_id: str, request: Request,
                        session_token: Optional[str] = Cookie(default=None),
                        authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    if not has_permission(user, "clients.delete"):
        raise HTTPException(status_code=403, detail="Missing permission: clients.delete")
    n_projects = await sdb.projects.count_documents({"client_id": client_id})
    n_invoices = await sdb.invoices.count_documents({"client_id": client_id})
    if n_projects or n_invoices:
        raise HTTPException(
            status_code=409,
            detail=f"Client has {n_projects} project(s) and {n_invoices} invoice(s). Archive it instead.")
    await sdb.clients.delete_one({"id": client_id})
    return {"ok": True}


# ============================================================
# Projects
# ============================================================
@api.get("/projects")
async def list_projects(request: Request, include_archived: bool = False,
                        session_token: Optional[str] = Cookie(default=None),
                        authorization: Optional[str] = Header(default=None)):
    await require_user(request, session_token, authorization)
    q = {} if include_archived else {"archived": {"$ne": True}}
    projects = await sdb.projects.find(q, {"_id": 0}).sort("created_at", -1).to_list(500)
    return projects


@api.post("/projects")
async def create_project(payload: ProjectIn, request: Request,
                         session_token: Optional[str] = Cookie(default=None),
                         authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    # Plan limit — max projects per tenant
    _org_id = user.get("org_id")
    if _org_id:
        _org = await db.organizations.find_one({"org_id": _org_id}, {"_id": 0, "features": 1})
        _max = ((_org or {}).get("features") or {}).get("limits", {}).get("max_projects")
        if _max:
            _current = await sdb.projects.count_documents({})
            if _current >= _max:
                raise HTTPException(status_code=402,
                                    detail=f"Project limit reached ({_current}/{_max}). Upgrade your plan.")
    doc = payload.model_dump()
    # Resolve engagement_type from the org's business_mode:
    #   consultancy → forced "consultancy"
    #   turnkey     → forced "turnkey"
    #   hybrid      → must be provided by the user
    org = await db.organizations.find_one({"org_id": user.get("org_id") or "org_default"},
                                          {"_id": 0, "business_mode": 1})
    mode = (org or {}).get("business_mode") or "hybrid"
    et = (doc.get("engagement_type") or "").strip().lower() or None
    if mode == "consultancy":
        doc["engagement_type"] = "consultancy"
    elif mode == "turnkey":
        doc["engagement_type"] = "turnkey"
    else:  # hybrid
        if et not in ("consultancy", "turnkey"):
            raise HTTPException(
                status_code=400,
                detail="Project engagement_type is required (consultancy | turnkey) for hybrid workspaces.",
            )
        doc["engagement_type"] = et
    doc["id"] = new_id("prj_")
    doc["share_token"] = new_id()
    doc["created_at"] = iso(now_utc())
    doc["created_by"] = user["user_id"]
    if doc.get("client_id"):
        c = await sdb.clients.find_one({"id": doc["client_id"]}, {"_id": 0})
        if c:
            doc["client_name"] = c.get("name")
    await sdb.projects.insert_one(dict(doc))
    await audit_log(user, "project.create", target=doc["id"], target_type="project",
                    meta={"name": doc.get("name")})
    return await sdb.projects.find_one({"id": doc["id"]}, {"_id": 0})


@api.get("/projects/{project_id}")
async def get_project(project_id: str, request: Request,
                      session_token: Optional[str] = Cookie(default=None),
                      authorization: Optional[str] = Header(default=None)):
    await require_user(request, session_token, authorization)
    p = await sdb.projects.find_one({"id": project_id}, {"_id": 0})
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")
    p["tasks"] = await sdb.tasks.find({"project_id": project_id}, {"_id": 0}).to_list(500)
    p["files"] = await sdb.files.find({"project_id": project_id}, {"_id": 0}).to_list(500)
    p["invoices"] = await sdb.invoices.find({"project_id": project_id}, {"_id": 0}).to_list(500)
    p["milestones"] = await sdb.milestones.find({"project_id": project_id}, {"_id": 0}).to_list(200)
    # --- connected records: vendors / purchase orders / bills ---
    p["purchase_orders"] = await sdb.purchase_orders.find(
        {"project_id": project_id}, {"_id": 0}).sort("created_at", -1).to_list(100)
    p["vendor_bills"] = await sdb.vendor_bills.find(
        {"project_id": project_id}, {"_id": 0}).sort("created_at", -1).to_list(100)
    # --- team enrichment ---
    team_ids = [i for i in (p.get("team_ids") or []) if i]
    pm_id = p.get("project_manager_id")
    lookup_ids = list({*team_ids, *( [pm_id] if pm_id else [] )})
    if lookup_ids:
        emps = await sdb.employees.find({"id": {"$in": lookup_ids}},
                                        {"_id": 0, "id": 1, "name": 1, "designation": 1,
                                         "department": 1, "employee_id": 1}).to_list(50)
        emap = {e["id"]: e for e in emps}
        p["project_manager"] = emap.get(pm_id)
        p["team"] = [emap[i] for i in team_ids if i in emap]
    else:
        p["project_manager"] = None
        p["team"] = []
    # --- financial snapshot (invoices + milestones + vendor cost) ---
    inv_total = sum(i.get("total", 0) or 0 for i in p["invoices"] if i.get("doc_type") != "quotation")
    inv_paid = sum(i.get("total", 0) or 0 for i in p["invoices"]
                   if i.get("doc_type") != "quotation" and i.get("status") == "paid")
    ms_total = sum(m.get("amount", 0) or 0 for m in p["milestones"])
    ms_paid = sum(m.get("amount", 0) or 0 for m in p["milestones"] if m.get("status") == "paid")
    vendor_cost = sum(b.get("total", 0) or 0 for b in p["vendor_bills"]
                      if b.get("status") not in ("cancelled", "draft"))
    p["financials"] = {
        "budget": p.get("budget", 0) or 0,
        "invoiced": round(inv_total, 2),
        "collected": round(inv_paid, 2),
        "outstanding": round(inv_total - inv_paid, 2),
        "milestones_value": round(ms_total, 2),
        "milestones_collected": round(ms_paid, 2),
        "vendor_cost": round(vendor_cost, 2),
    }
    return p


@api.patch("/projects/{project_id}/stage")
async def update_project_stage(project_id: str, payload: ProjectStageUpdate, request: Request,
                                session_token: Optional[str] = Cookie(default=None),
                                authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    from routes.master_data import get_values as _md_values
    valid_stages = await _md_values(user.get("org_id") or "org_default", "project_stage", PROJECT_STAGES)
    if payload.stage not in valid_stages and payload.stage not in PROJECT_STAGES:
        raise HTTPException(status_code=400, detail="Invalid stage")
    await sdb.projects.update_one({"id": project_id}, {"$set": {"stage": payload.stage, "updated_at": iso(now_utc())}})
    await audit_log(user, "project.stage_change", target=project_id, target_type="project",
                    meta={"stage": payload.stage})
    return await sdb.projects.find_one({"id": project_id}, {"_id": 0})


@api.delete("/projects/{project_id}")
async def delete_project(project_id: str, request: Request,
                         session_token: Optional[str] = Cookie(default=None),
                         authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    if not has_permission(user, "projects.delete"):
        raise HTTPException(status_code=403, detail="Missing permission: projects.delete")
    n_inv = await sdb.invoices.count_documents({"project_id": project_id})
    n_ms = await sdb.milestones.count_documents({"project_id": project_id, "status": "paid"})
    if n_inv or n_ms:
        raise HTTPException(
            status_code=409,
            detail=f"Project has {n_inv} invoice(s) / {n_ms} paid milestone(s). Archive it instead to preserve financial history.")
    await sdb.projects.delete_one({"id": project_id})
    await sdb.tasks.delete_many({"project_id": project_id})
    return {"ok": True}


@api.patch("/projects/{project_id}")
async def update_project(project_id: str, payload: ProjectUpdate, request: Request,
                         session_token: Optional[str] = Cookie(default=None),
                         authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    if not has_permission(user, "projects.update"):
        raise HTTPException(status_code=403, detail="Missing permission: projects.update")
    upd = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not upd:
        raise HTTPException(status_code=400, detail="Nothing to update")
    if upd.get("engagement_type") and upd["engagement_type"] not in ("consultancy", "turnkey"):
        raise HTTPException(status_code=400, detail="engagement_type must be consultancy | turnkey")
    if upd.get("client_id"):
        c = await sdb.clients.find_one({"id": upd["client_id"]}, {"_id": 0})
        if not c:
            raise HTTPException(status_code=404, detail="Client not found")
        upd["client_name"] = c.get("name")
    upd["updated_at"] = iso(now_utc())
    res = await sdb.projects.update_one({"id": project_id}, {"$set": upd})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Project not found")
    await audit_log(user, "project.update", target=project_id, target_type="project",
                    meta={"fields": [k for k in upd if k != "updated_at"]})
    return await sdb.projects.find_one({"id": project_id}, {"_id": 0})


@api.post("/projects/{project_id}/archive")
async def archive_project(project_id: str, request: Request,
                          session_token: Optional[str] = Cookie(default=None),
                          authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    if not has_permission(user, "projects.update"):
        raise HTTPException(status_code=403, detail="Missing permission: projects.update")
    res = await sdb.projects.update_one(
        {"id": project_id},
        {"$set": {"archived": True, "archived_at": iso(now_utc()), "archived_by": user.get("name")}})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Project not found")
    await audit_log(user, "project.archive", target=project_id, target_type="project")
    return {"ok": True, "archived": True}


@api.post("/projects/{project_id}/restore")
async def restore_project(project_id: str, request: Request,
                          session_token: Optional[str] = Cookie(default=None),
                          authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    if not has_permission(user, "projects.update"):
        raise HTTPException(status_code=403, detail="Missing permission: projects.update")
    res = await sdb.projects.update_one(
        {"id": project_id}, {"$set": {"archived": False}, "$unset": {"archived_at": "", "archived_by": ""}})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Project not found")
    await audit_log(user, "project.restore", target=project_id, target_type="project")
    return {"ok": True, "archived": False}


# ============================================================
# Tasks
# ============================================================
# Tasks module routes are now provided by routes/tasks.py (extended: employee/vendor,
# follow-ups, timeline audit, bulk update, project-scoped areas/categories, reminders).


# ============================================================
# Files
# ============================================================
@api.get("/files")
async def list_files(request: Request, project_id: Optional[str] = None,
                     session_token: Optional[str] = Cookie(default=None),
                     authorization: Optional[str] = Header(default=None)):
    await require_user(request, session_token, authorization)
    q = {}
    if project_id:
        q["project_id"] = project_id
    return await sdb.files.find(q, {"_id": 0}).sort("created_at", -1).to_list(500)


@api.post("/files")
async def create_file(payload: FileIn, request: Request,
                      session_token: Optional[str] = Cookie(default=None),
                      authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    doc = payload.model_dump()
    doc["id"] = new_id("fil_")
    doc["created_at"] = iso(now_utc())
    doc["created_by"] = user["user_id"]
    doc["uploader_name"] = user["name"]
    await sdb.files.insert_one(dict(doc))
    return await sdb.files.find_one({"id": doc["id"]}, {"_id": 0})


@api.delete("/files/{file_id}")
async def delete_file(file_id: str, request: Request,
                      session_token: Optional[str] = Cookie(default=None),
                      authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    f = await sdb.files.find_one({"id": file_id}, {"_id": 0})
    if not f:
        raise HTTPException(status_code=404, detail="File not found")
    # uploader can remove their own file; otherwise needs files.delete
    if f.get("created_by") != user.get("user_id") and not has_permission(user, "files.delete"):
        raise HTTPException(status_code=403, detail="Missing permission: files.delete")
    await sdb.files.delete_one({"id": file_id})
    return {"ok": True}


# ============================================================
# Invoices + Quotations
# ============================================================
def compute_invoice_totals(doc: dict) -> dict:
    items = doc.get("items", []) or []
    subtotal = 0.0
    for it in items:
        amt = float(it.get("quantity", 1)) * float(it.get("rate", 0))
        it["amount"] = round(amt, 2)
        subtotal += amt
    tax_rate = float(doc.get("tax_rate", 0) or 0)
    tax = round(subtotal * tax_rate / 100.0, 2)
    total = round(subtotal + tax, 2)
    doc["subtotal"] = round(subtotal, 2)
    doc["tax"] = tax
    doc["total"] = total
    return doc


@api.get("/invoices")
async def list_invoices(request: Request, doc_type: Optional[str] = None,
                        session_token: Optional[str] = Cookie(default=None),
                        authorization: Optional[str] = Header(default=None)):
    await require_user(request, session_token, authorization)
    q = {}
    if doc_type:
        q["doc_type"] = doc_type
    return await sdb.invoices.find(q, {"_id": 0}).sort("created_at", -1).to_list(500)


@api.post("/invoices")
async def create_invoice(payload: InvoiceIn, request: Request,
                         session_token: Optional[str] = Cookie(default=None),
                         authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    doc = payload.model_dump()
    doc["id"] = new_id("inv_")
    # number
    prefix = "QUO" if doc.get("doc_type") == "quotation" else "INV"
    count = await sdb.invoices.count_documents({"doc_type": doc.get("doc_type", "invoice")})
    doc["number"] = f"{prefix}-{1000 + count + 1}"
    doc["created_at"] = iso(now_utc())
    doc["issue_date"] = now_utc().date().isoformat()
    doc["created_by"] = user["user_id"]
    if doc.get("client_id") and not doc.get("client_name"):
        c = await sdb.clients.find_one({"id": doc["client_id"]}, {"_id": 0})
        if c:
            doc["client_name"] = c.get("name")
    if doc.get("project_id") and not doc.get("project_name"):
        p = await sdb.projects.find_one({"id": doc["project_id"]}, {"_id": 0})
        if p:
            doc["project_name"] = p.get("name")
    doc = compute_invoice_totals(doc)
    if doc.get("status") == "paid" and doc.get("doc_type", "invoice") == "invoice":
        doc["paid_date"] = now_utc().date().isoformat()
    await sdb.invoices.insert_one(dict(doc))
    # Invoice created directly as paid → post the receipt JE so the books match.
    if doc.get("status") == "paid" and doc.get("doc_type", "invoice") == "invoice" \
            and float(doc.get("total") or 0) > 0:
        from routes.accounting import post_receipt_je
        je = await post_receipt_je(
            user, amount=float(doc["total"]), date=doc["paid_date"],
            narration=f"Invoice {doc.get('number')} payment received"
                      + (f" · {doc.get('client_name')}" if doc.get("client_name") else ""),
            source="invoice_payment", source_id=doc["id"],
            reference=doc.get("number"),
            project_id=doc.get("project_id"), client_id=doc.get("client_id"))
        if je:
            await sdb.invoices.update_one({"id": doc["id"]},
                                          {"$set": {"journal_id": je["id"]}})
    return await sdb.invoices.find_one({"id": doc["id"]}, {"_id": 0})


@api.get("/invoices/{invoice_id}")
async def get_invoice(invoice_id: str, request: Request,
                      session_token: Optional[str] = Cookie(default=None),
                      authorization: Optional[str] = Header(default=None)):
    await require_user(request, session_token, authorization)
    doc = await sdb.invoices.find_one({"id": invoice_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Not found")
    return doc


@api.patch("/invoices/{invoice_id}")
async def update_invoice(invoice_id: str, payload: InvoiceUpdate, request: Request,
                         session_token: Optional[str] = Cookie(default=None),
                         authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    if not has_permission(user, "invoices.update"):
        raise HTTPException(status_code=403, detail="Missing permission: invoices.update")
    doc = await sdb.invoices.find_one({"id": invoice_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Not found")
    if doc.get("status") == "paid":
        raise HTTPException(status_code=409, detail="Paid invoices cannot be edited")
    upd = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not upd:
        raise HTTPException(status_code=400, detail="Nothing to update")
    if "items" in upd:
        upd["items"] = [i if isinstance(i, dict) else i for i in upd["items"]]
    if upd.get("client_id"):
        c = await sdb.clients.find_one({"id": upd["client_id"]}, {"_id": 0})
        if c:
            upd["client_name"] = c.get("name")
    if upd.get("project_id"):
        p = await sdb.projects.find_one({"id": upd["project_id"]}, {"_id": 0})
        if p:
            upd["project_name"] = p.get("name")
    merged = {**doc, **upd}
    merged = compute_invoice_totals(merged)
    merged["updated_at"] = iso(now_utc())
    merged.pop("_id", None)
    await sdb.invoices.update_one({"id": invoice_id}, {"$set": {
        k: merged[k] for k in
    ("client_id", "client_name", "project_id", "project_name", "items",
         "tax_rate", "notes", "due_date", "subtotal", "tax", "total", "updated_at")
        if k in merged
    }})
    return await sdb.invoices.find_one({"id": invoice_id}, {"_id": 0})


@api.patch("/invoices/{invoice_id}/status")
async def update_invoice_status(invoice_id: str, payload: InvoiceStatusUpdate, request: Request,
                                 session_token: Optional[str] = Cookie(default=None),
                                 authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    if not has_permission(user, "invoices.update"):
        raise HTTPException(status_code=403, detail="Missing permission: invoices.update")
    if payload.status not in INVOICE_STATUSES:
        raise HTTPException(status_code=400, detail="Invalid status")
    inv = await sdb.invoices.find_one({"id": invoice_id}, {"_id": 0})
    if not inv:
        raise HTTPException(status_code=404, detail="Not found")
    upd = {"status": payload.status, "updated_at": iso(now_utc())}

    # --- Accounting is the source of truth: keep books in sync ---
    from routes.accounting import post_receipt_je, reverse_receipt_je
    if payload.status == "paid" and inv.get("status") != "paid" \
            and inv.get("doc_type", "invoice") == "invoice":
        upd["paid_date"] = now_utc().date().isoformat()
        amount = float(inv.get("total") or 0)
        if amount > 0:
            je = await post_receipt_je(
                user, amount=amount, date=upd["paid_date"],
                narration=f"Invoice {inv.get('number') or invoice_id} payment received"
                          + (f" · {inv.get('client_name')}" if inv.get("client_name") else ""),
                source="invoice_payment", source_id=invoice_id,
                reference=inv.get("number"),
                project_id=inv.get("project_id"), client_id=inv.get("client_id"))
            if je:
                upd["journal_id"] = je["id"]
    elif inv.get("status") == "paid" and payload.status != "paid" \
            and inv.get("doc_type", "invoice") == "invoice":
        await reverse_receipt_je(
            user, source="invoice_payment", source_id=invoice_id,
            narration=f"Invoice {inv.get('number') or invoice_id} payment reversed")
        upd["paid_date"] = None
        upd["journal_id"] = None

    await sdb.invoices.update_one({"id": invoice_id}, {"$set": upd})
    return await sdb.invoices.find_one({"id": invoice_id}, {"_id": 0})


@api.delete("/invoices/{invoice_id}")
async def delete_invoice(invoice_id: str, request: Request,
                         session_token: Optional[str] = Cookie(default=None),
                         authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    if not has_permission(user, "invoices.delete"):
        raise HTTPException(status_code=403, detail="Missing permission: invoices.delete")
    await sdb.invoices.delete_one({"id": invoice_id})
    return {"ok": True}


def _safe(s) -> str:
    """Sanitize text to latin-1 compatible for FPDF Helvetica."""
    if s is None:
        return ""
    s = str(s)
    replacements = {
        "\u2013": "-", "\u2014": "-", "\u2018": "'", "\u2019": "'",
        "\u201C": '"', "\u201D": '"', "\u2022": "*", "\u2026": "...",
        "\u20B9": "Rs.", "\u2122": "TM", "\u00A9": "(c)",
    }
    for k, v in replacements.items():
        s = s.replace(k, v)
    return s.encode("latin-1", "replace").decode("latin-1")


def _hex_to_rgb(h: str):
    """Parse '#RRGGBB' → (r, g, b) tuple. Defaults to Klein Blue."""
    try:
        h = (h or "").lstrip("#")
        if len(h) == 3:
            h = "".join(c * 2 for c in h)
        return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    except Exception:
        return 0, 47, 167


def _inr(n) -> str:
    """Indian digit grouping: 1234567.5 → 'Rs. 12,34,567.50'."""
    try:
        n = float(n or 0)
    except (TypeError, ValueError):
        n = 0.0
    neg = n < 0
    paise = int(round(abs(n) * 100))
    rupees, p = divmod(paise, 100)
    s = str(rupees)
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        s = ",".join(parts + [tail])
    return ("-" if neg else "") + f"Rs. {s}.{p:02d}"


_ONES = ["", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine", "Ten",
         "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen", "Sixteen", "Seventeen",
         "Eighteen", "Nineteen"]
_TENS = ["", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety"]


def _two_words(n: int) -> str:
    if n < 20:
        return _ONES[n]
    return (_TENS[n // 10] + (" " + _ONES[n % 10] if n % 10 else "")).strip()


def _three_words(n: int) -> str:
    out = ""
    if n >= 100:
        out = _ONES[n // 100] + " Hundred"
        if n % 100:
            out += " " + _two_words(n % 100)
        return out
    return _two_words(n)


def _amount_in_words_inr(amount) -> str:
    """Indian numbering system: crore / lakh / thousand. Returns e.g.
    'Rupees Twelve Lakh Thirty-Four Thousand Five Hundred Sixty-Seven and Fifty Paise Only'."""
    try:
        amount = float(amount or 0)
    except (TypeError, ValueError):
        amount = 0.0
    paise_total = int(round(abs(amount) * 100))
    rupees, paise = divmod(paise_total, 100)
    if rupees == 0 and paise == 0:
        return "Rupees Zero Only"
    parts = []
    crore, rem = divmod(rupees, 10_000_000)
    lakh, rem = divmod(rem, 100_000)
    thousand, hundreds = divmod(rem, 1000)
    if crore:
        parts.append(_two_words(crore % 100) if crore < 100 else _three_words(crore))
        parts.append("Crore")
    if lakh:
        parts.append(_two_words(lakh))
        parts.append("Lakh")
    if thousand:
        parts.append(_two_words(thousand))
        parts.append("Thousand")
    if hundreds:
        parts.append(_three_words(hundreds))
    words = "Rupees " + " ".join(p for p in parts if p) if rupees else "Rupees Zero"
    if paise:
        words += f" and {_two_words(paise)} Paise"
    return words.strip() + " Only"


def _org_logo_bytes(org: Optional[dict]):
    """Best-effort fetch of the org logo bytes from object storage.
    Returns (bytes, ext) or (None, None)."""
    try:
        branding = (org or {}).get("branding") or {}
        url = branding.get("logo_url") or ""
        if not url:
            return None, None
        if url.startswith("data:"):
            import base64
            head, _, b64 = url.partition(",")
            ext = "png" if "png" in head else "jpg"
            return base64.b64decode(b64), ext
        marker = "/api/org/logo/"
        if marker in url:
            path = url.split(marker, 1)[1]
            from services import storage as _pdf_storage
            data, ctype = _pdf_storage.get_object(path)
            ext = "png" if "png" in (ctype or "") else "jpg"
            return data, ext
    except Exception:
        pass
    return None, None


def generate_invoice_pdf(doc: dict, org: Optional[dict] = None) -> bytes:
    """Corporate invoice/quotation PDF — branded header, itemised table,
    Indian currency formatting, amount-in-words, bank details, terms."""
    pdf = FPDF(format="A4", unit="mm")
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.add_page()

    org = org or {}
    branding = org.get("branding") or {}
    primary = _hex_to_rgb(branding.get("primary_color") or "#002FA7")
    ink = (16, 16, 16)
    grey = (105, 105, 105)
    line = (222, 222, 222)
    soft = (247, 248, 250)

    org_name = org.get("display_name") or org.get("name") or "Design Saga"
    tagline = branding.get("tagline") or "Architecture & Interior Design Studio"
    addr = org.get("address") or {}
    addr_bits = [addr.get("line1"), addr.get("line2"),
                 ", ".join(x for x in [addr.get("city"), addr.get("state")] if x),
                 addr.get("pincode")]
    addr_line = " · ".join(str(x) for x in addr_bits if x)
    contact_bits = [org.get("phone"), org.get("email"), org.get("website")]
    contact_line = " · ".join(str(x) for x in contact_bits if x)
    footer_note = branding.get("pdf_footer") or f"Thank you for choosing {org_name}."
    is_quote = doc.get("doc_type") == "quotation"
    title = "QUOTATION" if is_quote else "INVOICE"

    # ---- Brand bar ----
    pdf.set_fill_color(*primary)
    pdf.rect(0, 0, 210, 3, "F")

    # ---- Header: logo + company (left) / doc title + meta (right) ----
    top_y = 12.0
    logo_bytes, logo_ext = _org_logo_bytes(org)
    text_x = 15.0
    if logo_bytes:
        try:
            pdf.image(io.BytesIO(logo_bytes), x=15, y=top_y, h=14,
                      type="PNG" if logo_ext == "png" else "JPEG")
            text_x = 34.0
        except Exception:
            text_x = 15.0

    pdf.set_xy(text_x, top_y)
    pdf.set_font("Helvetica", "B", 15)
    pdf.set_text_color(*ink)
    pdf.cell(110, 7, _safe(org_name.upper()), ln=1)
    pdf.set_x(text_x)
    pdf.set_font("Helvetica", "", 8.5)
    pdf.set_text_color(*grey)
    pdf.cell(110, 4.5, _safe(tagline), ln=1)
    if addr_line:
        pdf.set_x(text_x)
        pdf.cell(110, 4.5, _safe(addr_line), ln=1)
    if contact_line:
        pdf.set_x(text_x)
        pdf.cell(110, 4.5, _safe(contact_line), ln=1)
    if org.get("gstin"):
        pdf.set_x(text_x)
        pdf.cell(110, 4.5, _safe(f"GSTIN: {org['gstin']}"), ln=1)

    # Right block — title + meta
    pdf.set_xy(130, top_y)
    pdf.set_font("Helvetica", "B", 24)
    pdf.set_text_color(*primary)
    pdf.cell(65, 10, _safe(title), 0, 1, "R")
    meta_rows = [
        ("No.", doc.get("number") or "—"),
        ("Date", (doc.get("created_at") or "")[:10]),
    ]
    if doc.get("due_date"):
        meta_rows.append(("Due Date", doc.get("due_date")[:10]))
    status = (doc.get("status") or "").upper()
    if status:
        meta_rows.append(("Status", status))
    pdf.set_font("Helvetica", "", 9)
    for label, val in meta_rows:
        pdf.set_x(130)
        pdf.set_text_color(*grey)
        pdf.cell(25, 5, _safe(label), 0, 0, "L")
        pdf.set_text_color(*ink)
        pdf.set_font("Helvetica", "B", 9)
        pdf.cell(40, 5, _safe(str(val)), 0, 1, "R")
        pdf.set_font("Helvetica", "", 9)

    y = max(pdf.get_y(), top_y + 26) + 4
    pdf.set_draw_color(*line)
    pdf.set_line_width(0.3)
    pdf.line(15, y, 195, y)

    # ---- Bill To / Project ----
    pdf.set_xy(15, y + 5)
    pdf.set_font("Helvetica", "B", 8)
    pdf.set_text_color(*grey)
    pdf.cell(90, 4.5, "BILL TO", 0, 0)
    pdf.cell(90, 4.5, "PROJECT", 0, 1)
    pdf.set_x(15)
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(*ink)
    pdf.cell(90, 6, _safe(doc.get("client_name") or "—"), 0, 0)
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(90, 6, _safe(doc.get("project_name") or "—"), 0, 1)
    pdf.ln(5)

    # ---- Items table ----
    col_w = {"idx": 10, "desc": 92, "qty": 18, "rate": 30, "amt": 30}
    pdf.set_fill_color(*ink)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Helvetica", "B", 8.5)
    pdf.cell(col_w["idx"], 8, " #", 0, 0, "L", fill=True)
    pdf.cell(col_w["desc"], 8, "DESCRIPTION", 0, 0, "L", fill=True)
    pdf.cell(col_w["qty"], 8, "QTY", 0, 0, "R", fill=True)
    pdf.cell(col_w["rate"], 8, "RATE", 0, 0, "R", fill=True)
    pdf.cell(col_w["amt"], 8, "AMOUNT  ", 0, 1, "R", fill=True)

    pdf.set_text_color(*ink)
    pdf.set_font("Helvetica", "", 9.5)
    items = doc.get("items", []) or []
    for i, it in enumerate(items, start=1):
        fill = i % 2 == 0
        if fill:
            pdf.set_fill_color(*soft)
        pdf.cell(col_w["idx"], 7.5, f" {i}", 0, 0, "L", fill=fill)
        pdf.cell(col_w["desc"], 7.5, _safe(it.get("description", ""))[:62], 0, 0, "L", fill=fill)
        pdf.cell(col_w["qty"], 7.5, f"{it.get('quantity', 0):g}", 0, 0, "R", fill=fill)
        pdf.cell(col_w["rate"], 7.5, f"{it.get('rate', 0):,.2f}", 0, 0, "R", fill=fill)
        pdf.cell(col_w["amt"], 7.5, f"{it.get('amount', 0):,.2f}  ", 0, 1, "R", fill=fill)
    if not items:
        pdf.set_text_color(*grey)
        pdf.cell(0, 8, "No line items.", 0, 1, "C")
        pdf.set_text_color(*ink)
    pdf.set_draw_color(*line)
    pdf.line(15, pdf.get_y(), 195, pdf.get_y())
    pdf.ln(3)

    # ---- Totals block (right-aligned) ----
    totals = [("Subtotal", doc.get("subtotal", 0))]
    if doc.get("discount"):
        totals.append((f"Discount ({doc.get('discount_pct', 0)}%)", -float(doc.get("discount", 0))))
    totals.append((f"GST ({doc.get('tax_rate', 0):g}%)", doc.get("tax", 0)))
    pdf.set_font("Helvetica", "", 10)
    for label, val in totals:
        pdf.cell(130, 6.5, _safe(label), 0, 0, "R")
        pdf.cell(60, 6.5, _safe(f"{_inr(val)}  "), 0, 1, "R")
    # Grand total bar
    pdf.set_fill_color(*primary)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Helvetica", "B", 11.5)
    pdf.cell(130, 9, "TOTAL  ", 0, 0, "R", fill=True)
    pdf.cell(60, 9, _safe(f"{_inr(doc.get('total', 0))}  "), 0, 1, "R", fill=True)
    pdf.set_text_color(*ink)
    pdf.ln(2)

    # ---- Amount in words ----
    pdf.set_font("Helvetica", "BI", 9)
    pdf.set_text_color(*grey)
    pdf.multi_cell(0, 5, _safe(f"Amount in words: {_amount_in_words_inr(doc.get('total', 0))}"))
    pdf.set_text_color(*ink)
    pdf.ln(4)

    # ---- Bank / payment details ----
    bank = org.get("bank_details") or {}
    if any(bank.get(k) for k in ("bank", "account", "ifsc", "upi")):
        box_y = pdf.get_y()
        n_rows = sum(1 for v in [bank.get("account_name") or org_name, bank.get("bank"),
                                 bank.get("account"), bank.get("ifsc"), bank.get("upi")] if v)
        box_h = 9 + n_rows * 4.6 + 3
        pdf.set_fill_color(*soft)
        pdf.rect(15, box_y, 110, box_h, "F")
        pdf.set_xy(19, box_y + 3)
        pdf.set_font("Helvetica", "B", 8)
        pdf.set_text_color(*grey)
        pdf.cell(0, 4.5, "PAYMENT DETAILS", ln=1)
        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(*ink)
        for label, val in [("Account Name", bank.get("account_name") or org_name),
                           ("Bank", bank.get("bank")),
                           ("A/C No.", bank.get("account")),
                           ("IFSC", bank.get("ifsc")),
                           ("UPI", bank.get("upi"))]:
            if not val:
                continue
            pdf.set_x(19)
            pdf.set_text_color(*grey)
            pdf.cell(28, 4.6, _safe(label), 0, 0)
            pdf.set_text_color(*ink)
            pdf.cell(0, 4.6, _safe(str(val)), ln=1)
        pdf.set_y(max(pdf.get_y(), box_y + box_h + 2))
        pdf.ln(2)

    # ---- Notes / terms ----
    if doc.get("notes"):
        pdf.set_font("Helvetica", "B", 9)
        pdf.set_text_color(*grey)
        pdf.cell(0, 5, "NOTES & TERMS", ln=1)
        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(*ink)
        pdf.multi_cell(0, 4.6, _safe(doc.get("notes")))
        pdf.ln(2)

    # ---- Footer ----
    pdf.ln(4)
    pdf.set_draw_color(*line)
    pdf.line(15, pdf.get_y(), 195, pdf.get_y())
    pdf.ln(2)
    pdf.set_font("Helvetica", "I", 8.5)
    pdf.set_text_color(*grey)
    pdf.cell(0, 5, _safe(footer_note), ln=1, align="C")
    pdf.cell(0, 4.5, _safe("This is a computer-generated document and does not require a physical signature."),
             ln=1, align="C")

    output = pdf.output(dest="S")
    if isinstance(output, str):
        return output.encode("latin-1")
    return bytes(output)


@api.get("/invoices/{invoice_id}/pdf")
async def invoice_pdf(invoice_id: str, request: Request,
                       session_token: Optional[str] = Cookie(default=None),
                       authorization: Optional[str] = Header(default=None),
                       token: Optional[str] = None):
    # Allow either auth OR share token for PDF
    user = await get_current_user(request, session_token, authorization)
    if not user:
        # Check if shared via token: invoice must be attached to a project with this share_token
        if not token:
            raise HTTPException(status_code=401, detail="Not authenticated")
        inv = await sdb.invoices.find_one({"id": invoice_id}, {"_id": 0})
        if not inv:
            raise HTTPException(status_code=404, detail="Not found")
        project = await sdb.projects.find_one({"id": inv.get("project_id"), "share_token": token}, {"_id": 0})
        if not project:
            raise HTTPException(status_code=401, detail="Invalid share token")
    doc = await sdb.invoices.find_one({"id": invoice_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Not found")
    # Load org branding for this invoice (falls back to default org)
    from core.tenancy import DEFAULT_ORG_ID
    org = await db.organizations.find_one(
        {"org_id": doc.get("org_id") or DEFAULT_ORG_ID}, {"_id": 0}
    )
    pdf_bytes = generate_invoice_pdf(doc, org)
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{doc.get("number", invoice_id)}.pdf"'}
    )


# ============================================================
# Client Portal (shareable token, no auth)
# ============================================================
@api.get("/portal/{token}")
async def portal_view(token: str):
    project = await sdb.projects.find_one({"share_token": token}, {"_id": 0})
    if not project:
        raise HTTPException(status_code=404, detail="Invalid link")
    tasks = await sdb.tasks.find({"project_id": project["id"]}, {"_id": 0}).to_list(200)
    files = await sdb.files.find({"project_id": project["id"]}, {"_id": 0}).to_list(200)
    invoices = await sdb.invoices.find({"project_id": project["id"]}, {"_id": 0}).to_list(200)
    milestones = await sdb.milestones.find({"project_id": project["id"]}, {"_id": 0}).to_list(100)

    stage_index = PROJECT_STAGES.index(project.get("stage", "Requirement")) if project.get("stage") in PROJECT_STAGES else 0
    progress = round(((stage_index + 1) / len(PROJECT_STAGES)) * 100)

    return {
        "project": {
            "id": project["id"],
            "name": project.get("name"),
            "client_name": project.get("client_name"),
            "project_type": project.get("project_type"),
            "stage": project.get("stage"),
            "description": project.get("description"),
            "progress": progress,
            "all_stages": PROJECT_STAGES,
        },
        "tasks_summary": {
            "total": len(tasks),
            "done": sum(1 for t in tasks if t.get("status") == "done"),
            "in_progress": sum(1 for t in tasks if t.get("status") == "in_progress"),
        },
        "files": [{"id": f["id"], "name": f.get("name"), "url": f.get("url"), "stage": f.get("stage"),
                   "created_at": f.get("created_at")} for f in files],
        "invoices": [{"id": i["id"], "number": i.get("number"), "total": i.get("total"),
                      "status": i.get("status"), "due_date": i.get("due_date"),
                      "doc_type": i.get("doc_type")} for i in invoices],
        "milestones": milestones,
    }


class PortalMessageIn(BaseModel):
    from_name: str
    message: str


@api.post("/portal/{token}/message")
async def portal_message(token: str, payload: PortalMessageIn):
    project = await sdb.projects.find_one({"share_token": token}, {"_id": 0})
    if not project:
        raise HTTPException(status_code=404, detail="Invalid link")
    doc = {
        "id": new_id("msg_"),
        "project_id": project["id"],
        "from_name": payload.from_name,
        "message": payload.message,
        "created_at": iso(now_utc()),
        "channel": "client_portal",
    }
    await db.chat_messages.insert_one(dict(doc))
    return {"ok": True}


# ============================================================
# AI Assistant (Claude Sonnet 4.5 via Emergent LLM Key)
# ============================================================
@api.post("/ai/chat")
async def ai_chat(payload: AIChatIn, request: Request,
                  session_token: Optional[str] = Cookie(default=None),
                  authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    if not EMERGENT_LLM_KEY:
        raise HTTPException(status_code=500, detail="LLM key not configured")

    session_id = payload.session_id or f"ai_{user['user_id']}_{uuid.uuid4().hex[:6]}"

    # Build project context
    projects = await sdb.projects.find({}, {"_id": 0, "name": 1, "stage": 1, "project_type": 1, "client_name": 1}).to_list(50)
    overdue = await sdb.tasks.count_documents({"status": {"$ne": "done"}})
    leads_count = await sdb.leads.count_documents({})
    project_ctx = "\n".join([f"- {p.get('name')} [{p.get('stage')}] for {p.get('client_name') or 'N/A'}" for p in projects[:20]])
    system_message = (
        f"You are Saga AI, the internal assistant for a boutique architecture & interior design studio called "
        f"{(await db.organizations.find_one({'org_id': user.get('org_id') or 'org_default'}, {'_id': 0, 'name': 1}) or {}).get('name', 'Design Saga')}. "
        f"You help the team with project status, quick summaries, smart task suggestions, and answering questions about their pipeline. "
        f"Be concise, pragmatic, and use short bullet lists when useful.\n\n"
        f"CURRENT PROJECTS ({len(projects)}):\n{project_ctx or 'No projects yet.'}\n\n"
        f"PIPELINE: {leads_count} leads total. OPEN TASKS: {overdue}.\n"
    )
    if payload.context:
        system_message += f"\nADDITIONAL CONTEXT:\n{payload.context}\n"

    chat = LlmChat(
        api_key=EMERGENT_LLM_KEY,
        session_id=session_id,
        system_message=system_message,
    ).with_model("anthropic", "claude-sonnet-4-5-20250929")

    try:
        response = await chat.send_message(UserMessage(text=payload.message))
    except Exception as e:
        logger.exception("AI chat failed")
        raise HTTPException(status_code=500, detail=f"AI error: {e}")

    # Persist
    await db.ai_messages.insert_one({
        "session_id": session_id,
        "user_id": user["user_id"],
        "role": "user",
        "content": payload.message,
        "created_at": iso(now_utc()),
    })
    await db.ai_messages.insert_one({
        "session_id": session_id,
        "user_id": user["user_id"],
        "role": "assistant",
        "content": response,
        "created_at": iso(now_utc()),
    })

    return {"response": response, "session_id": session_id}


@api.get("/ai/history/{session_id}")
async def ai_history(session_id: str, request: Request,
                     session_token: Optional[str] = Cookie(default=None),
                     authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    msgs = await db.ai_messages.find(
        {"session_id": session_id, "user_id": user["user_id"]}, {"_id": 0}
    ).sort("created_at", 1).to_list(200)
    return msgs


# ============================================================
# Seed demo data
# ============================================================
@api.post("/seed")
async def seed_demo(request: Request, session_token: Optional[str] = Cookie(default=None),
                    authorization: Optional[str] = Header(default=None)):
    if os.environ.get("ENABLE_SEED_DEMO", "").lower() not in ("1", "true", "yes"):
        raise HTTPException(status_code=403,
                            detail="Demo seeding disabled. Set ENABLE_SEED_DEMO=true to enable.")
    user = await require_user(request, session_token, authorization)
    if not has_permission(user, "*.*"):
        raise HTTPException(status_code=403, detail="Admin only")

    # Clients
    clients_seed = [
        {"id": new_id("cli_"), "name": "Aravind Menon", "email": "aravind@example.com", "phone": "+91 98765 43210", "company": "Menon Residence", "address": "Bandra, Mumbai", "created_at": iso(now_utc())},
        {"id": new_id("cli_"), "name": "Studio North", "email": "hello@studionorth.co", "phone": "+91 98122 22111", "company": "Studio North Cafe", "address": "Indiranagar, Bangalore", "created_at": iso(now_utc())},
        {"id": new_id("cli_"), "name": "Priya Kapoor", "email": "priya.k@example.com", "phone": "+91 99887 77665", "company": "Kapoor Villa", "address": "Jubilee Hills, Hyderabad", "created_at": iso(now_utc())},
    ]
    for c in clients_seed:
        c["org_id"] = c.get("org_id") or user.get("org_id") or "org_default"
        await sdb.clients.update_one({"id": c["id"]}, {"$set": c}, upsert=True)

    # Leads
    leads_seed = [
        ("Rahul Desai", "Instagram", "Residential", 1800000, "New"),
        ("Oak & Pine Cafe", "Referral", "Commercial", 3500000, "Qualified"),
        ("Neha Iyer", "Website", "Residential", 2200000, "Proposal"),
        ("Co-space Labs", "Walk-in", "Commercial", 5800000, "Negotiation"),
        ("Vikram Singh", "Marketplace", "Residential", 1500000, "New"),
        ("Luma Boutique", "Referral", "Commercial", 2700000, "Qualified"),
    ]
    for name, src, pt, bud, stage in leads_seed:
        lead = {
            "id": new_id("lead_"),
            "name": name,
            "email": f"{name.lower().replace(' ', '.').replace('&','and')}@example.com",
            "phone": "+91 98000 00000",
            "source": src,
            "project_type": pt,
            "budget": bud,
            "location": "Mumbai",
            "stage": stage,
            "notes": "",
            "timeline": [],
            "created_at": iso(now_utc()),
            "created_by": user["user_id"],
        }
        await sdb.leads.insert_one(dict(lead))

    # Projects
    projects_seed = [
        ("Menon Residence – 4BHK Duplex", clients_seed[0]["id"], clients_seed[0]["name"], "Residential", 2400000, "Design Dev"),
        ("Studio North Cafe Flagship", clients_seed[1]["id"], clients_seed[1]["name"], "Commercial", 4100000, "Tech Drawings"),
        ("Kapoor Villa Revamp", clients_seed[2]["id"], clients_seed[2]["name"], "Residential", 3000000, "Concept"),
    ]
    created_project_ids = []
    for name, cid, cname, pt, bud, stage in projects_seed:
        pid = new_id("prj_")
        p = {
            "id": pid,
            "name": name,
            "client_id": cid,
            "client_name": cname,
            "project_type": pt,
            "budget": bud,
            "stage": stage,
            "description": f"{pt} project for {cname}. Full-scope design and execution.",
            "share_token": new_id(),
            "created_at": iso(now_utc()),
            "created_by": user["user_id"],
        }
        await sdb.projects.insert_one(dict(p))
        created_project_ids.append(pid)

    # Tasks
    task_samples = [
        ("Site measurement visit", "todo", "high", created_project_ids[0]),
        ("Moodboard v2", "in_progress", "medium", created_project_ids[0]),
        ("Finalise joinery BOQ", "review", "high", created_project_ids[1]),
        ("MEP coordination call", "todo", "medium", created_project_ids[1]),
        ("3D render – living room", "in_progress", "high", created_project_ids[2]),
        ("Client concept presentation", "done", "medium", created_project_ids[2]),
        ("Vendor followup – stone", "todo", "low", created_project_ids[1]),
    ]
    for title, status, pri, pid in task_samples:
        due = (now_utc() + timedelta(days=(3 if status != "done" else -1))).date().isoformat()
        t = {
            "id": new_id("tsk_"),
            "title": title,
            "description": "",
            "project_id": pid,
            "assignee_id": user["user_id"],
            "assignee_name": user["name"],
            "priority": pri,
            "status": status,
            "due_date": due,
            "created_at": iso(now_utc()),
            "created_by": user["user_id"],
        }
        await sdb.tasks.insert_one(dict(t))

    # Invoices
    inv_samples = [
        (created_project_ids[0], clients_seed[0]["name"], clients_seed[0]["id"], "Concept design – retainer", 1, 600000, "paid", "invoice"),
        (created_project_ids[0], clients_seed[0]["name"], clients_seed[0]["id"], "Design development – milestone 2", 1, 550000, "sent", "invoice"),
        (created_project_ids[1], clients_seed[1]["name"], clients_seed[1]["id"], "Flagship cafe – total fee proposal", 1, 820000, "sent", "quotation"),
        (created_project_ids[2], clients_seed[2]["name"], clients_seed[2]["id"], "Villa revamp – concept fee", 1, 300000, "paid", "invoice"),
    ]
    for pid, cname, cid, desc, qty, rate, status, dtype in inv_samples:
        prefix = "QUO" if dtype == "quotation" else "INV"
        count = await sdb.invoices.count_documents({"doc_type": dtype})
        inv = {
            "id": new_id("inv_"),
            "number": f"{prefix}-{1000 + count + 1}",
            "client_id": cid,
            "client_name": cname,
            "project_id": pid,
            "items": [{"description": desc, "quantity": qty, "rate": rate, "amount": qty * rate}],
            "tax_rate": 18,
            "notes": "Payment due within 15 days of receipt.",
            "due_date": (now_utc() + timedelta(days=15)).date().isoformat(),
            "status": status,
            "doc_type": dtype,
            "created_at": iso(now_utc()),
            "created_by": user["user_id"],
        }
        compute_invoice_totals(inv)
        proj = await sdb.projects.find_one({"id": pid}, {"_id": 0})
        if proj:
            inv["project_name"] = proj.get("name")
        await sdb.invoices.insert_one(dict(inv))

    # Files
    files_seed = [
        (created_project_ids[0], "Living_Room_Render_v3.jpg", "https://images.unsplash.com/photo-1600585154340-be6161a56a0c", "Design Dev"),
        (created_project_ids[0], "Floor_Plan_v2.pdf", "https://example.com/floorplan.pdf", "Tech Drawings"),
        (created_project_ids[1], "Cafe_Moodboard.pdf", "https://example.com/moodboard.pdf", "Concept"),
    ]
    for pid, name, url, stage in files_seed:
        f = {
            "id": new_id("fil_"),
            "project_id": pid,
            "name": name,
            "url": url,
            "stage": stage,
            "version": 1,
            "created_at": iso(now_utc()),
            "created_by": user["user_id"],
            "uploader_name": user["name"],
        }
        await sdb.files.insert_one(dict(f))

    return {"ok": True, "projects": len(created_project_ids), "leads": len(leads_seed),
            "tasks": len(task_samples), "invoices": len(inv_samples)}


# ============================================================
# ADVANCED QUOTATION ENGINE
# (Enterprise-grade module: BOQ, Rooms, Materials, Payment Plan,
#  Timeline, Terms, Versions, Approval, Change Orders, Premium PDF)
# ============================================================

QUOTATION_TYPES = ["turnkey", "consultancy", "execution", "hybrid"]
QUOTATION_STATUSES = ["draft", "sent", "under_review", "approved", "rejected", "converted"]
ROOM_PRESETS = ["Living Room", "Kitchen", "Master Bedroom", "Kids Bedroom",
                "Guest Bedroom", "Master Bath", "Common Bath", "Dining",
                "Foyer", "Balcony", "Study", "Pooja", "Utility", "Other"]
BRAND_TIERS = ["Premium", "Standard", "Budget"]
PAYMENT_STRUCTURE_TYPES = ["milestone", "time", "custom"]


# ---------- BOQ Library Templates ----------
BOQ_TEMPLATES = {
    "Kitchen": [
        {"description": "Base unit – 18mm BWP ply with laminate finish", "unit": "rft", "quantity": 12, "rate": 2200, "margin_pct": 18},
        {"description": "Wall unit – 18mm BWP ply with laminate finish", "unit": "rft", "quantity": 10, "rate": 1800, "margin_pct": 18},
        {"description": "Tall unit / pantry pull-out", "unit": "nos", "quantity": 1, "rate": 32000, "margin_pct": 18},
        {"description": "Quartz countertop 20mm", "unit": "sq.ft", "quantity": 22, "rate": 950, "margin_pct": 22},
        {"description": "Tile backsplash – 8x4ft", "unit": "sq.ft", "quantity": 32, "rate": 350, "margin_pct": 18},
        {"description": "Soft-close hinges & telescopic channels", "unit": "set", "quantity": 1, "rate": 18500, "margin_pct": 15},
        {"description": "Sink + pull-out faucet (Premium)", "unit": "set", "quantity": 1, "rate": 24500, "margin_pct": 12},
        {"description": "Chimney 90cm auto-clean", "unit": "nos", "quantity": 1, "rate": 28000, "margin_pct": 10},
        {"description": "Hob – 4 burner with safety", "unit": "nos", "quantity": 1, "rate": 18500, "margin_pct": 10},
        {"description": "Under-cabinet LED lighting", "unit": "rft", "quantity": 10, "rate": 380, "margin_pct": 20},
    ],
    "Wardrobe": [
        {"description": "Wardrobe carcass – 18mm BWR ply", "unit": "sq.ft", "quantity": 90, "rate": 1450, "margin_pct": 20},
        {"description": "Shutters – laminate finish, soft close", "unit": "sq.ft", "quantity": 60, "rate": 750, "margin_pct": 20},
        {"description": "Hardware kit – Hettich/Hafele equivalent", "unit": "set", "quantity": 1, "rate": 9500, "margin_pct": 15},
        {"description": "Internal drawers (4)", "unit": "set", "quantity": 1, "rate": 7800, "margin_pct": 18},
        {"description": "LED profile lighting inside wardrobe", "unit": "nos", "quantity": 2, "rate": 1850, "margin_pct": 18},
        {"description": "Loft storage – 12mm ply", "unit": "sq.ft", "quantity": 18, "rate": 950, "margin_pct": 18},
    ],
    "Electrical": [
        {"description": "Concealed wiring – Polycab/Havells equivalent", "unit": "point", "quantity": 60, "rate": 850, "margin_pct": 12},
        {"description": "Modular switches & sockets", "unit": "point", "quantity": 60, "rate": 480, "margin_pct": 15},
        {"description": "Recessed COB downlights 7W", "unit": "nos", "quantity": 18, "rate": 950, "margin_pct": 18},
        {"description": "Profile lights – linear LED", "unit": "rft", "quantity": 24, "rate": 620, "margin_pct": 18},
        {"description": "Ceiling fan – BLDC premium", "unit": "nos", "quantity": 4, "rate": 6500, "margin_pct": 10},
        {"description": "AC point + copper piping (split)", "unit": "nos", "quantity": 3, "rate": 3800, "margin_pct": 12},
        {"description": "MCB distribution board upgrade", "unit": "nos", "quantity": 1, "rate": 8500, "margin_pct": 12},
    ],
    "Civil & Finishes": [
        {"description": "Demolition + debris disposal", "unit": "lot", "quantity": 1, "rate": 18000, "margin_pct": 10},
        {"description": "POP false ceiling – plain", "unit": "sq.ft", "quantity": 320, "rate": 105, "margin_pct": 18},
        {"description": "POP cove + design accents", "unit": "rft", "quantity": 80, "rate": 220, "margin_pct": 20},
        {"description": "Wall putty + 2 coats premium emulsion", "unit": "sq.ft", "quantity": 1800, "rate": 38, "margin_pct": 15},
        {"description": "Texture wall – statement", "unit": "sq.ft", "quantity": 90, "rate": 220, "margin_pct": 25},
        {"description": "Wallpaper – branded vinyl", "unit": "sq.ft", "quantity": 60, "rate": 180, "margin_pct": 20},
    ],
    "Bathroom": [
        {"description": "Wall tiles – designer 600x1200", "unit": "sq.ft", "quantity": 180, "rate": 145, "margin_pct": 18},
        {"description": "Floor tiles – anti-skid", "unit": "sq.ft", "quantity": 45, "rate": 110, "margin_pct": 18},
        {"description": "Sanitaryware set – wall hung WC + basin", "unit": "set", "quantity": 1, "rate": 32000, "margin_pct": 14},
        {"description": "CP fittings – Jaquar/Kohler equivalent", "unit": "set", "quantity": 1, "rate": 28000, "margin_pct": 14},
        {"description": "Shower partition glass 10mm", "unit": "sq.ft", "quantity": 24, "rate": 850, "margin_pct": 18},
        {"description": "Vanity unit – BWR ply with stone top", "unit": "rft", "quantity": 4, "rate": 4500, "margin_pct": 22},
    ],
}

# ---------- Consultancy Fee Schedule Templates (no procurement noise) ----------
CONSULTANCY_FEE_TEMPLATES = {
    "Design Fees": [
        {"description": "Concept design + mood boards + space planning", "unit": "lot", "quantity": 1, "rate": 75000, "margin_pct": 0},
        {"description": "Design development (detailed 2D layouts)", "unit": "lot", "quantity": 1, "rate": 60000, "margin_pct": 0},
        {"description": "3D visualisation (per view)", "unit": "nos", "quantity": 6, "rate": 8000, "margin_pct": 0},
        {"description": "Working drawings / GFC set", "unit": "lot", "quantity": 1, "rate": 85000, "margin_pct": 0},
    ],
    "Consultation & Site Services": [
        {"description": "Design consultation session", "unit": "nos", "quantity": 4, "rate": 5000, "margin_pct": 0},
        {"description": "Site visit + supervision", "unit": "visit", "quantity": 6, "rate": 3500, "margin_pct": 0},
        {"description": "Vendor / agency coordination", "unit": "lot", "quantity": 1, "rate": 25000, "margin_pct": 0},
    ],
    "Revisions & Extras": [
        {"description": "Additional design revision (beyond limit)", "unit": "nos", "quantity": 1, "rate": 12000, "margin_pct": 0},
        {"description": "As-built documentation", "unit": "lot", "quantity": 1, "rate": 30000, "margin_pct": 0},
    ],
}

CONSULTANCY_TERMS = [
    {"section": "Validity", "content": "This fee proposal is valid for 30 days from the date of issue."},
    {"section": "Scope", "content": "Fees cover professional design services only. Execution, procurement, and material costs are borne directly by the client / appointed contractors."},
    {"section": "Payment", "content": "Fees are payable milestone-wise as per the payment plan. All payments via NEFT/IMPS to the registered firm account."},
    {"section": "Revisions", "content": "The quoted fee includes the stated revision limit. Additional revisions are billed as per the extras schedule."},
    {"section": "Site Visits", "content": "Site visits beyond the included count are billed per visit. Outstation visits attract travel & stay at actuals."},
    {"section": "Cancellation", "content": "On cancellation, fees for completed stages plus work-in-progress (pro-rata) are payable. Advance is non-refundable."},
]

DEFAULT_TERMS = [
    {"section": "Validity", "content": "This quotation is valid for 30 days from the date of issue."},
    {"section": "Payment", "content": "All payments to be made via NEFT/IMPS to the registered firm account. Cheques subject to realisation."},
    {"section": "Warranty", "content": "Civil works carry 1-year workmanship warranty. Modular furniture carries 5-year warranty on carcass and 1-year on hardware. Brand-supplied appliances carry manufacturer warranty."},
    {"section": "Exclusions", "content": "Government approvals, society NOC, structural changes affecting the building shell, and any taxes/duties beyond GST quoted."},
    {"section": "Delay clause", "content": "Project timelines assume uninterrupted site access. Delays attributable to client (material selection delays, payment delays, blocked access) will extend the delivery proportionately."},
    {"section": "Cancellation", "content": "On cancellation post advance, design fees are non-refundable. Material already procured will be billed at cost + 10%."},
]

DEFAULT_PAYMENT_PLAN_BY_TYPE = {
    "turnkey": [
        {"label": "Booking advance", "type": "milestone", "percentage": 10, "due_after_days": 0,
         "notes": "Required to lock the project and start design phase."},
        {"label": "Design sign-off", "type": "milestone", "percentage": 15, "due_after_days": 14,
         "notes": "On approval of final 3D + working drawings."},
        {"label": "Material procurement (50%)", "type": "milestone", "percentage": 35, "due_after_days": 30,
         "notes": "Before site mobilisation."},
        {"label": "Carcass + civil completion", "type": "milestone", "percentage": 25, "due_after_days": 60,
         "notes": "On completion of carcass and civil work."},
        {"label": "Pre-handover", "type": "milestone", "percentage": 10, "due_after_days": 80,
         "notes": "Before final installations and snag close."},
        {"label": "Handover", "type": "milestone", "percentage": 5, "due_after_days": 90,
         "notes": "On final handover and snag list close."},
    ],
    "consultancy": [
        {"label": "Project kickoff", "type": "milestone", "percentage": 30, "due_after_days": 0, "notes": ""},
        {"label": "Concept design", "type": "milestone", "percentage": 30, "due_after_days": 14, "notes": ""},
        {"label": "Design development", "type": "milestone", "percentage": 25, "due_after_days": 28, "notes": ""},
        {"label": "Final drawings + handover", "type": "milestone", "percentage": 15, "due_after_days": 45, "notes": ""},
    ],
    "execution": [
        {"label": "Mobilisation advance", "type": "milestone", "percentage": 20, "due_after_days": 0, "notes": ""},
        {"label": "Material procurement", "type": "milestone", "percentage": 40, "due_after_days": 14, "notes": ""},
        {"label": "Civil + carcass", "type": "milestone", "percentage": 25, "due_after_days": 45, "notes": ""},
        {"label": "Pre-handover", "type": "milestone", "percentage": 10, "due_after_days": 70, "notes": ""},
        {"label": "Handover", "type": "milestone", "percentage": 5, "due_after_days": 90, "notes": ""},
    ],
    "hybrid": [
        {"label": "Booking advance", "type": "milestone", "percentage": 15, "due_after_days": 0, "notes": ""},
        {"label": "Design sign-off", "type": "milestone", "percentage": 20, "due_after_days": 14, "notes": ""},
        {"label": "Execution mobilisation", "type": "milestone", "percentage": 30, "due_after_days": 28, "notes": ""},
        {"label": "Mid-execution", "type": "milestone", "percentage": 25, "due_after_days": 60, "notes": ""},
        {"label": "Handover", "type": "milestone", "percentage": 10, "due_after_days": 90, "notes": ""},
    ],
}

DEFAULT_TIMELINE_BY_TYPE = {
    "turnkey": [
        {"phase": "Design – Concept & DD", "duration_weeks": 3, "start_offset_weeks": 0},
        {"phase": "Design – Tech drawings & approvals", "duration_weeks": 2, "start_offset_weeks": 3},
        {"phase": "Procurement", "duration_weeks": 3, "start_offset_weeks": 5},
        {"phase": "Civil + carcass", "duration_weeks": 4, "start_offset_weeks": 6},
        {"phase": "Finishing + installation", "duration_weeks": 3, "start_offset_weeks": 10},
        {"phase": "Snag + handover", "duration_weeks": 1, "start_offset_weeks": 13},
    ],
    "consultancy": [
        {"phase": "Concept", "duration_weeks": 2, "start_offset_weeks": 0},
        {"phase": "Design Development", "duration_weeks": 2, "start_offset_weeks": 2},
        {"phase": "Tech drawings", "duration_weeks": 2, "start_offset_weeks": 4},
    ],
    "execution": [
        {"phase": "Procurement", "duration_weeks": 2, "start_offset_weeks": 0},
        {"phase": "Civil + carcass", "duration_weeks": 4, "start_offset_weeks": 1},
        {"phase": "Finishing + installation", "duration_weeks": 3, "start_offset_weeks": 5},
        {"phase": "Snag + handover", "duration_weeks": 1, "start_offset_weeks": 8},
    ],
    "hybrid": [
        {"phase": "Concept + DD", "duration_weeks": 3, "start_offset_weeks": 0},
        {"phase": "Tech drawings", "duration_weeks": 2, "start_offset_weeks": 3},
        {"phase": "Partial execution", "duration_weeks": 5, "start_offset_weeks": 5},
        {"phase": "Handover", "duration_weeks": 1, "start_offset_weeks": 10},
    ],
}

DEFAULT_DELIVERABLES_BY_TYPE = {
    "turnkey":     {"type_2d": 12, "type_3d": 6, "drawings": 18, "site_visits": 30, "revision_limit": 3},
    "consultancy": {"type_2d": 10, "type_3d": 5, "drawings": 14, "site_visits": 6,  "revision_limit": 3},
    "execution":   {"type_2d": 4,  "type_3d": 0, "drawings": 8,  "site_visits": 30, "revision_limit": 1},
    "hybrid":      {"type_2d": 10, "type_3d": 4, "drawings": 14, "site_visits": 18, "revision_limit": 2},
}

DEFAULT_MATERIALS = [
    {"category": "Plywood / Boards", "brand_premium": "Greenply Club Prime BWP", "brand_standard": "Century Sainik", "brand_budget": "Local ISI BWR", "selected_tier": "Standard", "notes": "18mm for carcass, 12mm for shutters internal"},
    {"category": "Laminates", "brand_premium": "Merino / Greenlam 1mm", "brand_standard": "Century 0.8mm", "brand_budget": "Royale 0.7mm", "selected_tier": "Standard", "notes": "Anti-fingerprint matte preferred"},
    {"category": "Hardware", "brand_premium": "Hettich / Hafele", "brand_standard": "Ebco Tandem", "brand_budget": "Generic ISI", "selected_tier": "Premium", "notes": "Soft close on all base + tall units"},
    {"category": "Sanitaryware", "brand_premium": "Kohler / Duravit", "brand_standard": "Jaquar Continental", "brand_budget": "Hindware", "selected_tier": "Standard", "notes": ""},
    {"category": "CP Fittings", "brand_premium": "Grohe / Kohler", "brand_standard": "Jaquar Fonte", "brand_budget": "Cera", "selected_tier": "Standard", "notes": ""},
    {"category": "Tiles", "brand_premium": "Italian / Spanish import", "brand_standard": "Kajaria Eternity", "brand_budget": "Somany", "selected_tier": "Standard", "notes": "Min 600x1200 for walls"},
    {"category": "Paint", "brand_premium": "Asian Royale Atmos", "brand_standard": "Asian Apex Ultima", "brand_budget": "Berger Silk", "selected_tier": "Standard", "notes": "Low-VOC preferred"},
    {"category": "Electricals", "brand_premium": "Schneider Livia", "brand_standard": "Legrand Mylinc", "brand_budget": "Anchor Roma", "selected_tier": "Standard", "notes": "Concealed Polycab/Havells wires"},
]


# ---------- helpers ----------
def _q_compute_costs(q: dict) -> dict:
    """Recompute subtotal, discount, tax, contingency, grand total + room totals + category totals from BOQ."""
    boq = q.get("boq", []) or []
    subtotal = 0.0
    cat_totals = {}
    room_totals = {}
    for cat in boq:
        cat_total = 0.0
        for it in cat.get("items", []):
            qty = float(it.get("quantity", 0) or 0)
            rate = float(it.get("rate", 0) or 0)
            margin = float(it.get("margin_pct", 0) or 0)
            base = qty * rate
            with_margin = round(base * (1 + margin / 100.0), 2)
            it["amount"] = with_margin
            cat_total += with_margin
            room = it.get("room") or "Unassigned"
            room_totals[room] = room_totals.get(room, 0) + with_margin
        cat["category_total"] = round(cat_total, 2)
        cat_totals[cat.get("category", "Misc")] = cat["category_total"]
        subtotal += cat_total

    cost = q.get("cost", {}) or {}
    discount_pct = float(cost.get("discount_pct", 0) or 0)
    tax_pct = float(cost.get("tax_pct", 18) or 0)
    contingency_pct = float(cost.get("contingency_pct", 0) or 0)

    discount_amt = round(subtotal * discount_pct / 100.0, 2)
    after_discount = subtotal - discount_amt
    contingency_amt = round(after_discount * contingency_pct / 100.0, 2)
    taxable = after_discount + contingency_amt
    tax_amt = round(taxable * tax_pct / 100.0, 2)
    grand_total = round(taxable + tax_amt, 2)

    q["cost"] = {
        "subtotal": round(subtotal, 2),
        "discount_pct": discount_pct,
        "discount_amt": discount_amt,
        "contingency_pct": contingency_pct,
        "contingency_amt": contingency_amt,
        "tax_pct": tax_pct,
        "tax_amt": tax_amt,
        "grand_total": grand_total,
    }
    q["category_totals"] = [{"category": k, "total": v} for k, v in cat_totals.items()]
    q["room_totals"] = [{"room": k, "total": round(v, 2)} for k, v in room_totals.items()]

    # payment plan amount derivation
    plan = q.get("payment_plan", []) or []
    for p in plan:
        pct = float(p.get("percentage", 0) or 0)
        p["amount"] = round(grand_total * pct / 100.0, 2)
    q["payment_plan"] = plan

    # timeline total
    tl = q.get("timeline", []) or []
    if tl:
        q["total_duration_weeks"] = max((p.get("start_offset_weeks", 0) + p.get("duration_weeks", 0)) for p in tl)
    else:
        q["total_duration_weeks"] = 0
    return q


def _new_quotation_doc(payload: dict, user: dict) -> dict:
    qtype = payload.get("type") or "turnkey"
    if qtype not in QUOTATION_TYPES:
        qtype = "turnkey"
    qid = new_id("quo_")
    # number is generated by the caller (needs DB count)
    doc = {
        "id": qid,
        "type": qtype,
        "status": "draft",
        "version": 1,
        "version_label": "v1",
        "parent_id": None,
        # cover
        "project_title": payload.get("project_title", "Untitled Project"),
        "client_id": payload.get("client_id"),
        "client_name": payload.get("client_name"),
        "project_id": payload.get("project_id"),
        "project_location": payload.get("project_location", ""),
        "area_sqft": float(payload.get("area_sqft", 0) or 0),
        "firm_name": payload.get("firm_name", "Design Saga"),
        "date": iso(now_utc())[:10],
        # exec summary
        "client_requirement": payload.get("client_requirement", ""),
        "design_intent": payload.get("design_intent", ""),
        "highlights": payload.get("highlights", {"budget_range": "", "timeline": "", "quality_level": "Premium"}),
        # scope
        "design_scope": payload.get("design_scope", []) or [],
        "execution_scope": payload.get("execution_scope", []) or [],
        "exclusions": payload.get("exclusions", []) or [],
        "deliverables": payload.get("deliverables") or DEFAULT_DELIVERABLES_BY_TYPE.get(qtype, {}),
        # boq
        "boq": payload.get("boq", []) or [],
        # materials
        "materials": payload.get("materials") or [m.copy() for m in DEFAULT_MATERIALS],
        # cost
        "cost": payload.get("cost") or {"discount_pct": 0, "tax_pct": 18, "contingency_pct": 5},
        # payment plan
        "payment_plan": payload.get("payment_plan") or [p.copy() for p in DEFAULT_PAYMENT_PLAN_BY_TYPE.get(qtype, [])],
        # timeline
        "timeline": payload.get("timeline") or [t.copy() for t in DEFAULT_TIMELINE_BY_TYPE.get(qtype, [])],
        # terms
        "terms": payload.get("terms") or [t.copy() for t in DEFAULT_TERMS],
        # approval
        "approval": {
            "internal_status": "pending",
            "internal_by": None,
            "internal_at": None,
            "client_status": "pending",
            "client_response": None,
            "client_at": None,
        },
        # versions log
        "versions_log": [],
        # change orders
        "change_orders": [],
        "created_at": iso(now_utc()),
        "created_by": user["user_id"],
        "created_by_name": user.get("name"),
    }
    return _q_compute_costs(doc)


# ---------- Pydantic in-models (lenient) ----------
class QuotationCreate(BaseModel):
    type: Optional[str] = "turnkey"
    project_title: str
    client_id: Optional[str] = None
    client_name: Optional[str] = None
    project_id: Optional[str] = None
    project_location: Optional[str] = ""
    area_sqft: Optional[float] = 0


class QuotationUpdate(BaseModel):
    project_title: Optional[str] = None
    type: Optional[str] = None
    client_id: Optional[str] = None
    client_name: Optional[str] = None
    project_id: Optional[str] = None
    project_location: Optional[str] = None
    area_sqft: Optional[float] = None
    client_requirement: Optional[str] = None
    design_intent: Optional[str] = None
    highlights: Optional[dict] = None
    design_scope: Optional[List[str]] = None
    execution_scope: Optional[List[str]] = None
    exclusions: Optional[List[str]] = None
    deliverables: Optional[dict] = None
    boq: Optional[List[dict]] = None
    materials: Optional[List[dict]] = None
    cost: Optional[dict] = None
    payment_plan: Optional[List[dict]] = None
    timeline: Optional[List[dict]] = None
    terms: Optional[List[dict]] = None


class StatusUpdate(BaseModel):
    status: str
    note: Optional[str] = None


class ApprovalUpdate(BaseModel):
    actor: Literal["internal", "client"]
    decision: Literal["approved", "rejected", "changes_requested"]
    note: Optional[str] = None


class ChangeOrderIn(BaseModel):
    description: str
    cost_delta: float = 0
    timeline_delta_weeks: float = 0
    items_added: Optional[List[dict]] = None
    items_removed: Optional[List[dict]] = None


# ---------- Endpoints ----------
@api.get("/quotations-adv/templates")
async def adv_templates(request: Request, session_token: Optional[str] = Cookie(default=None),
                        authorization: Optional[str] = Header(default=None)):
    await require_user(request, session_token, authorization)
    return {
        "types": QUOTATION_TYPES,
        "statuses": QUOTATION_STATUSES,
        "rooms": ROOM_PRESETS,
        "brand_tiers": BRAND_TIERS,
        "boq_templates": BOQ_TEMPLATES,
        "consultancy_fee_templates": CONSULTANCY_FEE_TEMPLATES,
        "consultancy_terms": CONSULTANCY_TERMS,
        "default_terms": DEFAULT_TERMS,
        "default_materials": DEFAULT_MATERIALS,
        "payment_plans": DEFAULT_PAYMENT_PLAN_BY_TYPE,
        "timelines": DEFAULT_TIMELINE_BY_TYPE,
        "deliverables": DEFAULT_DELIVERABLES_BY_TYPE,
    }


@api.get("/quotations-adv")
async def adv_list(request: Request, session_token: Optional[str] = Cookie(default=None),
                   authorization: Optional[str] = Header(default=None)):
    await require_user(request, session_token, authorization)
    rows = await sdb.quotations_adv.find({}, {"_id": 0}).sort("created_at", -1).to_list(500)
    # summary
    out = []
    for r in rows:
        out.append({
            "id": r["id"], "number": r.get("number"), "project_title": r.get("project_title"),
            "client_name": r.get("client_name"), "type": r.get("type"), "status": r.get("status"),
            "version": r.get("version"), "version_label": r.get("version_label"),
            "grand_total": (r.get("cost") or {}).get("grand_total", 0),
            "created_at": r.get("created_at"),
            "created_by_name": r.get("created_by_name"),
            "area_sqft": r.get("area_sqft", 0),
        })
    return out


@api.post("/quotations-adv")
async def adv_create(payload: QuotationCreate, request: Request,
                     session_token: Optional[str] = Cookie(default=None),
                     authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    doc = _new_quotation_doc(payload.model_dump(), user)
    count = await sdb.quotations_adv.count_documents({})
    doc["number"] = f"Q-{2026}-{1000 + count + 1}"
    if doc.get("client_id") and not doc.get("client_name"):
        c = await sdb.clients.find_one({"id": doc["client_id"]}, {"_id": 0})
        if c:
            doc["client_name"] = c.get("name")
    await sdb.quotations_adv.insert_one(dict(doc))
    return await sdb.quotations_adv.find_one({"id": doc["id"]}, {"_id": 0})


@api.get("/quotations-adv/{qid}")
async def adv_get(qid: str, request: Request, session_token: Optional[str] = Cookie(default=None),
                  authorization: Optional[str] = Header(default=None)):
    await require_user(request, session_token, authorization)
    doc = await sdb.quotations_adv.find_one({"id": qid}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Not found")
    return doc


@api.put("/quotations-adv/{qid}")
async def adv_update(qid: str, payload: QuotationUpdate, request: Request,
                     session_token: Optional[str] = Cookie(default=None),
                     authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    doc = await sdb.quotations_adv.find_one({"id": qid}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Not found")
    update = {k: v for k, v in payload.model_dump().items() if v is not None}
    doc.update(update)
    doc["updated_at"] = iso(now_utc())
    doc["updated_by"] = user["user_id"]
    doc = _q_compute_costs(doc)
    await sdb.quotations_adv.replace_one({"id": qid}, dict(doc))
    return await sdb.quotations_adv.find_one({"id": qid}, {"_id": 0})


@api.delete("/quotations-adv/{qid}")
async def adv_delete(qid: str, request: Request, session_token: Optional[str] = Cookie(default=None),
                     authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    if not has_permission(user, "quotations.delete"):
        raise HTTPException(status_code=403, detail="Missing permission: quotations.delete")
    await sdb.quotations_adv.delete_one({"id": qid})
    return {"ok": True}


@api.post("/quotations-adv/{qid}/status")
async def adv_status(qid: str, payload: StatusUpdate, request: Request,
                     session_token: Optional[str] = Cookie(default=None),
                     authorization: Optional[str] = Header(default=None)):
    await require_user(request, session_token, authorization)
    if payload.status not in QUOTATION_STATUSES:
        raise HTTPException(status_code=400, detail="Invalid status")
    await sdb.quotations_adv.update_one(
        {"id": qid},
        {"$set": {"status": payload.status, "status_note": payload.note, "updated_at": iso(now_utc())}}
    )
    return await sdb.quotations_adv.find_one({"id": qid}, {"_id": 0})


@api.post("/quotations-adv/{qid}/approval")
async def adv_approval(qid: str, payload: ApprovalUpdate, request: Request,
                       session_token: Optional[str] = Cookie(default=None),
                       authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    doc = await sdb.quotations_adv.find_one({"id": qid}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Not found")
    approval = doc.get("approval") or {}
    field = "internal" if payload.actor == "internal" else "client"
    approval[f"{field}_status"] = payload.decision
    approval[f"{field}_at"] = iso(now_utc())
    approval[f"{field}_response"] = payload.note
    if payload.actor == "internal":
        approval["internal_by"] = user.get("name")
    next_status = doc.get("status")
    if payload.decision == "approved" and approval.get("client_status") == "approved":
        next_status = "approved"
    elif payload.decision == "rejected":
        next_status = "rejected"
    elif payload.decision == "changes_requested":
        next_status = "under_review"
    await sdb.quotations_adv.update_one(
        {"id": qid},
        {"$set": {"approval": approval, "status": next_status, "updated_at": iso(now_utc())}}
    )
    return await sdb.quotations_adv.find_one({"id": qid}, {"_id": 0})


@api.post("/quotations-adv/{qid}/version")
async def adv_new_version(qid: str, request: Request, session_token: Optional[str] = Cookie(default=None),
                          authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    body = {}
    try:
        body = await request.json()
    except Exception:
        body = {}
    note = body.get("note", "")
    src = await sdb.quotations_adv.find_one({"id": qid}, {"_id": 0})
    if not src:
        raise HTTPException(status_code=404, detail="Not found")

    # archive snapshot
    versions_log = src.get("versions_log") or []
    versions_log.append({
        "version": src.get("version", 1),
        "version_label": src.get("version_label"),
        "grand_total": (src.get("cost") or {}).get("grand_total", 0),
        "snapshot_at": iso(now_utc()),
        "by": user.get("name"),
        "note": note,
        "snapshot": {
            "boq": src.get("boq"),
            "cost": src.get("cost"),
            "payment_plan": src.get("payment_plan"),
            "timeline": src.get("timeline"),
            "materials": src.get("materials"),
        },
    })
    new_v = int(src.get("version", 1)) + 1
    await sdb.quotations_adv.update_one(
        {"id": qid},
        {"$set": {
            "version": new_v,
            "version_label": f"v{new_v}",
            "versions_log": versions_log,
            "updated_at": iso(now_utc()),
            "status": "draft",
        }}
    )
    return await sdb.quotations_adv.find_one({"id": qid}, {"_id": 0})


@api.post("/quotations-adv/{qid}/change-order")
async def adv_change_order(qid: str, payload: ChangeOrderIn, request: Request,
                           session_token: Optional[str] = Cookie(default=None),
                           authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    doc = await sdb.quotations_adv.find_one({"id": qid}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Not found")
    co = {
        "id": new_id("co_"),
        "description": payload.description,
        "cost_delta": payload.cost_delta,
        "timeline_delta_weeks": payload.timeline_delta_weeks,
        "items_added": payload.items_added or [],
        "items_removed": payload.items_removed or [],
        "status": "pending",
        "created_at": iso(now_utc()),
        "created_by": user.get("name"),
    }
    cos = doc.get("change_orders") or []
    cos.append(co)
    await sdb.quotations_adv.update_one({"id": qid}, {"$set": {"change_orders": cos, "updated_at": iso(now_utc())}})
    return co


@api.post("/quotations-adv/{qid}/convert-to-project")
async def adv_convert(qid: str, request: Request, session_token: Optional[str] = Cookie(default=None),
                      authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    q = await sdb.quotations_adv.find_one({"id": qid}, {"_id": 0})
    if not q:
        raise HTTPException(status_code=404, detail="Not found")
    if q.get("status") not in ("approved", "sent", "under_review"):
        raise HTTPException(status_code=400, detail="Quotation must be approved (or near-final) to convert")

    # reuse client or create
    client_id = q.get("client_id")
    if not client_id:
        client_id = new_id("cli_")
        await sdb.clients.insert_one({
            "id": client_id, "name": q.get("client_name") or "Client",
            "email": None, "phone": None, "company": None,
            "address": q.get("project_location"), "created_at": iso(now_utc()),
        })

    project_id = new_id("prj_")
    project = {
        "id": project_id,
        "name": q.get("project_title"),
        "client_id": client_id,
        "client_name": q.get("client_name"),
        "project_type": "Residential" if "residential" in (q.get("project_title", "").lower()) else "Commercial",
        "budget": (q.get("cost") or {}).get("grand_total", 0),
        "stage": "Requirement",
        "share_token": new_id(),
        "description": q.get("design_intent") or q.get("client_requirement") or "",
        "created_at": iso(now_utc()),
        "created_by": user["user_id"],
        "from_quotation_id": qid,
    }
    await sdb.projects.insert_one(dict(project))

    # Auto-create tasks from BOQ categories + timeline phases
    today = now_utc().date()
    for i, cat in enumerate(q.get("boq", []) or []):
        due = (today + timedelta(days=14 + i * 7)).isoformat()
        await sdb.tasks.insert_one({
            "id": new_id("tsk_"),
            "title": f"Procure & finalise: {cat.get('category')}",
            "description": f"From quotation {q.get('number')}",
            "project_id": project_id,
            "project_name": project["name"],
            "assignee_id": user["user_id"],
            "assignee_name": user["name"],
            "priority": "medium",
            "status": "todo",
            "due_date": due,
            "created_at": iso(now_utc()),
            "created_by": user["user_id"],
        })
    for ph in q.get("timeline", []) or []:
        due = (today + timedelta(weeks=ph.get("start_offset_weeks", 0) + ph.get("duration_weeks", 0))).isoformat()
        await sdb.tasks.insert_one({
            "id": new_id("tsk_"),
            "title": f"Phase: {ph.get('phase')}",
            "description": f"Auto-generated milestone task. Duration {ph.get('duration_weeks')} weeks.",
            "project_id": project_id,
            "project_name": project["name"],
            "assignee_id": user["user_id"],
            "assignee_name": user["name"],
            "priority": "high",
            "status": "todo",
            "due_date": due,
            "created_at": iso(now_utc()),
            "created_by": user["user_id"],
        })

    # mark quotation
    await sdb.quotations_adv.update_one(
        {"id": qid},
        {"$set": {"status": "converted", "converted_project_id": project_id, "updated_at": iso(now_utc())}}
    )
    return {"project_id": project_id, "client_id": client_id}


@api.post("/quotations-adv/{qid}/cost-vs-actual")
async def adv_cost_vs_actual(qid: str, request: Request, session_token: Optional[str] = Cookie(default=None),
                             authorization: Optional[str] = Header(default=None)):
    """Aggregates paid invoice totals on the converted project vs quoted grand_total."""
    await require_user(request, session_token, authorization)
    q = await sdb.quotations_adv.find_one({"id": qid}, {"_id": 0})
    if not q:
        raise HTTPException(status_code=404, detail="Not found")
    quoted = (q.get("cost") or {}).get("grand_total", 0)
    pid = q.get("converted_project_id")
    paid = 0.0
    sent = 0.0
    if pid:
        async for inv in sdb.invoices.find({"project_id": pid, "doc_type": "invoice"}, {"_id": 0}):
            if inv.get("status") == "paid":
                paid += float(inv.get("total", 0))
            elif inv.get("status") in ("sent", "overdue"):
                sent += float(inv.get("total", 0))
    actual = paid + sent
    margin = quoted - actual
    margin_pct = round((margin / quoted * 100.0), 2) if quoted else 0
    return {"quoted": quoted, "paid": paid, "sent_outstanding": sent, "actual": actual,
            "margin": margin, "margin_pct": margin_pct}


@api.post("/quotations-adv/{qid}/ai-suggest")
async def adv_ai_suggest(qid: str, request: Request, session_token: Optional[str] = Cookie(default=None),
                         authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    if not EMERGENT_LLM_KEY:
        raise HTTPException(status_code=500, detail="LLM not configured")
    q = await sdb.quotations_adv.find_one({"id": qid}, {"_id": 0})
    if not q:
        raise HTTPException(status_code=404, detail="Not found")
    body = {}
    try:
        body = await request.json()
    except Exception:
        body = {}
    focus = body.get("focus", "missing_items")  # missing_items | cost_optimisation | premium_upgrades

    boq_summary = []
    for cat in q.get("boq", []):
        items = ", ".join((it.get("description", "")[:50]) for it in cat.get("items", [])[:6])
        boq_summary.append(f"  • {cat.get('category')}: {items}")
    boq_text = "\n".join(boq_summary) or "(empty)"

    system = (
        "You are a senior architect/interior cost consultant in India. You audit BOQs of residential and commercial "
        "interior projects. Return a TIGHT bullet-point list (max 8 bullets). Be specific with item descriptions, "
        "approximate rates in INR, and reasoning. Don't hedge."
    )
    instruction_map = {
        "missing_items": "Identify line items that appear MISSING from this BOQ. Focus on commonly-forgotten items (electrical points, false-ceiling cove lights, door hardware, plumbing access panels, anti-termite, civil chasing, debris disposal, painting after-finish, transport). For each, give: item, suggested unit, approximate rate, and why it matters.",
        "cost_optimisation": "Suggest cost-optimisation moves WITHOUT compromising the brief. For each: what to swap/value-engineer, expected % savings, and any quality trade-off the studio should call out to the client.",
        "premium_upgrades": "Suggest 6-8 PREMIUM upgrades that visibly elevate the design language for this project. For each: upgrade item, estimated ₹ uplift, and the experiential payoff for the client.",
    }
    prompt = (
        f"PROJECT: {q.get('project_title')} ({q.get('type')}, {q.get('area_sqft')} sq.ft, "
        f"location: {q.get('project_location') or 'N/A'})\n"
        f"CURRENT GRAND TOTAL: ₹{(q.get('cost') or {}).get('grand_total', 0):,.0f}\n\n"
        f"DESIGN INTENT: {q.get('design_intent') or 'not specified'}\n\n"
        f"BOQ SNAPSHOT:\n{boq_text}\n\n"
        f"TASK: {instruction_map.get(focus, instruction_map['missing_items'])}"
    )

    chat = LlmChat(
        api_key=EMERGENT_LLM_KEY,
        session_id=f"quote_ai_{qid}_{focus}_{uuid.uuid4().hex[:6]}",
        system_message=system,
    ).with_model("anthropic", "claude-sonnet-4-5-20250929")
    try:
        response = await chat.send_message(UserMessage(text=prompt))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI error: {e}")
    return {"focus": focus, "response": response}


# ---------- Premium PDF ----------
def generate_quotation_pdf_adv(doc: dict, org: Optional[dict] = None) -> bytes:
    pdf = FPDF(format="A4", unit="mm")
    pdf.set_auto_page_break(auto=True, margin=18)
    is_consult = (doc.get("type") or "turnkey") == "consultancy"

    org = org or {}
    branding = org.get("branding") or {}
    org_name = org.get("display_name") or org.get("name") or "Design Saga"
    org_tagline = branding.get("tagline") or "Architecture & Interior Design"
    klein = _hex_to_rgb(branding.get("primary_color") or "#002FA7")
    ink = (10, 10, 10)
    grey = (92, 92, 92)
    line = (220, 220, 220)

    def hr():
        pdf.set_draw_color(*line)
        pdf.set_line_width(0.2)
        pdf.line(15, pdf.get_y(), 195, pdf.get_y())
        pdf.ln(2)

    def header_section(title):
        pdf.set_font("Helvetica", "B", 9)
        pdf.set_text_color(*grey)
        pdf.cell(0, 5, _safe(title.upper()), ln=1)
        pdf.set_font("Helvetica", "B", 16)
        pdf.set_text_color(*ink)

    # ============ COVER PAGE ============
    pdf.add_page()
    # brand bar
    pdf.set_fill_color(*klein)
    pdf.rect(0, 0, 210, 14, "F")
    pdf.set_text_color(255, 255, 255)
    pdf.set_xy(15, 4)
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 6, _safe(f"{org_name.upper()}  ·  {org_tagline.upper()[:40]}"), ln=1)
    pdf.set_text_color(*ink)

    pdf.set_xy(15, 30)
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(*grey)
    pdf.cell(0, 5, _safe(f"QUOTATION  ·  {(doc.get('type') or 'turnkey').upper()}  ·  {doc.get('version_label', 'v1')}"), ln=1)

    pdf.set_xy(15, 40)
    pdf.set_text_color(*ink)
    pdf.set_font("Helvetica", "B", 28)
    pdf.multi_cell(180, 12, _safe(doc.get("project_title", "")))
    pdf.ln(2)

    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(*grey)
    pdf.cell(0, 6, _safe(doc.get("design_intent") or doc.get("client_requirement") or ""), ln=1)
    pdf.ln(8)

    # Cover meta block
    pdf.set_text_color(*ink)
    pdf.set_font("Helvetica", "B", 9)
    cover_rows = [
        ("CLIENT", doc.get("client_name") or "—"),
        ("LOCATION", doc.get("project_location") or "—"),
        ("AREA", f"{doc.get('area_sqft', 0):g} sq.ft"),
        ("QUOTATION NO.", doc.get("number") or "—"),
        ("DATE", (doc.get("date") or "")[:10]),
        ("VERSION", doc.get("version_label") or "v1"),
    ]
    for label, val in cover_rows:
        pdf.set_font("Helvetica", "B", 8)
        pdf.set_text_color(*grey)
        pdf.cell(40, 6, _safe(label), 0, 0)
        pdf.set_font("Helvetica", "", 11)
        pdf.set_text_color(*ink)
        pdf.cell(0, 6, _safe(str(val)), ln=1)

    # Cover footer
    pdf.set_y(265)
    pdf.set_draw_color(*ink)
    pdf.set_line_width(0.4)
    pdf.line(15, pdf.get_y(), 195, pdf.get_y())
    pdf.ln(3)
    pdf.set_font("Helvetica", "I", 8)
    pdf.set_text_color(*grey)
    pdf.cell(0, 4, _safe("Confidential. Prepared exclusively for the client named above."), ln=1, align="C")

    # ============ EXECUTIVE SUMMARY (skipped when empty) ============
    h = doc.get("highlights") or {}
    _summary_rows = [("BUDGET RANGE", h.get("budget_range")),
                     ("TIMELINE", h.get("timeline")),
                     ("QUALITY LEVEL", h.get("quality_level"))]
    _has_summary = bool(doc.get("client_requirement") or doc.get("design_intent")
                        or any(v for _, v in _summary_rows))
    if _has_summary:
        pdf.add_page()
        header_section("01 / Executive Summary")
        pdf.cell(0, 9, _safe("Brief, intent and key markers."), ln=1)
        hr()
        if doc.get("client_requirement"):
            pdf.set_font("Helvetica", "B", 10)
            pdf.cell(0, 6, "Client requirement", ln=1)
            pdf.set_font("Helvetica", "", 10)
            pdf.multi_cell(0, 5, _safe(doc.get("client_requirement")))
            pdf.ln(2)
        if doc.get("design_intent"):
            pdf.set_font("Helvetica", "B", 10)
            pdf.cell(0, 6, "Design intent", ln=1)
            pdf.set_font("Helvetica", "", 10)
            pdf.multi_cell(0, 5, _safe(doc.get("design_intent")))
            pdf.ln(4)
        pdf.set_font("Helvetica", "B", 9)
        pdf.set_text_color(*grey)
        for k, v in _summary_rows:
            if not v:
                continue
            pdf.cell(45, 6, _safe(k), 0, 0)
            pdf.set_font("Helvetica", "", 11)
            pdf.set_text_color(*ink)
            pdf.cell(0, 6, _safe(str(v)), ln=1)
            pdf.set_font("Helvetica", "B", 9)
            pdf.set_text_color(*grey)
        pdf.set_text_color(*ink)

    # ============ SCOPE (skipped when empty) ============
    scope_rows = [("Design Scope", doc.get("design_scope", []))]
    if not is_consult:
        scope_rows.append(("Execution Scope", doc.get("execution_scope", [])))
    scope_rows.append(("Exclusions", doc.get("exclusions", [])))
    scope_rows = [(lbl, items) for lbl, items in scope_rows if items]
    d = doc.get("deliverables") or {}
    _deliv_rows = [(k, v) for k, v in
                   [("2D drawings", d.get("type_2d")), ("3D renders", d.get("type_3d")),
                    ("Working drawings", d.get("drawings")), ("Site visits", d.get("site_visits")),
                    ("Revision limit", d.get("revision_limit"))] if v is not None]
    if scope_rows or _deliv_rows:
        pdf.add_page()
        header_section("02 / Scope of Work")
        pdf.cell(0, 9, _safe("What is in. What is out."), ln=1)
        hr()
        for label, items in scope_rows:
            pdf.set_font("Helvetica", "B", 11)
            pdf.cell(0, 7, _safe(label), ln=1)
            pdf.set_font("Helvetica", "", 10)
            for it in items:
                pdf.set_x(15)
                pdf.multi_cell(180, 5, _safe(f"  *  {it}"))
            pdf.ln(2)
        if _deliv_rows:
            pdf.set_font("Helvetica", "B", 11)
            pdf.cell(0, 7, "Deliverables", ln=1)
            pdf.set_font("Helvetica", "", 10)
            for k, v in _deliv_rows:
                pdf.cell(60, 6, _safe(k), 0, 0)
                pdf.cell(0, 6, _safe(str(v)), ln=1)

    # ============ BOQ / FEE SCHEDULE (skipped when empty) ============
    grand = 0
    _has_boq = any((cat.get("items") or []) for cat in (doc.get("boq") or []))
    if _has_boq:
        pdf.add_page()
        if is_consult:
            header_section("03 / Fee Schedule")
            pdf.cell(0, 9, _safe("Professional fees, stage-wise."), ln=1)
        else:
            header_section("03 / Bill of Quantities")
            pdf.cell(0, 9, _safe("Line items, fully detailed."), ln=1)
        hr()
        pdf.set_font("Helvetica", "B", 8)
        pdf.set_fill_color(0, 0, 0)
        pdf.set_text_color(255, 255, 255)
        if is_consult:
            pdf.cell(95, 7, " Professional Service", 0, 0, "L", fill=True)
            pdf.cell(20, 7, "Unit", 0, 0, "C", fill=True)
            pdf.cell(18, 7, "Qty", 0, 0, "R", fill=True)
            pdf.cell(25, 7, "Rate", 0, 0, "R", fill=True)
            pdf.cell(22, 7, "Amount", 0, 1, "R", fill=True)
        else:
            pdf.cell(80, 7, " Description", 0, 0, "L", fill=True)
            pdf.cell(20, 7, "Unit", 0, 0, "C", fill=True)
            pdf.cell(18, 7, "Qty", 0, 0, "R", fill=True)
            pdf.cell(25, 7, "Rate", 0, 0, "R", fill=True)
            pdf.cell(15, 7, "Mgn%", 0, 0, "R", fill=True)
            pdf.cell(22, 7, "Amount", 0, 1, "R", fill=True)
        pdf.set_text_color(*ink)

        for cat in doc.get("boq", []):
            pdf.set_font("Helvetica", "B", 10)
            pdf.set_fill_color(245, 245, 245)
            pdf.cell(0, 6, _safe(f"  {cat.get('category', 'Misc')}"), 0, 1, "L", fill=True)
            pdf.set_font("Helvetica", "", 9)
            for it in cat.get("items", []):
                if is_consult:
                    pdf.cell(95, 6, _safe(it.get("description", ""))[:65], 0, 0, "L")
                    pdf.cell(20, 6, _safe(it.get("unit", "")), 0, 0, "C")
                    pdf.cell(18, 6, f"{it.get('quantity', 0):g}", 0, 0, "R")
                    pdf.cell(25, 6, f"{it.get('rate', 0):,.0f}", 0, 0, "R")
                    pdf.cell(22, 6, f"{it.get('amount', 0):,.0f}", 0, 1, "R")
                else:
                    pdf.cell(80, 6, _safe(it.get("description", ""))[:55], 0, 0, "L")
                    pdf.cell(20, 6, _safe(it.get("unit", "")), 0, 0, "C")
                    pdf.cell(18, 6, f"{it.get('quantity', 0):g}", 0, 0, "R")
                    pdf.cell(25, 6, f"{it.get('rate', 0):,.0f}", 0, 0, "R")
                    pdf.cell(15, 6, f"{it.get('margin_pct', 0):g}", 0, 0, "R")
                    pdf.cell(22, 6, f"{it.get('amount', 0):,.0f}", 0, 1, "R")
            pdf.set_font("Helvetica", "B", 9)
            pdf.cell(158, 6, _safe(f"Sub-total: {cat.get('category')}"), 0, 0, "R")
            pdf.cell(22, 6, f"{cat.get('category_total', 0):,.0f}", 0, 1, "R")
            grand += cat.get("category_total", 0)
            pdf.ln(2)

    # ============ ROOM-WISE ============
    if doc.get("room_totals") and not is_consult:
        pdf.add_page()
        header_section("04 / Room-wise Cost Mapping")
        pdf.cell(0, 9, _safe("Cost broken down by room."), ln=1)
        hr()
        pdf.set_font("Helvetica", "B", 9)
        pdf.set_fill_color(0, 0, 0)
        pdf.set_text_color(255, 255, 255)
        pdf.cell(120, 7, "  Room", 0, 0, "L", fill=True)
        pdf.cell(60, 7, "Total", 0, 1, "R", fill=True)
        pdf.set_text_color(*ink)
        pdf.set_font("Helvetica", "", 10)
        for r in doc.get("room_totals", []):
            pdf.cell(120, 6, _safe(f"  {r.get('room')}"), 0, 0, "L")
            pdf.cell(60, 6, f"{r.get('total', 0):,.0f}", 0, 1, "R")

    # ============ MATERIALS ============
    if doc.get("materials") and not is_consult:
        pdf.add_page()
        header_section("05 / Material Specifications")
        pdf.cell(0, 9, _safe("Brand-tier specifications."), ln=1)
        hr()
        pdf.set_font("Helvetica", "B", 8)
        pdf.set_fill_color(0, 0, 0)
        pdf.set_text_color(255, 255, 255)
        pdf.cell(45, 7, " Category", 0, 0, "L", fill=True)
        pdf.cell(45, 7, "Premium", 0, 0, "L", fill=True)
        pdf.cell(45, 7, "Standard", 0, 0, "L", fill=True)
        pdf.cell(45, 7, "Selected", 0, 1, "L", fill=True)
        pdf.set_text_color(*ink)
        pdf.set_font("Helvetica", "", 8)
        for m in doc.get("materials", []):
            pdf.cell(45, 5, _safe(m.get("category", ""))[:25], 0, 0)
            pdf.cell(45, 5, _safe(m.get("brand_premium", ""))[:25], 0, 0)
            pdf.cell(45, 5, _safe(m.get("brand_standard", ""))[:25], 0, 0)
            pdf.cell(45, 5, _safe(m.get("selected_tier", ""))[:25], 0, 1)

    # ============ COST SUMMARY (skipped when no commercials) ============
    cost = doc.get("cost") or {}
    if _has_boq or float(cost.get("grand_total") or 0) > 0:
        pdf.add_page()
        header_section("06 / Cost Summary")
        pdf.cell(0, 9, _safe("Final commercials."), ln=1)
        hr()
        rows = [
            ("Subtotal (Professional Fees)" if is_consult else "Subtotal (BOQ)", cost.get("subtotal", 0)),
            (f"Discount ({cost.get('discount_pct', 0)}%)", -cost.get("discount_amt", 0)),
            (f"Contingency ({cost.get('contingency_pct', 0)}%)", cost.get("contingency_amt", 0)),
            (f"GST ({cost.get('tax_pct', 18)}%)", cost.get("tax_amt", 0)),
        ]
        # Hide zero-value adjustment rows for a clean corporate output
        rows = [(l, v) for i, (l, v) in enumerate(rows) if i == 0 or abs(float(v or 0)) > 0.005]
        pdf.set_font("Helvetica", "", 11)
        for label, val in rows:
            pdf.cell(140, 7, _safe(label), 0, 0, "R")
            pdf.cell(40, 7, f"{val:,.0f}", 0, 1, "R")
        pdf.set_draw_color(*ink)
        pdf.set_line_width(0.4)
        pdf.line(15, pdf.get_y(), 195, pdf.get_y())
        pdf.ln(2)
        pdf.set_font("Helvetica", "B", 14)
        pdf.cell(140, 9, "GRAND TOTAL", 0, 0, "R")
        pdf.set_text_color(*klein)
        pdf.cell(40, 9, f"{cost.get('grand_total', 0):,.0f}", 0, 1, "R")
        pdf.set_text_color(*ink)

    # ============ PAYMENT PLAN ============
    if doc.get("payment_plan"):
        pdf.add_page()
        header_section("07 / Payment Plan")
        pdf.cell(0, 9, _safe("Milestone-linked schedule."), ln=1)
        hr()
        pdf.set_font("Helvetica", "B", 9)
        pdf.set_fill_color(0, 0, 0)
        pdf.set_text_color(255, 255, 255)
        pdf.cell(80, 7, "  Milestone", 0, 0, "L", fill=True)
        pdf.cell(25, 7, "%", 0, 0, "R", fill=True)
        pdf.cell(35, 7, "Amount", 0, 0, "R", fill=True)
        pdf.cell(40, 7, "Due (days)", 0, 1, "R", fill=True)
        pdf.set_text_color(*ink)
        pdf.set_font("Helvetica", "", 10)
        for p in doc.get("payment_plan", []):
            pdf.cell(80, 6, _safe(f"  {p.get('label', '')}"), 0, 0)
            pdf.cell(25, 6, f"{p.get('percentage', 0):g}%", 0, 0, "R")
            pdf.cell(35, 6, f"{p.get('amount', 0):,.0f}", 0, 0, "R")
            pdf.cell(40, 6, _safe(f"{p.get('due_after_days', 0)}"), 0, 1, "R")

    # ============ TIMELINE ============
    if doc.get("timeline"):
        pdf.add_page()
        header_section("08 / Timeline")
        pdf.cell(0, 9, _safe(f"Total: {doc.get('total_duration_weeks', 0)} weeks"), ln=1)
        hr()
        pdf.set_font("Helvetica", "B", 9)
        pdf.set_fill_color(0, 0, 0)
        pdf.set_text_color(255, 255, 255)
        pdf.cell(100, 7, "  Phase", 0, 0, "L", fill=True)
        pdf.cell(40, 7, "Start (wk)", 0, 0, "R", fill=True)
        pdf.cell(40, 7, "Duration (wk)", 0, 1, "R", fill=True)
        pdf.set_text_color(*ink)
        pdf.set_font("Helvetica", "", 10)
        for t in doc.get("timeline", []):
            pdf.cell(100, 6, _safe(f"  {t.get('phase', '')}"), 0, 0)
            pdf.cell(40, 6, f"{t.get('start_offset_weeks', 0):g}", 0, 0, "R")
            pdf.cell(40, 6, f"{t.get('duration_weeks', 0):g}", 0, 1, "R")

    # ============ TERMS ============
    if doc.get("terms"):
        pdf.add_page()
        header_section("09 / Terms & Conditions")
        pdf.cell(0, 9, _safe("Smart blocks."), ln=1)
        hr()
        for t in doc.get("terms", []):
            pdf.set_font("Helvetica", "B", 10)
            pdf.cell(0, 6, _safe(t.get("section", "")), ln=1)
            pdf.set_font("Helvetica", "", 9)
            pdf.multi_cell(0, 4.5, _safe(t.get("content", "")))
            pdf.ln(2)

    # ============ SIGNATURE ============
    pdf.add_page()
    header_section("10 / Acceptance & Signature")
    pdf.cell(0, 9, _safe("This quotation is binding once signed."), ln=1)
    hr()
    pdf.ln(20)
    y = pdf.get_y()
    pdf.set_draw_color(*ink)
    pdf.line(20, y + 25, 95, y + 25)
    pdf.line(115, y + 25, 190, y + 25)
    pdf.set_xy(20, y + 27)
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(75, 5, _safe(f"FOR {org_name.upper()}"), 0, 0)
    pdf.set_xy(115, y + 27)
    pdf.cell(75, 5, _safe(f"FOR {(doc.get('client_name') or 'CLIENT').upper()}"), 0, 1)
    pdf.set_xy(20, y + 32)
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(*grey)
    pdf.cell(75, 5, _safe("Authorised signatory"), 0, 0)
    pdf.set_xy(115, y + 32)
    pdf.cell(75, 5, _safe("Authorised signatory"), 0, 1)

    # Page numbers footer (alias)
    pdf.alias_nb_pages()

    output = pdf.output(dest="S")
    if isinstance(output, str):
        return output.encode("latin-1")
    return bytes(output)


@api.get("/quotations-adv/{qid}/pdf")
async def adv_pdf(qid: str, request: Request, session_token: Optional[str] = Cookie(default=None),
                  authorization: Optional[str] = Header(default=None)):
    await require_user(request, session_token, authorization)
    doc = await sdb.quotations_adv.find_one({"id": qid}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Not found")
    _org = None
    if doc.get("org_id"):
        _org = await db.organizations.find_one({"org_id": doc["org_id"]}, {"_id": 0})
    pdf_bytes = generate_quotation_pdf_adv(doc, _org)
    return StreamingResponse(io.BytesIO(pdf_bytes), media_type="application/pdf",
                             headers={"Content-Disposition": f'inline; filename="{doc.get("number", qid)}.pdf"'})


# ---------- Seed an advanced quotation example ----------
@api.post("/quotations-adv/seed")
async def adv_seed(request: Request, session_token: Optional[str] = Cookie(default=None),
                   authorization: Optional[str] = Header(default=None)):
    if os.environ.get("ENABLE_SEED_DEMO", "").lower() not in ("1", "true", "yes"):
        raise HTTPException(status_code=403,
                            detail="Demo seeding disabled. Set ENABLE_SEED_DEMO=true to enable.")
    user = await require_user(request, session_token, authorization)
    # find first project
    projects = await sdb.projects.find({}, {"_id": 0}).to_list(5)
    proj = projects[0] if projects else None

    payload = {
        "type": "turnkey",
        "project_title": (proj.get("name") if proj else "Turnkey Residence – 4BHK") + " (Quotation)",
        "client_id": (proj.get("client_id") if proj else None),
        "client_name": (proj.get("client_name") if proj else "Aravind Menon"),
        "project_id": (proj.get("id") if proj else None),
        "project_location": "Bandra West, Mumbai",
        "area_sqft": 2400,
    }
    doc = _new_quotation_doc(payload, user)

    # Build BOQ from templates with rooms
    boq = []
    for cat_name in ["Civil & Finishes", "Kitchen", "Wardrobe", "Electrical", "Bathroom"]:
        items = []
        for tpl in BOQ_TEMPLATES.get(cat_name, []):
            it = tpl.copy()
            it["code"] = f"{cat_name[:3].upper()}-{new_id()[:5]}"
            it["amount"] = it["quantity"] * it["rate"] * (1 + it["margin_pct"] / 100)
            it["room"] = ("Kitchen" if cat_name == "Kitchen" else
                          "Master Bedroom" if cat_name == "Wardrobe" else
                          "Master Bath" if cat_name == "Bathroom" else
                          "Living Room")
            it["brand_tier"] = "Standard"
            items.append(it)
        boq.append({"category": cat_name, "items": items, "category_total": 0})
    doc["boq"] = boq
    doc["client_requirement"] = "A 4BHK duplex for a young family of four. Warm, contemporary, low-maintenance, and entertainment-friendly."
    doc["design_intent"] = "Layered neutrals with brass accents, fluted teak panelling, and statement lighting. Library-led living, hospitable kitchen, and a quiet master suite."
    doc["highlights"] = {"budget_range": "₹50L – ₹70L", "timeline": "14 weeks", "quality_level": "Premium"}
    doc["design_scope"] = [
        "Concept and design development for all 9 spaces",
        "Material/finish selection with branded swatches",
        "Furniture & lighting curation (loose & fixed)",
        "10 photoreal renders (key views)",
    ]
    doc["execution_scope"] = [
        "Civil works incl. demolition, plaster, POP false ceiling",
        "All modular furniture (kitchen, wardrobes, TV unit, foyer)",
        "Painting, wall treatments, wallpapers in 3 spaces",
        "Electrical wiring, switches, lights & fans",
    ]
    doc["exclusions"] = [
        "Loose furniture, soft furnishing & art (curated separately)",
        "Society NOC, BMC permissions",
        "Major plumbing relocation beyond 2 ft of existing risers",
    ]
    doc = _q_compute_costs(doc)
    count = await sdb.quotations_adv.count_documents({})
    doc["number"] = f"Q-2026-{1000 + count + 1}"
    await sdb.quotations_adv.insert_one(dict(doc))
    return {"id": doc["id"], "number": doc["number"]}




@api.get("/")
async def root():
    return {"service": "Design Saga API", "status": "ok"}


# ============================================================
# MODULE 2 — Employee Management
# HR records (separate from `users` which is auth). Optional 1:1 link
# via `user_id`. Includes salary math, warnings, rewards, documents.
# ============================================================
EMPLOYMENT_TYPES = ["full_time", "part_time", "contract", "intern"]
EMPLOYMENT_STATUSES = ["active", "probation", "notice", "terminated"]
DEPARTMENTS_DEFAULT = [
    "Design", "Site Execution", "Sales & CRM", "Finance",
    "HR", "Operations", "Leadership",
]


class SalaryStructure(BaseModel):
    basic: float = 0
    hra: float = 0
    conveyance: float = 0
    medical: float = 0
    other_allowances: float = 0
    pf_employee: float = 0
    esi_employee: float = 0
    professional_tax: float = 0
    tds: float = 0


class BankInfo(BaseModel):
    account_holder: Optional[str] = ""
    account_number: Optional[str] = ""
    ifsc: Optional[str] = ""
    bank_name: Optional[str] = ""
    upi: Optional[str] = ""


class EmergencyContact(BaseModel):
    name: Optional[str] = ""
    phone: Optional[str] = ""
    relation: Optional[str] = ""


class EmployeeIn(BaseModel):
    first_name: str
    last_name: Optional[str] = ""
    email: Optional[str] = ""
    phone: Optional[str] = ""
    photo: Optional[str] = ""
    dob: Optional[str] = ""
    gender: Optional[str] = ""
    blood_group: Optional[str] = ""
    aadhaar: Optional[str] = ""
    pan: Optional[str] = ""
    address: Optional[str] = ""
    city: Optional[str] = ""
    state: Optional[str] = ""
    pincode: Optional[str] = ""
    emergency_contact: Optional[EmergencyContact] = None
    department: Optional[str] = "Design"
    designation: Optional[str] = ""
    employment_type: Optional[str] = "full_time"
    employment_status: Optional[str] = "active"
    joining_date: Optional[str] = None
    probation_end_date: Optional[str] = None
    notice_period_days: Optional[int] = 30
    shift_start: Optional[str] = "09:00"
    shift_end: Optional[str] = "18:00"
    weekly_hours: Optional[int] = 45
    reporting_to: Optional[str] = None
    user_id: Optional[str] = None
    salary: Optional[SalaryStructure] = None
    bank: Optional[BankInfo] = None
    # --- Merged from Jewellers ERP (attendance + payroll config) ---
    grace_minutes: Optional[int] = None            # late-mark grace override
    weekly_offs: Optional[List[int]] = None        # [0..6] 0=Mon; None = org policy
    geofence_ids: Optional[List[str]] = None       # allowed fences; None/[] = all
    half_day_min_minutes: Optional[int] = None
    full_day_min_minutes: Optional[int] = None
    monthly_salary: Optional[float] = None         # flat fallback (no structure)
    payroll_basis_days: Optional[int] = 26


class EmployeeUpdate(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    photo: Optional[str] = None
    dob: Optional[str] = None
    gender: Optional[str] = None
    blood_group: Optional[str] = None
    aadhaar: Optional[str] = None
    pan: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    pincode: Optional[str] = None
    emergency_contact: Optional[EmergencyContact] = None
    department: Optional[str] = None
    designation: Optional[str] = None
    employment_type: Optional[str] = None
    employment_status: Optional[str] = None
    joining_date: Optional[str] = None
    probation_end_date: Optional[str] = None
    notice_period_days: Optional[int] = None
    shift_start: Optional[str] = None
    shift_end: Optional[str] = None
    weekly_hours: Optional[int] = None
    reporting_to: Optional[str] = None
    user_id: Optional[str] = None
    salary: Optional[SalaryStructure] = None
    bank: Optional[BankInfo] = None
    current_kpi_score: Optional[float] = None
    # --- Merged from Jewellers ERP (attendance + payroll config) ---
    grace_minutes: Optional[int] = None
    weekly_offs: Optional[List[int]] = None
    geofence_ids: Optional[List[str]] = None
    half_day_min_minutes: Optional[int] = None
    full_day_min_minutes: Optional[int] = None
    monthly_salary: Optional[float] = None
    payroll_basis_days: Optional[int] = None


class DocumentIn(BaseModel):
    label: str
    url: str


class WarningIn(BaseModel):
    reason: str
    note: Optional[str] = ""


class RewardIn(BaseModel):
    title: str
    note: Optional[str] = ""


def _compute_salary(s: dict) -> dict:
    """Recompute derived salary fields on top of the input structure."""
    s = dict(s or {})
    gross = sum(float(s.get(k, 0) or 0) for k in
                ("basic", "hra", "conveyance", "medical", "other_allowances"))
    ded = sum(float(s.get(k, 0) or 0) for k in
              ("pf_employee", "esi_employee", "professional_tax", "tds"))
    s["gross_monthly"] = round(gross, 2)
    s["total_deductions"] = round(ded, 2)
    s["net_monthly"] = round(gross - ded, 2)
    s["ctc_annual"] = round(gross * 12, 2)
    return s


async def _next_employee_id() -> str:
    year = now_utc().year
    count = await sdb.employees.count_documents({"employee_id": {"$regex": f"^EMP-{year}-"}})
    return f"EMP-{year}-{count + 1:04d}"


@api.get("/employees")
async def list_employees(request: Request,
                         department: Optional[str] = None,
                         status: Optional[str] = None,
                         session_token: Optional[str] = Cookie(default=None),
                         authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    if not has_permission(user, "employees.read"):
        raise HTTPException(status_code=403, detail="Missing permission: employees.read")
    q = {}
    if department:
        q["department"] = department
    if status:
        q["employment_status"] = status
    rows = await sdb.employees.find(q, {"_id": 0}).sort("created_at", -1).to_list(1000)
    return rows


@api.get("/employees/meta")
async def employee_meta(request: Request,
                        session_token: Optional[str] = Cookie(default=None),
                        authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    if not has_permission(user, "employees.read"):
        raise HTTPException(status_code=403, detail="Missing permission: employees.read")
    from routes.master_data import get_values as _md_values
    from core.tenancy import user_org_id as _uoid
    _org = _uoid(user)
    seen = set()
    async for e in sdb.employees.find({}, {"_id": 0, "department": 1}):
        if e.get("department"):
            seen.add(e["department"])
    md_departments = await _md_values(_org, "department", DEPARTMENTS_DEFAULT) if _org else DEPARTMENTS_DEFAULT
    departments = sorted(set(md_departments) | seen)
    designations = await _md_values(_org, "designation", []) if _org else []
    return {
        "departments": departments,
        "designations": designations,
        "employment_types": EMPLOYMENT_TYPES,
        "employment_statuses": EMPLOYMENT_STATUSES,
    }


@api.get("/employees/{eid}")
async def get_employee(eid: str, request: Request,
                       session_token: Optional[str] = Cookie(default=None),
                       authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    if not has_permission(user, "employees.read"):
        raise HTTPException(status_code=403, detail="Missing permission: employees.read")
    doc = await sdb.employees.find_one({"id": eid}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Employee not found")
    return doc


@api.post("/employees")
async def create_employee(payload: EmployeeIn, request: Request,
                          session_token: Optional[str] = Cookie(default=None),
                          authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    if not has_permission(user, "employees.create"):
        raise HTTPException(status_code=403, detail="Missing permission: employees.create")
    data = payload.model_dump()
    if data.get("employment_type") not in EMPLOYMENT_TYPES:
        data["employment_type"] = "full_time"
    if data.get("employment_status") not in EMPLOYMENT_STATUSES:
        data["employment_status"] = "active"
    data["salary"] = _compute_salary(data.get("salary") or {})
    data["bank"] = data.get("bank") or {}
    data["emergency_contact"] = data.get("emergency_contact") or {}
    data["documents"] = []
    data["performance"] = {
        "current_kpi_score": 0,
        "last_review_at": None,
        "warnings": [],
        "rewards": [],
    }
    data["id"] = new_id("emp_")
    data["employee_id"] = await _next_employee_id()
    data["created_at"] = iso(now_utc())
    data["created_by"] = user["user_id"]
    await sdb.employees.insert_one(dict(data))
    return await sdb.employees.find_one({"id": data["id"]}, {"_id": 0})


@api.put("/employees/{eid}")
async def update_employee(eid: str, payload: EmployeeUpdate, request: Request,
                          session_token: Optional[str] = Cookie(default=None),
                          authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    if not has_permission(user, "employees.update"):
        raise HTTPException(status_code=403, detail="Missing permission: employees.update")
    doc = await sdb.employees.find_one({"id": eid}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Employee not found")
    patch = {k: v for k, v in payload.model_dump().items() if v is not None}
    if "salary" in patch:
        patch["salary"] = _compute_salary(patch["salary"])
    if "current_kpi_score" in patch:
        perf = dict(doc.get("performance") or {})
        perf["current_kpi_score"] = patch.pop("current_kpi_score")
        patch["performance"] = perf
    if "employment_type" in patch and patch["employment_type"] not in EMPLOYMENT_TYPES:
        raise HTTPException(status_code=400, detail="Invalid employment_type")
    if "employment_status" in patch and patch["employment_status"] not in EMPLOYMENT_STATUSES:
        raise HTTPException(status_code=400, detail="Invalid employment_status")
    patch["updated_at"] = iso(now_utc())
    patch["updated_by"] = user["user_id"]
    await sdb.employees.update_one({"id": eid}, {"$set": patch})
    return await sdb.employees.find_one({"id": eid}, {"_id": 0})


@api.delete("/employees/{eid}")
async def delete_employee(eid: str, request: Request,
                          session_token: Optional[str] = Cookie(default=None),
                          authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    if not has_permission(user, "employees.delete"):
        raise HTTPException(status_code=403, detail="Missing permission: employees.delete")
    res = await sdb.employees.delete_one({"id": eid})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Employee not found")
    return {"ok": True}


@api.get("/employees/{eid}/account")
async def get_employee_account(eid: str, request: Request,
                               session_token: Optional[str] = Cookie(default=None),
                               authorization: Optional[str] = Header(default=None)):
    """ERP identity linked to this employee — login, role, status."""
    user = await require_user(request, session_token, authorization)
    if not has_permission(user, "employees.read"):
        raise HTTPException(status_code=403, detail="Missing permission: employees.read")
    emp = await sdb.employees.find_one({"id": eid}, {"_id": 0})
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")
    linked = None
    if emp.get("user_id"):
        linked = await db.users.find_one({"user_id": emp["user_id"]}, {"_id": 0, "password_hash": 0})
    if not linked and emp.get("email"):
        linked = await db.users.find_one(
            {"email": emp["email"].lower(), "org_id": user.get("org_id") or "org_default"},
            {"_id": 0, "password_hash": 0})
    if linked:
        return {"linked": True, "user": {
            "user_id": linked["user_id"], "email": linked.get("email"),
            "employee_id": linked.get("employee_id"), "role": linked.get("role"),
            "is_active": linked.get("is_active", True),
            "approval_status": linked.get("approval_status"),
            "last_login": linked.get("last_login"),
        }}
    return {"linked": False, "user": None}


class EmployeeAccountIn(BaseModel):
    password: str = Field(min_length=8, max_length=128)
    role: str = "Employee"
    email: Optional[str] = None       # defaults to the employee's email


@api.post("/employees/{eid}/account")
async def create_employee_account(eid: str, payload: EmployeeAccountIn, request: Request,
                                  session_token: Optional[str] = Cookie(default=None),
                                  authorization: Optional[str] = Header(default=None)):
    """Create the ERP login for an employee in one step (Admin only).
    Links the new user back to the employee record."""
    user = await require_user(request, session_token, authorization)
    if not has_permission(user, "*.*"):
        raise HTTPException(status_code=403, detail="Admin only")
    emp = await sdb.employees.find_one({"id": eid}, {"_id": 0})
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")
    email = (payload.email or emp.get("email") or "").lower().strip()
    if not email:
        raise HTTPException(status_code=400, detail="Employee has no email — provide one")
    if await db.users.find_one({"email": email}):
        raise HTTPException(status_code=409, detail="Email already registered")
    from routes.auth import hash_password as _hash_pw
    from core.rbac import normalize_role as _norm_role
    role = _norm_role(payload.role)
    org_id = user.get("org_id") or emp.get("org_id") or "org_default"
    # Plan limit check
    _org = await db.organizations.find_one({"org_id": org_id}, {"_id": 0, "features": 1})
    _max = ((_org or {}).get("features") or {}).get("limits", {}).get("max_users")
    if _max:
        _current = await db.users.count_documents({"org_id": org_id, "is_active": {"$ne": False}})
        if _current >= _max:
            raise HTTPException(status_code=402,
                                detail=f"User limit reached ({_current}/{_max}). Upgrade your plan.")
    new_user = {
        "user_id": f"user_{uuid.uuid4().hex[:12]}",
        "org_id": org_id,
        "employee_id": emp.get("employee_id"),
        "email": email,
        "name": f"{emp.get('first_name', '')} {emp.get('last_name', '')}".strip() or email,
        "phone": emp.get("phone"),
        "role": role,
        "password_hash": _hash_pw(payload.password),
        "is_active": True,
        "approval_status": "approved",
        "created_at": iso(now_utc()),
        "created_by": user["user_id"],
    }
    await db.users.insert_one(dict(new_user))
    await sdb.employees.update_one({"id": eid}, {"$set": {"user_id": new_user["user_id"]}})
    return {"ok": True, "user_id": new_user["user_id"], "email": email, "role": role}


class EmployeeAccountStatusIn(BaseModel):
    active: bool


@api.post("/employees/{eid}/account/status")
async def set_employee_account_status(eid: str, payload: EmployeeAccountStatusIn, request: Request,
                                      session_token: Optional[str] = Cookie(default=None),
                                      authorization: Optional[str] = Header(default=None)):
    """Activate / deactivate the employee's ERP login (Admin only)."""
    user = await require_user(request, session_token, authorization)
    if not has_permission(user, "*.*"):
        raise HTTPException(status_code=403, detail="Admin only")
    emp = await sdb.employees.find_one({"id": eid}, {"_id": 0})
    if not emp or not emp.get("user_id"):
        raise HTTPException(status_code=404, detail="No linked ERP account")
    target = await db.users.find_one({"user_id": emp["user_id"]}, {"_id": 0})
    if not target:
        raise HTTPException(status_code=404, detail="Linked user not found")
    if target["user_id"] == user["user_id"] and not payload.active:
        raise HTTPException(status_code=400, detail="You cannot deactivate your own account")
    await db.users.update_one({"user_id": emp["user_id"]},
                              {"$set": {"is_active": payload.active}})
    if not payload.active:
        await db.user_sessions.delete_many({"user_id": emp["user_id"]})
    return {"ok": True, "is_active": payload.active}


@api.post("/employees/{eid}/documents")
async def add_employee_doc(eid: str, payload: DocumentIn, request: Request,
                           session_token: Optional[str] = Cookie(default=None),
                           authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    if not has_permission(user, "employees.update"):
        raise HTTPException(status_code=403, detail="Missing permission: employees.update")
    entry = {"id": new_id("edoc_"), "label": payload.label, "url": payload.url,
             "uploaded_at": iso(now_utc()), "uploaded_by": user.get("name")}
    res = await sdb.employees.update_one(
        {"id": eid},
        {"$push": {"documents": entry}, "$set": {"updated_at": iso(now_utc())}},
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Employee not found")
    return entry


@api.delete("/employees/{eid}/documents/{doc_id}")
async def remove_employee_doc(eid: str, doc_id: str, request: Request,
                              session_token: Optional[str] = Cookie(default=None),
                              authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    if not has_permission(user, "employees.update"):
        raise HTTPException(status_code=403, detail="Missing permission: employees.update")
    await sdb.employees.update_one(
        {"id": eid},
        {"$pull": {"documents": {"id": doc_id}}, "$set": {"updated_at": iso(now_utc())}},
    )
    return {"ok": True}


@api.post("/employees/{eid}/warnings")
async def add_warning(eid: str, payload: WarningIn, request: Request,
                      session_token: Optional[str] = Cookie(default=None),
                      authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    if not has_permission(user, "employees.update"):
        raise HTTPException(status_code=403, detail="Missing permission: employees.update")
    entry = {"id": new_id("warn_"), "reason": payload.reason, "note": payload.note,
             "at": iso(now_utc()), "by": user.get("name")}
    res = await sdb.employees.update_one(
        {"id": eid},
        {"$push": {"performance.warnings": entry}, "$set": {"updated_at": iso(now_utc())}},
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Employee not found")
    return entry


@api.post("/employees/{eid}/rewards")
async def add_reward(eid: str, payload: RewardIn, request: Request,
                     session_token: Optional[str] = Cookie(default=None),
                     authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    if not has_permission(user, "employees.update"):
        raise HTTPException(status_code=403, detail="Missing permission: employees.update")
    entry = {"id": new_id("rwd_"), "title": payload.title, "note": payload.note,
             "at": iso(now_utc()), "by": user.get("name")}
    res = await sdb.employees.update_one(
        {"id": eid},
        {"$push": {"performance.rewards": entry}, "$set": {"updated_at": iso(now_utc())}},
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Employee not found")
    return entry


@api.post("/employees/seed")
async def seed_employees(request: Request,
                         session_token: Optional[str] = Cookie(default=None),
                         authorization: Optional[str] = Header(default=None)):
    if os.environ.get("ENABLE_SEED_DEMO", "").lower() not in ("1", "true", "yes"):
        raise HTTPException(status_code=403,
                            detail="Demo seeding disabled. Set ENABLE_SEED_DEMO=true to enable.")
    user = await require_user(request, session_token, authorization)
    if not has_permission(user, "*.*"):
        raise HTTPException(status_code=403, detail="Admin only")
    samples = [
        ("Ananya", "Sharma", "Design", "Senior Interior Designer",
         {"basic": 45000, "hra": 18000, "conveyance": 3200, "medical": 1250, "other_allowances": 5500,
          "pf_employee": 3600, "esi_employee": 0, "professional_tax": 200, "tds": 4200}),
        ("Rohit", "Kulkarni", "Design", "Architect",
         {"basic": 55000, "hra": 22000, "conveyance": 3200, "medical": 1250, "other_allowances": 7500,
          "pf_employee": 3600, "esi_employee": 0, "professional_tax": 200, "tds": 6800}),
        ("Meera", "Iyer", "Sales & CRM", "Business Development Manager",
         {"basic": 38000, "hra": 15200, "conveyance": 3200, "medical": 1250, "other_allowances": 4500,
          "pf_employee": 3600, "esi_employee": 0, "professional_tax": 200, "tds": 3100}),
        ("Vikram", "Patel", "Site Execution", "Site Supervisor",
         {"basic": 28000, "hra": 11200, "conveyance": 3200, "medical": 1250, "other_allowances": 3500,
          "pf_employee": 3200, "esi_employee": 460, "professional_tax": 200, "tds": 0}),
        ("Priyanka", "Rao", "Finance", "Accountant",
         {"basic": 40000, "hra": 16000, "conveyance": 3200, "medical": 1250, "other_allowances": 4000,
          "pf_employee": 3600, "esi_employee": 0, "professional_tax": 200, "tds": 3400}),
        ("Nitin", "Verma", "HR", "HR Executive",
         {"basic": 30000, "hra": 12000, "conveyance": 3200, "medical": 1250, "other_allowances": 3000,
          "pf_employee": 3600, "esi_employee": 0, "professional_tax": 200, "tds": 1200}),
    ]
    created = []
    for fn, ln, dept, desig, salary in samples:
        eid = new_id("emp_")
        emp_no = await _next_employee_id()
        doc = {
            "id": eid,
            "employee_id": emp_no,
            "first_name": fn, "last_name": ln,
            "email": f"{fn.lower()}.{ln.lower()}@designsaga.co",
            "phone": f"+91 9{80000000 + len(created) * 111111:08d}",
            "photo": "",
            "dob": "", "gender": "", "blood_group": "",
            "aadhaar": "", "pan": "",
            "address": "Mumbai, MH", "city": "Mumbai",
            "state": "Maharashtra", "pincode": "400001",
            "emergency_contact": {"name": "", "phone": "", "relation": ""},
            "department": dept, "designation": desig,
            "employment_type": "full_time", "employment_status": "active",
            "joining_date": (now_utc() - timedelta(days=180 + len(created) * 30)).date().isoformat(),
            "probation_end_date": None, "notice_period_days": 30,
            "shift_start": "09:30", "shift_end": "18:30",
            "weekly_hours": 45, "reporting_to": None, "user_id": None,
            "salary": _compute_salary(salary),
            "bank": {"account_holder": f"{fn} {ln}",
                     "account_number": "", "ifsc": "", "bank_name": "", "upi": ""},
            "documents": [],
            "performance": {"current_kpi_score": 70 + len(created) * 4,
                            "last_review_at": None, "warnings": [], "rewards": []},
            "created_at": iso(now_utc()),
            "created_by": user["user_id"],
        }
        await sdb.employees.insert_one(dict(doc))
        created.append(emp_no)
    return {"ok": True, "created": created}



# ============================================================
# Register router & middleware
# ============================================================
# Include modular routers (Phase-1 refactor: Tasks module extracted)
from routes.tasks import router as tasks_router  # noqa: E402
from routes.attendance import router as attendance_router  # noqa: E402
from routes.accounting import router as accounting_router  # noqa: E402
from routes.payroll import router as payroll_router  # noqa: E402
from routes.vendors import router as vendors_router  # noqa: E402
from routes.auth import router as auth_router  # noqa: E402
from routes.notifications import router as notifications_router  # noqa: E402
from routes.platform import router as platform_router  # noqa: E402
from routes.organization import router as organization_router  # noqa: E402
from routes.loans import router as loans_router  # noqa: E402
from routes.audit import router as audit_router  # noqa: E402
from routes.purchase import router as purchase_router  # noqa: E402
from routes.expenses import router as expenses_router  # noqa: E402
from routes.holidays import router as holidays_router  # noqa: E402
from routes.master_data import router as master_data_router  # noqa: E402
from routes.search import router as search_router  # noqa: E402
from routes.comments import router as comments_router  # noqa: E402
from routes.calendar import router as calendar_router  # noqa: E402
api.include_router(tasks_router)
api.include_router(attendance_router)
api.include_router(accounting_router)
api.include_router(payroll_router)
api.include_router(vendors_router)
api.include_router(auth_router)
api.include_router(notifications_router)
api.include_router(platform_router)
api.include_router(organization_router)
api.include_router(loans_router)
api.include_router(audit_router)
api.include_router(purchase_router)
api.include_router(expenses_router)
api.include_router(holidays_router)
api.include_router(master_data_router)
api.include_router(search_router)
api.include_router(comments_router)
api.include_router(calendar_router)

app.include_router(api)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# Multi-tenant bootstrap: ensure a default org exists + backfill
# ============================================================
@app.on_event("startup")
async def _bootstrap_default_org():
    """Idempotently create the default Design Saga organisation and
    backfill `org_id` onto every legacy document that predates the
    multi-tenant migration."""
    from core.tenancy import DEFAULT_ORG_ID, DEFAULT_ORG_SLUG
    default = await db.organizations.find_one({"org_id": DEFAULT_ORG_ID}, {"_id": 0})
    if not default:
        from models.organization import features_for_mode as _feats
        await db.organizations.insert_one({
            "org_id": DEFAULT_ORG_ID,
            "slug": DEFAULT_ORG_SLUG,
            "name": "Design Saga",
            "display_name": "Design Saga",
            "business_mode": "hybrid",
            "industry": "Architecture & Interior Design",
            "plan": "enterprise",
            "address": {"country": "India"},
            "branding": {
                "primary_color": "#002FA7",
                "accent_color": "#0A0A0A",
                "tagline": "Studio OS · v0.2",
                "logo_url": None,
            },
            "features": {
                "modules": _feats("hybrid"),
                "limits": {"max_users": 500, "max_projects": 10000, "storage_mb": 5000},
            },
            "is_active": True,
            "is_suspended": False,
            "is_default": True,
            "created_at": iso(now_utc()),
            "created_by": "system",
        })
        logger.info("[Bootstrap] Created default organisation: %s", DEFAULT_ORG_ID)
    else:
        # Retro-fit business_mode + full features on legacy default org
        updates = {}
        if not default.get("business_mode"):
            updates["business_mode"] = "hybrid"
        if not (default.get("features") or {}).get("modules", {}).get("procurement"):
            from models.organization import features_for_mode as _feats
            updates["features"] = {
                "modules": _feats("hybrid"),
                "limits": (default.get("features") or {}).get("limits",
                          {"max_users": 500, "max_projects": 10000, "storage_mb": 5000}),
            }
        if updates:
            await db.organizations.update_one({"org_id": DEFAULT_ORG_ID}, {"$set": updates})
            logger.info("[Bootstrap] Retro-fit default org: %s", list(updates.keys()))

    # Backfill org_id on all legacy collections (only where missing)
    collections = [
        "users", "leads", "clients", "projects", "tasks", "invoices",
        "quotations", "quotations_adv", "employees",
        "vendors_acc", "vendor_bills", "vendor_payments", "vendor_commissions",
        "attendance", "leave_applications", "leave_rules",
        "journal_entries", "accounts", "payroll_runs",
        "notifications", "files", "milestones",
        "payment_milestones", "calendar_events", "holidays", "office_locations",
        "expenses", "purchase_orders", "goods_receipts", "loans",
        "vendor_ratings", "commission_settlements", "attendance_corrections",
        "leaves", "comments",
    ]
    total = 0
    for coll in collections:
        try:
            res = await db[coll].update_many(
                {"$or": [{"org_id": {"$exists": False}}, {"org_id": None}]},
                {"$set": {"org_id": DEFAULT_ORG_ID}},
            )
            if res.modified_count:
                logger.info("[Bootstrap] %s: backfilled %d docs", coll, res.modified_count)
                total += res.modified_count
        except Exception as e:
            logger.warning("[Bootstrap] backfill %s skipped: %s", coll, e)

    # Elevate whitelisted super-admin users to the SuperAdmin role
    for sa_email in SUPER_ADMIN_EMAILS:
        u = await db.users.find_one({"email": sa_email}, {"_id": 0})
        if u and _normalize_role(u.get("role")) != "SuperAdmin":
            await db.users.update_one(
                {"user_id": u["user_id"]},
                {"$set": {"role": "SuperAdmin", "is_active": True,
                          "approval_status": "approved"},
                 "$unset": {"org_id": ""}},
            )
            logger.info("[Bootstrap] Elevated %s to SuperAdmin", sa_email)

    if total:
        logger.info("[Bootstrap] Multi-tenant backfill complete: %d docs updated", total)

    # ==============================================
    # Ensure Mongo indexes (idempotent)
    # ==============================================
    try:
        from core.indexes import ensure_indexes
        await ensure_indexes()
        logger.info("[Bootstrap] Mongo indexes ensured")
    except Exception as e:
        logger.warning("[Bootstrap] Index setup skipped: %s", e)

    # ==============================================
    # Production safety warning
    # ==============================================
    if "designsaga10@gmail.com" in SUPER_ADMIN_EMAILS and len(SUPER_ADMIN_EMAILS) == 1:
        env_flag = os.environ.get("ENV") or os.environ.get("EMERGENT_ENV") or ""
        if env_flag.lower() in ("prod", "production"):
            logger.warning(
                "[SECURITY] SUPER_ADMIN_EMAILS is still the default in production. "
                "Whoever registers %s becomes SuperAdmin — change this env var!",
                "designsaga10@gmail.com",
            )

    # ==============================================
    # Object storage (best-effort — no-op if key missing)
    # ==============================================
    try:
        from services import storage as _storage
        if _storage.init_storage():
            logger.info("Object storage initialised")
    except Exception as e:  # noqa: BLE001
        logger.warning("Object storage init failed: %s", e)

    # ==============================================
    # Background scheduler — automated notification scan for every org
    # (due/overdue invoices, vendor bills, milestones, tasks).
    # Runs shortly after boot, then every 6 hours. Idempotent per-day.
    # ==============================================
    async def _scan_loop():
        await asyncio.sleep(30)
        while True:
            try:
                from routes.notifications import scheduled_scan_all_orgs
                results = await scheduled_scan_all_orgs()
                logger.info("[Scheduler] notification scan complete: %s",
                            {k: v for k, v in list(results.items())[:5]})
            except Exception as exc:  # noqa: BLE001
                logger.warning("[Scheduler] scan failed: %s", exc)
            await asyncio.sleep(6 * 3600)

    app.state._scan_task = asyncio.create_task(_scan_loop())


@app.on_event("shutdown")
async def shutdown():
    client.close()
