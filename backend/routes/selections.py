"""Room-wise selections and finish approvals (P2.3).

A designer records, per room or area, which product or finish is proposed
(optionally from the Product & Material Library), its specification and
supplier, and gets the client's decision through the same client-portal
approvals as drawings and variations. Purchasing can see what is still
unapproved before raising an order.

Studio side (signed in):
  GET    /projects/{id}/selections          list + counts (projects.read, visible project)
  POST   /projects/{id}/selections          propose a selection          (projects.update)
  PATCH  /selections/{id}                   edit; a material change after a decision
                                            reopens it and withdraws a pending request
  DELETE /selections/{id}                   remove a selection not yet approved
  POST   /selections/{id}/send              ask the client in the portal
  POST   /selections/{id}/decision          record a decision the client gave in person

Client side: the portal decision route in routes/approvals.py writes the
decision back here (kind "selection").
"""
from typing import Literal, Optional

from fastapi import APIRouter, Cookie, Header, HTTPException, Request
from pydantic import Field

from core.access_control import get_visible_project
from core.audit import audit
from core.deps import require_user
from core.helpers import iso_now, new_id
from core.limits import MAX_LIST_ROWS
from core.rbac import has_permission
from core.scoped_db import sdb
from models.base import FiniteModel

router = APIRouter()

STATUS_LABEL = {"proposed": "proposed", "sent": "waiting for the client",
                "approved": "approved", "changes_requested": "sent back by the client"}
# Fields whose change means the client must look again.
MATERIAL = ("room", "item", "product_id", "specification", "supplier", "vendor_id", "quantity", "unit")


class SelectionIn(FiniteModel):
    room: str = Field(min_length=1, max_length=80)
    item: Optional[str] = Field(default=None, max_length=160)
    product_id: Optional[str] = Field(default=None, max_length=60)
    specification: Optional[str] = Field(default=None, max_length=1000)
    supplier: Optional[str] = Field(default=None, max_length=160)
    vendor_id: Optional[str] = Field(default=None, max_length=60)
    quantity: Optional[float] = Field(default=None, ge=0, le=1e7)
    unit: Optional[str] = Field(default=None, max_length=20)
    notes: Optional[str] = Field(default=None, max_length=1000)


class SelectionUpdate(FiniteModel):
    room: Optional[str] = Field(default=None, min_length=1, max_length=80)
    item: Optional[str] = Field(default=None, max_length=160)
    product_id: Optional[str] = Field(default=None, max_length=60)
    specification: Optional[str] = Field(default=None, max_length=1000)
    supplier: Optional[str] = Field(default=None, max_length=160)
    vendor_id: Optional[str] = Field(default=None, max_length=60)
    quantity: Optional[float] = Field(default=None, ge=0, le=1e7)
    unit: Optional[str] = Field(default=None, max_length=20)
    notes: Optional[str] = Field(default=None, max_length=1000)


class SendIn(FiniteModel):
    note: Optional[str] = Field(default=None, max_length=1000)


class StudioDecisionIn(FiniteModel):
    decision: Literal["approve", "changes"]
    note: str = Field(min_length=3, max_length=1000)   # how and when the client decided


def _clean(text: Optional[str]) -> Optional[str]:
    return (text or "").strip() or None


def _event(event: str, by: Optional[str], comment: Optional[str] = None) -> dict:
    row = {"at": iso_now(), "event": event, "by": by}
    if comment:
        row["comment"] = comment
    return row


def _require_manage(user: dict) -> None:
    if not has_permission(user, "projects.update"):
        raise HTTPException(status_code=403, detail="Missing permission: projects.update")


def summarise(rows: list[dict]) -> dict:
    out = {"total": len(rows), "proposed": 0, "sent": 0, "approved": 0, "changes_requested": 0}
    for r in rows:
        if r.get("status") in out:
            out[r["status"]] += 1
    out["not_approved"] = out["total"] - out["approved"]
    return out


