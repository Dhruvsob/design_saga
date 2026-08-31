"""Generic comments / notes — attachable to any record.

One collection (`comments`), tenant-scoped. Used by Projects, Clients,
Tasks, Vendors, Leads detail views so discussion stays with the record.
"""
from typing import Optional
from fastapi import APIRouter, HTTPException, Request, Cookie, Header
from pydantic import BaseModel

from core.scoped_db import sdb
from core.deps import require_user
from core.helpers import iso_now, new_id

router = APIRouter()

ALLOWED_ENTITIES = {"project", "client", "task", "vendor", "lead", "invoice", "employee", "purchase_order"}


class CommentIn(BaseModel):
    entity_type: str
    entity_id: str
    body: str


@router.get("/comments")
async def list_comments(request: Request, entity_type: str, entity_id: str,
                        session_token: Optional[str] = Cookie(default=None),
                        authorization: Optional[str] = Header(default=None)):
    await require_user(request, session_token, authorization)
    rows = await sdb.comments.find(
        {"entity_type": entity_type, "entity_id": entity_id},
        {"_id": 0}).sort("created_at", 1).to_list(500)
    return rows


@router.post("/comments")
async def add_comment(payload: CommentIn, request: Request,
                      session_token: Optional[str] = Cookie(default=None),
                      authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    if payload.entity_type not in ALLOWED_ENTITIES:
        raise HTTPException(status_code=400, detail=f"Unknown entity type: {payload.entity_type}")
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
    if c.get("author_id") != user.get("user_id") and user.get("role") not in ("Admin", "SuperAdmin"):
        raise HTTPException(status_code=403, detail="You can only delete your own comments")
    await sdb.comments.delete_one({"id": comment_id})
    return {"ok": True}
