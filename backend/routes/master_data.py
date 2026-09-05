"""Centralized tenant-level Master Data / Configuration.

Every configurable dropdown in the ERP reads from here. Values are
tenant-scoped (org_id), seeded from the platform defaults on first access,
and never hard-deleted once referenced — they are deactivated instead so
historical records stay intact.

Schema (collection: master_data)
--------------------------------
{ id, org_id, kind, label, sort_order, is_active, is_system, created_at, updated_at }
"""
from typing import Optional
from fastapi import APIRouter, HTTPException, Request, Cookie, Header, Depends
from pydantic import BaseModel

from core.db import db
from core.deps import require_user
from core.helpers import iso_now, new_id
from core.tenancy import user_org_id
from core.rbac import has_permission

router = APIRouter()

# ------------------------------------------------------------------
# Platform defaults — seeded per-org on first read. `system` kinds have
# ordering semantics (pipelines) so they can be renamed/reordered but not
# removed entirely.
# ------------------------------------------------------------------
DEFAULTS = {
    "project_type": ["Residential", "Commercial", "Retail", "Hospitality", "Office", "Landscape"],
    "project_stage": ["Requirement", "Concept", "Design Dev", "Tech Drawings",
                       "Review", "Signoff", "Procurement", "Execution", "Handover"],
    "lead_source": ["Website", "Referral", "Instagram", "Facebook", "Google Ads",
                     "Walk-in", "Exhibition", "Other"],
    "lead_stage": ["New", "Qualified", "Proposal", "Negotiation", "Won", "Lost"],
    "task_category": [
        "Furniture", "Lighting", "Decor", "Wall Feature", "Flooring", "Ceiling",
        "Painting", "Wallpaper", "Curtains", "Blinds", "Hardware", "Doors", "Windows",
        "Wardrobe", "TV Unit", "Kitchen", "Vanity", "Bathroom Accessories",
        "Electrical", "Plumbing", "HVAC", "False Ceiling", "Marble", "Granite",
        "Tiles", "Glass", "Mirror", "Metal Work", "Fabrication", "Landscape",
        "Civil Work", "Automation", "Accessories", "Others",
    ],
    "task_area": [
        "Entrance", "Foyer", "Living Room", "Drawing Room", "Dining Room", "Kitchen",
        "Utility", "Store Room", "Pooja Room", "Parents Bedroom", "Master Bedroom",
        "Kids Bedroom", "Guest Bedroom", "Walk-in Closet",
        "Master Bathroom", "Common Bathroom", "Powder Room", "Balcony", "Terrace",
        "Home Office", "Study Room", "Family Lounge", "Staircase", "Lift Lobby",
        "Basement", "Parking", "Garden", "Outdoor Area",
    ],
    "client_type": ["Individual", "Corporate", "Builder", "Developer", "Government", "Other"],
    "designation": [
        "Principal Architect", "Senior Architect", "Architect", "Interior Designer",
        "Senior Designer", "3D Visualizer", "Draftsman", "Site Supervisor",
        "Project Manager", "Accountant", "HR Executive", "Office Admin", "Marketing Executive",
    ],
    "department": ["Design", "Finance", "HR", "Leadership", "Operations", "Sales & CRM", "Site Execution"],
    "expense_category": ["travel", "meals", "materials", "utilities", "site", "office", "other"],
    "payment_method": ["cash", "bank_transfer", "upi", "cheque", "credit_card", "online", "other"],
    "document_type": ["Drawing", "3D Render", "Contract", "MoodBoard", "Site Photo",
                       "Approval", "BOQ", "Specification", "Other"],
}

SYSTEM_KINDS = {"project_stage", "lead_stage"}

KIND_LABELS = {
    "project_type": "Project Types",
    "project_stage": "Project Stages",
    "lead_source": "Lead Sources",
    "lead_stage": "Lead Stages",
    "task_category": "Task Categories",
    "task_area": "Areas / Rooms",
    "client_type": "Client Types",
    "designation": "Employee Designations",
    "department": "Departments",
    "expense_category": "Expense Categories",
    "payment_method": "Payment Methods",
    "document_type": "Document Types",
}

