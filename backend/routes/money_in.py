"""Payment reminders (demand notes) and the Received Payments register.

Documents vs money:
- A reminder asks for payment. It is a numbered document with a PDF and a
  WhatsApp message; it never creates a journal and is not proof of payment.
- Collections Due (routes/accounting.collection_rows) tracks what is still owed.
- Only Record Payment (/accounting/collections/receive) posts cash/bank, once.
- Received Payments lists those postings, read-only.
"""
from __future__ import annotations

import io
import re
from datetime import date as _date
from typing import Literal, Optional
from urllib.parse import quote

from fastapi import APIRouter, Cookie, Header, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from core.audit import audit
from core.db import db
from core.deps import require_user
from core.downloads import content_disposition
from core.helpers import business_today, iso_now, new_id, next_sequence
from core.rbac import has_permission
from core.scoped_db import current_org_id, sdb
from core.tenancy import user_org_id

router = APIRouter()

SOURCE_TYPES = ("invoice", "milestone", "vendor_commission", "other_receivable")
MONEY_IN_SOURCES = ("income", "invoice_payment", "milestone_payment",
                    "other_receivable_income", "commission_income")
SOURCE_LABELS = {
    "income": "Money in", "invoice_payment": "Invoice payment",
    "milestone_payment": "Milestone payment", "other_receivable_income": "Other receivable",
    "commission_income": "Vendor incentive",
}


def _require_finance_read(user: dict) -> None:
    if not has_permission(user, "finance.read"):
        raise HTTPException(status_code=403, detail="Missing permission: finance.read")


def _require_reminder_write(user: dict) -> None:
    if not (has_permission(user, "finance.create") or has_permission(user, "invoices.update")):
        raise HTTPException(status_code=403, detail="Missing permission: finance.create")


def _inr(value: float) -> str:
    """Indian grouping, whole rupees unless paise exist: 590000 -> 5,90,000."""
    amount = round(float(value or 0), 2)
    whole, paise = divmod(round(abs(amount) * 100), 100)
    digits = str(int(whole))
    if len(digits) > 3:
        head, tail = digits[:-3], digits[-3:]
        head = ",".join([head[max(0, i - 2):i] for i in range(len(head), 0, -2)][::-1])
        digits = f"{head},{tail}"
    sign = "-" if amount < 0 else ""
    return f"{sign}{digits}" + (f".{paise:02d}" if paise else "")


def _display_date(value: Optional[str]) -> str:
    try:
        return _date.fromisoformat(str(value)[:10]).strftime("%d/%m/%Y")
    except (TypeError, ValueError):
        return "—"


def whatsapp_number(phone: Optional[str]) -> Optional[str]:
    """wa.me wants country code + number, digits only. Indian 10-digit numbers get 91."""
    digits = re.sub(r"\D", "", str(phone or ""))
    if digits.startswith("00"):
        digits = digits[2:]
    if len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]
    if len(digits) == 10:
        digits = "91" + digits
    return digits if 11 <= len(digits) <= 15 else None


def reminder_message(reminder: dict, org: dict) -> str:
    company = (org or {}).get("display_name") or (org or {}).get("name") or "our studio"
    what = reminder.get("project_name") or reminder.get("title") or "your project"
    lines = [
        f"Dear {reminder.get('party_name') or 'Sir/Madam'},",
        "",
        f"This is a gentle reminder from {company} that Rs. {_inr(reminder['amount_due'])} "
        f"for {what} is due by {_display_date(reminder.get('due_by'))}.",
        f"Reference: {reminder['number']}" + (f" ({reminder['reference']})" if reminder.get("reference") else ""),
    ]
    bank = (org or {}).get("bank_details") or {}
    pay = [x for x in (
        f"UPI: {bank['upi']}" if bank.get("upi") else "",
        f"A/c {bank['account']}" if bank.get("account") else "",
        f"IFSC {bank['ifsc']}" if bank.get("ifsc") else "",
        bank.get("bank") or "",
    ) if x]
    if pay:
        lines.append("Payment details: " + " · ".join(pay))
    if reminder.get("message"):
        lines += ["", reminder["message"]]
    lines += ["", "If you have already paid, please ignore this message. Thank you."]
    return "\n".join(lines)


def whatsapp_url(reminder: dict, org: dict) -> Optional[str]:
    number = whatsapp_number(reminder.get("party_phone"))
    text = quote(reminder_message(reminder, org))
    return f"https://wa.me/{number}?text={text}" if number else f"https://wa.me/?text={text}"


async def _org() -> dict:
    return await db.organizations.find_one({"org_id": current_org_id() or "org_default"}, {"_id": 0}) or {}


