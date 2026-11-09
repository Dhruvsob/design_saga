"""Drawing register: one row per drawing number, revisions A, B, C ... per row.

Files are not stored here. Each revision points at a project file uploaded
through the existing project Files workflow (`files` collection), so there is
one file engine, one permission check and one storage/backup path.

Lifecycle of a revision: issued (for review / approval / construction / as
built) -> approved | rejected | commented. Issuing a new revision supersedes
the previous one; history is never rewritten. A drawing with issued
revisions is archived, not deleted.
"""
import re
from datetime import date as _date
from typing import Literal, Optional

from fastapi import APIRouter, Cookie, Header, HTTPException, Request
from fastapi.responses import Response
from pydantic import Field
from pymongo.errors import DuplicateKeyError

from core.access_control import get_visible_project
from core.audit import audit
from core.deps import require_user
from core.downloads import content_disposition
from core.helpers import business_today, iso_now, new_id
from core.limits import MAX_LIST_ROWS
from core.rbac import has_permission
from core.scoped_db import sdb
from core.xlsx import build_xlsx
from models.base import FiniteModel

router = APIRouter()

DISCIPLINES = ("Architecture", "Interior", "Furniture", "Structure", "MEP", "Landscape", "Other")
PURPOSES = {
    "review": "For review", "approval": "For approval",
    "construction": "For construction (GFC)", "as_built": "As built", "information": "For information",
}
_NUMBER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ._/-]{0,39}$")


class DrawingIn(FiniteModel):
    number: str = Field(min_length=1, max_length=40)
    title: str = Field(min_length=1, max_length=160)
    discipline: Literal[DISCIPLINES] = "Architecture"   # type: ignore[valid-type]
    scale: Optional[str] = Field(default=None, max_length=30)


class DrawingUpdate(FiniteModel):
    number: Optional[str] = Field(default=None, min_length=1, max_length=40)
    title: Optional[str] = Field(default=None, min_length=1, max_length=160)
    discipline: Optional[Literal[DISCIPLINES]] = None   # type: ignore[valid-type]
    scale: Optional[str] = Field(default=None, max_length=30)
    archived: Optional[bool] = None


class RevisionIn(FiniteModel):
    file_id: str
    purpose: Literal[tuple(PURPOSES)] = "review"   # type: ignore[valid-type]
    issued_to: Optional[str] = Field(default=None, max_length=160)
    issued_on: Optional[str] = None
    note: Optional[str] = Field(default=None, max_length=500)


class DecisionIn(FiniteModel):
    decision: Literal["approved", "rejected", "commented"]
    comment: Optional[str] = Field(default=None, max_length=500)


def _require(user: dict, perm: str) -> None:
    if not has_permission(user, perm):
        raise HTTPException(status_code=403, detail=f"Missing permission: {perm}")


def next_revision(previous: Optional[str]) -> str:
    """A, B, ... Z, AA, AB ... (spreadsheet-style)."""
    if not previous:
        return "A"
    letters = [ord(c) - 64 for c in previous.upper() if "A" <= c <= "Z"]
    n = 0
    for x in letters:
        n = n * 26 + x
    n += 1
    out = ""
    while n:
        n, r = divmod(n - 1, 26)
        out = chr(65 + r) + out
    return out


def _clean_number(raw: str) -> str:
    number = re.sub(r"\s+", " ", str(raw or "")).strip().upper()
    if not _NUMBER.match(number):
        raise HTTPException(status_code=400, detail="Drawing number may use letters, digits, space, . _ / - (e.g. A-101)")
    return number


def _shape(d: dict) -> dict:
    revs = d.get("revisions") or []
    current = revs[-1] if revs else None
    return {**d, "current": current, "revision_count": len(revs)}


async def _drawing(user: dict, drawing_id: str, perm: str) -> dict:
    d = await sdb.drawings.find_one({"id": drawing_id}, {"_id": 0})
    if not d:
        raise HTTPException(status_code=404, detail="Drawing not found")
    await get_visible_project(user, d["project_id"], permission=perm)
    return d


