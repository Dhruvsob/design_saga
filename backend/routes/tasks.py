"""Task Management routes.

Covers both `employee` and `vendor` task workflows sharing the same DB shape,
follow-ups, timeline audit, custom areas / categories per project, and bulk
updates + reminders — all on the existing `tasks` collection with
backward-compatible fields.
"""
from fastapi import APIRouter, HTTPException, Request, Cookie, Header, Depends
from typing import Optional, List
from datetime import datetime, timezone, timedelta

from core.db import db
from core.scoped_db import sdb
from core.helpers import now_utc, iso, iso_now, new_id
from core.deps import require_user
from core.tenancy import user_org_id

from models.task import (
    TaskIn, TaskUpdate, TaskStatusUpdate, FollowUpIn, BulkUpdateIn,
    CustomAreaIn, CustomCategoryIn,
    TASK_LANES, TASK_TYPES, TASK_STATUS_DETAIL, TASK_PRIORITIES,
    STATUS_TO_LANE, LANE_TO_DEFAULT_STATUS,
    DEFAULT_AREAS, DEFAULT_CATEGORIES, DEFAULT_CATEGORIES_EMPLOYEE,
    DEFAULT_CATEGORIES_VENDOR, REMINDER_FREQUENCIES, TIMELINE_EVENTS,
)

router = APIRouter()


# ==================================================
# Helpers
# ==================================================
def _timeline_entry(user: dict, event: str, details: str = "", **extra) -> dict:
    return {
        "id": new_id("evt_"),
        "event": event,
        "details": details,
        "actor": user.get("user_id"),
        "actor_name": user.get("name"),
        "at": iso_now(),
        **extra,
    }


def _sync_status_from_detail(doc: dict):
    """Ensure `status` (kanban lane) is consistent with `status_detail`."""
    if doc.get("status_detail") and doc["status_detail"] in STATUS_TO_LANE:
        doc["status"] = STATUS_TO_LANE[doc["status_detail"]]
    elif doc.get("status") and doc["status"] in LANE_TO_DEFAULT_STATUS and not doc.get("status_detail"):
        doc["status_detail"] = LANE_TO_DEFAULT_STATUS[doc["status"]]


# ==================================================
# Meta (dropdowns for UI)
# ==================================================
@router.get("/tasks/meta")
async def tasks_meta(request: Request,
                     project_id: Optional[str] = None,
                     session_token: Optional[str] = Cookie(default=None),
                     authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)

    # Tenant-level master data first (Settings → Master Data), then built-in
    # defaults, then per-project customisations.
    from routes.master_data import get_values as _md_values
    from core.tenancy import user_org_id as _uoid
    _org = _uoid(user)
    areas = list(await _md_values(_org, "task_area", DEFAULT_AREAS)) if _org else list(DEFAULT_AREAS)
    cats = list(await _md_values(_org, "task_category", DEFAULT_CATEGORIES)) if _org else list(DEFAULT_CATEGORIES)
    cats_emp = list(DEFAULT_CATEGORIES_EMPLOYEE)
    cats_vendor = list(DEFAULT_CATEGORIES_VENDOR)

    if project_id:
        # Merge in project-specific customizations
        p = await sdb.projects.find_one({"id": project_id}, {"_id": 0, "custom_areas": 1, "custom_categories": 1})
        if p:
            for a in (p.get("custom_areas") or []):
                if a not in areas:
                    areas.append(a)
            for c in (p.get("custom_categories") or []):
                nm = c.get("name") if isinstance(c, dict) else c
                if nm and nm not in cats:
                    cats.append(nm)
                # bucket by task_type if provided
                if isinstance(c, dict):
                    tt = c.get("task_type")
                    if tt == "employee" and nm not in cats_emp:
                        cats_emp.append(nm)
                    elif tt == "vendor" and nm not in cats_vendor:
                        cats_vendor.append(nm)

    return {
        "task_types": TASK_TYPES,
        "lanes": TASK_LANES,
        "status_detail": TASK_STATUS_DETAIL,
        "priorities": TASK_PRIORITIES,
        "status_to_lane": STATUS_TO_LANE,
        "lane_to_default_status": LANE_TO_DEFAULT_STATUS,
        "areas": areas,
        "categories": cats,
        "categories_employee": cats_emp,
        "categories_vendor": cats_vendor,
        "reminder_frequencies": REMINDER_FREQUENCIES,
    }


