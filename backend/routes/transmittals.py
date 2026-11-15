"""Drawing transmittals (P2.7): a numbered issue set of drawing revisions sent
to named recipients for a purpose, with a branded PDF and per-recipient
acknowledgement.

Studio (signed in):
  GET  /projects/{id}/transmittals                    files.read
  POST /projects/{id}/transmittals                    files.create
  GET  /transmittals/{id}/pdf                         files.read
  POST /transmittals/{id}/recipients/{rid}/acknowledge files.create (signed copy / reply received)
  POST /transmittals/{id}/void                        files.create (kept on record, marked VOID)

Client portal (public, the link is the credential, rate-limited):
  GET  /portal/{token}/transmittals/{id}/items/{n}/file
  GET  /portal/{token}/transmittals/{id}/pdf
  POST /portal/{token}/transmittals/{id}/acknowledge  personal link of a listed recipient only

A transmittal snapshots the revision letter and file of each drawing when it
is issued. When a newer revision is issued later, every view (studio, portal,
PDF) marks that line "superseded by rev X" so nobody builds from an old sheet.
Transmittals are never deleted; a wrong one is voided with a reason.
"""
import io
import re
from datetime import date as _date
from typing import Literal, Optional

from fastapi import APIRouter, Cookie, Header, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import Field
from pymongo import ReturnDocument

from core import portal
from core.access_control import get_visible_project
from core.audit import audit
from core.db import db
from core.deps import require_user
from core.downloads import content_disposition
from core.helpers import business_today, iso_now, new_id
from core.limits import MAX_LIST_ROWS
from core.rbac import has_permission
from core.scoped_db import sdb
from core.tenancy import DEFAULT_ORG_ID, user_org_id
from models.base import FiniteModel
from routes.drawings import PURPOSES

router = APIRouter()

MAX_ITEMS = 200
MAX_RECIPIENTS = 20
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class ItemIn(FiniteModel):
    drawing_id: str


class RecipientIn(FiniteModel):
    name: Optional[str] = Field(default=None, max_length=120)
    company: Optional[str] = Field(default=None, max_length=120)
    email: Optional[str] = Field(default=None, max_length=200)
    portal_person_id: Optional[str] = None


class TransmittalIn(FiniteModel):
    items: list[ItemIn] = Field(min_length=1, max_length=MAX_ITEMS)
    recipients: list[RecipientIn] = Field(min_length=1, max_length=MAX_RECIPIENTS)
    purpose: Literal[tuple(PURPOSES)] = "approval"   # type: ignore[valid-type]
    issued_date: Optional[str] = None
    note: Optional[str] = Field(default=None, max_length=1000)
    share_in_portal: bool = True


class AckIn(FiniteModel):
    note: Optional[str] = Field(default=None, max_length=300)
    received_date: Optional[str] = None


class VoidIn(FiniteModel):
    reason: str = Field(min_length=3, max_length=300)


class PortalAckIn(FiniteModel):
    note: Optional[str] = Field(default=None, max_length=300)


def _require(user: dict, perm: str) -> None:
    if not has_permission(user, perm):
        raise HTTPException(status_code=403, detail=f"Missing permission: {perm}")


def _clean(text: Optional[str]) -> Optional[str]:
    return (text or "").strip() or None


def _ddmmyyyy(iso: Optional[str]) -> str:
    try:
        return _date.fromisoformat(str(iso)[:10]).strftime("%d/%m/%Y")
    except (TypeError, ValueError):
        return ""


def decorate(t: dict, current: dict[str, dict]) -> dict:
    """Add superseded marks and acknowledgement status from live drawings.

    `current` maps drawing_id -> {"rev", "archived"} for the drawings in it.
    """
    items = []
    for it in t.get("items") or []:
        now = current.get(it.get("drawing_id")) or {}
        newer = now.get("rev") if now.get("rev") and now.get("rev") != it.get("rev") else None
        items.append({**it, "superseded_by": newer})
    recips = t.get("recipients") or []
    done = sum(1 for r in recips if r.get("acknowledged_at"))
    status = ("void" if t.get("status") == "void" else
              "acknowledged" if recips and done == len(recips) else
              "partly_acknowledged" if done else "awaiting")
    return {**t, "items": items, "ack_status": status, "acknowledged_count": done,
            "superseded_count": sum(1 for i in items if i["superseded_by"])}


