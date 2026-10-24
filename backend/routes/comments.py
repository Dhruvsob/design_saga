"""Generic comments / notes — attachable to any record.

One collection (`comments`), tenant-scoped. Used by Projects, Clients,
Tasks, Vendors, Leads detail views so discussion stays with the record.
"""
from typing import Optional
from fastapi import APIRouter, HTTPException, Request, Cookie, Header, Query
from pydantic import BaseModel, Field

from core.scoped_db import sdb
from core.deps import require_user
from core.helpers import iso_now, new_id
from core.rbac import has_permission
from core.access_control import get_visible_project, get_visible_purchase_order, get_visible_task

router = APIRouter()

ALLOWED_ENTITIES = {"project", "client", "task", "vendor", "lead", "invoice", "employee", "purchase_order"}


class CommentIn(BaseModel):
    entity_type: str
    entity_id: str = Field(min_length=1, max_length=100)
    body: str = Field(min_length=1, max_length=5000)


ENTITY_RULES = {
    "client": ("clients", "clients.read"),
    "vendor": ("vendors_acc", "vendors.read"),
    "lead": ("leads", "leads.read"),
    "invoice": ("invoices", "invoices.read"),
    "employee": ("employees", "employees.read"),
    "purchase_order": ("purchase_orders", "purchase_orders.read"),
}


async def _require_entity_access(user: dict, entity_type: str, entity_id: str) -> None:
    """Require the same read boundary as the entity's primary endpoint."""
    if entity_type not in ALLOWED_ENTITIES:
        raise HTTPException(status_code=400, detail=f"Unknown entity type: {entity_type}")
    if entity_type == "project":
        await get_visible_project(user, entity_id, projection={"_id": 0, "id": 1})
        return
    if entity_type == "task":
        await get_visible_task(user, entity_id, projection={"_id": 0, "id": 1})
        return
    if entity_type == "purchase_order":
        await get_visible_purchase_order(user, entity_id, projection={"_id": 0, "id": 1})
        return

    collection_name, permission = ENTITY_RULES[entity_type]
    if not has_permission(user, permission):
        raise HTTPException(status_code=403, detail=f"Missing permission: {permission}")
    if not await getattr(sdb, collection_name).find_one({"id": entity_id}, {"_id": 0, "id": 1}):
        raise HTTPException(status_code=404, detail=f"{entity_type.replace('_', ' ').title()} not found")


@router.get("/comments")
async def list_comments(request: Request,
                        entity_type: str = Query(min_length=1, max_length=50),
                        entity_id: str = Query(min_length=1, max_length=100),
                        session_token: Optional[str] = Cookie(default=None),
                        authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    await _require_entity_access(user, entity_type, entity_id)
    rows = await sdb.comments.find(
        {"entity_type": entity_type, "entity_id": entity_id},
        {"_id": 0}).sort("created_at", 1).to_list(500)
    return rows


@router.post("/comments")
async def add_comment(payload: CommentIn, request: Request,
                      session_token: Optional[str] = Cookie(default=None),
                      authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    await _require_entity_access(user, payload.entity_type, payload.entity_id)
    body = (payload.body or "").strip()
    if not body:
        raise HTTPException(status_code=400, detail="Comment cannot be empty")
    if len(body) > 5000:
        raise HTTPException(status_code=400, detail="Comment too long (max 5000 chars)")
    doc = {
        "id": new_id("cmt_"),
        "entity_type": payload.entity_type,
        "entity_id": payload.entity_id,
        "body": body,
        "author_id": user.get("user_id"),
        "author_name": user.get("name"),
        "author_role": user.get("role"),
        "created_at": iso_now(),
    }
    await sdb.comments.insert_one(dict(doc))
    doc.pop("_id", None)
    return doc


@router.delete("/comments/{comment_id}")
async def delete_comment(comment_id: str, request: Request,
                         session_token: Optional[str] = Cookie(default=None),
                         authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    c = await sdb.comments.find_one({"id": comment_id}, {"_id": 0})
    if not c:
        raise HTTPException(status_code=404, detail="Comment not found")
    await _require_entity_access(user, c.get("entity_type"), c.get("entity_id"))
    if c.get("author_id") != user.get("user_id") and not has_permission(user, "*.*"):
        raise HTTPException(status_code=403, detail="You can only delete your own comments")
    await sdb.comments.delete_one({"id": comment_id})
    return {"ok": True}
