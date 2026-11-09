"""Site snags / issues with photo evidence and verified closure (PRJ-02).

Flow: anyone working on the project raises a snag (photo optional) and assigns
it to a team member or a vendor -> the assignee (or a manager) marks it fixed
with a photo of the fix -> a manager verifies and closes it, or reopens it.
Photos use the shared upload service (services.local_files), the same storage,
size/type checks and backups as site-visit photos and project files.
"""
from datetime import date as _date
from pathlib import Path
from typing import Literal, Optional

from fastapi import APIRouter, Cookie, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import Field

from core.access_control import get_visible_project, user_identity_ids
from core.audit import audit
from core.deps import require_user
from core.helpers import iso_now, new_id, next_sequence
from core.limits import MAX_LIST_ROWS
from core.rbac import has_any_permission, has_permission
from core.scoped_db import sdb
from core.tenancy import user_org_id
from models.base import FiniteModel
from services.local_files import remove_upload, resolve_storage_key, save_upload

router = APIRouter()

PHOTO_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
MAX_PHOTOS = 10
PRIORITIES = ("low", "normal", "high", "urgent")


class SnagUpdate(FiniteModel):
    title: Optional[str] = Field(default=None, min_length=2, max_length=160)
    area: Optional[str] = Field(default=None, max_length=120)
    description: Optional[str] = Field(default=None, max_length=1000)
    priority: Optional[Literal[PRIORITIES]] = None   # type: ignore[valid-type]
    due_date: Optional[str] = None
    assignee_user_id: Optional[str] = None
    vendor_id: Optional[str] = None


class SnagStatusIn(FiniteModel):
    action: Literal["close", "reopen", "wont_fix"]
    note: Optional[str] = Field(default=None, max_length=500)


def _can_raise(user: dict) -> bool:
    return has_any_permission(user, "tasks.create", "tasks.update", "projects.update")


def _require_raise(user: dict) -> None:
    if not _can_raise(user):
        raise HTTPException(status_code=403, detail="You cannot raise snags")


def _require_manage(user: dict) -> None:
    if not has_permission(user, "projects.update"):
        raise HTTPException(status_code=403, detail="Only a project manager can verify, reopen or cancel snags")


