"""Client approvals (P2.6): one approvals model for drawings, variations and
other documents, decided by the client in the portal.

Studio side (signed in, `projects.update` to ask or withdraw):
  GET    /projects/{id}/approvals          requests, personal links, totals
  POST   /projects/{id}/approvals          ask the client to approve something
  POST   /approvals/{id}/withdraw          take a pending request back
  POST   /projects/{id}/portal-people      personal portal link for a client contact
  POST   /portal-people/{id}/new-link      replace a contact's link (old one stops)
  DELETE /portal-people/{id}               revoke a contact's link

Client side (public, token is the credential, rate-limited):
  GET    /portal/{token}/approvals/{id}/file      the document being approved
  POST   /portal/{token}/approvals/{id}/decision  approve / ask for changes

Only a personal link can decide, so each decision names the person who made
it. A drawing decision is written onto the drawing revision itself (status,
who, when, comment, "client portal") and both the request and the drawing get
an audit row. Issuing a newer revision or deciding in the studio closes any
pending client request for that drawing.
"""
import re
from typing import Literal, Optional

from fastapi import APIRouter, Cookie, Header, HTTPException, Request
from pydantic import Field

from core import portal
from core.access_control import get_visible_project
from core.audit import audit
from core.db import db
from core.deps import require_user
from core.helpers import iso_now, new_id
from core.limits import MAX_LIST_ROWS
from core.rbac import has_permission
from core.scoped_db import sdb
from core.url_security import external_http_url
from models.base import FiniteModel

router = APIRouter()

KIND_LABEL = {"drawing": "Drawing", "variation": "Variation", "document": "Document",
              "selection": "Selection", "quotation": "Quotation"}
STATUS_LABEL = {"pending": "waiting for a decision", "approved": "approved",
                "changes_requested": "sent back for changes", "withdrawn": "withdrawn",
                "superseded": "replaced by a newer revision"}
CLIENT_VISIBLE = ("pending", "approved", "changes_requested")
MAX_PEOPLE = 20
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class ApprovalIn(FiniteModel):
    kind: Literal["drawing", "variation", "document"]
    drawing_id: Optional[str] = None
    title: Optional[str] = Field(default=None, max_length=160)
    description: Optional[str] = Field(default=None, max_length=2000)
    file_id: Optional[str] = None
    amount: Optional[float] = Field(default=None, ge=-1e10, le=1e10)
    days: Optional[int] = Field(default=None, ge=-3650, le=3650)
    note: Optional[str] = Field(default=None, max_length=1000)


class QuoteSendIn(FiniteModel):
    note: Optional[str] = Field(default=None, max_length=1000)


class WithdrawIn(FiniteModel):
    reason: Optional[str] = Field(default=None, max_length=300)


class PersonIn(FiniteModel):
    name: str = Field(min_length=1, max_length=120)
    email: Optional[str] = Field(default=None, max_length=200)
    phone: Optional[str] = Field(default=None, max_length=40)


class ClientDecisionIn(FiniteModel):
    decision: Literal["approve", "changes"]
    comment: Optional[str] = Field(default=None, max_length=1000)


def _require(user: dict, perm: str) -> None:
    if not has_permission(user, perm):
        raise HTTPException(status_code=403, detail=f"Missing permission: {perm}")


def _clean(text: Optional[str]) -> Optional[str]:
    return (text or "").strip() or None


def _event(event: str, by: Optional[str], comment: Optional[str] = None) -> dict:
    row = {"at": iso_now(), "event": event, "by": by}
    if comment:
        row["comment"] = comment
    return row


def summarise(rows: list[dict]) -> dict:
    out = {"pending": 0, "approved": 0, "changes_requested": 0,
           "variations_approved_amount": 0.0, "variations_approved_days": 0}
    for r in rows:
        if r.get("status") in out:
            out[r["status"]] += 1
        if r.get("kind") == "variation" and r.get("status") == "approved":
            out["variations_approved_amount"] = round(
                out["variations_approved_amount"] + float(r.get("amount") or 0), 2)
            out["variations_approved_days"] += int(r.get("days") or 0)
    return out


