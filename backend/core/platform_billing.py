"""GAMAA's own billing of its customer studios (P1.3, decision G5).

Manual invoices and bank transfer / UPI first; no payment gateway. This is the
platform's ledger, separate from every studio's own accounting:

* ``platform_billing_settings`` (one row) – seller details, GSTIN, tax rate,
  bank/UPI, numbering and payment terms.
* ``platform_invoices`` – draft -> issued -> paid / partially paid, or void.
  An issued invoice is never edited or deleted; it can only be voided (with a
  reason) while nothing has been paid against it.
* ``platform_payments`` – append-only receipts against an invoice.

Platform revenue is read only from these collections. Paying an invoice in
full extends the studio's ``subscription.paid_through`` to the invoice period
end, which lifts grace/read-only at once (see core.subscription).

GST: with a seller GSTIN and a tax rate, tax is split CGST+SGST when the
studio's GSTIN (or state) is in the seller's state, otherwise IGST. Have the
first invoices checked by the company's accountant.
"""
from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Optional

from fastapi import HTTPException

PAYMENT_METHODS = ("bank_transfer", "upi", "cheque", "cash", "card", "other")
METHOD_LABELS = {"bank_transfer": "Bank transfer", "upi": "UPI", "cheque": "Cheque",
                 "cash": "Cash", "card": "Card", "other": "Other"}
REMINDER_DAYS = (14, 7, 1, 0)
DEFAULT_SETTINGS = {
    "seller_name": "Gamaa", "address": "", "state": "", "gstin": "", "pan": "",
    "email": "", "phone": "", "tax_rate": 0.0, "sac": "", "invoice_prefix": "GAMAA",
    "payment_terms_days": 7, "notes": "",
    "bank": {"account_name": "", "bank": "", "account": "", "ifsc": "", "upi": ""},
}
# GSTIN state codes (first two digits) for the states most likely to appear.
STATE_CODES = {
    "01": "jammu and kashmir", "02": "himachal pradesh", "03": "punjab", "04": "chandigarh",
    "05": "uttarakhand", "06": "haryana", "07": "delhi", "08": "rajasthan", "09": "uttar pradesh",
    "10": "bihar", "18": "assam", "19": "west bengal", "20": "jharkhand", "21": "odisha",
    "22": "chhattisgarh", "23": "madhya pradesh", "24": "gujarat", "27": "maharashtra",
    "29": "karnataka", "30": "goa", "32": "kerala", "33": "tamil nadu", "34": "puducherry",
    "36": "telangana", "37": "andhra pradesh",
}
_GSTIN_RE = re.compile(r"^\d{2}[A-Z0-9]{13}$")


def _db():
    from .db import db
    return db


def money(v) -> float:
    return round(float(v or 0) + 1e-9, 2)


def state_code(gstin: Optional[str], state: Optional[str]) -> Optional[str]:
    g = str(gstin or "").strip().upper()
    if _GSTIN_RE.match(g):
        return g[:2]
    name = str(state or "").strip().lower()
    for code, label in STATE_CODES.items():
        if name and name == label:
            return code
    return None


def compute_totals(lines: list, tax_rate: float, seller: dict, buyer: dict) -> dict:
    subtotal = money(sum(money(x.get("amount")) for x in lines))
    rate = max(0.0, float(tax_rate or 0))
    tax = money(subtotal * rate / 100) if seller.get("gstin") and rate else 0.0
    out = {"subtotal": subtotal, "tax_rate": rate if tax else 0.0, "cgst": 0.0, "sgst": 0.0,
           "igst": 0.0, "tax": tax, "total": money(subtotal + tax)}
    if tax:
        mine = state_code(seller.get("gstin"), seller.get("state"))
        # No GSTIN or state on file for the studio: the supplier's location is
        # the place of supply, so the supply is treated as within the state.
        theirs = state_code(buyer.get("gstin"), buyer.get("state")) or mine
        if mine and theirs and mine == theirs:
            out["cgst"] = money(tax / 2)
            out["sgst"] = money(tax - out["cgst"])
        else:
            out["igst"] = tax
    return out