async def _current_revs(database, org_id: Optional[str], rows: list[dict]) -> dict[str, dict]:
    ids = sorted({i.get("drawing_id") for t in rows for i in t.get("items") or [] if i.get("drawing_id")})
    if not ids:
        return {}
    q = {"id": {"$in": ids}}
    if org_id:
        q["org_id"] = org_id
    out = {}
    for d in await database.drawings.find(q, {"_id": 0, "id": 1, "revisions": 1, "archived": 1}).to_list(MAX_LIST_ROWS):
        revs = d.get("revisions") or []
        out[d["id"]] = {"rev": revs[-1].get("rev") if revs else None, "archived": bool(d.get("archived"))}
    return out


async def _next_number(org_id: str, project_id: str) -> str:
    key = {"org_id": org_id or DEFAULT_ORG_ID, "kind": f"transmittal:{project_id}"}
    if not await db.counters.find_one(key):
        try:
            await db.counters.insert_one({**key, "seq": 0})
        except Exception:  # noqa: BLE001 - a concurrent creator seeded it
            pass
    row = await db.counters.find_one_and_update(key, {"$inc": {"seq": 1}}, return_document=ReturnDocument.AFTER)
    return f"TR-{int(row['seq']):03d}"


async def _transmittal(user: dict, transmittal_id: str) -> dict:
    t = await sdb.transmittals.find_one({"id": transmittal_id}, {"_id": 0})
    if not t:
        raise HTTPException(status_code=404, detail="Transmittal not found")
    await get_visible_project(user, t["project_id"])
    return t