# ------------------------------------------------------------------ studio
@router.get("/projects/{project_id}/approvals")
async def list_approvals(project_id: str, request: Request,
                         session_token: Optional[str] = Cookie(default=None),
                         authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    await get_visible_project(user, project_id)
    rows = await sdb.approvals.find({"project_id": project_id}, {"_id": 0}) \
        .sort("requested_at", -1).to_list(MAX_LIST_ROWS)
    people = await sdb.portal_access.find(
        {"project_id": project_id, "revoked_at": None}, {"_id": 0, "token_hash": 0}) \
        .sort("created_at", 1).to_list(MAX_PEOPLE * 2)
    return {"approvals": rows, "people": [portal.contact_view(p) for p in people],
            "summary": summarise(rows), "can_manage": has_permission(user, "projects.update")}


@router.post("/projects/{project_id}/approvals")
async def request_approval(project_id: str, payload: ApprovalIn, request: Request,
                           session_token: Optional[str] = Cookie(default=None),
                           authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    _require(user, "projects.update")
    await get_visible_project(user, project_id)
    doc = {"id": new_id("apr_"), "project_id": project_id, "kind": payload.kind,
           "description": _clean(payload.description), "note": _clean(payload.note),
           "status": "pending", "requested_at": iso_now(), "requested_by": user["user_id"],
           "requested_by_name": user.get("name")}
    if payload.kind == "drawing":
        d = await sdb.drawings.find_one({"id": payload.drawing_id or "", "project_id": project_id}, {"_id": 0})
        if not d:
            raise HTTPException(status_code=404, detail="Drawing not found in this project")
        revs = d.get("revisions") or []
        if d.get("archived") or not revs:
            raise HTTPException(status_code=409, detail="Issue a revision of this drawing first")
        cur = revs[-1]
        if cur.get("status") != "issued":
            raise HTTPException(status_code=409, detail=f"Revision {cur['rev']} is already {cur.get('status')}")
        if await sdb.approvals.find_one({"drawing_id": d["id"], "rev": cur["rev"], "status": "pending"},
                                        {"_id": 0, "id": 1}):
            raise HTTPException(status_code=409, detail=f"Revision {cur['rev']} is already waiting for the client")
        doc.update({"title": f"{d['number']} rev {cur['rev']} · {d.get('title') or ''}".strip(" ·"),
                    "drawing_id": d["id"], "drawing_number": d["number"], "rev": cur["rev"],
                    "file_id": cur.get("file_id"), "file_name": cur.get("file_name"),
                    "description": doc["description"] or cur.get("note")})
    else:
        title = _clean(payload.title)
        if not title:
            raise HTTPException(status_code=400, detail="Give the request a short title")
        if payload.kind == "variation" and payload.amount is None:
            raise HTTPException(status_code=400, detail="Enter the cost change (0 if the price doesn't change)")
        doc.update({"title": title, "amount": None if payload.amount is None else round(payload.amount, 2),
                    "days": payload.days})
        if payload.file_id:
            f = await sdb.files.find_one({"id": payload.file_id}, {"_id": 0, "id": 1, "project_id": 1, "name": 1})
            if not f or f.get("project_id") != project_id:
                raise HTTPException(status_code=400, detail="Choose a file uploaded to this project")
            doc.update({"file_id": f["id"], "file_name": f.get("name")})
    doc["history"] = [_event("requested", user.get("name"), doc["note"])]
    await sdb.approvals.insert_one(dict(doc))
    await audit(user, "approval.request", target=doc["id"], target_type="approval",
                meta={"project_id": project_id, "kind": doc["kind"], "title": doc["title"],
                      "drawing_id": doc.get("drawing_id"), "rev": doc.get("rev"), "amount": doc.get("amount")})
    return doc


@router.post("/approvals/{approval_id}/withdraw")
async def withdraw_approval(approval_id: str, request: Request, payload: Optional[WithdrawIn] = None,
                            session_token: Optional[str] = Cookie(default=None),
                            authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    _require(user, "projects.update")
    a = await sdb.approvals.find_one({"id": approval_id}, {"_id": 0})
    if not a:
        raise HTTPException(status_code=404, detail="Request not found")
    await get_visible_project(user, a["project_id"])
    reason = _clean(payload.reason if payload else None)
    result = await sdb.approvals.update_one(
        {"id": approval_id, "status": "pending"},
        {"$set": {"status": "withdrawn", "closed_at": iso_now(),
                  "closed_reason": reason or f"Withdrawn by {user.get('name') or 'the studio'}"},
         "$push": {"history": _event("withdrawn", user.get("name"), reason)}})
    if not result.modified_count:
        raise HTTPException(status_code=409, detail=f"This request is already {STATUS_LABEL.get(a['status'], a['status'])}")
    if a.get("kind") == "selection":
        from routes.selections import reopen_after_withdraw
        await reopen_after_withdraw(a)
    elif a.get("kind") == "quotation":
        await sdb.quotations_adv.update_one(
            {"id": a.get("quotation_id"), "approval.client_approval_id": approval_id},
            {"$set": {"approval.client_status": "withdrawn"}})
    await audit(user, "approval.withdraw", target=approval_id, target_type="approval",
                meta={"project_id": a["project_id"], "title": a.get("title"), "reason": reason})
    return await sdb.approvals.find_one({"id": approval_id}, {"_id": 0})


@router.post("/quotations-adv/{quotation_id}/send-for-acceptance")
async def send_quotation_for_acceptance(quotation_id: str, request: Request,
                                        payload: Optional[QuoteSendIn] = None,
                                        session_token: Optional[str] = Cookie(default=None),
                                        authorization: Optional[str] = Header(default=None)):
    """Put this exact version of a quotation in the client portal for acceptance.

    The quotation's existing approval model already had a client side that
    nothing could fill ("Client decisions require a verified client approval
    link"); a personal portal link is that verified link. The client accepts
    or asks for changes; the decision names the person, and any later edit to
    the quotation makes the pending request stale.
    """
    user = await require_user(request, session_token, authorization)
    _require(user, "quotations.update")
    q = await sdb.quotations_adv.find_one({"id": quotation_id}, {"_id": 0})
    if not q:
        raise HTTPException(status_code=404, detail="Quotation not found")
    if q.get("status") == "converted" or q.get("converted_project_id"):
        raise HTTPException(status_code=409, detail="This quotation is already converted into a project")
    if not q.get("project_id"):
        raise HTTPException(status_code=409, detail="Link this quotation to a project first: the client portal belongs to a project")
    await get_visible_project(user, q["project_id"])
    total = float((q.get("cost") or {}).get("grand_total") or 0)
    if total <= 0:
        raise HTTPException(status_code=409, detail="Add the quotation's items or fee first; its total is zero")
    if not await sdb.portal_access.count_documents({"project_id": q["project_id"], "revoked_at": None}):
        raise HTTPException(status_code=409, detail="Add a client contact under the project's Approvals first, so someone can accept")
    pending = await sdb.approvals.find_one({"quotation_id": quotation_id, "status": "pending"}, {"_id": 0})
    if pending and pending.get("quotation_updated_at") == q.get("updated_at"):
        raise HTTPException(status_code=409, detail="This version is already waiting for the client")
    now = iso_now()
    if pending:
        await sdb.approvals.update_many({"quotation_id": quotation_id, "status": "pending"},
                                        {"$set": {"status": "superseded", "closed_at": now,
                                                  "closed_reason": "A newer version was sent"}})
    version = int(q.get("version") or 1)
    note = _clean(payload.note if payload else None)
    approval_id = new_id("apr_")
    approval = dict(q.get("approval") or {})
    if approval.get("internal_status") != "approved":
        approval.update({"internal_status": "approved", "internal_at": now, "internal_by": user.get("name"),
                         "internal_response": "Approved when sent to the client"})
    approval.update({"client_status": "pending", "client_requested_at": now,
                     "client_approval_id": approval_id, "client_by": None, "client_at": None,
                     "client_response": None})
    result = await sdb.quotations_adv.update_one(
        {"id": quotation_id, "updated_at": q.get("updated_at"), "converted_project_id": None},
        {"$set": {"approval": approval, "status": "sent", "updated_at": now}})
    if not result.matched_count:
        raise HTTPException(status_code=409, detail="Quotation changed; refresh and retry")
    label = q.get("number") or "Quotation"
    doc = {"id": approval_id, "project_id": q["project_id"], "kind": "quotation",
           "quotation_id": quotation_id, "quotation_version": version, "quotation_updated_at": now,
           "title": f"{label} v{version}: {q.get('project_title') or ''}".strip(": ")[:160],
           "description": f"Total Rs. {total:,.2f} including tax. Open the PDF for the full scope, items and payment plan.",
           "amount": round(total, 2), "note": note, "status": "pending", "requested_at": now,
           "requested_by": user["user_id"], "requested_by_name": user.get("name"),
           "history": [_event("requested", user.get("name"), note)]}
    await sdb.approvals.insert_one(dict(doc))
    await audit(user, "quotation.client.requested", target=quotation_id, target_type="quotation",
                meta={"approval_id": approval_id, "version": version, "total": round(total, 2),
                      "project_id": q["project_id"]})
    return {"approval": doc, "quotation": await sdb.quotations_adv.find_one({"id": quotation_id}, {"_id": 0})}


async def close_for_drawing(drawing_id: str, reason: str, rev: Optional[str] = None,
                            status: str = "superseded") -> None:
    """Close pending client requests when the drawing moves on without them."""
    q = {"drawing_id": drawing_id, "status": "pending"}
    if rev:
        q["rev"] = rev
    await sdb.approvals.update_many(q, {"$set": {"status": status, "closed_at": iso_now(),
                                                 "closed_reason": reason}})


@router.post("/projects/{project_id}/portal-people")
async def add_portal_person(project_id: str, payload: PersonIn, request: Request,
                            session_token: Optional[str] = Cookie(default=None),
                            authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    _require(user, "projects.update")
    await get_visible_project(user, project_id)
    email = (_clean(payload.email) or "").lower() or None
    if email and not _EMAIL.match(email):
        raise HTTPException(status_code=400, detail="Enter a valid email address or leave it blank")
    if await sdb.portal_access.count_documents({"project_id": project_id, "revoked_at": None}) >= MAX_PEOPLE:
        raise HTTPException(status_code=409, detail=f"A project can have up to {MAX_PEOPLE} client links")
    token = portal.new_personal_token()
    now = iso_now()
    doc = {"id": new_id("pax_"), "project_id": project_id, "name": payload.name.strip(), "email": email,
           "phone": _clean(payload.phone), "token_hash": portal.token_hash(token), "revoked_at": None,
           "last_used_at": None, "link_issued_at": now, "created_at": now,
           "created_by": user["user_id"], "created_by_name": user.get("name")}
    await sdb.portal_access.insert_one(dict(doc))
    await audit(user, "portal.person.add", target=doc["id"], target_type="portal_access",
                meta={"project_id": project_id, "name": doc["name"], "email": email})
    return {**portal.contact_view(doc), "token": token}


async def _person(user: dict, contact_id: str) -> dict:
    row = await sdb.portal_access.find_one({"id": contact_id, "revoked_at": None}, {"_id": 0, "token_hash": 0})
    if not row:
        raise HTTPException(status_code=404, detail="Client link not found")
    await get_visible_project(user, row["project_id"])
    return row


@router.post("/portal-people/{contact_id}/new-link")
async def renew_portal_link(contact_id: str, request: Request,
                            session_token: Optional[str] = Cookie(default=None),
                            authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    _require(user, "projects.update")
    row = await _person(user, contact_id)
    token = portal.new_personal_token()
    now = iso_now()
    await sdb.portal_access.update_one({"id": contact_id, "revoked_at": None},
                                       {"$set": {"token_hash": portal.token_hash(token), "link_issued_at": now}})
    await audit(user, "portal.person.new_link", target=contact_id, target_type="portal_access",
                meta={"project_id": row["project_id"], "name": row.get("name")})
    return {**portal.contact_view({**row, "link_issued_at": now}), "token": token}


@router.delete("/portal-people/{contact_id}")
async def revoke_portal_person(contact_id: str, request: Request,
                               session_token: Optional[str] = Cookie(default=None),
                               authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    _require(user, "projects.update")
    row = await _person(user, contact_id)
    await sdb.portal_access.update_one({"id": contact_id, "revoked_at": None},
                                       {"$set": {"revoked_at": iso_now(), "revoked_by": user["user_id"]}})
    await audit(user, "portal.person.revoke", target=contact_id, target_type="portal_access",
                meta={"project_id": row["project_id"], "name": row.get("name")})
    return {"ok": True}


# ------------------------------------------------------------------ client portal
def _file_link(token: str, a: dict, f: Optional[dict]) -> Optional[str]:
    if not f:
        return None
    if f.get("storage_key"):
        return f"/api/portal/{token}/approvals/{a['id']}/file"
    try:
        return external_http_url(f.get("url"))
    except (TypeError, ValueError):
        return None


async def for_portal(database, ctx: dict, token: str) -> list[dict]:
    """Client-safe list of what the studio asked this client to decide."""
    owned = {"project_id": ctx["project"]["id"], "org_id": ctx["org_id"]}
    rows = await database.approvals.find({**owned, "status": {"$in": list(CLIENT_VISIBLE)}},
                                         {"_id": 0}).to_list(MAX_LIST_ROWS)
    file_ids = [r["file_id"] for r in rows if r.get("file_id")]
    files = {}
    if file_ids:
        for f in await database.files.find({**owned, "id": {"$in": file_ids}},
                                           {"_id": 0, "id": 1, "storage_key": 1, "url": 1}).to_list(MAX_LIST_ROWS):
            files[f["id"]] = f
    keep = ("id", "kind", "title", "description", "note", "drawing_number", "rev", "amount", "days",
            "status", "requested_at", "requested_by_name", "decided_at", "decided_by_name", "decision_comment",
            "file_name")
    out = []
    for r in rows:
        item = {k: r.get(k) for k in keep}
        if r.get("kind") == "quotation":
            item["file_url"] = f"/api/portal/{token}/approvals/{r['id']}/file"
            item["file_name"] = f"{r.get('title') or 'Quotation'}.pdf"
        else:
            item["file_url"] = _file_link(token, r, files.get(r.get("file_id")))
        out.append(item)
    # waiting first (oldest first), then decided (newest first)
    pending = sorted([x for x in out if x["status"] == "pending"], key=lambda x: x.get("requested_at") or "")
    decided = sorted([x for x in out if x["status"] != "pending"],
                     key=lambda x: x.get("decided_at") or "", reverse=True)
    return pending + decided


@router.get("/portal/{token}/approvals/{approval_id}/file")
async def portal_approval_file(token: str, approval_id: str):
    ctx = await portal.resolve(db, token)
    owned = {"project_id": ctx["project"]["id"], "org_id": ctx["org_id"]}
    a = await db.approvals.find_one({**owned, "id": approval_id, "status": {"$in": list(CLIENT_VISIBLE)}},
                                    {"_id": 0})
    if a and a.get("kind") == "quotation":
        return await _quotation_pdf(owned, a)
    if not a or not a.get("file_id"):
        raise HTTPException(status_code=404, detail="File not found")
    f = await db.files.find_one({**owned, "id": a["file_id"]}, {"_id": 0})
    current, superseded = None, False
    if a.get("kind") == "drawing" and a.get("drawing_id"):
        d = await db.drawings.find_one({**owned, "id": a["drawing_id"]}, {"_id": 0, "revisions": 1})
        revs = (d or {}).get("revisions") or []
        current = revs[-1].get("rev") if revs else None
        from routes.drawings import is_superseded_file
        superseded = is_superseded_file(revs, a.get("rev"))
    from core.stamp import serve_drawing_file
    return await serve_drawing_file(f, current, superseded=superseded)


@router.post("/portal/{token}/approvals/{approval_id}/decision")
async def portal_decide(token: str, approval_id: str, payload: ClientDecisionIn):
    ctx = await portal.resolve(db, token)
    contact = ctx["contact"]
    if not contact:
        raise HTTPException(status_code=403, detail="Open the personal link the studio sent you to approve or send this back")
    org_id, project_id = ctx["org_id"], ctx["project"]["id"]
    owned = {"project_id": project_id, "org_id": org_id}
    a = await db.approvals.find_one({**owned, "id": approval_id}, {"_id": 0})
    if not a:
        raise HTTPException(status_code=404, detail="Request not found")
    if a.get("status") != "pending":
        raise HTTPException(status_code=409, detail=f"This request is already {STATUS_LABEL.get(a.get('status'), a.get('status'))}")
    comment = _clean(payload.comment)
    if payload.decision == "changes" and not comment:
        raise HTTPException(status_code=400, detail="Tell the studio what should change")
    status = "approved" if payload.decision == "approve" else "changes_requested"
    who = contact.get("name") or "Client"
    now = iso_now()

    if a.get("kind") == "selection":
        sel = await db.project_selections.find_one({**owned, "id": a.get("selection_id")}, {"_id": 0})
        if not sel or sel.get("status") != "sent" or sel.get("approval_id") != approval_id:
            await _supersede(owned, approval_id, now, "The selection changed before a decision was made")
            raise HTTPException(status_code=409, detail="The studio has changed this selection since it was sent. They will share the latest version.")
    quote = None
    if a.get("kind") == "quotation":
        quote = await db.quotations_adv.find_one({**owned, "id": a.get("quotation_id")}, {"_id": 0})
        if (not quote or quote.get("converted_project_id")
                or quote.get("updated_at") != a.get("quotation_updated_at")):
            await _supersede(owned, approval_id, now, "The quotation changed before a decision was made")
            raise HTTPException(status_code=409, detail="The studio has changed this quotation since it was sent. They will share the latest version.")

    drawing, index = None, None
    if a.get("kind") == "drawing":
        drawing = await db.drawings.find_one({**owned, "id": a.get("drawing_id")}, {"_id": 0})
        revs = (drawing or {}).get("revisions") or []
        if not revs or revs[-1].get("rev") != a.get("rev") or revs[-1].get("status") != "issued":
            await db.approvals.update_one(
                {**owned, "id": approval_id, "status": "pending"},
                {"$set": {"status": "superseded", "closed_at": now,
                          "closed_reason": "The drawing changed before a decision was made"}})
            raise HTTPException(status_code=409, detail="This drawing has changed since it was sent. The studio will share the latest revision.")
        index = len(revs) - 1

    result = await db.approvals.update_one(
        {**owned, "id": approval_id, "status": "pending"},
        {"$set": {"status": status, "decided_at": now, "decided_by_contact_id": contact["id"],
                  "decided_by_name": who, "decided_by_email": contact.get("email"),
                  "decision_comment": comment, "decided_via": "client_portal"},
         "$push": {"history": _event(status, f"{who} (client)", comment)}})
    if not result.modified_count:
        raise HTTPException(status_code=409, detail="This request changed just now. Refresh the page.")

    actor = {"user_id": f"portal:{contact['id']}", "email": contact.get("email"), "role": "Client",
             "org_id": org_id, "name": who}
    if a.get("kind") == "selection":
        from routes.selections import apply_client_decision
        if not await apply_client_decision(db, owned, a, status, who, comment, now):
            await _supersede(owned, approval_id, now, "The selection changed before the decision was saved")
            raise HTTPException(status_code=409, detail="The studio has changed this selection since it was sent. They will share the latest version.")
    if quote is not None:
        accepted = status == "approved"
        written = await db.quotations_adv.update_one(
            {**owned, "id": quote["id"], "updated_at": a.get("quotation_updated_at"), "converted_project_id": None},
            {"$set": {"approval.client_status": "approved" if accepted else "changes_requested",
                      "approval.client_at": now, "approval.client_by": who,
                      "approval.client_by_email": contact.get("email"),
                      "approval.client_response": comment, "approval.client_version": a.get("quotation_version"),
                      "approval.client_total": a.get("amount"),
                      "status": "approved" if accepted else "under_review", "updated_at": now}})
        if not written.modified_count:
            await _supersede(owned, approval_id, now, "The quotation changed before the decision was saved")
            raise HTTPException(status_code=409, detail="The studio has changed this quotation since it was sent. They will share the latest version.")
        await audit(actor, f"quotation.client.{'accepted' if accepted else 'changes_requested'}",
                    target=quote["id"], target_type="quotation", org_id=org_id,
                    meta={"version": a.get("quotation_version"), "total": a.get("amount"),
                          "comment": comment, "by": who, "approval_id": approval_id})
    if drawing is not None:
        i = index
        written = await db.drawings.update_one(
            {**owned, "id": drawing["id"], f"revisions.{i}.rev": a["rev"], f"revisions.{i}.status": "issued"},
            {"$set": {f"revisions.{i}.status": "approved" if status == "approved" else "rejected",
                      f"revisions.{i}.decision": "approved" if status == "approved" else "rejected",
                      f"revisions.{i}.decided_at": now, f"revisions.{i}.decided_by": actor["user_id"],
                      f"revisions.{i}.decided_by_name": f"{who} (client)", f"revisions.{i}.comment": comment,
                      f"revisions.{i}.decided_via": "client_portal", f"revisions.{i}.client_approval_id": approval_id,
                      "updated_at": now}})
        if not written.modified_count:
            await db.approvals.update_one(
                {**owned, "id": approval_id},
                {"$set": {"status": "superseded", "closed_at": now,
                          "closed_reason": "The drawing changed before the decision was saved"}})
            raise HTTPException(status_code=409, detail="This drawing has changed since it was sent. The studio will share the latest revision.")
        await audit(actor, f"drawing.revision.{'approved' if status == 'approved' else 'rejected'}",
                    target=drawing["id"], target_type="drawing", org_id=org_id,
                    meta={"number": drawing.get("number"), "rev": a["rev"], "comment": comment,
                          "via": "client_portal", "by": who, "approval_id": approval_id})
    await audit(actor, f"approval.client.{status}", target=approval_id, target_type="approval", org_id=org_id,
                meta={"project_id": project_id, "kind": a.get("kind"), "title": a.get("title"),
                      "amount": a.get("amount"), "comment": comment, "by": who})
    try:
        from core.notifications import emit
        verb = "approved" if status == "approved" else "asked for changes to"
        await emit([a.get("requested_by")], "client_decision", f"{who} {verb} {a.get('title')}",
                   body=comment or "", link=f"/projects/{project_id}?tab=Approvals",
                   priority="normal" if status == "approved" else "high",
                   meta={"project_id": project_id, "approval_id": approval_id})
    except Exception:  # noqa: BLE001 - a missed bell must not undo the decision
        pass
    return {"ok": True, "status": status}


async def _supersede(owned: dict, approval_id: str, now: str, reason: str) -> None:
    await db.approvals.update_one(
        {**owned, "id": approval_id, "status": {"$in": ["pending", "approved", "changes_requested"]}},
        {"$set": {"status": "superseded", "closed_at": now, "closed_reason": reason}})


async def _quotation_pdf(owned: dict, a: dict):
    """The quotation being decided, as the PDF the studio would send."""
    import io
    from fastapi.responses import StreamingResponse
    from core.downloads import content_disposition
    q = await db.quotations_adv.find_one({**owned, "id": a.get("quotation_id")}, {"_id": 0})
    if not q:
        raise HTTPException(status_code=404, detail="File not found")
    if a.get("status") == "pending" and q.get("updated_at") != a.get("quotation_updated_at"):
        raise HTTPException(status_code=409, detail="The studio has changed this quotation since it was sent. They will share the latest version.")
    org = await db.organizations.find_one({"org_id": owned["org_id"]}, {"_id": 0})
    if q.get("type") == "consultancy" and q.get("proposal"):
        from core.consultancy_proposal import generate_proposal_pdf
        pdf_bytes = generate_proposal_pdf(q, org)
    else:
        from server import generate_quotation_pdf_adv
        pdf_bytes = generate_quotation_pdf_adv(q, org)
    name = f'{q.get("number") or "quotation"}-v{a.get("quotation_version") or 1}.pdf'
    return StreamingResponse(io.BytesIO(pdf_bytes), media_type="application/pdf",
                             headers={"Content-Disposition": content_disposition("inline", name, "quotation.pdf"),
                                      "Cache-Control": "private, no-store"})