# ==================================================
# List / filters
# ==================================================
@router.get("/tasks")
async def list_tasks(request: Request,
                     project_id: Optional[str] = None,
                     task_type: Optional[str] = None,
                     status: Optional[str] = None,
                     status_detail: Optional[str] = None,
                     priority: Optional[str] = None,
                     area: Optional[str] = None,
                     category: Optional[str] = None,
                     assignee_id: Optional[str] = None,
                     search: Optional[str] = None,
                     due_before: Optional[str] = None,
                     due_after: Optional[str] = None,
                     session_token: Optional[str] = Cookie(default=None),
                     authorization: Optional[str] = Header(default=None)):
    await require_user(request, session_token, authorization)
    q: dict = {}
    if project_id: q["project_id"] = project_id
    if task_type: q["task_type"] = task_type
    if status: q["status"] = status
    if status_detail: q["status_detail"] = status_detail
    if priority: q["priority"] = priority
    if area: q["area"] = area
    if category: q["category"] = category
    if assignee_id:
        q["$or"] = [{"assignee_id": assignee_id}, {"assignees": assignee_id}]
    if due_before or due_after:
        d = {}
        if due_after: d["$gte"] = due_after
        if due_before: d["$lte"] = due_before
        q["due_date"] = d
    if search:
        rx = {"$regex": search, "$options": "i"}
        q["$or"] = q.get("$or", []) + [
            {"title": rx}, {"description": rx},
            {"item_description": rx}, {"remarks": rx},
            {"vendor_contact.vendor_name": rx},
        ]
    rows = await sdb.tasks.find(q, {"_id": 0}).sort("created_at", -1).to_list(2000)
    return rows


# ==================================================
# Get one (with follow-ups + timeline)
# ==================================================
@router.get("/tasks/{task_id}")
async def get_task(task_id: str, request: Request,
                   session_token: Optional[str] = Cookie(default=None),
                   authorization: Optional[str] = Header(default=None)):
    await require_user(request, session_token, authorization)
    t = await sdb.tasks.find_one({"id": task_id}, {"_id": 0})
    if not t:
        raise HTTPException(status_code=404, detail="Task not found")
    # Normalize list-shaped fields to [] so the frontend can use .length safely.
    for k in ("follow_ups", "timeline", "attachments", "reference_links", "assignees"):
        if not t.get(k):
            t[k] = []
    return t