# kind → (collection, field) used to protect referenced values from deletion
REFERENCE_MAP = {
    "project_type": ("projects", "project_type"),
    "project_stage": ("projects", "stage"),
    "lead_source": ("leads", "source"),
    "lead_stage": ("leads", "stage"),
    "task_category": ("tasks", "category"),
    "task_area": ("tasks", "area"),
    "client_type": ("clients", "client_type"),
    "designation": ("employees", "designation"),
    "department": ("employees", "department"),
    "expense_category": ("expenses", "items.category"),
    "payment_method": ("journal_entries", "payment_method"),
    "document_type": ("files", "doc_type"),
}


class ItemIn(BaseModel):
    label: str


class ItemUpdate(BaseModel):
    label: Optional[str] = None
    is_active: Optional[bool] = None
    sort_order: Optional[int] = None


class ReorderIn(BaseModel):
    ordered_ids: list


async def _seed_org(org_id: str):
    """Idempotent — seed platform defaults for an org that has no rows yet."""
    count = await db.master_data.count_documents({"org_id": org_id})
    if count:
        return
    now = iso_now()
    docs = []
    for kind, values in DEFAULTS.items():
        for i, label in enumerate(values):
            docs.append({
                "id": new_id("md_"),
                "org_id": org_id,
                "kind": kind,
                "label": label,
                "sort_order": i,
                "is_active": True,
                "is_system": kind in SYSTEM_KINDS,
                "created_at": now,
                "updated_at": now,
            })
    if docs:
        await db.master_data.insert_many(docs)


async def get_values(org_id: str, kind: str, fallback: Optional[list] = None) -> list:
    """Helper for other modules — active labels for a kind (ordered)."""
    rows = await db.master_data.find(
        {"org_id": org_id, "kind": kind, "is_active": True},
        {"_id": 0, "label": 1, "sort_order": 1},
    ).sort("sort_order", 1).to_list(300)
    labels = [r["label"] for r in rows]
    return labels or (fallback or DEFAULTS.get(kind, []))


def _require_admin(user):
    if not (has_permission(user, "settings.manage") or user.get("role") in ("Admin", "SuperAdmin")):
        raise HTTPException(status_code=403, detail="Only Admins can manage master data")