@router.get("/projects/{project_id}/drawings")
async def list_drawings(project_id: str, request: Request, include_archived: bool = False,
                        session_token: Optional[str] = Cookie(default=None),
                        authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    _require(user, "files.read")
    await get_visible_project(user, project_id)
    q = {"project_id": project_id}
    if not include_archived:
        q["archived"] = {"$ne": True}
    rows = await sdb.drawings.find(q, {"_id": 0}).sort("number", 1).to_list(MAX_LIST_ROWS)
    shaped = [_shape(d) for d in rows]
    counts = {"total": len(shaped), "approved": 0, "awaiting": 0, "construction": 0}
    for d in shaped:
        cur = d["current"] or {}
        if cur.get("status") == "approved":
            counts["approved"] += 1
        if cur.get("status") == "issued" and cur.get("purpose") in ("review", "approval"):
            counts["awaiting"] += 1
        if cur.get("purpose") == "construction":
            counts["construction"] += 1
    return {"drawings": shaped, "counts": counts, "purposes": PURPOSES, "disciplines": list(DISCIPLINES)}


@router.post("/projects/{project_id}/drawings")
async def create_drawing(project_id: str, payload: DrawingIn, request: Request,
                         session_token: Optional[str] = Cookie(default=None),
                         authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    _require(user, "files.create")
    await get_visible_project(user, project_id)
    number = _clean_number(payload.number)
    if await sdb.drawings.find_one({"project_id": project_id, "number": number}, {"_id": 0, "id": 1}):
        raise HTTPException(status_code=409, detail=f"Drawing {number} already exists in this project")
    doc = {"id": new_id("drw_"), "project_id": project_id, "number": number,
           "title": payload.title.strip(), "discipline": payload.discipline,
           "scale": (payload.scale or "").strip() or None, "revisions": [], "rev_count": 0, "archived": False,
           "created_at": iso_now(), "created_by": user["user_id"], "created_by_name": user.get("name")}
    try:
        await sdb.drawings.insert_one(dict(doc))
    except DuplicateKeyError:
        raise HTTPException(status_code=409, detail=f"Drawing {number} already exists in this project")
    await audit(user, "drawing.create", target=doc["id"], target_type="drawing",
                meta={"project_id": project_id, "number": number})
    return _shape(doc)


@router.patch("/drawings/{drawing_id}")
async def update_drawing(drawing_id: str, payload: DrawingUpdate, request: Request,
                         session_token: Optional[str] = Cookie(default=None),
                         authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    _require(user, "files.create")
    d = await _drawing(user, drawing_id, "projects.read")
    patch = {k: v for k, v in payload.model_dump(exclude_unset=True).items() if v is not None}
    if "number" in patch:
        patch["number"] = _clean_number(patch["number"])
        clash = await sdb.drawings.find_one(
            {"project_id": d["project_id"], "number": patch["number"], "id": {"$ne": drawing_id}}, {"_id": 0, "id": 1})
        if clash:
            raise HTTPException(status_code=409, detail=f"Drawing {patch['number']} already exists in this project")
        if d.get("revisions") and patch["number"] != d["number"]:
            raise HTTPException(status_code=409, detail="This drawing has been issued; its number is fixed. Add a new drawing instead.")
    if "title" in patch:
        patch["title"] = patch["title"].strip()
    if not patch:
        return _shape(d)
    patch["updated_at"] = iso_now()
    await sdb.drawings.update_one({"id": drawing_id}, {"$set": patch})
    await audit(user, "drawing.archive" if patch.get("archived") else "drawing.update", target=drawing_id,
                target_type="drawing", meta={k: v for k, v in patch.items() if k != "updated_at"})
    return _shape(await sdb.drawings.find_one({"id": drawing_id}, {"_id": 0}))


@router.delete("/drawings/{drawing_id}")
async def delete_drawing(drawing_id: str, request: Request,
                         session_token: Optional[str] = Cookie(default=None),
                         authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    _require(user, "files.create")
    d = await _drawing(user, drawing_id, "projects.read")
    if d.get("revisions"):
        raise HTTPException(status_code=409, detail="This drawing has issued revisions. Archive it instead so its history stays.")
    result = await sdb.drawings.delete_one({"id": drawing_id, "rev_count": {"$in": [0, None]}})
    if not result.deleted_count:
        raise HTTPException(status_code=409, detail="A revision was issued meanwhile. Archive it instead.")
    await audit(user, "drawing.delete", target=drawing_id, target_type="drawing", meta={"number": d.get("number")})
    return {"ok": True}


@router.post("/drawings/{drawing_id}/revisions")
async def issue_revision(drawing_id: str, payload: RevisionIn, request: Request,
                         session_token: Optional[str] = Cookie(default=None),
                         authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    _require(user, "files.create")
    d = await _drawing(user, drawing_id, "projects.read")
    if d.get("archived"):
        raise HTTPException(status_code=409, detail="Restore this drawing before issuing a revision")
    f = await sdb.files.find_one({"id": payload.file_id}, {"_id": 0, "id": 1, "project_id": 1, "name": 1, "url": 1})
    if not f or f.get("project_id") != d["project_id"]:
        raise HTTPException(status_code=400, detail="Choose a file uploaded to this project")
    issued_on = payload.issued_on or business_today().isoformat()
    try:
        _date.fromisoformat(issued_on)
    except ValueError:
        raise HTTPException(status_code=400, detail="Issue date must be a date like 2026-11-09")
    revs = d.get("revisions") or []
    rev = {"rev": next_revision(revs[-1]["rev"] if revs else None), "file_id": f["id"], "file_name": f.get("name"),
           "file_url": f.get("url"), "purpose": payload.purpose, "issued_to": (payload.issued_to or "").strip() or None,
           "issued_on": issued_on, "note": (payload.note or "").strip() or None, "status": "issued",
           "created_at": iso_now(), "created_by": user["user_id"], "created_by_name": user.get("name")}
    # Compare-and-set on the revision count so two people cannot issue the same letter.
    new_revs = [dict(r) for r in revs]
    if new_revs:
        prev = new_revs[-1]
        prev["superseded_by"] = rev["rev"]
        if prev.get("status") != "rejected":
            prev["status"] = "superseded"
    new_revs.append(rev)
    updates = {"$set": {"revisions": new_revs, "rev_count": len(new_revs), "updated_at": iso_now()}}
    current = {"rev_count": len(revs)} if len(revs) else {"rev_count": {"$in": [0, None]}}
    result = await sdb.drawings.update_one({"id": drawing_id, **current}, updates)
    if not result.modified_count:
        raise HTTPException(status_code=409, detail="Someone issued a revision just now. Refresh and try again.")
    await audit(user, "drawing.revision.issue", target=drawing_id, target_type="drawing",
                meta={"number": d["number"], "rev": rev["rev"], "purpose": rev["purpose"], "file_id": f["id"]})
    return _shape(await sdb.drawings.find_one({"id": drawing_id}, {"_id": 0}))


@router.post("/drawings/{drawing_id}/revisions/{rev}/decision")
async def decide_revision(drawing_id: str, rev: str, payload: DecisionIn, request: Request,
                          session_token: Optional[str] = Cookie(default=None),
                          authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    _require(user, "projects.update")
    d = await _drawing(user, drawing_id, "projects.read")
    revs = d.get("revisions") or []
    if not revs or revs[-1]["rev"] != rev.upper():
        raise HTTPException(status_code=409, detail="Only the current revision can be approved or rejected")
    if revs[-1]["status"] != "issued":
        raise HTTPException(status_code=409, detail=f"Revision {rev.upper()} is already {revs[-1]['status']}")
    if payload.decision == "rejected" and not (payload.comment or "").strip():
        raise HTTPException(status_code=400, detail="Say what needs to change")
    i = len(revs) - 1
    result = await sdb.drawings.update_one(
        {"id": drawing_id, f"revisions.{i}.rev": revs[i]["rev"], f"revisions.{i}.status": "issued"},
        {"$set": {f"revisions.{i}.status": payload.decision, f"revisions.{i}.decided_at": iso_now(),
                  f"revisions.{i}.decided_by": user["user_id"], f"revisions.{i}.decided_by_name": user.get("name"),
                  f"revisions.{i}.comment": (payload.comment or "").strip() or None, "updated_at": iso_now()}})
    if not result.modified_count:
        raise HTTPException(status_code=409, detail="This revision changed meanwhile. Refresh and check.")
    await audit(user, f"drawing.revision.{payload.decision}", target=drawing_id, target_type="drawing",
                meta={"number": d["number"], "rev": revs[i]["rev"], "comment": payload.comment})
    return _shape(await sdb.drawings.find_one({"id": drawing_id}, {"_id": 0}))


@router.get("/projects/{project_id}/drawings/register.xlsx")
async def drawing_register_export(project_id: str, request: Request,
                                  session_token: Optional[str] = Cookie(default=None),
                                  authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    _require(user, "files.read")
    project = await get_visible_project(user, project_id, projection={"_id": 0, "id": 1, "name": 1})
    rows = await sdb.drawings.find({"project_id": project_id}, {"_id": 0}).sort("number", 1).to_list(MAX_LIST_ROWS)
    fmt = lambda iso: _date.fromisoformat(iso[:10]).strftime("%d/%m/%Y") if iso else ""   # noqa: E731
    register = [["Number", "Title", "Discipline", "Scale", "Current rev", "Purpose", "Status", "Issued on", "Issued to", "Archived"]]
    history = [["Number", "Rev", "Purpose", "Status", "Issued on", "Issued to", "File", "Decided by", "Comment / note"]]
    for d in rows:
        cur = (d.get("revisions") or [{}])[-1] if d.get("revisions") else {}
        register.append([d["number"], d.get("title"), d.get("discipline"), d.get("scale"), cur.get("rev", "—"),
                         PURPOSES.get(cur.get("purpose"), ""), (cur.get("status") or "not issued").title(),
                         fmt(cur.get("issued_on")), cur.get("issued_to"), bool(d.get("archived"))])
        for r in d.get("revisions") or []:
            history.append([d["number"], r["rev"], PURPOSES.get(r.get("purpose"), r.get("purpose")), r.get("status", "").title(),
                            fmt(r.get("issued_on")), r.get("issued_to"), r.get("file_name"), r.get("decided_by_name"),
                            r.get("comment") or r.get("note")])
    data = build_xlsx([("Drawing register", register), ("Revision history", history)])
    name = f"drawing-register-{re.sub(r'[^A-Za-z0-9]+', '-', project.get('name') or project_id).strip('-')[:60]}.xlsx"
    return Response(content=data, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": content_disposition("attachment", name)})