def fy_label(d: date) -> str:
    start = d.year if d.month >= 4 else d.year - 1
    return f"{start}-{str(start + 1)[2:]}"


def invoice_status(inv: dict, today: Optional[date] = None) -> str:
    """draft | issued | overdue | partially_paid | paid | void (computed)."""
    if inv.get("voided_at"):
        return "void"
    if not inv.get("issued_on"):
        return "draft"
    paid = money(inv.get("amount_paid"))
    if paid >= money(inv.get("total")) and money(inv.get("total")) > 0:
        return "paid"
    from .helpers import business_today
    today = today or business_today()
    if inv.get("due_on") and str(inv["due_on"]) < today.isoformat():
        return "overdue"
    return "partially_paid" if paid > 0 else "issued"


def public_invoice(inv: dict) -> dict:
    out = {k: v for k, v in inv.items() if k != "_id"}
    out["status"] = invoice_status(inv)
    out["balance"] = money(money(inv.get("total")) - money(inv.get("amount_paid")))
    return out


async def get_settings() -> dict:
    row = await _db().platform_billing_settings.find_one({"key": "default"}, {"_id": 0}) or {}
    merged = {**DEFAULT_SETTINGS, **{k: v for k, v in row.items() if k in DEFAULT_SETTINGS}}
    merged["bank"] = {**DEFAULT_SETTINGS["bank"], **(row.get("bank") or {})}
    return merged


async def next_invoice_number(prefix: str, on: date) -> str:
    from pymongo import ReturnDocument
    fy = fy_label(on)
    key = {"org_id": "__platform__", "kind": f"platform_invoice:{fy}"}
    db = _db()
    if not await db.counters.find_one(key):
        try:
            await db.counters.insert_one({**key, "seq": 0})
        except Exception:  # noqa: BLE001 - a concurrent creator seeded it
            pass
    row = await db.counters.find_one_and_update(key, {"$inc": {"seq": 1}},
                                                return_document=ReturnDocument.AFTER)
    clean = re.sub(r"[^A-Za-z0-9]", "", prefix or "GAMAA")[:12] or "GAMAA"
    return f"{clean}/{fy}/{int(row['seq']):04d}"


def buyer_snapshot(org: dict) -> dict:
    addr = org.get("address") or {}
    line = ", ".join(x for x in (addr.get("line1"), addr.get("line2"), addr.get("city"),
                                 addr.get("state"), addr.get("pincode")) if x)
    return {"name": org.get("display_name") or org.get("name") or "", "gstin": org.get("gstin") or "",
            "address": line, "state": addr.get("state") or "", "email": org.get("email") or ""}


def suggest_period(org: dict, today: date) -> tuple:
    """Next period to bill: from the day after paid_through (or today) for one billing cycle."""
    sub = org.get("subscription") or {}
    billing = org.get("billing") or {}
    try:
        start = date.fromisoformat(str(sub.get("paid_through"))[:10]) + timedelta(days=1)
    except ValueError:
        start = today
    cycle = billing.get("billing_cycle") or "yearly"
    months = {"monthly": 1, "quarterly": 3}.get(cycle, 12)
    return start, add_months(start, months) - timedelta(days=1), cycle


def add_months(d: date, months: int) -> date:
    """Same day `months` later, clamped to the month's last day (31 Jan + 1 = 28/29 Feb)."""
    import calendar
    y, m = divmod(d.month - 1 + months, 12)
    year, month = d.year + y, m + 1
    return date(year, month, min(d.day, calendar.monthrange(year, month)[1]))