# ------------------------------------------------------------------ studio
@router.get("/projects/{project_id}/transmittals")
async def list_transmittals(project_id: str, request: Request,
                            session_token: Optional[str] = Cookie(default=None),
                            authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    _require(user, "files.read")
    await get_visible_project(user, project_id)
    rows = await sdb.transmittals.find({"project_id": project_id}, {"_id": 0}) \
        .sort("created_at", -1).to_list(MAX_LIST_ROWS)
    current = await _current_revs(sdb, None, rows)
    shaped = [decorate(t, current) for t in rows]
    live = [t for t in shaped if t["ack_status"] != "void"]
    return {"transmittals": shaped, "purposes": PURPOSES,
            "summary": {"total": len(live),
                        "awaiting": sum(1 for t in live if t["ack_status"] != "acknowledged"),
                        "with_superseded": sum(1 for t in live if t["superseded_count"])},
            "can_issue": has_permission(user, "files.create")}


@router.post("/projects/{project_id}/transmittals")
async def issue_transmittal(project_id: str, payload: TransmittalIn, request: Request,
                            session_token: Optional[str] = Cookie(default=None),
                            authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    _require(user, "files.create")
    await get_visible_project(user, project_id)

    ids = list(dict.fromkeys(i.drawing_id for i in payload.items))
    found = {d["id"]: d for d in await sdb.drawings.find(
        {"id": {"$in": ids}, "project_id": project_id}, {"_id": 0}).to_list(MAX_ITEMS)}
    items = []
    for drawing_id in ids:
        d = found.get(drawing_id)
        if not d:
            raise HTTPException(status_code=400, detail="Choose drawings from this project")
        revs = d.get("revisions") or []
        if d.get("archived") or not revs:
            raise HTTPException(status_code=400, detail=f"{d['number']} has no issued revision to send")
        cur = revs[-1]
        items.append({"drawing_id": d["id"], "number": d["number"], "title": d.get("title"),
                      "discipline": d.get("discipline"), "rev": cur["rev"], "rev_status": cur.get("status"),
                      "file_id": cur.get("file_id"), "file_name": cur.get("file_name")})
    items.sort(key=lambda i: i["number"])

    people = {p["id"]: p for p in await sdb.portal_access.find(
        {"project_id": project_id, "revoked_at": None}, {"_id": 0, "token_hash": 0}).to_list(MAX_RECIPIENTS * 2)}
    recipients, seen = [], set()
    for r in payload.recipients:
        if r.portal_person_id:
            p = people.get(r.portal_person_id)
            if not p:
                raise HTTPException(status_code=400, detail="That client link no longer exists. Refresh and choose again.")
            if p["id"] in seen:
                continue
            seen.add(p["id"])
            name, email, company = p.get("name"), p.get("email"), _clean(r.company) or "Client"
        else:
            name, email, company = _clean(r.name), (_clean(r.email) or "").lower() or None, _clean(r.company)
            if not name:
                raise HTTPException(status_code=400, detail="Give each recipient a name")
            if email and not _EMAIL.match(email):
                raise HTTPException(status_code=400, detail=f"Check the email address for {name}")
        recipients.append({"id": new_id("rcp_"), "name": name, "company": company, "email": email,
                           "portal_person_id": r.portal_person_id or None, "acknowledged_at": None})

    issued_date = payload.issued_date or business_today().isoformat()
    org_id = user_org_id(user) or DEFAULT_ORG_ID
    doc = {"id": new_id("trm_"), "project_id": project_id, "number": await _next_number(org_id, project_id),
           "issued_date": issued_date, "purpose": payload.purpose, "note": _clean(payload.note),
           "items": items, "recipients": recipients, "share_in_portal": bool(payload.share_in_portal),
           "status": "issued", "created_at": iso_now(), "created_by": user["user_id"],
           "created_by_name": user.get("name")}
    await sdb.transmittals.insert_one(dict(doc))
    await audit(user, "transmittal.issue", target=doc["id"], target_type="transmittal",
                meta={"project_id": project_id, "number": doc["number"], "purpose": doc["purpose"],
                      "items": [f"{i['number']} rev {i['rev']}" for i in items],
                      "recipients": [r["name"] for r in recipients]})
    return decorate(doc, {i["drawing_id"]: {"rev": i["rev"]} for i in items})


@router.post("/transmittals/{transmittal_id}/recipients/{recipient_id}/acknowledge")
async def record_acknowledgement(transmittal_id: str, recipient_id: str, payload: AckIn, request: Request,
                                 session_token: Optional[str] = Cookie(default=None),
                                 authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    _require(user, "files.create")
    t = await _transmittal(user, transmittal_id)
    if t.get("status") == "void":
        raise HTTPException(status_code=409, detail="This transmittal is void")
    idx = next((n for n, r in enumerate(t.get("recipients") or []) if r.get("id") == recipient_id), None)
    if idx is None:
        raise HTTPException(status_code=404, detail="Recipient not found")
    received = payload.received_date or business_today().isoformat()
    result = await sdb.transmittals.update_one(
        {"id": transmittal_id, f"recipients.{idx}.id": recipient_id, f"recipients.{idx}.acknowledged_at": None},
        {"$set": {f"recipients.{idx}.acknowledged_at": iso_now(), f"recipients.{idx}.received_date": received,
                  f"recipients.{idx}.acknowledged_via": "recorded",
                  f"recipients.{idx}.recorded_by_name": user.get("name"),
                  f"recipients.{idx}.ack_note": _clean(payload.note)}})
    if not result.modified_count:
        raise HTTPException(status_code=409, detail="Already acknowledged")
    await audit(user, "transmittal.acknowledge", target=transmittal_id, target_type="transmittal",
                meta={"number": t.get("number"), "recipient": t["recipients"][idx].get("name"),
                      "via": "recorded", "received_date": received})
    t = await sdb.transmittals.find_one({"id": transmittal_id}, {"_id": 0})
    return decorate(t, await _current_revs(sdb, None, [t]))


@router.post("/transmittals/{transmittal_id}/void")
async def void_transmittal(transmittal_id: str, payload: VoidIn, request: Request,
                           session_token: Optional[str] = Cookie(default=None),
                           authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    _require(user, "files.create")
    t = await _transmittal(user, transmittal_id)
    result = await sdb.transmittals.update_one(
        {"id": transmittal_id, "status": "issued"},
        {"$set": {"status": "void", "void_reason": payload.reason.strip(), "voided_at": iso_now(),
                  "voided_by_name": user.get("name")}})
    if not result.modified_count:
        raise HTTPException(status_code=409, detail="This transmittal is already void")
    await audit(user, "transmittal.void", target=transmittal_id, target_type="transmittal",
                meta={"number": t.get("number"), "reason": payload.reason.strip()})
    t = await sdb.transmittals.find_one({"id": transmittal_id}, {"_id": 0})
    return decorate(t, await _current_revs(sdb, None, [t]))


# ------------------------------------------------------------------ PDF
def transmittal_pdf(t: dict, org: Optional[dict], project: dict) -> bytes:
    from core.pdf_brand import (BrandedPDF, Brand, CONTENT_W, GREY, INK, LEFT, LINE, RIGHT,
                                draw_letterhead, safe_text, section_label)
    brand = Brand(org)
    pdf = BrandedPDF(brand, "Drawing transmittal", t.get("number") or "")
    pdf.add_page()
    draw_letterhead(pdf, "Drawing transmittal", [
        ("No.", t.get("number")), ("Date", _ddmmyyyy(t.get("issued_date"))),
        ("Issued for", PURPOSES.get(t.get("purpose"), t.get("purpose")))])

    if t.get("status") == "void":
        pdf.set_font("Helvetica", "B", 13)
        pdf.set_text_color(178, 43, 34)
        pdf.cell(CONTENT_W, 7, safe_text(f"VOID - {t.get('void_reason') or ''}")[:110], 0, 1)
        pdf.ln(1)

    section_label(pdf, "Project")
    pdf.set_font("Helvetica", "B", 10)
    pdf.set_text_color(*INK)
    pdf.multi_cell(CONTENT_W, 5, safe_text(project.get("name") or ""), 0, "L", new_x="LMARGIN", new_y="NEXT")
    if project.get("client_name"):
        pdf.set_font("Helvetica", "", 8.5)
        pdf.set_text_color(*GREY)
        pdf.cell(CONTENT_W, 4.5, safe_text(f"Client: {project['client_name']}"), 0, 1)
    pdf.ln(2)

    section_label(pdf, "To")
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(*INK)
    for r in t.get("recipients") or []:
        line = " | ".join(x for x in (r.get("name"), r.get("company"), r.get("email")) if x)
        pdf.multi_cell(CONTENT_W, 4.8, safe_text(line), 0, "L", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)

    section_label(pdf, "Drawings")
    cols = [("#", 8), ("Drawing no.", 30), ("Title", 82), ("Rev", 12), ("Status", 48)]
    pdf.set_fill_color(245, 244, 240)
    pdf.set_font("Helvetica", "B", 8)
    pdf.set_text_color(*GREY)
    for label, w in cols:
        pdf.cell(w, 6, label, 0, 0, "L", True)
    pdf.ln(6)
    pdf.set_draw_color(*LINE)
    for n, it in enumerate(t.get("items") or [], start=1):
        superseded = it.get("superseded_by")
        title = safe_text(it.get("title") or "")
        while title and pdf.get_string_width(title) > 80:
            title = title[:-2].rstrip() + "."
        pdf.set_font("Helvetica", "", 8.6)
        pdf.set_text_color(*INK)
        pdf.cell(8, 6, str(n), "B")
        pdf.set_font("Helvetica", "B", 8.6)
        pdf.cell(30, 6, safe_text(it.get("number"))[:18], "B")
        pdf.set_font("Helvetica", "", 8.6)
        pdf.cell(82, 6, title, "B")
        pdf.cell(12, 6, safe_text(it.get("rev")), "B")
        if superseded:
            pdf.set_font("Helvetica", "B", 8.2)
            pdf.set_text_color(178, 43, 34)
            pdf.cell(48, 6, safe_text(f"SUPERSEDED by rev {superseded}"), "B", 1)
        else:
            pdf.set_text_color(*GREY)
            pdf.cell(48, 6, "Current", "B", 1)
    pdf.ln(3)

    if t.get("note"):
        section_label(pdf, "Note")
        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(*INK)
        pdf.multi_cell(CONTENT_W, 4.8, safe_text(t["note"]), 0, "L", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(2)

    section_label(pdf, "Acknowledgement of receipt")
    for r in t.get("recipients") or []:
        pdf.set_font("Helvetica", "B", 9)
        pdf.set_text_color(*INK)
        pdf.cell(60, 6, safe_text(r.get("name"))[:34], 0, 0)
        pdf.set_font("Helvetica", "", 8.6)
        if r.get("acknowledged_at"):
            how = "in the client portal" if r.get("acknowledged_via") == "portal" else \
                f"(recorded by {r.get('recorded_by_name') or 'the studio'})"
            when = _ddmmyyyy(r.get("received_date") or r.get("acknowledged_at"))
            pdf.set_text_color(29, 99, 62)
            pdf.cell(RIGHT - LEFT - 60, 6, safe_text(f"Acknowledged on {when} {how}"), 0, 1)
        else:
            pdf.set_text_color(*GREY)
            pdf.cell(RIGHT - LEFT - 60, 6, "Received by ____________________   Signature ______________   Date ________", 0, 1)
    pdf.ln(3)
    pdf.set_font("Helvetica", "I", 7.8)
    pdf.set_text_color(*GREY)
    pdf.multi_cell(CONTENT_W, 4, safe_text(
        f"Issued by {t.get('created_by_name') or brand.name}. Lines marked SUPERSEDED have a newer revision; "
        "please use the latest revision for any work."), 0, "L", new_x="LMARGIN", new_y="NEXT")
    return pdf.to_bytes()


def _pdf_response(t: dict, data: bytes) -> StreamingResponse:
    name = f"transmittal-{t.get('number') or t['id']}.pdf"
    return StreamingResponse(io.BytesIO(data), media_type="application/pdf",
                             headers={"Content-Disposition": content_disposition("inline", name, "transmittal.pdf")})


@router.get("/transmittals/{transmittal_id}/pdf")
async def transmittal_pdf_route(transmittal_id: str, request: Request,
                                session_token: Optional[str] = Cookie(default=None),
                                authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    _require(user, "files.read")
    t = await _transmittal(user, transmittal_id)
    project = await get_visible_project(user, t["project_id"])
    org = await db.organizations.find_one({"org_id": user_org_id(user) or DEFAULT_ORG_ID}, {"_id": 0})
    t = decorate(t, await _current_revs(sdb, None, [t]))
    return _pdf_response(t, transmittal_pdf(t, org, project))


# ------------------------------------------------------------------ client portal
async def for_portal(database, ctx: dict, token: str) -> list[dict]:
    """Transmittals shared in the portal, with the viewer's own acknowledgement state."""
    owned = {"project_id": ctx["project"]["id"], "org_id": ctx["org_id"]}
    rows = await database.transmittals.find({**owned, "share_in_portal": True, "status": "issued"},
                                            {"_id": 0}).to_list(MAX_LIST_ROWS)
    if not rows:
        return []
    current = await _current_revs(database, ctx["org_id"], rows)
    contact_id = (ctx.get("contact") or {}).get("id")
    out = []
    for t in sorted(rows, key=lambda x: (x.get("issued_date") or "", x.get("created_at") or ""), reverse=True):
        d = decorate(t, current)
        mine = next((r for r in d["recipients"] if contact_id and r.get("portal_person_id") == contact_id), None)
        out.append({
            "id": d["id"], "number": d["number"], "issued_date": d.get("issued_date"),
            "purpose": PURPOSES.get(d.get("purpose"), d.get("purpose")), "note": d.get("note"),
            "ack_status": d["ack_status"],
            "pdf_url": f"/api/portal/{token}/transmittals/{d['id']}/pdf",
            "items": [{"number": i.get("number"), "title": i.get("title"), "rev": i.get("rev"),
                       "superseded_by": i.get("superseded_by"),
                       "file_url": f"/api/portal/{token}/transmittals/{d['id']}/items/{n}/file" if i.get("file_id") else None}
                      for n, i in enumerate(d["items"])],
            "recipients": [{"name": r.get("name"), "acknowledged": bool(r.get("acknowledged_at"))} for r in d["recipients"]],
            "can_acknowledge": bool(mine and not mine.get("acknowledged_at")),
            "you_acknowledged_at": (mine or {}).get("acknowledged_at"),
        })
    return out


async def _portal_transmittal(token: str, transmittal_id: str) -> tuple[dict, dict]:
    ctx = await portal.resolve(db, token)
    t = await db.transmittals.find_one({"id": transmittal_id, "project_id": ctx["project"]["id"],
                                        "org_id": ctx["org_id"], "share_in_portal": True, "status": "issued"},
                                       {"_id": 0})
    if not t:
        raise HTTPException(status_code=404, detail="Transmittal not found")
    return ctx, t


@router.get("/portal/{token}/transmittals/{transmittal_id}/items/{index}/file")
async def portal_transmittal_file(token: str, transmittal_id: str, index: int):
    ctx, t = await _portal_transmittal(token, transmittal_id)
    items = t.get("items") or []
    if index < 0 or index >= len(items) or not items[index].get("file_id"):
        raise HTTPException(status_code=404, detail="File not found")
    f = await db.files.find_one({"id": items[index]["file_id"], "project_id": ctx["project"]["id"],
                                 "org_id": ctx["org_id"]}, {"_id": 0})
    if not f or not f.get("storage_key"):
        raise HTTPException(status_code=404, detail="File not found")
    from services.local_files import resolve_storage_key
    try:
        path = resolve_storage_key(f["storage_key"])
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="File not found") from exc
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Stored file is unavailable")
    media_type = f.get("content_type") or "application/octet-stream"
    disposition = "inline" if media_type == "application/pdf" or media_type.startswith("image/") else "attachment"
    return FileResponse(path, media_type=media_type, filename=f.get("original_name") or f.get("name") or "drawing",
                        content_disposition_type=disposition,
                        headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"})


@router.get("/portal/{token}/transmittals/{transmittal_id}/pdf")
async def portal_transmittal_pdf(token: str, transmittal_id: str):
    ctx, t = await _portal_transmittal(token, transmittal_id)
    org = await db.organizations.find_one({"org_id": ctx["org_id"]}, {"_id": 0})
    t = decorate(t, await _current_revs(db, ctx["org_id"], [t]))
    return _pdf_response(t, transmittal_pdf(t, org, ctx["project"]))


@router.post("/portal/{token}/transmittals/{transmittal_id}/acknowledge")
async def portal_acknowledge(token: str, transmittal_id: str, payload: Optional[PortalAckIn] = None):
    ctx, t = await _portal_transmittal(token, transmittal_id)
    contact = ctx["contact"]
    if not contact:
        raise HTTPException(status_code=403, detail="Open the personal link the studio sent you to acknowledge receipt")
    idx = next((n for n, r in enumerate(t.get("recipients") or []) if r.get("portal_person_id") == contact["id"]), None)
    if idx is None:
        raise HTTPException(status_code=403, detail="This transmittal was not addressed to you")
    rid = t["recipients"][idx]["id"]
    note = _clean(payload.note if payload else None)
    result = await db.transmittals.update_one(
        {"id": transmittal_id, "org_id": ctx["org_id"], "status": "issued",
         f"recipients.{idx}.id": rid, f"recipients.{idx}.acknowledged_at": None},
        {"$set": {f"recipients.{idx}.acknowledged_at": iso_now(),
                  f"recipients.{idx}.received_date": business_today().isoformat(),
                  f"recipients.{idx}.acknowledged_via": "portal", f"recipients.{idx}.ack_note": note}})
    if not result.modified_count:
        raise HTTPException(status_code=409, detail="You have already acknowledged this transmittal")
    actor = {"user_id": f"portal:{contact['id']}", "email": contact.get("email"), "role": "Client",
             "org_id": ctx["org_id"], "name": contact.get("name")}
    await audit(actor, "transmittal.acknowledge", target=transmittal_id, target_type="transmittal",
                org_id=ctx["org_id"], meta={"number": t.get("number"), "recipient": contact.get("name"),
                                            "via": "client_portal", "note": note})
    try:
        from core.notifications import emit
        await emit([t.get("created_by")], "client_decision",
                   f"{contact.get('name') or 'The client'} acknowledged transmittal {t.get('number')}",
                   body=note or "", link=f"/projects/{ctx['project']['id']}?tab=Drawings",
                   meta={"project_id": ctx["project"]["id"], "transmittal_id": transmittal_id})
    except Exception:  # noqa: BLE001 - a missed bell must not undo the acknowledgement
        pass
    return {"ok": True}