async def _party(row: dict) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """(name, phone, address) of whoever owes the money."""
    if row.get("source_type") == "vendor_commission" and row.get("vendor_id"):
        v = await sdb.vendors_acc.find_one({"id": row["vendor_id"]}, {"_id": 0}) or {}
        return v.get("name") or row.get("vendor_name"), v.get("phone"), v.get("address")
    if row.get("client_id"):
        c = await sdb.clients.find_one({"id": row["client_id"]}, {"_id": 0}) or {}
        return c.get("name") or row.get("client_name"), c.get("phone"), c.get("address")
    return row.get("client_name") or row.get("vendor_name"), None, None


def _decorate(reminder: dict, rows_by_key: dict, org: dict) -> dict:
    live = rows_by_key.get((reminder["source_type"], reminder["source_id"]))
    out = dict(reminder)
    out["outstanding_now"] = live["outstanding"] if live else 0.0
    out["collection_status"] = live["status"] if live else "received"
    if reminder.get("status") != "cancelled":
        out["state"] = "settled" if out["outstanding_now"] <= 0.004 else (
            "overdue" if str(reminder.get("due_by") or "9999") < business_today().isoformat() else "open")
    else:
        out["state"] = "cancelled"
    out["whatsapp_url"] = whatsapp_url(reminder, org)
    out["has_whatsapp_number"] = bool(whatsapp_number(reminder.get("party_phone")))
    return out


class ReminderIn(BaseModel):
    source_type: Literal["invoice", "milestone", "vendor_commission", "other_receivable"]
    source_id: str = Field(min_length=1, max_length=80)
    due_by: str
    message: Optional[str] = Field(default=None, max_length=600)


