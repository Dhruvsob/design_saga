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

EMERGENT_LLM_KEY = os.environ.get("EMERGENT_LLM_KEY")
EMERGENT_AUTH_BASE = "https://demobackend.emergentagent.com/auth/v1/env/oauth/session-data"

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
    token = session_token
    if not token and authorization and authorization.startswith("Bearer "):
        token = authorization.split(" ", 1)[1]
    if not token:
        return None

    session = await db.user_sessions.find_one({"session_token": token}, {"_id": 0})
    if not session:
        return None

    expires_at = session.get("expires_at")
    if isinstance(expires_at, str):
        expires_at = datetime.fromisoformat(expires_at)
    if expires_at and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at and expires_at < now_utc():
        return None

    user = await db.users.find_one({"user_id": session["user_id"]}, {"_id": 0})
    return user


async def require_user(request: Request, session_token: Optional[str] = Cookie(default=None),
                       authorization: Optional[str] = Header(default=None)):
    user = await get_current_user(request, session_token, authorization)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user


# ============================================================
# RBAC – Roles, Permissions, Guards
# ============================================================
ROLES = ["Admin", "Director", "ProjectManager", "Designer",
         "Accountant", "HR", "Employee", "Client"]

# Permission grammar: "resource.action" — supports wildcards.
#   "*.*"           → grants everything
#   "leads.*"       → grants every action on leads
#   "leads.delete"  → grants only that exact action
ROLE_PERMISSIONS = {
    "Admin": ["*.*"],
    "Director": [
        "leads.*", "projects.*", "tasks.*", "clients.*",
        "files.*", "invoices.*", "quotations.*",
        "employees.*",
        "users.read", "users.update",
        "dashboard.read", "ai.use", "rbac.read",
    ],
    "ProjectManager": [
        "leads.*", "projects.*", "tasks.*",
        "clients.read", "clients.create", "clients.update",
        "files.*", "invoices.read",
        "quotations.read", "quotations.create", "quotations.update",
        "employees.read",
        "users.read", "dashboard.read", "ai.use",
    ],
    "Designer": [
        "projects.read", "projects.update",
        "tasks.read", "tasks.create", "tasks.update",
        "files.*",
        "quotations.read", "quotations.create", "quotations.update",
        "clients.read", "leads.read",
        "employees.read",
        "dashboard.read", "ai.use",
    ],
    "Accountant": [
        "invoices.*", "quotations.*",
        "clients.read", "projects.read", "leads.read",
        "files.read", "dashboard.read", "ai.use",
        "employees.read",
    ],
    "HR": [
        "users.read", "users.update",
        "employees.*",
        "dashboard.read", "ai.use",
    ],
    "Employee": [
        "projects.read", "tasks.read", "tasks.update",
        "clients.read", "leads.read",
        "files.read", "files.create",
        "dashboard.read", "ai.use",
    ],
    "Client": [],  # Studio panel access denied; portal is a separate token-based flow.
}

# Legacy → new-casing mapping (safe forward migration for existing docs).
_LEGACY_ROLE_MAP = {
    "admin": "Admin",
    "employee": "Employee",
    "manager": "ProjectManager",
    "designer": "Designer",
    "accountant": "Accountant",
    "hr": "HR",
    "director": "Director",
    "owner": "Director",
    "client": "Client",
}


def _normalize_role(role: Optional[str]) -> str:
    if not role:
        return "Employee"
    if role in ROLES:
        return role
    return _LEGACY_ROLE_MAP.get(role.lower(), "Employee")


def _expand_permissions(role: str) -> List[str]:
    """Return the explicit list of grants for a role (wildcards preserved)."""
    return list(ROLE_PERMISSIONS.get(_normalize_role(role), []))


def has_permission(user: dict, perm: str) -> bool:
    """True if `user` has the `resource.action` permission."""
    if not user:
        return False
    role = _normalize_role(user.get("role"))
    grants = ROLE_PERMISSIONS.get(role, [])
    if not grants:
        return False
    if "*.*" in grants:
        return True
    if perm in grants:
        return True
    resource = perm.split(".", 1)[0] if "." in perm else perm
    return f"{resource}.*" in grants


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
    """Attach normalised role + expanded permissions for wire output."""
    if not user:
        return user
    out = dict(user)
    out["role"] = _normalize_role(user.get("role"))
    out["permissions"] = _expand_permissions(out["role"])
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


class ClientIn(BaseModel):
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    company: Optional[str] = None
    address: Optional[str] = None


class ProjectIn(BaseModel):
    name: str
    client_id: Optional[str] = None
    project_type: Optional[str] = "Residential"
    budget: Optional[float] = 0
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    stage: Optional[str] = "Requirement"
    description: Optional[str] = None