async def apply_payment(inv: dict, amount: float, method: str, reference: str,
                        received_on: date, actor: dict) -> dict:
    """Record a receipt; a fully paid invoice extends the studio's paid-through date."""
    if inv.get("voided_at") or not inv.get("issued_on"):
        raise HTTPException(409, "Payments can be recorded only against an issued invoice")
    amount = money(amount)
    balance = money(money(inv.get("total")) - money(inv.get("amount_paid")))
    if amount <= 0:
        raise HTTPException(400, "Amount must be more than zero")
    if amount > balance + 0.009:
        raise HTTPException(400, f"Amount is more than the balance due (Rs. {balance:,.2f})")
    if method not in PAYMENT_METHODS:
        raise HTTPException(400, "Unknown payment method")
    from .helpers import iso_now, new_id
    db = _db()
    pay = {"id": new_id("ppay_"), "invoice_id": inv["id"], "org_id": inv["org_id"],
           "amount": amount, "method": method, "reference": (reference or "")[:120],
           "received_on": received_on.isoformat(), "recorded_by": actor.get("user_id"),
           "created_at": iso_now()}
    await db.platform_payments.insert_one(dict(pay))
    paid = money(money(inv.get("amount_paid")) + amount)
    upd = {"amount_paid": paid, "updated_at": iso_now()}
    fully = paid >= money(inv.get("total"))
    if fully:
        upd["paid_on"] = received_on.isoformat()
    await db.platform_invoices.update_one({"id": inv["id"]}, {"$set": upd})
    extended = None
    if fully and inv.get("period_end"):
        org = await db.organizations.find_one({"org_id": inv["org_id"]}, {"_id": 0, "subscription": 1})
        sub = dict((org or {}).get("subscription") or {})
        current = str(sub.get("paid_through") or "")
        new_through = max(current, str(inv["period_end"])[:10]) if sub.get("status") == "active" else str(inv["period_end"])[:10]
        sub.update({"status": "active", "paid_through": new_through, "trial_ends_on": None,
                    "updated_at": iso_now(), "updated_by": actor.get("user_id"), "via": inv["number"]})
        sub.pop("ended_on", None)
        await db.organizations.update_one({"org_id": inv["org_id"]}, {"$set": {"subscription": sub}})
        extended = new_through
    return {"payment": pay, "amount_paid": paid, "paid_in_full": fully, "paid_through": extended}


async def billing_summary(today: Optional[date] = None) -> dict:
    """Platform revenue figures, read only from GAMAA's own ledger."""
    from .helpers import business_today
    today = today or business_today()
    month = today.strftime("%Y-%m")
    db = _db()
    invoiced = outstanding = 0.0
    overdue = 0
    async for inv in db.platform_invoices.find({"issued_on": {"$ne": None}, "voided_at": None}, {"_id": 0}):
        if str(inv.get("issued_on") or "").startswith(month):
            invoiced += money(inv.get("total"))
        bal = money(money(inv.get("total")) - money(inv.get("amount_paid")))
        if bal > 0:
            outstanding += bal
            if invoice_status(inv, today) == "overdue":
                overdue += 1
    received = 0.0
    async for p in db.platform_payments.find({"received_on": {"$regex": f"^{month}"}}, {"_id": 0, "amount": 1}):
        received += money(p.get("amount"))
    return {"month": month, "invoiced_this_month": money(invoiced), "received_this_month": money(received),
            "outstanding": money(outstanding), "overdue_invoices": overdue}


async def send_renewal_reminders(today: Optional[date] = None) -> dict:
    """Daily, idempotent: tell each studio's admins before renewal, when grace
    starts and when editing pauses; flag overdue GAMAA invoices."""
    from .helpers import business_today
    from .notifications import emit_admins
    from .subscription import subscription_state
    today = today or business_today()
    db = _db()
    sent = 0
    async for org in db.organizations.find({"subscription.status": "active",
                                            "subscription.paid_through": {"$nin": [None, ""]},
                                            "is_active": {"$ne": False}},
                                           {"_id": 0, "org_id": 1, "subscription": 1}):
        st = subscription_state(org, today)
        through = st["paid_through"]
        days = (date.fromisoformat(through) - today).days
        key = None
        if days in REMINDER_DAYS:
            key, title = f"renew:{days}", (f"Your Gamaa plan renews in {days} day{'s' if days != 1 else ''}"
                                          if days else "Your Gamaa plan renews today")
            body = f"Paid up to {through}. Pay the renewal invoice to keep editing without a break."
        elif st["status"] == "grace" and days == -1:
            key, title = "grace", "Gamaa plan payment overdue"
            body = f"Everything still works until {st['grace_ends_on']}; after that the workspace becomes read-only."
        elif st["read_only"] and st["ended_on"] == (today - timedelta(days=1)).isoformat():
            key, title = "read_only", "Workspace is now read-only"
            body = "Your work is safe and can be viewed or downloaded. Pay the renewal invoice to resume editing."
        if key:
            sent += await emit_admins("reminder", title, body, link="/settings/company", priority="high",
                                      dedup_key=f"gamaa-billing:{org['org_id']}:{through}:{key}",
                                      org_id=org["org_id"])
    async for inv in db.platform_invoices.find({"issued_on": {"$ne": None}, "voided_at": None}, {"_id": 0}):
        if invoice_status(inv, today) == "overdue":
            sent += await emit_admins(
                "reminder", f"Gamaa invoice {inv['number']} is overdue",
                f"Balance Rs. {money(money(inv.get('total')) - money(inv.get('amount_paid'))):,.2f} was due on {inv['due_on']}.",
                link="/settings/company", priority="high",
                dedup_key=f"gamaa-invoice-overdue:{inv['id']}", org_id=inv["org_id"])
    return {"notified": sent}