def _check_date(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    try:
        return _date.fromisoformat(str(value)[:10]).isoformat()
    except ValueError:
        raise HTTPException(status_code=400, detail="Due date must be a date like 2026-11-20")


def _public(s: dict) -> dict:
    out = {k: v for k, v in s.items() if k != "photos"}
    out["photos"] = [{k: p.get(k) for k in ("id", "kind", "caption", "uploaded_by_name", "captured_at")}
                     for p in s.get("photos") or []]
    return out


async def _event(snag_id: str, user: dict, action: str, note: Optional[str] = None, extra: Optional[dict] = None):
    await sdb.snags.update_one({"id": snag_id}, {"$push": {"history": {
        "at": iso_now(), "by": user["user_id"], "by_name": user.get("name"), "action": action,
        "note": (note or "").strip() or None}}, "$set": {"updated_at": iso_now(), **(extra or {})}})


async def _store_photo(user: dict, upload: UploadFile) -> dict:
    if Path(upload.filename or "").suffix.lower() not in PHOTO_EXTENSIONS:
        raise HTTPException(status_code=422, detail="Photos must be JPG, PNG or WebP")
    try:
        stored = await save_upload(upload, user_org_id(user) or "org_default")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(status_code=503, detail="File storage is unavailable") from exc
    if not str(stored.get("content_type") or "").startswith("image/"):
        remove_upload(stored["storage_key"])
        raise HTTPException(status_code=422, detail="Photos must be JPG, PNG or WebP")
    return stored


async def _snag(user: dict, snag_id: str) -> dict:
    s = await sdb.snags.find_one({"id": snag_id}, {"_id": 0})
    if not s:
        raise HTTPException(status_code=404, detail="Snag not found")
    await get_visible_project(user, s["project_id"])
    return s


async def _assignee_fields(user_id: Optional[str], vendor_id: Optional[str]) -> dict:
    out = {"assignee_user_id": None, "assignee_name": None, "vendor_id": None, "vendor_name": None}
    if user_id:
        u = await sdb.users.find_one({"user_id": user_id}, {"_id": 0, "user_id": 1, "name": 1}) \
            or await sdb.employees.find_one({"user_id": user_id}, {"_id": 0, "user_id": 1, "first_name": 1, "last_name": 1})
        if not u:
            raise HTTPException(status_code=400, detail="Choose a team member from this company")
        out["assignee_user_id"] = user_id
        out["assignee_name"] = u.get("name") or " ".join(x for x in [u.get("first_name"), u.get("last_name")] if x)
    if vendor_id:
        v = await sdb.vendors_acc.find_one({"id": vendor_id}, {"_id": 0, "id": 1, "name": 1})
        if not v:
            raise HTTPException(status_code=400, detail="Choose a vendor from this company")
        out["vendor_id"], out["vendor_name"] = v["id"], v.get("name")
    return out


@router.get("/projects/{project_id}/snags")
async def list_snags(project_id: str, request: Request,
                     session_token: Optional[str] = Cookie(default=None),
                     authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    await get_visible_project(user, project_id)
    rows = await sdb.snags.find({"project_id": project_id}, {"_id": 0}).sort("created_at", -1).to_list(MAX_LIST_ROWS)
    counts = {k: 0 for k in ("open", "fixed", "closed", "wont_fix")}
    for r in rows:
        counts[r.get("status", "open")] = counts.get(r.get("status", "open"), 0) + 1
    ids = await user_identity_ids(user)
    return {"snags": [_public(r) for r in rows], "counts": counts,
            "can_raise": _can_raise(user), "can_manage": has_permission(user, "projects.update"),
            "my_ids": sorted(i for i in ids if i)}


@router.post("/projects/{project_id}/snags")
async def raise_snag(project_id: str, request: Request,
                     title: str = Form(...), area: Optional[str] = Form(None),
                     description: Optional[str] = Form(None), priority: str = Form("normal"),
                     due_date: Optional[str] = Form(None), assignee_user_id: Optional[str] = Form(None),
                     vendor_id: Optional[str] = Form(None), photo: Optional[UploadFile] = File(None),
                     session_token: Optional[str] = Cookie(default=None),
                     authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    _require_raise(user)
    await get_visible_project(user, project_id)
    title = (title or "").strip()
    if len(title) < 2 or len(title) > 160:
        raise HTTPException(status_code=400, detail="Describe the snag in 2-160 characters")
    if priority not in PRIORITIES:
        raise HTTPException(status_code=400, detail="Priority must be low, normal, high or urgent")
    assignee = await _assignee_fields(assignee_user_id or None, vendor_id or None)
    stored = await _store_photo(user, photo) if photo is not None and photo.filename else None
    org = user_org_id(user) or "org_default"
    seq = await next_sequence(org, f"snag:{project_id}", 0)
    doc = {"id": new_id("sng_"), "number": f"SN-{seq - 1000:03d}", "project_id": project_id, "title": title,
           "area": (area or "").strip()[:120] or None, "description": (description or "").strip()[:1000] or None,
           "priority": priority, "due_date": _check_date(due_date), "status": "open", **assignee,
           "photos": [], "photo_count": 0, "reopen_count": 0,
           "created_at": iso_now(), "created_by": user["user_id"], "created_by_name": user.get("name"),
           "history": [{"at": iso_now(), "by": user["user_id"], "by_name": user.get("name"), "action": "raised", "note": None}]}
    if stored:
        doc["photos"] = [{"id": new_id("snp_"), "kind": "issue", **stored, "captured_at": iso_now(),
                          "uploaded_by": user["user_id"], "uploaded_by_name": user.get("name")}]
        doc["photo_count"] = 1
    try:
        await sdb.snags.insert_one(dict(doc))
    except Exception:
        if stored:
            remove_upload(stored["storage_key"])
        raise
    await audit(user, "snag.raise", target=doc["id"], target_type="snag",
                meta={"project_id": project_id, "number": doc["number"], "photo": bool(stored)})
    return _public(doc)


@router.patch("/snags/{snag_id}")
async def edit_snag(snag_id: str, payload: SnagUpdate, request: Request,
                    session_token: Optional[str] = Cookie(default=None),
                    authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    _require_raise(user)
    s = await _snag(user, snag_id)
    if s.get("created_by") != user["user_id"] and not has_permission(user, "projects.update"):
        raise HTTPException(status_code=403, detail="Only the person who raised it or a manager can edit this snag")
    if s["status"] in ("closed", "wont_fix"):
        raise HTTPException(status_code=409, detail="Reopen the snag before editing it")
    patch = payload.model_dump(exclude_unset=True)
    if "due_date" in patch:
        patch["due_date"] = _check_date(patch["due_date"])
    if "assignee_user_id" in patch or "vendor_id" in patch:
        patch.update(await _assignee_fields(
            patch.pop("assignee_user_id", s.get("assignee_user_id")) or None,
            patch.pop("vendor_id", s.get("vendor_id")) or None))
    for k in ("title", "area", "description"):
        if isinstance(patch.get(k), str):
            patch[k] = patch[k].strip() or None
    if patch.get("title") is None and "title" in patch:
        patch.pop("title")
    if patch:
        await sdb.snags.update_one({"id": snag_id, "status": s["status"]}, {"$set": {**patch, "updated_at": iso_now()}})
        await audit(user, "snag.update", target=snag_id, target_type="snag", meta=patch)
    return _public(await sdb.snags.find_one({"id": snag_id}, {"_id": 0}))


@router.post("/snags/{snag_id}/fixed")
async def mark_fixed(snag_id: str, request: Request, photo: UploadFile = File(...),
                     note: Optional[str] = Form(None),
                     session_token: Optional[str] = Cookie(default=None),
                     authorization: Optional[str] = Header(default=None)):
    """The assignee (or a manager) reports the fix with a photo as evidence."""
    user = await require_user(request, session_token, authorization)
    _require_raise(user)
    s = await _snag(user, snag_id)
    ids = await user_identity_ids(user)
    if s.get("assignee_user_id") not in ids and not has_permission(user, "projects.update"):
        raise HTTPException(status_code=403, detail="Only the assignee or a manager can mark this snag fixed")
    if s["status"] != "open":
        raise HTTPException(status_code=409, detail=f"This snag is {s['status'].replace('_', ' ')}")
    if int(s.get("photo_count") or 0) >= MAX_PHOTOS:
        raise HTTPException(status_code=409, detail=f"A snag can hold up to {MAX_PHOTOS} photos")
    stored = await _store_photo(user, photo)
    p = {"id": new_id("snp_"), "kind": "fix", **stored, "captured_at": iso_now(),
         "caption": (note or "").strip()[:300] or None,
         "uploaded_by": user["user_id"], "uploaded_by_name": user.get("name")}
    result = await sdb.snags.update_one(
        {"id": snag_id, "status": "open"},
        {"$push": {"photos": p}, "$inc": {"photo_count": 1},
         "$set": {"status": "fixed", "fixed_at": iso_now(), "fixed_by": user["user_id"], "fixed_by_name": user.get("name")}})
    if not result.modified_count:
        remove_upload(stored["storage_key"])
        raise HTTPException(status_code=409, detail="This snag changed meanwhile. Refresh and check.")
    await _event(snag_id, user, "fixed", note)
    await audit(user, "snag.fixed", target=snag_id, target_type="snag", meta={"photo_id": p["id"], "sha256": stored.get("sha256")})
    return _public(await sdb.snags.find_one({"id": snag_id}, {"_id": 0}))


@router.post("/snags/{snag_id}/status")
async def change_status(snag_id: str, payload: SnagStatusIn, request: Request,
                        session_token: Optional[str] = Cookie(default=None),
                        authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    _require_manage(user)
    s = await _snag(user, snag_id)
    allowed = {"close": {"fixed"}, "reopen": {"fixed", "closed", "wont_fix"}, "wont_fix": {"open"}}
    if s["status"] not in allowed[payload.action]:
        raise HTTPException(status_code=409, detail=(
            "Only a snag marked fixed (with its photo) can be verified and closed" if payload.action == "close"
            else f"A {s['status'].replace('_', ' ')} snag cannot be {payload.action.replace('_', ' ')}"))
    if payload.action in ("reopen", "wont_fix") and not (payload.note or "").strip():
        raise HTTPException(status_code=400, detail="Say why")
    new_status = {"close": "closed", "reopen": "open", "wont_fix": "wont_fix"}[payload.action]
    extra = {"closed_at": iso_now(), "closed_by_name": user.get("name")} if new_status == "closed" else {}
    update = {"$set": {"status": new_status, **extra}}
    if payload.action == "reopen":
        update["$inc"] = {"reopen_count": 1}
    result = await sdb.snags.update_one({"id": snag_id, "status": s["status"]}, update)
    if not result.modified_count:
        raise HTTPException(status_code=409, detail="This snag changed meanwhile. Refresh and check.")
    await _event(snag_id, user, {"close": "verified & closed", "reopen": "reopened", "wont_fix": "won't fix"}[payload.action], payload.note)
    await audit(user, f"snag.{payload.action}", target=snag_id, target_type="snag", meta={"note": payload.note})
    return _public(await sdb.snags.find_one({"id": snag_id}, {"_id": 0}))


@router.delete("/snags/{snag_id}")
async def delete_snag(snag_id: str, request: Request,
                      session_token: Optional[str] = Cookie(default=None),
                      authorization: Optional[str] = Header(default=None)):
    """Raised by mistake: only an open snag with no fix evidence can be removed."""
    user = await require_user(request, session_token, authorization)
    _require_raise(user)
    s = await _snag(user, snag_id)
    if s.get("created_by") != user["user_id"] and not has_permission(user, "projects.update"):
        raise HTTPException(status_code=403, detail="Only the person who raised it or a manager can delete this snag")
    if s["status"] != "open" or any(p.get("kind") == "fix" for p in s.get("photos") or []) or s.get("reopen_count"):
        raise HTTPException(status_code=409, detail="This snag has history. Use Won't fix instead of deleting it.")
    result = await sdb.snags.delete_one({"id": snag_id, "status": "open"})
    if result.deleted_count:
        for p in s.get("photos") or []:
            if p.get("storage_key"):
                remove_upload(p["storage_key"])
    await audit(user, "snag.delete", target=snag_id, target_type="snag", meta={"number": s.get("number")})
    return {"ok": True}


@router.get("/snags/{snag_id}/photos/{photo_id}")
async def snag_photo(snag_id: str, photo_id: str, request: Request,
                     session_token: Optional[str] = Cookie(default=None),
                     authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    s = await _snag(user, snag_id)
    photo = next((p for p in s.get("photos") or [] if p.get("id") == photo_id), None)
    if not photo or not photo.get("storage_key"):
        raise HTTPException(status_code=404, detail="Photo not found")
    try:
        path = resolve_storage_key(photo["storage_key"])
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Photo not found") from exc
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Stored photo is unavailable")
    return FileResponse(path, media_type=photo.get("content_type") or "application/octet-stream",
                        filename=photo.get("original_name") or "snag-photo.jpg", content_disposition_type="inline",
                        headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"})