@router.post("/accounting/reminders")
async def create_reminder(payload: ReminderIn, request: Request,
                          session_token: Optional[str] = Cookie(default=None),
                          authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    _require_finance_read(user)
    _require_reminder_write(user)
    try:
        _date.fromisoformat(payload.due_by)
    except ValueError:
        raise HTTPException(status_code=400, detail="Pay-by date must be YYYY-MM-DD")
    from routes.accounting import collection_rows
    data = await collection_rows()
    row = next((r for r in data["rows"]
                if r["source_type"] == payload.source_type and r["id"] == payload.source_id), None)
    if not row:
        raise HTTPException(status_code=404, detail="Collection not found")
    if row["outstanding"] <= 0.004:
        raise HTTPException(status_code=409, detail="Nothing is due on this collection")
    name, phone, address = await _party(row)
    org_id = user_org_id(user) or "org_default"
    seq = await next_sequence(org_id, "payment_reminder", 0)
    reminder = {
        "id": new_id("rem_"), "number": f"PR-{seq:04d}",
        "source_type": row["source_type"], "source_id": row["id"],
        "title": row.get("name"), "reference": row.get("reference"),
        "party_name": name, "party_phone": phone, "party_address": address,
        "client_id": row.get("client_id"), "vendor_id": row.get("vendor_id"),
        "project_id": row.get("project_id"), "project_name": row.get("project_name"),
        "total_amount": row["amount"], "received_before": row["received_amount"],
        "amount_due": row["outstanding"], "original_due_date": row.get("due_date"),
        "due_by": payload.due_by, "message": (payload.message or "").strip() or None,
        "status": "active", "created_at": iso_now(), "created_by": user["user_id"],
        "created_by_name": user.get("name"),
    }
    await sdb.payment_reminders.insert_one(dict(reminder))
    await audit(user, "reminder.create", target=reminder["id"], target_type="payment_reminder",
                meta={"number": reminder["number"], "source_type": row["source_type"],
                      "source_id": row["id"], "amount_due": row["outstanding"]},
                org_id=org_id)
    return _decorate(reminder, {(row["source_type"], row["id"]): row}, await _org())


@router.get("/accounting/reminders")
async def list_reminders(request: Request, source_type: Optional[str] = None,
                         source_id: Optional[str] = None,
                         session_token: Optional[str] = Cookie(default=None),
                         authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    _require_finance_read(user)
    q: dict = {}
    if source_type:
        q["source_type"] = source_type
    if source_id:
        q["source_id"] = source_id
    rows = await sdb.payment_reminders.find(q, {"_id": 0}).sort("created_at", -1).to_list(2000)
    from routes.accounting import collection_rows
    live = {(r["source_type"], r["id"]): r for r in (await collection_rows())["rows"]}
    org = await _org()
    return [_decorate(r, live, org) for r in rows]


@router.post("/accounting/reminders/{reminder_id}/shared")
async def mark_shared(reminder_id: str, request: Request,
                      session_token: Optional[str] = Cookie(default=None),
                      authorization: Optional[str] = Header(default=None)):
    """Remember when the reminder was opened in WhatsApp (no money, no journal)."""
    user = await require_user(request, session_token, authorization)
    _require_finance_read(user)
    res = await sdb.payment_reminders.update_one(
        {"id": reminder_id}, {"$set": {"last_shared_at": iso_now(), "last_shared_by": user["user_id"]},
                              "$inc": {"share_count": 1}})
    if not res.matched_count:
        raise HTTPException(status_code=404, detail="Reminder not found")
    return {"ok": True}


@router.delete("/accounting/reminders/{reminder_id}")
async def cancel_reminder(reminder_id: str, request: Request,
                          session_token: Optional[str] = Cookie(default=None),
                          authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    _require_reminder_write(user)
    res = await sdb.payment_reminders.update_one(
        {"id": reminder_id, "status": {"$ne": "cancelled"}},
        {"$set": {"status": "cancelled", "cancelled_at": iso_now(), "cancelled_by": user["user_id"]}})
    if not res.matched_count:
        raise HTTPException(status_code=404, detail="Reminder not found")
    await audit(user, "reminder.cancel", target=reminder_id, target_type="payment_reminder",
                org_id=user_org_id(user))
    return {"ok": True}


def generate_reminder_pdf(reminder: dict, org: dict) -> bytes:
    from core.pdf_brand import (Brand, BrandedPDF, draw_letterhead, draw_bank_block, draw_signatory,
                                section_label, wrap, safe_text, INK, GREY, LEFT, RIGHT, CONTENT_W)
    brand = Brand(org)
    pdf = BrandedPDF(brand, "Payment Reminder", reminder["number"])
    pdf.add_page()
    draw_letterhead(pdf, "PAYMENT REMINDER", [
        ("Reminder No.", reminder["number"]),
        ("Date", _display_date(reminder.get("created_at"))),
        ("Please pay by", _display_date(reminder.get("due_by"))),
    ])
    # To / Project
    top = pdf.get_y()
    to_lines = [reminder.get("party_name") or "—"] + [x for x in (
        reminder.get("party_address"), reminder.get("party_phone")) if x]
    proj_lines = [reminder.get("project_name") or "—"]
    if reminder.get("title"):
        proj_lines.append(reminder["title"])
    bottom = top
    for x, label, lines in ((LEFT, "TO", to_lines), (110, "FOR", proj_lines)):
        pdf.set_xy(x, top)
        section_label(pdf, label)
        for i, value in enumerate(lines[:4]):
            for part in wrap(str(value), 46)[:2]:
                pdf.set_x(x)
                pdf.set_font("Helvetica", "B" if i == 0 else "", 10 if i == 0 else 8.6)
                pdf.set_text_color(*(INK if i == 0 else GREY))
                pdf.cell(85, 4.8, part, 0, 1)
        bottom = max(bottom, pdf.get_y())
    pdf.set_y(bottom + 6)

    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(*INK)
    intro = (f"This is a friendly reminder that the amount below is due. "
             f"We request you to kindly arrange the payment by {_display_date(reminder.get('due_by'))}.")
    for part in wrap(intro, 100):
        pdf.cell(CONTENT_W, 5.4, part, 0, 1)
    pdf.ln(4)

    # amounts
    rows = [("Total amount", reminder.get("total_amount"))]
    if float(reminder.get("received_before") or 0) > 0:
        rows.append(("Received so far", reminder.get("received_before")))
    pdf.set_fill_color(*brand.primary)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Helvetica", "B", 8.5)
    pdf.cell(CONTENT_W - 50, 8, "  DESCRIPTION", 0, 0, "L", fill=True)
    pdf.cell(50, 8, "AMOUNT (Rs.)  ", 0, 1, "R", fill=True)
    pdf.set_text_color(*INK)
    pdf.set_font("Helvetica", "", 9.5)
    label = reminder.get("title") or "Amount"
    if reminder.get("reference") and reminder["reference"] not in label:
        label += f" ({reminder['reference']})"
    for name, value in rows:
        pdf.cell(CONTENT_W - 50, 7.5, safe_text(f"  {name} - {label}" if name == "Total amount" else f"  {name}"), "B", 0)
        pdf.cell(50, 7.5, safe_text(_inr(value) + "  "), "B", 1, "R")
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(CONTENT_W - 50, 10, "  AMOUNT DUE", 0, 0)
    pdf.set_text_color(*brand.primary)
    pdf.cell(50, 10, safe_text("Rs. " + _inr(reminder.get("amount_due")) + "  "), 0, 1, "R")
    pdf.set_text_color(*INK)
    if reminder.get("message"):
        pdf.ln(2)
        pdf.set_font("Helvetica", "", 9.2)
        for part in wrap(reminder["message"], 105)[:6]:
            pdf.cell(CONTENT_W, 5, part, 0, 1)
    pdf.ln(5)
    y = pdf.get_y()
    draw_bank_block(pdf, LEFT, 105)
    pdf.set_y(y)
    draw_signatory(pdf, 125, 70)
    pdf.set_y(max(pdf.get_y(), y) + 30)
    pdf.set_font("Helvetica", "I", 8.2)
    pdf.set_text_color(*GREY)
    contact = " / ".join(x for x in ((org or {}).get("phone"), (org or {}).get("email")) if x)
    note = ("This is a payment request, not a tax invoice or a receipt. "
            "If you have already paid, please share the payment reference and ignore this reminder.")
    if contact:
        note += f" For any query, contact {contact}."
    for part in wrap(note, 120):
        pdf.cell(CONTENT_W, 4.4, part, 0, 1)
    return pdf.to_bytes()


@router.get("/accounting/reminders/{reminder_id}/pdf")
async def reminder_pdf(reminder_id: str, request: Request,
                       session_token: Optional[str] = Cookie(default=None),
                       authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    _require_finance_read(user)
    reminder = await sdb.payment_reminders.find_one({"id": reminder_id}, {"_id": 0})
    if not reminder:
        raise HTTPException(status_code=404, detail="Reminder not found")
    data = generate_reminder_pdf(reminder, await _org())
    return StreamingResponse(io.BytesIO(data), media_type="application/pdf", headers={
        "Content-Disposition": content_disposition("inline", f"{reminder['number']}.pdf", "reminder.pdf")})


@router.get("/accounting/received-payments")
async def received_payments(request: Request, from_date: Optional[str] = None,
                            to_date: Optional[str] = None,
                            session_token: Optional[str] = Cookie(default=None),
                            authorization: Optional[str] = Header(default=None)):
    """Money actually received (posted by Record Payment / Money In), newest first."""
    user = await require_user(request, session_token, authorization)
    _require_finance_read(user)
    q: dict = {"source": {"$in": list(MONEY_IN_SOURCES)}, "reversed": {"$ne": True},
               "voided_from_view": {"$ne": True}}
    if from_date or to_date:
        q["date"] = {k: v for k, v in (("$gte", from_date), ("$lte", to_date)) if v}
    entries = await sdb.journal_entries.find(q, {"_id": 0}).sort("date", -1).to_list(5000)
    client_ids = {e.get("client_id") for e in entries if e.get("client_id")}
    vendor_ids = {e.get("vendor_id") for e in entries if e.get("vendor_id")}
    project_ids = {e.get("project_id") for e in entries if e.get("project_id")}
    clients = {c["id"]: c.get("name") async for c in sdb.clients.find(
        {"id": {"$in": list(client_ids)}}, {"_id": 0, "id": 1, "name": 1})} if client_ids else {}
    vendors = {v["id"]: v.get("name") async for v in sdb.vendors_acc.find(
        {"id": {"$in": list(vendor_ids)}}, {"_id": 0, "id": 1, "name": 1})} if vendor_ids else {}
    projects = {p["id"]: p.get("name") async for p in sdb.projects.find(
        {"id": {"$in": list(project_ids)}}, {"_id": 0, "id": 1, "name": 1})} if project_ids else {}
    out = []
    for e in entries:
        cash_lines = [l for l in e.get("lines") or []
                      if l.get("account_type") == "asset" and float(l.get("debit") or 0) > 0
                      and l.get("account_name") != "Accounts Receivable"]
        amount = round(sum(float(l["debit"]) for l in cash_lines), 2)
        if amount <= 0:
            continue
        out.append({
            "id": e["id"], "date": e.get("date"), "amount": amount,
            "account": ", ".join(sorted({l.get("account_name") or "" for l in cash_lines})),
            "source": e.get("source"), "source_label": SOURCE_LABELS.get(e.get("source"), "Money in"),
            "source_id": e.get("source_id"), "reference": e.get("reference"),
            "narration": e.get("narration"),
            "party": clients.get(e.get("client_id")) or vendors.get(e.get("vendor_id")),
            "client_id": e.get("client_id"), "vendor_id": e.get("vendor_id"),
            "project_id": e.get("project_id"), "project_name": projects.get(e.get("project_id")),
        })
    return {"rows": out, "total": round(sum(r["amount"] for r in out), 2), "count": len(out)}