# ==================================================
# Create
# ==================================================
@router.post("/tasks")
async def create_task(payload: TaskIn, request: Request,
                      session_token: Optional[str] = Cookie(default=None),
                      authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    doc = payload.model_dump()
    doc["id"] = new_id("tsk_")
    doc["created_at"] = iso_now()
    doc["created_by"] = user["user_id"]
    doc["created_by_name"] = user.get("name")
    doc["updated_at"] = doc["created_at"]

    if not doc.get("assignee_name") and doc.get("task_type") == "employee":
        doc["assignee_name"] = user.get("name")
    if doc.get("project_id"):
        p = await sdb.projects.find_one({"id": doc["project_id"]}, {"_id": 0})
        if p:
            doc["project_name"] = p.get("name")
    # If a vendor_id is provided, backfill vendor_contact from the master
    # so existing readers (list filters, ledger match) keep working.
    if doc.get("vendor_id"):
        v = await sdb.vendors_acc.find_one({"id": doc["vendor_id"]}, {"_id": 0})
        if v:
            doc["vendor_name"] = v.get("name")
            existing_vc = doc.get("vendor_contact") or {}
            doc["vendor_contact"] = {
                "vendor_name": v.get("name") or existing_vc.get("vendor_name") or "",
                "contact_person": v.get("contact_person") or existing_vc.get("contact_person") or "",
                "phone": v.get("phone") or existing_vc.get("phone") or "",
                "email": v.get("email") or existing_vc.get("email") or "",
                "whatsapp": existing_vc.get("whatsapp") or "",
                "company_name": v.get("company") or existing_vc.get("company_name") or "",
                "address": v.get("address") or existing_vc.get("address") or "",
            }

    _sync_status_from_detail(doc)
    # Ensure list-shaped fields are [] not None so the frontend can rely on .length
    for k in ("follow_ups", "attachments", "reference_links", "assignees"):
        if not doc.get(k):
            doc[k] = []
    # Future-compat placeholders (never break schema when procurement/PO come online)
    doc.setdefault("procurement_link", None)
    doc.setdefault("po_id", None)
    doc.setdefault("inventory_id", None)
    doc.setdefault("vendor_payment_status", None)

    doc["timeline"] = [_timeline_entry(user, TIMELINE_EVENTS["CREATED"],
                                       f"Task '{doc['title']}' created")]
    if doc.get("assignee_name"):
        doc["timeline"].append(
            _timeline_entry(user, TIMELINE_EVENTS["ASSIGNED"],
                            f"Assigned to {doc['assignee_name']}")
        )

    await sdb.tasks.insert_one(dict(doc))

    # Emit notification to the assignee.
    try:
        from core.notifications import emit as _notify
        assignee_uid = doc.get("assignee_id")
        if not assignee_uid and doc.get("assignee_name"):
            assignee = await db.users.find_one(
                {"name": doc["assignee_name"], "org_id": user_org_id(user)},
                {"_id": 0, "user_id": 1})
            if assignee:
                assignee_uid = assignee["user_id"]
        if assignee_uid and assignee_uid != user["user_id"]:
            await _notify(
                [assignee_uid], "task_assigned",
                f"New task · {doc['title'][:60]}",
                body=(doc.get("description") or "")[:120] or "You've been assigned a new task.",
                link=f"/tasks/{doc['id']}",
                priority="high" if (doc.get("priority") or "").lower() in ("urgent", "critical", "high") else "normal",
                meta={"task_id": doc["id"], "assigned_by": user.get("name")},
            )
    except Exception:
        pass  # notifications never block task creation

    return await sdb.tasks.find_one({"id": doc["id"]}, {"_id": 0})


# ==================================================
# Update (full)
# ==================================================
@router.put("/tasks/{task_id}")
async def update_task(task_id: str, payload: TaskUpdate, request: Request,
                      session_token: Optional[str] = Cookie(default=None),
                      authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    existing = await sdb.tasks.find_one({"id": task_id}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Task not found")

    updates = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not updates:
        return existing

    # Track material changes for the timeline audit
    events: List[dict] = []
    tracked = ["title", "priority", "status", "status_detail", "assignee_name",
               "area", "category", "due_date", "task_type"]
    for k in tracked:
        if k in updates and updates[k] != existing.get(k):
            if k in ("status", "status_detail"):
                events.append(_timeline_entry(
                    user, TIMELINE_EVENTS["STATUS_CHANGED"],
                    f"{k} changed: {existing.get(k) or '—'} → {updates[k]}",
                    field=k, old=existing.get(k), new=updates[k],
                ))
            elif k == "assignee_name":
                events.append(_timeline_entry(
                    user, TIMELINE_EVENTS["ASSIGNED"],
                    f"Reassigned to {updates[k]}"
                ))
            else:
                events.append(_timeline_entry(
                    user, TIMELINE_EVENTS["UPDATED"],
                    f"{k}: {existing.get(k) or '—'} → {updates[k]}",
                    field=k, old=existing.get(k), new=updates[k],
                ))

    merged = {**existing, **updates}
    _sync_status_from_detail(merged)
    updates["status"] = merged["status"]
    updates["status_detail"] = merged.get("status_detail")

    updates["updated_at"] = iso_now()
    updates["updated_by"] = user["user_id"]

    if merged.get("status") == "done":
        events.append(_timeline_entry(user, TIMELINE_EVENTS["COMPLETED"], "Task completed"))

    if events:
        await sdb.tasks.update_one({"id": task_id}, {
            "$set": updates,
            "$push": {"timeline": {"$each": events}},
        })
    else:
        await sdb.tasks.update_one({"id": task_id}, {"$set": updates})
    return await sdb.tasks.find_one({"id": task_id}, {"_id": 0})


# ==================================================
# Status shortcut (used by kanban drag-drop)
# ==================================================
@router.patch("/tasks/{task_id}/status")
async def update_task_status(task_id: str, payload: TaskStatusUpdate, request: Request,
                             session_token: Optional[str] = Cookie(default=None),
                             authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    existing = await sdb.tasks.find_one({"id": task_id}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Task not found")

    lane = payload.status
    detail = payload.status_detail
    if not lane and not detail:
        raise HTTPException(status_code=400, detail="status or status_detail required")

    if detail and detail not in TASK_STATUS_DETAIL:
        raise HTTPException(status_code=400, detail=f"Invalid status_detail: {detail}")
    if lane and lane not in TASK_LANES:
        raise HTTPException(status_code=400, detail=f"Invalid lane: {lane}")

    merged = dict(existing)
    if lane:
        # Explicit lane change (typical Kanban drag): move the lane AND set a
        # sensible status_detail so the auto-sync below does not undo it.
        merged["status"] = lane
        # Overwrite status_detail only if not simultaneously specified by caller.
        if not detail:
            merged["status_detail"] = LANE_TO_DEFAULT_STATUS.get(lane)
    if detail:
        merged["status_detail"] = detail
    _sync_status_from_detail(merged)

    updates = {
        "status": merged["status"],
        "status_detail": merged.get("status_detail"),
        "updated_at": iso_now(),
        "updated_by": user["user_id"],
    }
    evt = _timeline_entry(
        user, TIMELINE_EVENTS["STATUS_CHANGED"],
        f"{existing.get('status_detail') or existing.get('status') or '—'} → "
        f"{merged.get('status_detail') or merged.get('status')}"
    )
    await sdb.tasks.update_one({"id": task_id},
                              {"$set": updates, "$push": {"timeline": evt}})
    return await sdb.tasks.find_one({"id": task_id}, {"_id": 0})


# ==================================================
# Delete
# ==================================================
@router.delete("/tasks/{task_id}")
async def delete_task(task_id: str, request: Request,
                      session_token: Optional[str] = Cookie(default=None),
                      authorization: Optional[str] = Header(default=None)):
    await require_user(request, session_token, authorization)
    await sdb.tasks.delete_one({"id": task_id})
    return {"ok": True}


# ==================================================
# Bulk update
# ==================================================
@router.post("/tasks/bulk-update")
async def bulk_update(payload: BulkUpdateIn, request: Request,
                      session_token: Optional[str] = Cookie(default=None),
                      authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    if not payload.task_ids:
        raise HTTPException(status_code=400, detail="task_ids required")

    upd = {k: v for k, v in payload.model_dump().items() if v is not None and k != "task_ids"}
    if not upd:
        raise HTTPException(status_code=400, detail="no fields to update")

    # If status_detail present, sync lane
    if upd.get("status_detail") in STATUS_TO_LANE:
        upd["status"] = STATUS_TO_LANE[upd["status_detail"]]
    elif upd.get("status") in LANE_TO_DEFAULT_STATUS and not upd.get("status_detail"):
        upd["status_detail"] = LANE_TO_DEFAULT_STATUS[upd["status"]]

    upd["updated_at"] = iso_now()
    upd["updated_by"] = user["user_id"]

    ev = _timeline_entry(user, TIMELINE_EVENTS["UPDATED"],
                         "Bulk update: " + ", ".join(f"{k}={v}" for k, v in upd.items()
                                                     if k not in ("updated_at", "updated_by")))
    await sdb.tasks.update_many(
        {"id": {"$in": payload.task_ids}},
        {"$set": upd, "$push": {"timeline": ev}},
    )
    return {"ok": True, "updated": len(payload.task_ids)}


# ==================================================
# Follow-ups
# ==================================================
@router.post("/tasks/{task_id}/follow-ups")
async def add_follow_up(task_id: str, payload: FollowUpIn, request: Request,
                        session_token: Optional[str] = Cookie(default=None),
                        authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    existing = await sdb.tasks.find_one({"id": task_id}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Task not found")

    fu = payload.model_dump()
    fu["id"] = new_id("fu_")
    fu["created_at"] = iso_now()
    fu["created_by"] = user["user_id"]
    fu["created_by_name"] = user.get("name")
    fu.setdefault("status", "pending")

    ev = _timeline_entry(
        user, TIMELINE_EVENTS["FOLLOW_UP_ADDED"],
        f"Follow-up added ({fu.get('follow_up_date') or 'no date'}): "
        f"{(fu.get('notes') or '')[:80]}"
    )
    # Also bump the parent task's next reminder for dashboard queries
    parent_updates = {
        "updated_at": iso_now(),
        "updated_by": user["user_id"],
    }
    if fu.get("reminder_date"):
        parent_updates["reminder_date"] = fu["reminder_date"]
    if fu.get("reminder_time"):
        parent_updates["reminder_time"] = fu["reminder_time"]
    if fu.get("follow_up_date"):
        parent_updates["follow_up_date"] = fu["follow_up_date"]

    await sdb.tasks.update_one(
        {"id": task_id},
        {"$push": {"follow_ups": fu, "timeline": ev}, "$set": parent_updates},
    )
    return await sdb.tasks.find_one({"id": task_id}, {"_id": 0})


@router.patch("/tasks/{task_id}/follow-ups/{fu_id}")
async def update_follow_up(task_id: str, fu_id: str, payload: FollowUpIn, request: Request,
                           session_token: Optional[str] = Cookie(default=None),
                           authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    updates = {f"follow_ups.$.{k}": v for k, v in payload.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="no fields to update")
    updates["follow_ups.$.updated_at"] = iso_now()

    ev = _timeline_entry(user, TIMELINE_EVENTS["FOLLOW_UP_UPDATED"],
                         f"Follow-up {fu_id} updated")
    r = await sdb.tasks.update_one(
        {"id": task_id, "follow_ups.id": fu_id},
        {"$set": updates, "$push": {"timeline": ev}},
    )
    if r.matched_count == 0:
        raise HTTPException(status_code=404, detail="Follow-up not found")
    return await sdb.tasks.find_one({"id": task_id}, {"_id": 0})


@router.delete("/tasks/{task_id}/follow-ups/{fu_id}")
async def delete_follow_up(task_id: str, fu_id: str, request: Request,
                           session_token: Optional[str] = Cookie(default=None),
                           authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    ev = _timeline_entry(user, TIMELINE_EVENTS["FOLLOW_UP_UPDATED"],
                         f"Follow-up {fu_id} deleted")
    await sdb.tasks.update_one(
        {"id": task_id},
        {"$pull": {"follow_ups": {"id": fu_id}}, "$push": {"timeline": ev},
         "$set": {"updated_at": iso_now()}},
    )
    return {"ok": True}


# ==================================================
# Dashboard: upcoming reminders (next 7 days incl overdue open ones)
# ==================================================
@router.get("/tasks/reminders/upcoming")
async def upcoming_reminders(request: Request,
                             days: int = 7,
                             session_token: Optional[str] = Cookie(default=None),
                             authorization: Optional[str] = Header(default=None)):
    await require_user(request, session_token, authorization)
    today = now_utc().date().isoformat()
    horizon = (now_utc() + timedelta(days=days)).date().isoformat()

    q = {
        "status": {"$ne": "done"},
        "$or": [
            {"reminder_date": {"$lte": horizon}},
            {"follow_up_date": {"$lte": horizon}},
            {"due_date": {"$lte": horizon}},
        ],
    }
    rows = await sdb.tasks.find(q, {
        "_id": 0, "id": 1, "title": 1, "task_type": 1, "project_name": 1,
        "assignee_name": 1, "area": 1, "category": 1, "priority": 1,
        "status": 1, "status_detail": 1,
        "reminder_date": 1, "reminder_time": 1,
        "follow_up_date": 1, "due_date": 1,
    }).sort("reminder_date", 1).to_list(500)

    for r in rows:
        earliest = min(
            filter(None, [r.get("reminder_date"), r.get("follow_up_date"), r.get("due_date")]),
            default=None,
        )
        r["earliest_alert"] = earliest
        r["overdue"] = bool(earliest and earliest < today)
    return rows


# ==================================================
# Project scoped custom areas / categories
# ==================================================
@router.get("/projects/{project_id}/areas")
async def list_project_areas(project_id: str, request: Request,
                             session_token: Optional[str] = Cookie(default=None),
                             authorization: Optional[str] = Header(default=None)):
    await require_user(request, session_token, authorization)
    p = await sdb.projects.find_one({"id": project_id}, {"_id": 0, "custom_areas": 1})
    custom = (p or {}).get("custom_areas") or []
    return {"default": DEFAULT_AREAS, "custom": custom,
            "all": DEFAULT_AREAS + [a for a in custom if a not in DEFAULT_AREAS]}


@router.post("/projects/{project_id}/areas")
async def add_project_area(project_id: str, payload: CustomAreaIn, request: Request,
                           session_token: Optional[str] = Cookie(default=None),
                           authorization: Optional[str] = Header(default=None)):
    await require_user(request, session_token, authorization)
    p = await sdb.projects.find_one({"id": project_id}, {"_id": 0})
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")
    await sdb.projects.update_one(
        {"id": project_id},
        {"$addToSet": {"custom_areas": payload.name}},
    )
    return {"ok": True, "name": payload.name}


@router.delete("/projects/{project_id}/areas/{name}")
async def delete_project_area(project_id: str, name: str, request: Request,
                              session_token: Optional[str] = Cookie(default=None),
                              authorization: Optional[str] = Header(default=None)):
    await require_user(request, session_token, authorization)
    await sdb.projects.update_one(
        {"id": project_id},
        {"$pull": {"custom_areas": name}},
    )
    return {"ok": True}


@router.get("/projects/{project_id}/categories")
async def list_project_categories(project_id: str, request: Request,
                                  session_token: Optional[str] = Cookie(default=None),
                                  authorization: Optional[str] = Header(default=None)):
    await require_user(request, session_token, authorization)
    p = await sdb.projects.find_one({"id": project_id}, {"_id": 0, "custom_categories": 1})
    custom = (p or {}).get("custom_categories") or []
    return {"default": DEFAULT_CATEGORIES,
            "default_employee": DEFAULT_CATEGORIES_EMPLOYEE,
            "default_vendor": DEFAULT_CATEGORIES_VENDOR,
            "custom": custom}


@router.post("/projects/{project_id}/categories")
async def add_project_category(project_id: str, payload: CustomCategoryIn, request: Request,
                               session_token: Optional[str] = Cookie(default=None),
                               authorization: Optional[str] = Header(default=None)):
    await require_user(request, session_token, authorization)
    p = await sdb.projects.find_one({"id": project_id}, {"_id": 0})
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")
    entry = {"name": payload.name, "task_type": payload.task_type}
    await sdb.projects.update_one(
        {"id": project_id},
        {"$addToSet": {"custom_categories": entry}},
    )
    return {"ok": True, **entry}


@router.delete("/projects/{project_id}/categories/{name}")
async def delete_project_category(project_id: str, name: str, request: Request,
                                  session_token: Optional[str] = Cookie(default=None),
                                  authorization: Optional[str] = Header(default=None)):
    await require_user(request, session_token, authorization)
    await sdb.projects.update_one(
        {"id": project_id},
        {"$pull": {"custom_categories": {"name": name}}},
    )
    return {"ok": True}