async def _references(payload: dict) -> dict:
    """Validate library product and supplier inside the tenant; fill blanks from them."""
    extra = {}
    if payload.get("product_id"):
        p = await sdb.products.find_one({"id": payload["product_id"]},
                                        {"_id": 0, "id": 1, "name": 1, "brand": 1, "model": 1, "finish": 1,
                                         "dimensions": 1, "specs": 1, "unit": 1, "default_vendor_id": 1})
        if not p:
            raise HTTPException(status_code=400, detail="Choose a product from your library")
        extra["product_name"] = " ".join(x for x in (p.get("brand"), p.get("name")) if x)
        if not payload.get("item"):
            extra["item"] = extra["product_name"]
        if not payload.get("specification"):
            bits = [p.get("model"), p.get("finish"), p.get("dimensions")]
            bits += [f"{sp.get('label')}: {sp.get('value')}" for sp in (p.get("specs") or [])
                     if isinstance(sp, dict) and sp.get("label") and sp.get("value")]
            spec = "; ".join(b for b in bits if b)
            if spec:
                extra["specification"] = spec[:1000]
        if not payload.get("unit") and p.get("unit"):
            extra["unit"] = p["unit"]
        if not payload.get("vendor_id") and p.get("default_vendor_id"):
            extra["vendor_id"] = p["default_vendor_id"]
    vendor_id = payload.get("vendor_id") or extra.get("vendor_id")
    if vendor_id:
        v = await sdb.vendors.find_one({"id": vendor_id}, {"_id": 0, "id": 1, "name": 1})
        if not v:
            if payload.get("vendor_id"):
                raise HTTPException(status_code=400, detail="Choose a supplier from your vendors")
            extra.pop("vendor_id", None)
        elif not payload.get("supplier"):
            extra["supplier"] = v.get("name")
    return extra


async def _get(user: dict, selection_id: str) -> dict:
    row = await sdb.project_selections.find_one({"id": selection_id}, {"_id": 0})
    if not row:
        raise HTTPException(status_code=404, detail="Selection not found")
    await get_visible_project(user, row["project_id"])
    return row