@router.get("/master-data")
async def list_all(request: Request,
                   include_inactive: bool = False,
                   session_token: Optional[str] = Cookie(default=None),
                   authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    org_id = user_org_id(user) or "org_default"
    await _seed_org(org_id)
    q = {"org_id": org_id}
    if not include_inactive:
        q["is_active"] = True
    rows = await db.master_data.find(q, {"_id": 0}).sort([("kind", 1), ("sort_order", 1)]).to_list(2000)
    grouped = {}
    for r in rows:
        grouped.setdefault(r["kind"], []).append(r)
    return {"kinds": KIND_LABELS, "system_kinds": sorted(SYSTEM_KINDS), "data": grouped}


@router.get("/master-data/{kind}")
async def list_kind(kind: str, request: Request,
                    include_inactive: bool = False,
                    session_token: Optional[str] = Cookie(default=None),
                    authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    org_id = user_org_id(user) or "org_default"
    await _seed_org(org_id)
    q = {"org_id": org_id, "kind": kind}
    if not include_inactive:
        q["is_active"] = True
    rows = await db.master_data.find(q, {"_id": 0}).sort("sort_order", 1).to_list(300)
    return rows


@router.post("/master-data/{kind}")
async def add_item(kind: str, payload: ItemIn, request: Request,
                   session_token: Optional[str] = Cookie(default=None),
                   authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    _require_admin(user)
    if kind not in DEFAULTS:
        raise HTTPException(status_code=400, detail=f"Unknown master data kind: {kind}")
    org_id = user_org_id(user) or "org_default"
    await _seed_org(org_id)
    label = payload.label.strip()
    if not label:
        raise HTTPException(status_code=400, detail="Label is required")
    dup = await db.master_data.find_one(
        {"org_id": org_id, "kind": kind, "label": {"$regex": f"^{__import__('re').escape(label)}$", "$options": "i"}})
    if dup:
        raise HTTPException(status_code=409, detail="Value already exists")
    last = await db.master_data.find({"org_id": org_id, "kind": kind}).sort("sort_order", -1).to_list(1)
    order = (last[0]["sort_order"] + 1) if last else 0
    doc = {
        "id": new_id("md_"), "org_id": org_id, "kind": kind, "label": label,
        "sort_order": order, "is_active": True, "is_system": False,
        "created_at": iso_now(), "updated_at": iso_now(),
    }
    await db.master_data.insert_one(dict(doc))
    doc.pop("_id", None)
    return doc


@router.patch("/master-data/items/{item_id}")
async def update_item(item_id: str, payload: ItemUpdate, request: Request,
                      session_token: Optional[str] = Cookie(default=None),
                      authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    _require_admin(user)
    org_id = user_org_id(user) or "org_default"
    item = await db.master_data.find_one({"id": item_id, "org_id": org_id}, {"_id": 0})
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    upd = {}
    if payload.label is not None and payload.label.strip():
        upd["label"] = payload.label.strip()
    if payload.is_active is not None:
        # Never allow deactivating ALL items of a system kind
        if payload.is_active is False and item["is_system"]:
            active = await db.master_data.count_documents(
                {"org_id": org_id, "kind": item["kind"], "is_active": True})
            if active <= 1:
                raise HTTPException(status_code=400,
                                    detail="At least one active value is required for this kind")
        upd["is_active"] = payload.is_active
    if payload.sort_order is not None:
        upd["sort_order"] = payload.sort_order
    if not upd:
        return item
    upd["updated_at"] = iso_now()
    await db.master_data.update_one({"id": item_id, "org_id": org_id}, {"$set": upd})
    return await db.master_data.find_one({"id": item_id}, {"_id": 0})


@router.post("/master-data/{kind}/reorder")
async def reorder(kind: str, payload: ReorderIn, request: Request,
                  session_token: Optional[str] = Cookie(default=None),
                  authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    _require_admin(user)
    org_id = user_org_id(user) or "org_default"
    for i, item_id in enumerate(payload.ordered_ids):
        await db.master_data.update_one(
            {"id": item_id, "org_id": org_id, "kind": kind},
            {"$set": {"sort_order": i, "updated_at": iso_now()}})
    return {"ok": True}


@router.delete("/master-data/items/{item_id}")
async def delete_item(item_id: str, request: Request,
                      session_token: Optional[str] = Cookie(default=None),
                      authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    _require_admin(user)
    org_id = user_org_id(user) or "org_default"
    item = await db.master_data.find_one({"id": item_id, "org_id": org_id}, {"_id": 0})
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    if item.get("is_system"):
        raise HTTPException(status_code=400,
                            detail="System values cannot be deleted — deactivate instead")
    # Reference check — never orphan historical records
    ref = REFERENCE_MAP.get(item["kind"])
    if ref:
        coll, field = ref
        n = await db[coll].count_documents({"org_id": org_id, field: item["label"]})
        if not n and org_id == "org_default":
            # legacy docs without org stamp
            n = await db[coll].count_documents({"org_id": {"$exists": False}, field: item["label"]})
        if n:
            await db.master_data.update_one({"id": item_id},
                                            {"$set": {"is_active": False, "updated_at": iso_now()}})
            return {"ok": True, "deactivated": True,
                    "detail": f"Value is referenced by {n} record(s) — deactivated instead of deleted"}
    await db.master_data.delete_one({"id": item_id, "org_id": org_id})
    return {"ok": True, "deleted": True}