class ProjectStageUpdate(BaseModel):
    stage: str


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
        await db.users.update_one(
            {"user_id": user_id},
            {"$set": {"name": name, "picture": picture, "last_login": iso(now_utc())}},
        )
        user = await db.users.find_one({"user_id": user_id}, {"_id": 0})
    else:
        user_id = f"user_{uuid.uuid4().hex[:12]}"
        user_count = await db.users.count_documents({})
        role = "Admin" if user_count == 0 else "Employee"
        user = {
            "user_id": user_id,
            "email": email,
            "name": name,
            "picture": picture,
            "role": role,
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
    """Any authenticated user may read the role catalogue (for their own UI)."""
    await require_user(request, session_token, authorization)
    return {
        "roles": [
            {"name": r, "permissions": ROLE_PERMISSIONS.get(r, [])}
            for r in ROLES
        ]
    }


@api.get("/rbac/users")
async def rbac_users(request: Request,
                     session_token: Optional[str] = Cookie(default=None),
                     authorization: Optional[str] = Header(default=None)):
    """Admin or HR can list users."""
    user = await require_user(request, session_token, authorization)
    if not (has_permission(user, "users.read") or has_permission(user, "rbac.read")):
        raise HTTPException(status_code=403, detail="Missing permission: users.read")
    users = await db.users.find({}, {"_id": 0}).sort("created_at", 1).to_list(500)
    return [
        {
            "user_id": u.get("user_id"),
            "email": u.get("email"),
            "name": u.get("name"),
            "picture": u.get("picture"),
            "role": _normalize_role(u.get("role")),
            "created_at": u.get("created_at"),
            "last_login": u.get("last_login"),
        }
        for u in users
    ]


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
    # Guard: never allow the last admin to demote themselves.
    if _normalize_role(target.get("role")) == "Admin" and new_role != "Admin":
        admin_count = 0
        async for u in db.users.find({}, {"_id": 0, "role": 1}):
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

    active_projects = await db.projects.count_documents({"stage": {"$nin": ["Handover"]}})
    total_projects = await db.projects.count_documents({})

    # Revenue: sum of paid invoices
    paid_cursor = db.invoices.find({"status": "paid", "doc_type": "invoice"}, {"_id": 0})
    revenue = 0.0
    async for inv in paid_cursor:
        revenue += float(inv.get("total", 0))

    # Collection due: sum of sent+overdue
    due_cursor = db.invoices.find({"status": {"$in": ["sent", "overdue"]}, "doc_type": "invoice"}, {"_id": 0})
    collection_due = 0.0
    async for inv in due_cursor:
        collection_due += float(inv.get("total", 0))

    # Overdue tasks
    today = now_utc().date().isoformat()
    overdue_tasks = await db.tasks.count_documents({
        "status": {"$ne": "done"},
        "due_date": {"$lt": today, "$ne": None}
    })

    # Pipeline funnel
    pipeline = []
    for stage in PIPELINE_STAGES:
        count = await db.leads.count_documents({"stage": stage})
        pipeline.append({"stage": stage, "count": count})

    # Lead sources
    sources = {}
    async for lead in db.leads.find({}, {"_id": 0, "source": 1}):
        s = lead.get("source", "Other")
        sources[s] = sources.get(s, 0) + 1
    source_list = [{"source": k, "count": v} for k, v in sources.items()]

    # Alerts
    alerts = []
    if overdue_tasks > 0:
        alerts.append({"level": "high", "message": f"{overdue_tasks} tasks overdue"})
    if collection_due > 0:
        alerts.append({"level": "medium", "message": f"${collection_due:,.0f} pending collection"})

    # Team utilization (dummy: count tasks per assignee)
    util = {}
    async for t in db.tasks.find({"status": {"$ne": "done"}}, {"_id": 0, "assignee_name": 1}):
        n = t.get("assignee_name") or "Unassigned"
        util[n] = util.get(n, 0) + 1
    utilization = [{"name": k, "load": v} for k, v in util.items()]

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
    leads = await db.leads.find({}, {"_id": 0}).sort("created_at", -1).to_list(1000)
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
    await db.leads.insert_one(dict(lead))
    return await db.leads.find_one({"id": lead["id"]}, {"_id": 0})


@api.patch("/leads/{lead_id}/stage")
async def update_lead_stage(lead_id: str, payload: LeadStageUpdate, request: Request,
                             session_token: Optional[str] = Cookie(default=None),
                             authorization: Optional[str] = Header(default=None)):
    await require_user(request, session_token, authorization)
    if payload.stage not in PIPELINE_STAGES:
        raise HTTPException(status_code=400, detail="Invalid stage")
    res = await db.leads.update_one(
        {"id": lead_id},
        {"$set": {"stage": payload.stage, "updated_at": iso(now_utc())},
         "$push": {"timeline": {"event": "stage_change", "to": payload.stage, "at": iso(now_utc())}}}
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Lead not found")
    return await db.leads.find_one({"id": lead_id}, {"_id": 0})


@api.delete("/leads/{lead_id}")
async def delete_lead(lead_id: str, request: Request,
                      session_token: Optional[str] = Cookie(default=None),
                      authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    if not has_permission(user, "leads.delete"):
        raise HTTPException(status_code=403, detail="Missing permission: leads.delete")
    await db.leads.delete_one({"id": lead_id})
    return {"ok": True}


@api.post("/leads/{lead_id}/convert")
async def convert_lead_to_project(lead_id: str, request: Request,
                                   session_token: Optional[str] = Cookie(default=None),
                                   authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    lead = await db.leads.find_one({"id": lead_id}, {"_id": 0})
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
    await db.clients.insert_one(dict(client_doc))

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
    await db.projects.insert_one(dict(project))
    await db.leads.update_one({"id": lead_id}, {"$set": {"stage": "Won", "converted_project_id": project_id}})
    return {"project_id": project_id, "client_id": client_id}


# ============================================================
# Clients
# ============================================================
@api.get("/clients")
async def list_clients(request: Request, session_token: Optional[str] = Cookie(default=None),
                       authorization: Optional[str] = Header(default=None)):
    await require_user(request, session_token, authorization)
    rows = await db.clients.find({}, {"_id": 0}).sort("created_at", -1).to_list(500)
    return rows


@api.post("/clients")
async def create_client(payload: ClientIn, request: Request,
                        session_token: Optional[str] = Cookie(default=None),
                        authorization: Optional[str] = Header(default=None)):
    await require_user(request, session_token, authorization)
    doc = payload.model_dump()
    doc["id"] = new_id("cli_")
    doc["created_at"] = iso(now_utc())
    await db.clients.insert_one(dict(doc))
    return await db.clients.find_one({"id": doc["id"]}, {"_id": 0})


# ============================================================
# Projects
# ============================================================
@api.get("/projects")
async def list_projects(request: Request, session_token: Optional[str] = Cookie(default=None),
                        authorization: Optional[str] = Header(default=None)):
    await require_user(request, session_token, authorization)
    projects = await db.projects.find({}, {"_id": 0}).sort("created_at", -1).to_list(500)
    return projects


@api.post("/projects")
async def create_project(payload: ProjectIn, request: Request,
                         session_token: Optional[str] = Cookie(default=None),
                         authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    doc = payload.model_dump()
    doc["id"] = new_id("prj_")
    doc["share_token"] = new_id()
    doc["created_at"] = iso(now_utc())
    doc["created_by"] = user["user_id"]
    if doc.get("client_id"):
        c = await db.clients.find_one({"id": doc["client_id"]}, {"_id": 0})
        if c:
            doc["client_name"] = c.get("name")
    await db.projects.insert_one(dict(doc))
    return await db.projects.find_one({"id": doc["id"]}, {"_id": 0})


@api.get("/projects/{project_id}")
async def get_project(project_id: str, request: Request,
                      session_token: Optional[str] = Cookie(default=None),
                      authorization: Optional[str] = Header(default=None)):
    await require_user(request, session_token, authorization)
    p = await db.projects.find_one({"id": project_id}, {"_id": 0})
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")
    p["tasks"] = await db.tasks.find({"project_id": project_id}, {"_id": 0}).to_list(500)
    p["files"] = await db.files.find({"project_id": project_id}, {"_id": 0}).to_list(500)
    p["invoices"] = await db.invoices.find({"project_id": project_id}, {"_id": 0}).to_list(500)
    p["milestones"] = await db.milestones.find({"project_id": project_id}, {"_id": 0}).to_list(200)
    return p


@api.patch("/projects/{project_id}/stage")
async def update_project_stage(project_id: str, payload: ProjectStageUpdate, request: Request,
                                session_token: Optional[str] = Cookie(default=None),
                                authorization: Optional[str] = Header(default=None)):
    await require_user(request, session_token, authorization)
    if payload.stage not in PROJECT_STAGES:
        raise HTTPException(status_code=400, detail="Invalid stage")
    await db.projects.update_one({"id": project_id}, {"$set": {"stage": payload.stage, "updated_at": iso(now_utc())}})
    return await db.projects.find_one({"id": project_id}, {"_id": 0})


@api.delete("/projects/{project_id}")
async def delete_project(project_id: str, request: Request,
                         session_token: Optional[str] = Cookie(default=None),
                         authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    if not has_permission(user, "projects.delete"):
        raise HTTPException(status_code=403, detail="Missing permission: projects.delete")
    await db.projects.delete_one({"id": project_id})
    return {"ok": True}


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
    return await db.files.find(q, {"_id": 0}).sort("created_at", -1).to_list(500)


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
    await db.files.insert_one(dict(doc))
    return await db.files.find_one({"id": doc["id"]}, {"_id": 0})


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
    return await db.invoices.find(q, {"_id": 0}).sort("created_at", -1).to_list(500)


@api.post("/invoices")
async def create_invoice(payload: InvoiceIn, request: Request,
                         session_token: Optional[str] = Cookie(default=None),
                         authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    doc = payload.model_dump()
    doc["id"] = new_id("inv_")
    # number
    prefix = "QUO" if doc.get("doc_type") == "quotation" else "INV"
    count = await db.invoices.count_documents({"doc_type": doc.get("doc_type", "invoice")})
    doc["number"] = f"{prefix}-{1000 + count + 1}"
    doc["created_at"] = iso(now_utc())
    doc["created_by"] = user["user_id"]
    if doc.get("client_id") and not doc.get("client_name"):
        c = await db.clients.find_one({"id": doc["client_id"]}, {"_id": 0})
        if c:
            doc["client_name"] = c.get("name")
    if doc.get("project_id") and not doc.get("project_name"):
        p = await db.projects.find_one({"id": doc["project_id"]}, {"_id": 0})
        if p:
            doc["project_name"] = p.get("name")
    doc = compute_invoice_totals(doc)
    await db.invoices.insert_one(dict(doc))
    return await db.invoices.find_one({"id": doc["id"]}, {"_id": 0})


@api.get("/invoices/{invoice_id}")
async def get_invoice(invoice_id: str, request: Request,
                      session_token: Optional[str] = Cookie(default=None),
                      authorization: Optional[str] = Header(default=None)):
    await require_user(request, session_token, authorization)
    doc = await db.invoices.find_one({"id": invoice_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Not found")
    return doc


@api.patch("/invoices/{invoice_id}/status")
async def update_invoice_status(invoice_id: str, payload: InvoiceStatusUpdate, request: Request,
                                 session_token: Optional[str] = Cookie(default=None),
                                 authorization: Optional[str] = Header(default=None)):
    await require_user(request, session_token, authorization)
    if payload.status not in INVOICE_STATUSES:
        raise HTTPException(status_code=400, detail="Invalid status")
    await db.invoices.update_one(
        {"id": invoice_id},
        {"$set": {"status": payload.status, "updated_at": iso(now_utc())}}
    )
    return await db.invoices.find_one({"id": invoice_id}, {"_id": 0})


@api.delete("/invoices/{invoice_id}")
async def delete_invoice(invoice_id: str, request: Request,
                         session_token: Optional[str] = Cookie(default=None),
                         authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    if not has_permission(user, "invoices.delete"):
        raise HTTPException(status_code=403, detail="Missing permission: invoices.delete")
    await db.invoices.delete_one({"id": invoice_id})
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


def generate_invoice_pdf(doc: dict) -> bytes:
    pdf = FPDF(format="A4", unit="mm")
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)

    # Header
    pdf.set_font("Helvetica", "B", 22)
    pdf.set_text_color(0, 47, 167)
    title = "QUOTATION" if doc.get("doc_type") == "quotation" else "INVOICE"
    pdf.cell(0, 12, _safe(title), ln=1)

    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(0, 0, 0)
    pdf.cell(0, 6, _safe("DESIGN SAGA"), ln=1)
    pdf.cell(0, 5, _safe("Architecture & Interior Design Studio"), ln=1)
    pdf.ln(4)

    # Meta
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(40, 6, "Number:", 0)
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 6, _safe(doc.get("number", "")), ln=1)

    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(40, 6, "Date:", 0)
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 6, _safe((doc.get("created_at") or "")[:10]), ln=1)

    if doc.get("due_date"):
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(40, 6, "Due:", 0)
        pdf.set_font("Helvetica", "", 10)
        pdf.cell(0, 6, _safe(doc.get("due_date")), ln=1)

    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(40, 6, "Client:", 0)
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 6, _safe(doc.get("client_name") or "-"), ln=1)

    if doc.get("project_name"):
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(40, 6, "Project:", 0)
        pdf.set_font("Helvetica", "", 10)
        pdf.cell(0, 6, _safe(doc.get("project_name")), ln=1)

    pdf.ln(6)

    # Line items table
    pdf.set_fill_color(0, 0, 0)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(100, 8, "Description", 0, 0, "L", fill=True)
    pdf.cell(25, 8, "Qty", 0, 0, "R", fill=True)
    pdf.cell(30, 8, "Rate", 0, 0, "R", fill=True)
    pdf.cell(35, 8, "Amount", 0, 1, "R", fill=True)

    pdf.set_text_color(0, 0, 0)
    pdf.set_font("Helvetica", "", 10)
    for it in doc.get("items", []):
        pdf.cell(100, 8, _safe(it.get("description", ""))[:60], 0, 0, "L")
        pdf.cell(25, 8, f"{it.get('quantity', 0):g}", 0, 0, "R")
        pdf.cell(30, 8, f"{it.get('rate', 0):,.2f}", 0, 0, "R")
        pdf.cell(35, 8, f"{it.get('amount', 0):,.2f}", 0, 1, "R")

    pdf.ln(4)

    # Totals
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(155, 6, "Subtotal", 0, 0, "R")
    pdf.cell(35, 6, f"{doc.get('subtotal', 0):,.2f}", 0, 1, "R")
    pdf.cell(155, 6, f"Tax ({doc.get('tax_rate', 0)}%)", 0, 0, "R")
    pdf.cell(35, 6, f"{doc.get('tax', 0):,.2f}", 0, 1, "R")
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(155, 8, "TOTAL", 0, 0, "R")
    pdf.cell(35, 8, f"{doc.get('total', 0):,.2f}", 0, 1, "R")

    if doc.get("notes"):
        pdf.ln(6)
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(0, 6, "Notes", ln=1)
        pdf.set_font("Helvetica", "", 10)
        pdf.multi_cell(0, 5, _safe(doc.get("notes")))

    pdf.ln(10)
    pdf.set_font("Helvetica", "I", 9)
    pdf.set_text_color(100, 100, 100)
    pdf.cell(0, 5, _safe("Thank you for choosing Design Saga."), ln=1, align="C")

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
        inv = await db.invoices.find_one({"id": invoice_id}, {"_id": 0})
        if not inv:
            raise HTTPException(status_code=404, detail="Not found")
        project = await db.projects.find_one({"id": inv.get("project_id"), "share_token": token}, {"_id": 0})
        if not project:
            raise HTTPException(status_code=401, detail="Invalid share token")
    doc = await db.invoices.find_one({"id": invoice_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Not found")
    pdf_bytes = generate_invoice_pdf(doc)
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
    project = await db.projects.find_one({"share_token": token}, {"_id": 0})
    if not project:
        raise HTTPException(status_code=404, detail="Invalid link")
    tasks = await db.tasks.find({"project_id": project["id"]}, {"_id": 0}).to_list(200)
    files = await db.files.find({"project_id": project["id"]}, {"_id": 0}).to_list(200)
    invoices = await db.invoices.find({"project_id": project["id"]}, {"_id": 0}).to_list(200)
    milestones = await db.milestones.find({"project_id": project["id"]}, {"_id": 0}).to_list(100)

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
    project = await db.projects.find_one({"share_token": token}, {"_id": 0})
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
    projects = await db.projects.find({}, {"_id": 0, "name": 1, "stage": 1, "project_type": 1, "client_name": 1}).to_list(50)
    overdue = await db.tasks.count_documents({"status": {"$ne": "done"}})
    leads_count = await db.leads.count_documents({})
    project_ctx = "\n".join([f"- {p.get('name')} [{p.get('stage')}] for {p.get('client_name') or 'N/A'}" for p in projects[:20]])
    system_message = (
        f"You are Saga AI, the internal assistant for a boutique architecture & interior design studio called Design Saga. "
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
        await db.clients.update_one({"id": c["id"]}, {"$set": c}, upsert=True)

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
        await db.leads.insert_one(dict(lead))

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
        await db.projects.insert_one(dict(p))
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
        await db.tasks.insert_one(dict(t))

    # Invoices
    inv_samples = [
        (created_project_ids[0], clients_seed[0]["name"], clients_seed[0]["id"], "Concept design – retainer", 1, 600000, "paid", "invoice"),
        (created_project_ids[0], clients_seed[0]["name"], clients_seed[0]["id"], "Design development – milestone 2", 1, 550000, "sent", "invoice"),
        (created_project_ids[1], clients_seed[1]["name"], clients_seed[1]["id"], "Flagship cafe – total fee proposal", 1, 820000, "sent", "quotation"),
        (created_project_ids[2], clients_seed[2]["name"], clients_seed[2]["id"], "Villa revamp – concept fee", 1, 300000, "paid", "invoice"),
    ]
    for pid, cname, cid, desc, qty, rate, status, dtype in inv_samples:
        prefix = "QUO" if dtype == "quotation" else "INV"
        count = await db.invoices.count_documents({"doc_type": dtype})
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
        proj = await db.projects.find_one({"id": pid}, {"_id": 0})
        if proj:
            inv["project_name"] = proj.get("name")
        await db.invoices.insert_one(dict(inv))

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
        await db.files.insert_one(dict(f))

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
    rows = await db.quotations_adv.find({}, {"_id": 0}).sort("created_at", -1).to_list(500)
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
    count = await db.quotations_adv.count_documents({})
    doc["number"] = f"Q-{2026}-{1000 + count + 1}"
    if doc.get("client_id") and not doc.get("client_name"):
        c = await db.clients.find_one({"id": doc["client_id"]}, {"_id": 0})
        if c:
            doc["client_name"] = c.get("name")
    await db.quotations_adv.insert_one(dict(doc))
    return await db.quotations_adv.find_one({"id": doc["id"]}, {"_id": 0})


@api.get("/quotations-adv/{qid}")
async def adv_get(qid: str, request: Request, session_token: Optional[str] = Cookie(default=None),
                  authorization: Optional[str] = Header(default=None)):
    await require_user(request, session_token, authorization)
    doc = await db.quotations_adv.find_one({"id": qid}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Not found")
    return doc


@api.put("/quotations-adv/{qid}")
async def adv_update(qid: str, payload: QuotationUpdate, request: Request,
                     session_token: Optional[str] = Cookie(default=None),
                     authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    doc = await db.quotations_adv.find_one({"id": qid}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Not found")
    update = {k: v for k, v in payload.model_dump().items() if v is not None}
    doc.update(update)
    doc["updated_at"] = iso(now_utc())
    doc["updated_by"] = user["user_id"]
    doc = _q_compute_costs(doc)
    await db.quotations_adv.replace_one({"id": qid}, dict(doc))
    return await db.quotations_adv.find_one({"id": qid}, {"_id": 0})


@api.delete("/quotations-adv/{qid}")
async def adv_delete(qid: str, request: Request, session_token: Optional[str] = Cookie(default=None),
                     authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    if not has_permission(user, "quotations.delete"):
        raise HTTPException(status_code=403, detail="Missing permission: quotations.delete")
    await db.quotations_adv.delete_one({"id": qid})
    return {"ok": True}


@api.post("/quotations-adv/{qid}/status")
async def adv_status(qid: str, payload: StatusUpdate, request: Request,
                     session_token: Optional[str] = Cookie(default=None),
                     authorization: Optional[str] = Header(default=None)):
    await require_user(request, session_token, authorization)
    if payload.status not in QUOTATION_STATUSES:
        raise HTTPException(status_code=400, detail="Invalid status")
    await db.quotations_adv.update_one(
        {"id": qid},
        {"$set": {"status": payload.status, "status_note": payload.note, "updated_at": iso(now_utc())}}
    )
    return await db.quotations_adv.find_one({"id": qid}, {"_id": 0})


@api.post("/quotations-adv/{qid}/approval")
async def adv_approval(qid: str, payload: ApprovalUpdate, request: Request,
                       session_token: Optional[str] = Cookie(default=None),
                       authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    doc = await db.quotations_adv.find_one({"id": qid}, {"_id": 0})
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
    await db.quotations_adv.update_one(
        {"id": qid},
        {"$set": {"approval": approval, "status": next_status, "updated_at": iso(now_utc())}}
    )
    return await db.quotations_adv.find_one({"id": qid}, {"_id": 0})


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
    src = await db.quotations_adv.find_one({"id": qid}, {"_id": 0})
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
    await db.quotations_adv.update_one(
        {"id": qid},
        {"$set": {
            "version": new_v,
            "version_label": f"v{new_v}",
            "versions_log": versions_log,
            "updated_at": iso(now_utc()),
            "status": "draft",
        }}
    )
    return await db.quotations_adv.find_one({"id": qid}, {"_id": 0})


@api.post("/quotations-adv/{qid}/change-order")
async def adv_change_order(qid: str, payload: ChangeOrderIn, request: Request,
                           session_token: Optional[str] = Cookie(default=None),
                           authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    doc = await db.quotations_adv.find_one({"id": qid}, {"_id": 0})
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
    await db.quotations_adv.update_one({"id": qid}, {"$set": {"change_orders": cos, "updated_at": iso(now_utc())}})
    return co


@api.post("/quotations-adv/{qid}/convert-to-project")
async def adv_convert(qid: str, request: Request, session_token: Optional[str] = Cookie(default=None),
                      authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    q = await db.quotations_adv.find_one({"id": qid}, {"_id": 0})
    if not q:
        raise HTTPException(status_code=404, detail="Not found")
    if q.get("status") not in ("approved", "sent", "under_review"):
        raise HTTPException(status_code=400, detail="Quotation must be approved (or near-final) to convert")

    # reuse client or create
    client_id = q.get("client_id")
    if not client_id:
        client_id = new_id("cli_")
        await db.clients.insert_one({
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
    await db.projects.insert_one(dict(project))

    # Auto-create tasks from BOQ categories + timeline phases
    today = now_utc().date()
    for i, cat in enumerate(q.get("boq", []) or []):
        due = (today + timedelta(days=14 + i * 7)).isoformat()
        await db.tasks.insert_one({
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
        await db.tasks.insert_one({
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
    await db.quotations_adv.update_one(
        {"id": qid},
        {"$set": {"status": "converted", "converted_project_id": project_id, "updated_at": iso(now_utc())}}
    )
    return {"project_id": project_id, "client_id": client_id}


@api.post("/quotations-adv/{qid}/cost-vs-actual")
async def adv_cost_vs_actual(qid: str, request: Request, session_token: Optional[str] = Cookie(default=None),
                             authorization: Optional[str] = Header(default=None)):
    """Aggregates paid invoice totals on the converted project vs quoted grand_total."""
    await require_user(request, session_token, authorization)
    q = await db.quotations_adv.find_one({"id": qid}, {"_id": 0})
    if not q:
        raise HTTPException(status_code=404, detail="Not found")
    quoted = (q.get("cost") or {}).get("grand_total", 0)
    pid = q.get("converted_project_id")
    paid = 0.0
    sent = 0.0
    if pid:
        async for inv in db.invoices.find({"project_id": pid, "doc_type": "invoice"}, {"_id": 0}):
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
    q = await db.quotations_adv.find_one({"id": qid}, {"_id": 0})
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
def generate_quotation_pdf_adv(doc: dict) -> bytes:
    pdf = FPDF(format="A4", unit="mm")
    pdf.set_auto_page_break(auto=True, margin=18)

    klein = (0, 47, 167)
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
    pdf.cell(0, 6, _safe("DESIGN SAGA  ·  STUDIO OS"), ln=1)
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

    # ============ EXECUTIVE SUMMARY ============
    pdf.add_page()
    header_section("01 / Executive Summary")
    pdf.cell(0, 9, _safe("Brief, intent and key markers."), ln=1)
    hr()
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(0, 6, "Client requirement", ln=1)
    pdf.set_font("Helvetica", "", 10)
    pdf.multi_cell(0, 5, _safe(doc.get("client_requirement") or "—"))
    pdf.ln(2)
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(0, 6, "Design intent", ln=1)
    pdf.set_font("Helvetica", "", 10)
    pdf.multi_cell(0, 5, _safe(doc.get("design_intent") or "—"))
    pdf.ln(4)
    h = doc.get("highlights") or {}
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_text_color(*grey)
    for k, v in [("BUDGET RANGE", h.get("budget_range")), ("TIMELINE", h.get("timeline")), ("QUALITY LEVEL", h.get("quality_level"))]:
        pdf.cell(45, 6, _safe(k), 0, 0)
        pdf.set_font("Helvetica", "", 11)
        pdf.set_text_color(*ink)
        pdf.cell(0, 6, _safe(str(v or "—")), ln=1)
        pdf.set_font("Helvetica", "B", 9)
        pdf.set_text_color(*grey)
    pdf.set_text_color(*ink)

    # ============ SCOPE ============
    pdf.add_page()
    header_section("02 / Scope of Work")
    pdf.cell(0, 9, _safe("What is in. What is out."), ln=1)
    hr()
    for label, items in [("Design Scope", doc.get("design_scope", [])),
                         ("Execution Scope", doc.get("execution_scope", [])),
                         ("Exclusions", doc.get("exclusions", []))]:
        pdf.set_font("Helvetica", "B", 11)
        pdf.cell(0, 7, _safe(label), ln=1)
        pdf.set_font("Helvetica", "", 10)
        for it in items or []:
            pdf.set_x(15)
            pdf.multi_cell(180, 5, _safe(f"  *  {it}"))
        if not items:
            pdf.set_text_color(*grey)
            pdf.cell(0, 5, _safe("—"), ln=1)
            pdf.set_text_color(*ink)
        pdf.ln(2)

    d = doc.get("deliverables") or {}
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 7, "Deliverables", ln=1)
    pdf.set_font("Helvetica", "", 10)
    for k, v in [("2D drawings", d.get("type_2d")), ("3D renders", d.get("type_3d")),
                 ("Working drawings", d.get("drawings")), ("Site visits", d.get("site_visits")),
                 ("Revision limit", d.get("revision_limit"))]:
        pdf.cell(60, 6, _safe(k), 0, 0)
        pdf.cell(0, 6, _safe(str(v if v is not None else "—")), ln=1)

    # ============ BOQ ============
    pdf.add_page()
    header_section("03 / Bill of Quantities")
    pdf.cell(0, 9, _safe("Line items, fully detailed."), ln=1)
    hr()
    pdf.set_font("Helvetica", "B", 8)
    pdf.set_fill_color(0, 0, 0)
    pdf.set_text_color(255, 255, 255)
    pdf.cell(80, 7, " Description", 0, 0, "L", fill=True)
    pdf.cell(20, 7, "Unit", 0, 0, "C", fill=True)
    pdf.cell(18, 7, "Qty", 0, 0, "R", fill=True)
    pdf.cell(25, 7, "Rate", 0, 0, "R", fill=True)
    pdf.cell(15, 7, "Mgn%", 0, 0, "R", fill=True)
    pdf.cell(22, 7, "Amount", 0, 1, "R", fill=True)
    pdf.set_text_color(*ink)

    grand = 0
    for cat in doc.get("boq", []):
        pdf.set_font("Helvetica", "B", 10)
        pdf.set_fill_color(245, 245, 245)
        pdf.cell(0, 6, _safe(f"  {cat.get('category', 'Misc')}"), 0, 1, "L", fill=True)
        pdf.set_font("Helvetica", "", 9)
        for it in cat.get("items", []):
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
    if doc.get("room_totals"):
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
    if doc.get("materials"):
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

    # ============ COST SUMMARY ============
    pdf.add_page()
    header_section("06 / Cost Summary")
    pdf.cell(0, 9, _safe("Final commercials."), ln=1)
    hr()
    cost = doc.get("cost") or {}
    rows = [
        ("Subtotal (BOQ)", cost.get("subtotal", 0)),
        (f"Discount ({cost.get('discount_pct', 0)}%)", -cost.get("discount_amt", 0)),
        (f"Contingency ({cost.get('contingency_pct', 0)}%)", cost.get("contingency_amt", 0)),
        (f"GST ({cost.get('tax_pct', 18)}%)", cost.get("tax_amt", 0)),
    ]
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
    pdf.cell(75, 5, _safe("FOR DESIGN SAGA"), 0, 0)
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
    doc = await db.quotations_adv.find_one({"id": qid}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Not found")
    pdf_bytes = generate_quotation_pdf_adv(doc)
    return StreamingResponse(io.BytesIO(pdf_bytes), media_type="application/pdf",
                             headers={"Content-Disposition": f'inline; filename="{doc.get("number", qid)}.pdf"'})


# ---------- Seed an advanced quotation example ----------
@api.post("/quotations-adv/seed")
async def adv_seed(request: Request, session_token: Optional[str] = Cookie(default=None),
                   authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    # find first project
    projects = await db.projects.find({}, {"_id": 0}).to_list(5)
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
    count = await db.quotations_adv.count_documents({})
    doc["number"] = f"Q-2026-{1000 + count + 1}"
    await db.quotations_adv.insert_one(dict(doc))
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
    count = await db.employees.count_documents({"employee_id": {"$regex": f"^EMP-{year}-"}})
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
    rows = await db.employees.find(q, {"_id": 0}).sort("created_at", -1).to_list(1000)
    return rows


@api.get("/employees/meta")
async def employee_meta(request: Request,
                        session_token: Optional[str] = Cookie(default=None),
                        authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    if not has_permission(user, "employees.read"):
        raise HTTPException(status_code=403, detail="Missing permission: employees.read")
    seen = set()
    async for e in db.employees.find({}, {"_id": 0, "department": 1}):
        if e.get("department"):
            seen.add(e["department"])
    departments = sorted(set(DEPARTMENTS_DEFAULT) | seen)
    return {
        "departments": departments,
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
    doc = await db.employees.find_one({"id": eid}, {"_id": 0})
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
    await db.employees.insert_one(dict(data))
    return await db.employees.find_one({"id": data["id"]}, {"_id": 0})


@api.put("/employees/{eid}")
async def update_employee(eid: str, payload: EmployeeUpdate, request: Request,
                          session_token: Optional[str] = Cookie(default=None),
                          authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    if not has_permission(user, "employees.update"):
        raise HTTPException(status_code=403, detail="Missing permission: employees.update")
    doc = await db.employees.find_one({"id": eid}, {"_id": 0})
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
    await db.employees.update_one({"id": eid}, {"$set": patch})
    return await db.employees.find_one({"id": eid}, {"_id": 0})


@api.delete("/employees/{eid}")
async def delete_employee(eid: str, request: Request,
                          session_token: Optional[str] = Cookie(default=None),
                          authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    if not has_permission(user, "employees.delete"):
        raise HTTPException(status_code=403, detail="Missing permission: employees.delete")
    res = await db.employees.delete_one({"id": eid})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Employee not found")
    return {"ok": True}


@api.post("/employees/{eid}/documents")
async def add_employee_doc(eid: str, payload: DocumentIn, request: Request,
                           session_token: Optional[str] = Cookie(default=None),
                           authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    if not has_permission(user, "employees.update"):
        raise HTTPException(status_code=403, detail="Missing permission: employees.update")
    entry = {"id": new_id("edoc_"), "label": payload.label, "url": payload.url,
             "uploaded_at": iso(now_utc()), "uploaded_by": user.get("name")}
    res = await db.employees.update_one(
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
    await db.employees.update_one(
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
    res = await db.employees.update_one(
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
    res = await db.employees.update_one(
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
        await db.employees.insert_one(dict(doc))
        created.append(emp_no)
    return {"ok": True, "created": created}



# ============================================================
# Register router & middleware
# ============================================================
# Include modular routers (Phase-1 refactor: Tasks module extracted)
from routes.tasks import router as tasks_router  # noqa: E402
api.include_router(tasks_router)

app.include_router(api)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("shutdown")
async def shutdown():
    client.close()