@router.get("/projects/{project_id}/selections")
async def list_selections(project_id: str, request: Request,
                          session_token: Optional[str] = Cookie(default=None),
                          authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    await get_visible_project(user, project_id)
    rows = await sdb.project_selections.find({"project_id": project_id}, {"_id": 0}) \
        .sort([("room", 1), ("created_at", 1)]).to_list(MAX_LIST_ROWS)
    people = await sdb.portal_access.count_documents({"project_id": project_id, "revoked_at": None})
    return {"selections": rows, "summary": summarise(rows),
            "can_manage": has_permission(user, "projects.update"), "client_contacts": people}


@router.post("/projects/{project_id}/selections")
async def create_selection(project_id: str, payload: SelectionIn, request: Request,
                           session_token: Optional[str] = Cookie(default=None),
                           authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    _require_manage(user)
    await get_visible_project(user, project_id)
    data = {k: (_clean(v) if isinstance(v, str) else v) for k, v in payload.model_dump().items()}
    data.update(await _references(data))
    if not data.get("item"):
        raise HTTPException(status_code=400, detail="Name the item or choose it from the library")
    now = iso_now()
    doc = {"id": new_id("sel_"), "project_id": project_id, **data, "status": "proposed",
           "approval_id": None, "decided_at": None, "decided_by_name": None, "decision_comment": None,
           "decided_via": None, "created_at": now, "created_by": user["user_id"],
           "created_by_name": user.get("name"), "updated_at": now,
           "history": [_event("proposed", user.get("name"))]}
    await sdb.project_selections.insert_one(dict(doc))
    await audit(user, "selection.create", target=doc["id"], target_type="selection",
                meta={"project_id": project_id, "room": doc["room"], "item": doc["item"]})
    return doc


@router.patch("/selections/{selection_id}")
async def update_selection(selection_id: str, payload: SelectionUpdate, request: Request,
                           session_token: Optional[str] = Cookie(default=None),
                           authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    _require_manage(user)
    row = await _get(user, selection_id)
    changes = {k: (_clean(v) if isinstance(v, str) else v)
               for k, v in payload.model_dump(exclude_unset=True).items()}
    if changes.get("room") is None:
        changes.pop("room", None)
    if changes.get("product_id") or changes.get("vendor_id"):
        merged = {**row, **changes}
        if changes.get("product_id"):
            # A new library item replaces the old item text and specification
            # unless the designer typed new ones in the same edit.
            for key in ("item", "specification", "unit"):
                if key not in changes:
                    merged[key] = None
        extra = await _references(merged)
        changes.update({k: v for k, v in extra.items() if k not in changes})
    material = [k for k in MATERIAL if k in changes and changes[k] != row.get(k)]
    now = iso_now()
    update = {**changes, "updated_at": now}
    push = None
    if material and row.get("status") != "proposed":
        # The client decided on something else: they must see the new version.
        update.update({"status": "proposed", "approval_id": None, "decided_at": None,
                       "decided_by_name": None, "decision_comment": None, "decided_via": None})
        push = _event("changed", user.get("name"),
                      f"Changed {', '.join(material)} after it was {STATUS_LABEL.get(row['status'], row['status'])}")
        if row.get("approval_id"):
            await sdb.approvals.update_many(
                {"id": row["approval_id"], "status": "pending"},
                {"$set": {"status": "superseded", "closed_at": now,
                          "closed_reason": "The studio changed this selection"}})
    op = {"$set": update}
    if push:
        op["$push"] = {"history": push}
    result = await sdb.project_selections.update_one(
        {"id": selection_id, "updated_at": row.get("updated_at")}, op)
    if not result.matched_count:
        raise HTTPException(status_code=409, detail="This selection changed just now. Refresh and try again.")
    await audit(user, "selection.update", target=selection_id, target_type="selection",
                meta={"project_id": row["project_id"], "fields": sorted(changes), "reopened": bool(push)})
    return await sdb.project_selections.find_one({"id": selection_id}, {"_id": 0})


@router.delete("/selections/{selection_id}")
async def delete_selection(selection_id: str, request: Request,
                           session_token: Optional[str] = Cookie(default=None),
                           authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    _require_manage(user)
    row = await _get(user, selection_id)
    if row.get("status") == "approved":
        raise HTTPException(status_code=409, detail="An approved selection stays on record. Change it instead; the client will be asked again.")
    if row.get("approval_id"):
        await sdb.approvals.update_many(
            {"id": row["approval_id"], "status": "pending"},
            {"$set": {"status": "withdrawn", "closed_at": iso_now(),
                      "closed_reason": "The studio removed this selection"}})
    await sdb.project_selections.delete_one({"id": selection_id})
    await audit(user, "selection.delete", target=selection_id, target_type="selection",
                meta={"project_id": row["project_id"], "room": row.get("room"), "item": row.get("item")})
    return {"ok": True}


def _approval_text(row: dict) -> str:
    parts = [row.get("specification")]
    if row.get("supplier"):
        parts.append(f"Supplier: {row['supplier']}")
    if row.get("quantity"):
        parts.append(f"Quantity: {row['quantity']:g} {row.get('unit') or ''}".strip())
    return "\n".join(p for p in parts if p)[:2000] or None


@router.post("/selections/{selection_id}/send")
async def send_selection(selection_id: str, request: Request, payload: Optional[SendIn] = None,
                         session_token: Optional[str] = Cookie(default=None),
                         authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    _require_manage(user)
    row = await _get(user, selection_id)
    if row.get("status") == "sent":
        raise HTTPException(status_code=409, detail="This selection is already waiting for the client")
    if row.get("status") == "approved":
        raise HTTPException(status_code=409, detail="The client has already approved this selection")
    if not await sdb.portal_access.count_documents({"project_id": row["project_id"], "revoked_at": None}):
        raise HTTPException(status_code=409, detail="Add a client contact under Approvals first, so someone can decide")
    now = iso_now()
    note = _clean(payload.note if payload else None)
    approval = {"id": new_id("apr_"), "project_id": row["project_id"], "kind": "selection",
                "selection_id": row["id"], "selection_updated_at": row.get("updated_at"),
                "title": f"{row['room']}: {row['item']}"[:160], "description": _approval_text(row),
                "note": note, "status": "pending", "requested_at": now,
                "requested_by": user["user_id"], "requested_by_name": user.get("name"),
                "history": [_event("requested", user.get("name"), note)]}
    await sdb.approvals.insert_one(dict(approval))
    result = await sdb.project_selections.update_one(
        {"id": selection_id, "updated_at": row.get("updated_at")},
        {"$set": {"status": "sent", "approval_id": approval["id"], "sent_at": now},
         "$push": {"history": _event("sent to client", user.get("name"), note)}})
    if not result.matched_count:
        await sdb.approvals.update_one({"id": approval["id"]}, {"$set": {"status": "withdrawn", "closed_at": now,
                                                                          "closed_reason": "Selection changed while sending"}})
        raise HTTPException(status_code=409, detail="This selection changed just now. Refresh and try again.")
    await audit(user, "selection.send", target=selection_id, target_type="selection",
                meta={"project_id": row["project_id"], "approval_id": approval["id"]})
    return await sdb.project_selections.find_one({"id": selection_id}, {"_id": 0})


@router.post("/selections/{selection_id}/decision")
async def record_decision(selection_id: str, payload: StudioDecisionIn, request: Request,
                          session_token: Optional[str] = Cookie(default=None),
                          authorization: Optional[str] = Header(default=None)):
    """The client decided in person or by phone: record it with how and when."""
    user = await require_user(request, session_token, authorization)
    _require_manage(user)
    row = await _get(user, selection_id)
    if row.get("status") == "approved" and payload.decision == "approve":
        raise HTTPException(status_code=409, detail="Already approved")
    status = "approved" if payload.decision == "approve" else "changes_requested"
    now = iso_now()
    note = payload.note.strip()
    if row.get("approval_id"):
        await sdb.approvals.update_many(
            {"id": row["approval_id"], "status": "pending"},
            {"$set": {"status": "withdrawn", "closed_at": now,
                      "closed_reason": f"Decided in the studio: {note}"[:300]}})
    result = await sdb.project_selections.update_one(
        {"id": selection_id, "updated_at": row.get("updated_at")},
        {"$set": {"status": status, "decided_at": now, "decided_via": "studio",
                  "decided_by_name": f"{user.get('name') or 'Studio'} (recorded)",
                  "decision_comment": note, "approval_id": None, "updated_at": now},
         "$push": {"history": _event(f"{STATUS_LABEL[status]} (recorded by studio)", user.get("name"), note)}})
    if not result.matched_count:
        raise HTTPException(status_code=409, detail="This selection changed just now. Refresh and try again.")
    await audit(user, f"selection.{status}", target=selection_id, target_type="selection",
                meta={"project_id": row["project_id"], "via": "studio", "note": note})
    return await sdb.project_selections.find_one({"id": selection_id}, {"_id": 0})


async def apply_client_decision(database, owned: dict, approval: dict, status: str,
                                who: str, comment: Optional[str], now: str) -> bool:
    """Called by the portal decision route. False when the selection moved on."""
    row = await database.project_selections.find_one(
        {**owned, "id": approval.get("selection_id")}, {"_id": 0})
    if (not row or row.get("status") != "sent" or row.get("approval_id") != approval["id"]):
        return False
    result = await database.project_selections.update_one(
        {**owned, "id": row["id"], "status": "sent", "approval_id": approval["id"]},
        {"$set": {"status": status, "decided_at": now, "decided_via": "client_portal",
                  "decided_by_name": f"{who} (client)", "decision_comment": comment, "updated_at": now},
         "$push": {"history": _event(STATUS_LABEL[status], f"{who} (client)", comment)}})
    return bool(result.modified_count)


async def reopen_after_withdraw(approval: dict) -> None:
    """A withdrawn portal request puts the selection back to proposed."""
    await sdb.project_selections.update_one(
        {"id": approval.get("selection_id"), "approval_id": approval["id"], "status": "sent"},
        {"$set": {"status": "proposed", "approval_id": None, "updated_at": iso_now()}})