# ---------------------------------------------------------------------------
# PDF
# ---------------------------------------------------------------------------
def _seller_org(settings: dict) -> dict:
    """Shape GAMAA's seller details like an organisation for the PDF letterhead."""
    b = settings.get("bank") or {}
    return {"name": settings.get("seller_name") or "Gamaa", "gstin": settings.get("gstin"),
            "pan": settings.get("pan"), "email": settings.get("email"), "phone": settings.get("phone"),
            "address": {"line1": settings.get("address"), "state": settings.get("state")},
            "branding": {"primary_color": "#76705E", "tagline": "Architecture & Interior ERP",
                         "pdf_footer": f"Thank you for choosing {settings.get('seller_name') or 'Gamaa'}."},
            "bank_details": {"account_name": b.get("account_name"), "bank": b.get("bank"),
                             "account": b.get("account"), "ifsc": b.get("ifsc"), "upi": b.get("upi")}}


def _d(value) -> str:
    try:
        return date.fromisoformat(str(value)[:10]).strftime("%d/%m/%Y")
    except ValueError:
        return "—"


def invoice_pdf(inv: dict, settings: dict) -> bytes:
    from .pdf_brand import (Brand, BrandedPDF, draw_bank_block, draw_letterhead, section_label,
                            wrap, safe_text, INK, GREY, LINE, LEFT, RIGHT, CONTENT_W)
    brand = Brand(_seller_org(settings))
    status = invoice_status(inv)
    title = "TAX INVOICE" if money(inv.get("tax")) > 0 else "INVOICE"
    pdf = BrandedPDF(brand, title.title(), inv.get("number") or "")
    pdf.add_page()
    meta = [("Invoice No.", inv.get("number") or "Draft"), ("Date", _d(inv.get("issued_on"))),
            ("Due date", _d(inv.get("due_on")))]
    if status in ("void", "paid"):
        meta.append(("Status", "Void" if status == "void" else "Paid"))
    draw_letterhead(pdf, title, meta)

    buyer = inv.get("buyer") or {}
    top = pdf.get_y()
    pdf.set_xy(LEFT, top)
    section_label(pdf, "BILL TO")
    rows = [buyer.get("name")] + [x for x in (buyer.get("address"),
                                             f"GSTIN: {buyer['gstin']}" if buyer.get("gstin") else "",
                                             buyer.get("email")) if x]
    for i, value in enumerate(rows):
        for part in wrap(str(value or ""), 48)[:2]:
            pdf.set_x(LEFT)
            pdf.set_font("Helvetica", "B" if i == 0 else "", 10 if i == 0 else 8.6)
            pdf.set_text_color(*(INK if i == 0 else GREY))
            pdf.cell(85, 4.8, safe_text(part), 0, 1)
    left_bottom = pdf.get_y()
    pdf.set_xy(110, top)
    section_label(pdf, "SERVICE PERIOD")
    pdf.set_x(110)
    pdf.set_font("Helvetica", "B", 10)
    pdf.set_text_color(*INK)
    pdf.cell(85, 4.8, safe_text(f"{_d(inv.get('period_start'))} to {_d(inv.get('period_end'))}"), 0, 1)
    if inv.get("plan_name"):
        pdf.set_x(110)
        pdf.set_font("Helvetica", "", 8.6)
        pdf.set_text_color(*GREY)
        pdf.cell(85, 4.8, safe_text(f"{inv['plan_name']} plan"), 0, 1)
    pdf.set_y(max(left_bottom, pdf.get_y()) + 5)

    pdf.set_fill_color(*brand.primary)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Helvetica", "B", 8.5)
    sac = settings.get("sac")
    pdf.cell(10, 8, " #", 0, 0, "L", fill=True)
    pdf.cell(130 if not sac else 110, 8, "DESCRIPTION", 0, 0, "L", fill=True)
    if sac:
        pdf.cell(20, 8, "SAC", 0, 0, "L", fill=True)
    pdf.cell(CONTENT_W - 140, 8, "AMOUNT (Rs.)  ", 0, 1, "R", fill=True)
    pdf.set_text_color(*INK)
    for i, line in enumerate(inv.get("lines") or [], start=1):
        parts = wrap(str(line.get("description") or ""), 70 if not sac else 58)
        h = max(7.5, len(parts) * 4.8 + 2.5)
        y = pdf.get_y()
        pdf.set_font("Helvetica", "", 9.3)
        pdf.set_xy(LEFT, y)
        pdf.cell(10, h, f" {i}", 0, 0, "L")
        pdf.set_xy(LEFT + 10, y + 1.2)
        pdf.multi_cell(130 if not sac else 110, 4.8, safe_text("\n".join(parts)), 0, "L")
        if sac:
            pdf.set_xy(LEFT + 120, y)
            pdf.cell(20, h, safe_text(sac), 0, 0, "L")
        pdf.set_xy(LEFT + 140, y)
        pdf.cell(CONTENT_W - 140, h, f"{money(line.get('amount')):,.2f}  ", 0, 0, "R")
        pdf.set_y(y + h)
    pdf.set_draw_color(*LINE)
    pdf.line(LEFT, pdf.get_y(), RIGHT, pdf.get_y())
    pdf.ln(2)

    def total_row(label, value, bold=False):
        pdf.set_x(110)
        pdf.set_font("Helvetica", "B" if bold else "", 10 if bold else 9)
        pdf.set_text_color(*INK)
        pdf.cell(55, 6, safe_text(label), 0, 0, "R")
        pdf.cell(RIGHT - 165, 6, f"{money(value):,.2f}  ", 0, 1, "R")

    total_row("Subtotal", inv.get("subtotal"))
    rate = inv.get("tax_rate") or 0
    if money(inv.get("cgst")):
        total_row(f"CGST @ {rate / 2:g}%", inv["cgst"])
        total_row(f"SGST @ {rate / 2:g}%", inv["sgst"])
    elif money(inv.get("igst")):
        total_row(f"IGST @ {rate:g}%", inv["igst"])
    total_row("Total", inv.get("total"), bold=True)
    if money(inv.get("amount_paid")):
        total_row("Paid", inv.get("amount_paid"))
        total_row("Balance due", money(money(inv.get("total")) - money(inv.get("amount_paid"))), bold=True)
    pdf.ln(4)
    if status != "void" and money(money(inv.get("total")) - money(inv.get("amount_paid"))) > 0:
        draw_bank_block(pdf)
    if inv.get("notes") or settings.get("notes"):
        pdf.ln(3)
        pdf.set_x(LEFT)
        pdf.set_font("Helvetica", "", 8.6)
        pdf.set_text_color(*GREY)
        pdf.multi_cell(CONTENT_W, 4.6, safe_text(inv.get("notes") or settings.get("notes")))
    if status == "void":
        pdf.ln(3)
        pdf.set_x(LEFT)
        pdf.set_font("Helvetica", "B", 10)
        pdf.set_text_color(160, 40, 40)
        pdf.multi_cell(CONTENT_W, 5, safe_text(f"VOID: {inv.get('void_reason') or 'cancelled'}"))
    return pdf.to_bytes()
