"""Finance extras — recurring expenses, favorite accounts, vendor statement PDFs,
and bank reconciliation. Mounted onto the main accounting router so everything
lives at /api/…

Every endpoint uses `sdb` for tenant scoping and the central `_post_journal`
engine for any accounting side-effects.
"""
from __future__ import annotations

from datetime import date as _date, datetime, timezone
from calendar import monthrange
from typing import List, Optional

from fastapi import APIRouter, Cookie, Depends, File, Header, HTTPException, Request, UploadFile
from fastapi.responses import Response as FastAPIResponse
from pydantic import BaseModel

from core.audit import audit
from core.db import db  # noqa: F401  (kept for future use)
from core.deps import require_user
from core.helpers import iso_now, new_id, now_utc
from core.rbac import has_permission
from core.scoped_db import sdb
from core.tenancy import user_org_id
from routes.accounting import _post_journal, _seed_coa_if_empty


router = APIRouter()


# ==========================================================================
# 1) RECURRING EXPENSES
# ==========================================================================
# Simple rule engine: a rule points at an expense account + bank account and a
# frequency (monthly/quarterly/yearly/weekly). A background scan runs the rule
# any time `next_run_date` is on-or-before today, posts a JE via the central
# engine and advances `next_run_date` idempotently.
# ==========================================================================

FREQUENCIES = ["weekly", "monthly", "quarterly", "yearly"]


class RecurringIn(BaseModel):
    name: str
    amount: float
    expense_account_id: str
    paid_from_account_id: str
    frequency: str = "monthly"
    day_of_month: Optional[int] = None       # 1-28 (monthly/quarterly/yearly)
    day_of_week: Optional[int] = None        # 0=Mon … 6=Sun (weekly)
    start_date: Optional[str] = None         # YYYY-MM-DD; defaults to today
    end_date: Optional[str] = None           # optional stop date
    vendor_id: Optional[str] = None
    project_id: Optional[str] = None
    client_id: Optional[str] = None
    reference: Optional[str] = None
    gst: Optional[float] = 0.0
    notes: Optional[str] = None
    active: Optional[bool] = True


class RecurringUpdate(BaseModel):
    name: Optional[str] = None
    amount: Optional[float] = None
    expense_account_id: Optional[str] = None
    paid_from_account_id: Optional[str] = None
    frequency: Optional[str] = None
    day_of_month: Optional[int] = None
    day_of_week: Optional[int] = None
    end_date: Optional[str] = None
    vendor_id: Optional[str] = None
    project_id: Optional[str] = None
    client_id: Optional[str] = None
    reference: Optional[str] = None
    gst: Optional[float] = None
    notes: Optional[str] = None
    active: Optional[bool] = None


def _add_months(d: _date, months: int) -> _date:
    y = d.year + (d.month - 1 + months) // 12
    m = (d.month - 1 + months) % 12 + 1
    day = min(d.day, monthrange(y, m)[1])
    return _date(y, m, day)


def _next_run(from_date: _date, freq: str, day_of_month: Optional[int],
              day_of_week: Optional[int]) -> _date:
    """Compute the next run-date strictly AFTER `from_date` for a rule."""
    if freq == "weekly":
        dow = day_of_week if day_of_week is not None else from_date.weekday()
        days_ahead = (dow - from_date.weekday()) % 7
        if days_ahead == 0:
            days_ahead = 7
        return from_date.fromordinal(from_date.toordinal() + days_ahead)
    if freq == "monthly":
        return _add_months(from_date.replace(day=1), 1).replace(
            day=min(day_of_month or from_date.day, monthrange(*_add_months(from_date, 1).timetuple()[:2])[1])
        )
    if freq == "quarterly":
        d = _add_months(from_date, 3)
        if day_of_month:
            d = d.replace(day=min(day_of_month, monthrange(d.year, d.month)[1]))
        return d
    if freq == "yearly":
        d = _add_months(from_date, 12)
        if day_of_month:
            d = d.replace(day=min(day_of_month, monthrange(d.year, d.month)[1]))
        return d
    # Fallback: monthly
    return _add_months(from_date, 1)


def _initial_run_date(payload_start: Optional[str], freq: str,
                      day_of_month: Optional[int], day_of_week: Optional[int]) -> str:
    """Pick the first `next_run_date` when the rule is created."""
    today = now_utc().date()
    start = _date.fromisoformat(payload_start) if payload_start else today
    # If start is in the future, use it directly; else compute the next occurrence.
    if start > today:
        return start.isoformat()
    if freq == "weekly":
        dow = day_of_week if day_of_week is not None else today.weekday()
        days_ahead = (dow - today.weekday()) % 7
        return today.fromordinal(today.toordinal() + days_ahead).isoformat()
    # monthly / quarterly / yearly — snap day-of-month within this period if not yet passed.
    if day_of_month:
        try:
            snap = today.replace(day=min(day_of_month, monthrange(today.year, today.month)[1]))
        except ValueError:
            snap = today
        if snap >= today:
            return snap.isoformat()
    return today.isoformat()


@router.get("/recurring-expenses")
async def list_recurring(request: Request,
                         active_only: bool = False,
                         session_token: Optional[str] = Cookie(default=None),
                         authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    if not has_permission(user, "finance.read"):
        raise HTTPException(403, "Missing permission: finance.read")
    q = {"active": True} if active_only else {}
    rows = await sdb.recurring_expenses.find(q, {"_id": 0}).sort("next_run_date", 1).to_list(500)
    return rows


@router.post("/recurring-expenses")
async def create_recurring(payload: RecurringIn, request: Request,
                           session_token: Optional[str] = Cookie(default=None),
                           authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    if not has_permission(user, "finance.create"):
        raise HTTPException(403, "Missing permission: finance.create")
    if payload.frequency not in FREQUENCIES:
        raise HTTPException(400, f"frequency must be one of {FREQUENCIES}")
    if payload.amount <= 0:
        raise HTTPException(400, "amount must be > 0")

    doc = payload.model_dump()
    doc["id"] = new_id("rec_")
    doc["next_run_date"] = _initial_run_date(
        payload.start_date, payload.frequency,
        payload.day_of_month, payload.day_of_week,
    )
    doc["last_run_date"] = None
    doc["last_journal_id"] = None
    doc["run_count"] = 0
    doc.setdefault("active", True)
    doc["created_at"] = iso_now()
    doc["created_by"] = user["user_id"]
    await sdb.recurring_expenses.insert_one(dict(doc))
    return await sdb.recurring_expenses.find_one({"id": doc["id"]}, {"_id": 0})


@router.patch("/recurring-expenses/{rec_id}")
async def update_recurring(rec_id: str, payload: RecurringUpdate, request: Request,
                           session_token: Optional[str] = Cookie(default=None),
                           authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    if not has_permission(user, "finance.update"):
        raise HTTPException(403, "Missing permission: finance.update")
    upd = {k: v for k, v in payload.model_dump().items() if v is not None}
    upd["updated_at"] = iso_now()
    if not upd:
        raise HTTPException(400, "Nothing to update")
    if upd.get("frequency") and upd["frequency"] not in FREQUENCIES:
        raise HTTPException(400, f"frequency must be one of {FREQUENCIES}")
    res = await sdb.recurring_expenses.update_one({"id": rec_id}, {"$set": upd})
    if res.matched_count == 0:
        raise HTTPException(404, "Recurring rule not found")
    return await sdb.recurring_expenses.find_one({"id": rec_id}, {"_id": 0})


@router.delete("/recurring-expenses/{rec_id}")
async def delete_recurring(rec_id: str, request: Request,
                           session_token: Optional[str] = Cookie(default=None),
                           authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    if not has_permission(user, "finance.delete"):
        raise HTTPException(403, "Missing permission: finance.delete")
    res = await sdb.recurring_expenses.delete_one({"id": rec_id})
    if res.deleted_count == 0:
        raise HTTPException(404, "Recurring rule not found")
    return {"ok": True}


async def _post_recurring_rule(rule: dict, user: dict) -> Optional[dict]:
    """Post a single JE for a due recurring rule and advance next_run_date.

    Idempotent per (rule_id, run_date) — we check for an existing JE with
    source='recurring_expense' + source_id=rule_id + date=run_date before posting.
    """
    if not rule.get("active"):
        return None
    end_date = rule.get("end_date")
    run_date = rule["next_run_date"]
    if end_date and run_date > end_date:
        # Mark inactive so we stop scanning it.
        await sdb.recurring_expenses.update_one(
            {"id": rule["id"]}, {"$set": {"active": False, "auto_deactivated_at": iso_now()}})
        return None

    existing = await sdb.journal_entries.find_one({
        "source": "recurring_expense",
        "source_id": rule["id"],
        "date": run_date,
    }, {"_id": 0, "id": 1})
    if existing:
        # Already posted for this date — just advance the pointer.
        nxt = _next_run(_date.fromisoformat(run_date), rule["frequency"],
                        rule.get("day_of_month"), rule.get("day_of_week"))
        await sdb.recurring_expenses.update_one(
            {"id": rule["id"]}, {"$set": {"next_run_date": nxt.isoformat()}})
        return None

    base_amt = float(rule["amount"])
    gst_amt = float(rule.get("gst") or 0)
    total = round(base_amt + gst_amt, 2)
    lines = [
        {"account_id": rule["expense_account_id"], "debit": base_amt, "credit": 0,
         "description": f"Recurring · {rule['name']}"},
    ]
    if gst_amt > 0:
        gst_acc = await sdb.accounts.find_one({"name": "GST Payable"}, {"_id": 0, "id": 1})
        if gst_acc:
            lines.append({"account_id": gst_acc["id"], "debit": gst_amt, "credit": 0,
                          "description": "GST input"})
        else:
            lines[0]["debit"] += gst_amt
    lines.append({"account_id": rule["paid_from_account_id"], "debit": 0, "credit": total,
                  "description": f"Paid · {rule['name']}"})

    je = await _post_journal(
        user, run_date,
        f"Recurring expense · {rule['name']}",
        lines,
        reference=rule.get("reference") or f"REC-{rule['id']}",
        project_id=rule.get("project_id"), client_id=rule.get("client_id"),
        vendor_id=rule.get("vendor_id"),
        source="recurring_expense", source_id=rule["id"],
    )

    nxt = _next_run(_date.fromisoformat(run_date), rule["frequency"],
                    rule.get("day_of_month"), rule.get("day_of_week"))
    await sdb.recurring_expenses.update_one(
        {"id": rule["id"]},
        {"$set": {"last_run_date": run_date, "last_journal_id": je["id"],
                  "next_run_date": nxt.isoformat()},
         "$inc": {"run_count": 1}},
    )
    return je


@router.post("/recurring-expenses/{rec_id}/run-now")
async def run_recurring_now(rec_id: str, request: Request,
                            session_token: Optional[str] = Cookie(default=None),
                            authorization: Optional[str] = Header(default=None)):
    """Manual trigger — useful for "post today's rent right now"."""
    user = await require_user(request, session_token, authorization)
    if not has_permission(user, "finance.create"):
        raise HTTPException(403, "Missing permission: finance.create")
    rule = await sdb.recurring_expenses.find_one({"id": rec_id}, {"_id": 0})
    if not rule:
        raise HTTPException(404, "Recurring rule not found")
    # Force the run_date to today (so admins can catch up) — idempotent.
    rule["next_run_date"] = now_utc().date().isoformat()
    je = await _post_recurring_rule(rule, user)
    return {"ok": True, "journal": je,
            "rule": await sdb.recurring_expenses.find_one({"id": rec_id}, {"_id": 0})}


@router.post("/recurring-expenses/scan")
async def scan_recurring(request: Request,
                         session_token: Optional[str] = Cookie(default=None),
                         authorization: Optional[str] = Header(default=None)):
    """Manual "post all due recurring rules for today" — the scheduler runs
    the same code every ~6h, but Admins can also fire it on demand."""
    user = await require_user(request, session_token, authorization)
    if not has_permission(user, "finance.create"):
        raise HTTPException(403, "Missing permission: finance.create")
    today = now_utc().date().isoformat()
    posted = []
    async for r in sdb.recurring_expenses.find(
            {"active": True, "next_run_date": {"$lte": today}}, {"_id": 0}):
        # Catch-up loop: if a rule is 2 months behind we post 2 JEs.
        for _ in range(60):  # safety cap
            if r["next_run_date"] > today:
                break
            je = await _post_recurring_rule(r, user)
            if je:
                posted.append({"rule_id": r["id"], "je_id": je["id"], "date": je["date"]})
            r = await sdb.recurring_expenses.find_one({"id": r["id"]}, {"_id": 0})
            if not r or not r.get("active"):
                break
    return {"ok": True, "posted": posted, "count": len(posted)}


# ==========================================================================
# 2) FAVORITE ACCOUNTS
# ==========================================================================
class FavoriteIn(BaseModel):
    account_id: str


@router.get("/favorite-accounts")
async def list_favorites(request: Request,
                         session_token: Optional[str] = Cookie(default=None),
                         authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    # Personal per-user list within the tenant.
    doc = await sdb.user_favorite_accounts.find_one(
        {"user_id": user["user_id"]}, {"_id": 0})
    ids = list((doc or {}).get("account_ids") or [])
    if not ids:
        return {"account_ids": [], "accounts": []}
    accs = await sdb.accounts.find({"id": {"$in": ids}, "active": {"$ne": False}},
                                   {"_id": 0}).to_list(50)
    order = {aid: i for i, aid in enumerate(ids)}
    accs.sort(key=lambda a: order.get(a["id"], 999))
    return {"account_ids": ids, "accounts": accs}


@router.post("/favorite-accounts")
async def add_favorite(payload: FavoriteIn, request: Request,
                       session_token: Optional[str] = Cookie(default=None),
                       authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    acc = await sdb.accounts.find_one({"id": payload.account_id}, {"_id": 0, "id": 1})
    if not acc:
        raise HTTPException(404, "Account not found")
    doc = await sdb.user_favorite_accounts.find_one(
        {"user_id": user["user_id"]}, {"_id": 0})
    ids = list((doc or {}).get("account_ids") or [])
    if payload.account_id in ids:
        return {"account_ids": ids}
    ids.append(payload.account_id)
    if doc:
        await sdb.user_favorite_accounts.update_one(
            {"user_id": user["user_id"]},
            {"$set": {"account_ids": ids, "updated_at": iso_now()}},
        )
    else:
        await sdb.user_favorite_accounts.insert_one({
            "id": new_id("fav_"),
            "user_id": user["user_id"],
            "account_ids": ids,
            "created_at": iso_now(),
        })
    return {"account_ids": ids}


@router.delete("/favorite-accounts/{account_id}")
async def remove_favorite(account_id: str, request: Request,
                          session_token: Optional[str] = Cookie(default=None),
                          authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    doc = await sdb.user_favorite_accounts.find_one(
        {"user_id": user["user_id"]}, {"_id": 0})
    ids = list((doc or {}).get("account_ids") or [])
    ids = [i for i in ids if i != account_id]
    await sdb.user_favorite_accounts.update_one(
        {"user_id": user["user_id"]},
        {"$set": {"account_ids": ids, "updated_at": iso_now()}},
        upsert=True,
    )
    return {"account_ids": ids}


# ==========================================================================
# 3) VENDOR COMMISSION STATEMENT PDF
# ==========================================================================
@router.get("/vendors/{vendor_id}/commission-statement.pdf")
async def vendor_commission_statement_pdf(vendor_id: str, request: Request,
                                          from_date: Optional[str] = None,
                                          to_date: Optional[str] = None,
                                          session_token: Optional[str] = Cookie(default=None),
                                          authorization: Optional[str] = Header(default=None)):
    """Generate a printable commission-statement PDF for a vendor.

    Lists every commission row in the period with Earned / Received / Pending
    totals, so the vendor / agency can invoice against it.
    """
    user = await require_user(request, session_token, authorization)
    if not has_permission(user, "vendors.read"):
        raise HTTPException(403, "Missing permission: vendors.read")
    vendor = await sdb.vendors_acc.find_one({"id": vendor_id}, {"_id": 0})
    if not vendor:
        raise HTTPException(404, "Vendor not found")

    q: dict = {"vendor_id": vendor_id}
    if from_date or to_date:
        d = {}
        if from_date: d["$gte"] = from_date
        if to_date:   d["$lte"] = to_date
        q["bill_date"] = d
    rows = await sdb.vendor_commissions.find(q, {"_id": 0}).sort("bill_date", 1).to_list(2000)

    org = None
    try:
        oid = user_org_id(user)
        if oid:
            org = await db.organizations.find_one({"id": oid}, {"_id": 0})
    except Exception:
        org = None
    org_name = (org or {}).get("name") or "Design Saga"

    earned = sum(float(r.get("amount") or 0) for r in rows if r.get("status") not in ("cancelled", "reversed"))
    received = sum(float(r.get("received_amount") or 0) for r in rows if r.get("status") not in ("cancelled", "reversed"))
    pending = round(earned - received, 2)

    # Build PDF (fpdf2). We deliberately keep it simple + latin-1 safe.
    from fpdf import FPDF

    def _s(v):
        if v is None:
            return "-"
        v = str(v)
        return (v.replace("\u20B9", "Rs.")
                 .replace("\u2013", "-").replace("\u2014", "-")
                 .replace("\u2018", "'").replace("\u2019", "'")
                 .replace("\u201C", '"').replace("\u201D", '"'))

    def _money(v):
        try:
            return f"Rs. {float(v or 0):,.2f}"
        except Exception:
            return "Rs. 0.00"

    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    # Header
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 8, _s(org_name), ln=1)
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 5, _s("Commission Statement"), ln=1)
    pdf.ln(2)

    # Vendor block
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 6, _s(f"Vendor: {vendor.get('name') or ''}"), ln=1)
    pdf.set_font("Helvetica", "", 9)
    if vendor.get("company"):    pdf.cell(0, 4, _s(vendor["company"]), ln=1)
    if vendor.get("gstin"):      pdf.cell(0, 4, _s(f"GSTIN: {vendor['gstin']}"), ln=1)
    if vendor.get("email"):      pdf.cell(0, 4, _s(f"Email: {vendor['email']}"), ln=1)
    if vendor.get("phone"):      pdf.cell(0, 4, _s(f"Phone: {vendor['phone']}"), ln=1)
    period = f"Period: {from_date or 'inception'}  to  {to_date or now_utc().date().isoformat()}"
    pdf.cell(0, 4, _s(period), ln=1)
    pdf.ln(3)

    # Totals card
    pdf.set_fill_color(245, 244, 240)
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(60, 8, _s("Total earned"), fill=True)
    pdf.cell(60, 8, _s("Received"), fill=True)
    pdf.cell(60, 8, _s("Pending"), fill=True, ln=1)
    pdf.set_font("Helvetica", "", 11)
    pdf.cell(60, 8, _money(earned))
    pdf.cell(60, 8, _money(received))
    pdf.cell(60, 8, _money(pending), ln=1)
    pdf.ln(3)

    # Table header
    pdf.set_fill_color(230, 226, 217)
    pdf.set_font("Helvetica", "B", 9)
    headers = [("Bill date", 22), ("Bill #", 26), ("Base", 26),
               ("Earned", 26), ("Received", 26), ("Status", 22), ("Ref", 32)]
    for h, w in headers:
        pdf.cell(w, 6, _s(h), border=1, fill=True)
    pdf.ln()
    pdf.set_font("Helvetica", "", 8)

    for r in rows:
        pdf.cell(22, 6, _s(r.get("bill_date")), border=1)
        pdf.cell(26, 6, _s(r.get("bill_number")), border=1)
        pdf.cell(26, 6, _money(r.get("purchase_amount") or 0), border=1)
        pdf.cell(26, 6, _money(r.get("amount") or 0), border=1)
        pdf.cell(26, 6, _money(r.get("received_amount") or 0), border=1)
        pdf.cell(22, 6, _s((r.get("status") or "").upper()), border=1)
        pdf.cell(32, 6, _s(r.get("reference") or ""), border=1, ln=1)

    if not rows:
        pdf.cell(0, 6, _s("No commission rows in this period."), ln=1)

    # Footer
    pdf.ln(4)
    pdf.set_font("Helvetica", "I", 8)
    pdf.set_text_color(120, 120, 120)
    pdf.cell(0, 4, _s(f"Generated {now_utc().date().isoformat()} · {org_name}"), ln=1)

    output = pdf.output(dest="S")
    # fpdf2 >= 2.5 returns bytearray; older returns str.
    body = bytes(output) if isinstance(output, (bytes, bytearray)) else output.encode("latin-1")
    filename = f"commission-statement-{(vendor.get('name') or 'vendor').replace(' ', '-').lower()}.pdf"
    return FastAPIResponse(
        content=body,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ==========================================================================
# 4) BANK RECONCILIATION
# ==========================================================================
# Upload a CSV (date, description, amount, [reference]) → we store rows in
# `bank_statement_rows` keyed to an account. Rows are auto-matched against
# posted JE lines on that bank account within ± amount tolerance and a date
# window. Admins can then mark rows reconciled, or create a new JE from an
# unmatched row (routed through _post_journal to keep the books balanced).
# ==========================================================================

class BankMatchIn(BaseModel):
    journal_id: str


class BankCreateJEIn(BaseModel):
    counterpart_account_id: str        # income or expense to book against
    narration: Optional[str] = None
    reference: Optional[str] = None
    project_id: Optional[str] = None
    vendor_id: Optional[str] = None
    client_id: Optional[str] = None


def _parse_amount(raw) -> Optional[float]:
    if raw is None:
        return None
    s = str(raw).strip().replace(",", "").replace("₹", "").replace("Rs.", "").replace("INR", "").strip()
    if s == "" or s.lower() in ("nan", "none"):
        return None
    # Handle bracketed negatives  → (1,200) means -1200
    negative = False
    if s.startswith("(") and s.endswith(")"):
        negative = True
        s = s[1:-1]
    try:
        v = float(s)
        return -abs(v) if negative else v
    except ValueError:
        return None


def _parse_date(raw) -> Optional[str]:
    if not raw:
        return None
    s = str(raw).strip()
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%m/%d/%Y", "%d %b %Y", "%d-%b-%Y", "%d-%b-%y"):
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            continue
    # Excel serial fallback (rough)
    try:
        f = float(s)
        base = _date(1899, 12, 30).toordinal()
        return _date.fromordinal(base + int(f)).isoformat()
    except ValueError:
        return None


@router.post("/bank-reconciliation/{account_id}/upload")
async def upload_bank_statement(account_id: str, request: Request,
                                file: UploadFile = File(...),
                                session_token: Optional[str] = Cookie(default=None),
                                authorization: Optional[str] = Header(default=None)):
    """Upload a bank-statement CSV. Expected columns (case-insensitive):
    date, description (or narration/particulars), amount (or debit/credit),
    reference (optional).

    Debit/Credit statements: if a `debit` column has value the amount is stored
    negative (money out); a `credit` column stores positive (money in). Signed
    `amount` columns are respected as-is.
    """
    user = await require_user(request, session_token, authorization)
    if not has_permission(user, "finance.create"):
        raise HTTPException(403, "Missing permission: finance.create")
    acc = await sdb.accounts.find_one({"id": account_id}, {"_id": 0})
    if not acc:
        raise HTTPException(404, "Bank account not found")
    if not (acc.get("is_bank") or acc.get("name") in ("Cash", "Petty Cash")):
        raise HTTPException(400, "This account is not a bank / cash account")

    raw = await file.read()
    try:
        text = raw.decode("utf-8-sig", errors="replace")
    except Exception:
        text = raw.decode("latin-1", errors="replace")

    import csv, io
    reader = csv.DictReader(io.StringIO(text))
    field_map = {(k or "").strip().lower(): k for k in (reader.fieldnames or [])}

    def pick(row, *names):
        for n in names:
            key = field_map.get(n)
            if key and row.get(key) not in (None, ""):
                return row.get(key)
        return None

    batch_id = new_id("brb_")
    rows_saved = []
    for row in reader:
        d = _parse_date(pick(row, "date", "txn date", "value date", "transaction date"))
        if not d:
            continue
        desc = pick(row, "description", "narration", "particulars", "details") or ""
        ref = pick(row, "reference", "ref", "utr", "chq no", "cheque no") or ""
        debit = _parse_amount(pick(row, "debit", "withdrawal", "dr"))
        credit = _parse_amount(pick(row, "credit", "deposit", "cr"))
        amount_field = _parse_amount(pick(row, "amount"))
        if amount_field is not None:
            amt = amount_field
        elif credit is not None and (credit or 0) != 0:
            amt = abs(credit)
        elif debit is not None and (debit or 0) != 0:
            amt = -abs(debit)
        else:
            continue
        if amt == 0:
            continue
        doc = {
            "id": new_id("brow_"),
            "batch_id": batch_id,
            "account_id": account_id,
            "date": d,
            "description": desc.strip(),
            "reference": (ref or "").strip(),
            "amount": round(float(amt), 2),
            "status": "unmatched",
            "matched_journal_id": None,
            "created_at": iso_now(),
            "created_by": user["user_id"],
        }
        await sdb.bank_statement_rows.insert_one(dict(doc))
        rows_saved.append(doc)

    # Auto-match: for each row, find a JE line on this bank account on ±3 days
    # with an equal signed amount (money-in = debit; money-out = credit). Reversed
    # or already-matched JEs are skipped.
    match_count = 0
    for r in rows_saved:
        signed_amt = r["amount"]
        window_lo = (_date.fromisoformat(r["date"]).toordinal() - 3)
        window_hi = (_date.fromisoformat(r["date"]).toordinal() + 3)
        lo = _date.fromordinal(window_lo).isoformat()
        hi = _date.fromordinal(window_hi).isoformat()
        # Find a JE with a matching bank-line
        # For a positive row amount (money-IN), we're looking for a JE where the
        # bank account was DEBITED (asset in). Negative → the bank account was
        # CREDITED.
        need_debit = signed_amt > 0
        pipeline = [
            {"$match": {"date": {"$gte": lo, "$lte": hi},
                        "reversed": {"$ne": True},
                        "lines.account_id": account_id}},
            {"$unwind": "$lines"},
            {"$match": {"lines.account_id": account_id,
                        ("lines.debit" if need_debit else "lines.credit"):
                            {"$gte": abs(signed_amt) - 0.5, "$lte": abs(signed_amt) + 0.5}}},
            {"$lookup": {
                "from": "bank_statement_rows",
                "localField": "id",
                "foreignField": "matched_journal_id",
                "as": "already",
            }},
            {"$match": {"already": {"$size": 0}}},
            {"$limit": 1},
        ]
        async for je in sdb.journal_entries.aggregate(pipeline):
            await sdb.bank_statement_rows.update_one(
                {"id": r["id"]},
                {"$set": {"status": "auto_matched",
                          "matched_journal_id": je["id"],
                          "matched_at": iso_now()}},
            )
            match_count += 1
            break

    # Persist an import-log record for this upload so accountants can review the
    # history per account, re-download the original CSV, or delete a bad import.
    batch_doc = {
        "id": batch_id,
        "account_id": account_id,
        "account_name": acc.get("name"),
        "filename": (file.filename or "statement.csv"),
        "raw_csv": text,                      # original file content for re-download
        "file_size": len(raw),
        "rows_saved": len(rows_saved),
        "auto_matched": match_count,
        "status": "active",
        "created_at": iso_now(),
        "created_by": user["user_id"],
        "created_by_name": user.get("name") or user.get("email") or user["user_id"],
    }
    await sdb.bank_statement_batches.insert_one(dict(batch_doc))

    await audit(user, "bank_recon.upload", target=batch_id, target_type="bank_batch",
                meta={"account_id": account_id, "rows": len(rows_saved),
                      "auto_matched": match_count})
    return {"ok": True, "batch_id": batch_id, "rows_saved": len(rows_saved),
            "auto_matched": match_count}


# ==========================================================================
# 4b) BANK STATEMENT IMPORT LOG
# ==========================================================================
# A history of uploaded statements per account. Each upload creates a batch
# record (see upload endpoint). Accountants can review the log, re-download the
# original CSV, or delete a bad import. Deleting a batch removes its statement
# rows but NEVER touches posted journal entries (accounting safety) — any JE
# created from a row stays on the books and simply loses its bank-row pointer.
# ==========================================================================

async def _batch_live_stats(batch_id: str) -> dict:
    """Live status breakdown of the rows still belonging to a batch."""
    stats = {"total": 0, "unmatched": 0, "auto_matched": 0,
             "matched": 0, "reconciled": 0, "ignored": 0, "has_je": 0}
    async for r in sdb.bank_statement_rows.find(
            {"batch_id": batch_id}, {"_id": 0, "status": 1, "matched_journal_id": 1}):
        stats["total"] += 1
        s = r.get("status") or "unmatched"
        stats[s] = stats.get(s, 0) + 1
        if r.get("matched_journal_id"):
            stats["has_je"] += 1
    return stats


@router.get("/bank-reconciliation/{account_id}/batches")
async def list_bank_batches(account_id: str, request: Request,
                            session_token: Optional[str] = Cookie(default=None),
                            authorization: Optional[str] = Header(default=None)):
    """Import log for a bank/cash account — newest upload first."""
    user = await require_user(request, session_token, authorization)
    if not has_permission(user, "finance.read"):
        raise HTTPException(403, "Missing permission: finance.read")
    batches = await sdb.bank_statement_batches.find(
        {"account_id": account_id}, {"_id": 0, "raw_csv": 0},
    ).sort("created_at", -1).to_list(500)
    for b in batches:
        b["live"] = await _batch_live_stats(b["id"])
    return {"batches": batches}


@router.get("/bank-reconciliation/batches/{batch_id}/download")
async def download_bank_batch(batch_id: str, request: Request,
                              session_token: Optional[str] = Cookie(default=None),
                              authorization: Optional[str] = Header(default=None)):
    """Re-download the original uploaded CSV for a batch."""
    user = await require_user(request, session_token, authorization)
    if not has_permission(user, "finance.read"):
        raise HTTPException(403, "Missing permission: finance.read")
    batch = await sdb.bank_statement_batches.find_one({"id": batch_id}, {"_id": 0})
    if not batch:
        raise HTTPException(404, "Import batch not found")
    csv_text = batch.get("raw_csv")
    if csv_text is None:
        raise HTTPException(404, "Original file not available for this import")
    filename = batch.get("filename") or f"{batch_id}.csv"
    body = csv_text.encode("utf-8-sig")
    return FastAPIResponse(
        content=body,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.delete("/bank-reconciliation/batches/{batch_id}")
async def delete_bank_batch(batch_id: str, request: Request,
                            force: bool = False,
                            session_token: Optional[str] = Cookie(default=None),
                            authorization: Optional[str] = Header(default=None)):
    """Delete a bad import: removes the batch's statement rows and the log entry.

    Posted journal entries are NEVER deleted. If any row in the batch is already
    reconciled or linked to a JE, the caller must pass `force=true` to confirm —
    the JEs remain on the books, only the bank-row pointers are removed.
    """
    user = await require_user(request, session_token, authorization)
    if not has_permission(user, "finance.delete"):
        raise HTTPException(403, "Missing permission: finance.delete")
    batch = await sdb.bank_statement_batches.find_one({"id": batch_id}, {"_id": 0})
    if not batch:
        raise HTTPException(404, "Import batch not found")
    stats = await _batch_live_stats(batch_id)
    sensitive = stats.get("reconciled", 0) + stats.get("has_je", 0)
    if sensitive > 0 and not force:
        raise HTTPException(
            409,
            f"This import has {stats.get('reconciled', 0)} reconciled and "
            f"{stats.get('has_je', 0)} JE-linked row(s). Re-send with force=true "
            f"to delete anyway (journal entries are preserved).",
        )
    del_res = await sdb.bank_statement_rows.delete_many({"batch_id": batch_id})
    await sdb.bank_statement_batches.delete_one({"id": batch_id})
    await audit(user, "bank_recon.delete_batch", target=batch_id, target_type="bank_batch",
                meta={"account_id": batch.get("account_id"),
                      "rows_deleted": del_res.deleted_count, "forced": force})
    return {"ok": True, "rows_deleted": del_res.deleted_count}


@router.get("/bank-reconciliation/{account_id}/rows")
async def list_bank_rows(account_id: str, request: Request,
                         status: Optional[str] = None,
                         from_date: Optional[str] = None,
                         to_date: Optional[str] = None,
                         session_token: Optional[str] = Cookie(default=None),
                         authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    if not has_permission(user, "finance.read"):
        raise HTTPException(403, "Missing permission: finance.read")
    q: dict = {"account_id": account_id}
    if status:
        q["status"] = status
    if from_date or to_date:
        d = {}
        if from_date: d["$gte"] = from_date
        if to_date:   d["$lte"] = to_date
        q["date"] = d
    rows = await sdb.bank_statement_rows.find(q, {"_id": 0}).sort("date", -1).to_list(2000)
    counts = {"unmatched": 0, "auto_matched": 0, "matched": 0, "reconciled": 0, "ignored": 0}
    for r in rows:
        s = r.get("status") or "unmatched"
        counts[s] = counts.get(s, 0) + 1
    return {"rows": rows, "counts": counts}


@router.post("/bank-reconciliation/rows/{row_id}/match")
async def match_bank_row(row_id: str, payload: BankMatchIn, request: Request,
                         session_token: Optional[str] = Cookie(default=None),
                         authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    if not has_permission(user, "finance.update"):
        raise HTTPException(403, "Missing permission: finance.update")
    row = await sdb.bank_statement_rows.find_one({"id": row_id}, {"_id": 0})
    if not row:
        raise HTTPException(404, "Row not found")
    je = await sdb.journal_entries.find_one({"id": payload.journal_id}, {"_id": 0})
    if not je:
        raise HTTPException(404, "Journal entry not found")
    await sdb.bank_statement_rows.update_one(
        {"id": row_id},
        {"$set": {"status": "matched",
                  "matched_journal_id": je["id"],
                  "matched_at": iso_now(),
                  "matched_by": user["user_id"]}},
    )
    return {"ok": True}


@router.post("/bank-reconciliation/rows/{row_id}/reconcile")
async def reconcile_bank_row(row_id: str, request: Request,
                             session_token: Optional[str] = Cookie(default=None),
                             authorization: Optional[str] = Header(default=None)):
    """Final tick: user confirms this row is fully reconciled (books match)."""
    user = await require_user(request, session_token, authorization)
    if not has_permission(user, "finance.update"):
        raise HTTPException(403, "Missing permission: finance.update")
    res = await sdb.bank_statement_rows.update_one(
        {"id": row_id},
        {"$set": {"status": "reconciled", "reconciled_at": iso_now(),
                  "reconciled_by": user["user_id"]}},
    )
    if res.matched_count == 0:
        raise HTTPException(404, "Row not found")
    return {"ok": True}


@router.post("/bank-reconciliation/rows/{row_id}/ignore")
async def ignore_bank_row(row_id: str, request: Request,
                          session_token: Optional[str] = Cookie(default=None),
                          authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    if not has_permission(user, "finance.update"):
        raise HTTPException(403, "Missing permission: finance.update")
    await sdb.bank_statement_rows.update_one(
        {"id": row_id},
        {"$set": {"status": "ignored", "ignored_at": iso_now(),
                  "ignored_by": user["user_id"]}},
    )
    return {"ok": True}


@router.post("/bank-reconciliation/rows/{row_id}/create-je")
async def create_je_from_bank_row(row_id: str, payload: BankCreateJEIn, request: Request,
                                  session_token: Optional[str] = Cookie(default=None),
                                  authorization: Optional[str] = Header(default=None)):
    """Post a fresh JE from an unmatched bank row.

    Positive row amount → money in → DR bank / CR counterpart (should be income).
    Negative row amount → money out → DR counterpart (should be expense) / CR bank.
    """
    user = await require_user(request, session_token, authorization)
    if not has_permission(user, "finance.create"):
        raise HTTPException(403, "Missing permission: finance.create")
    row = await sdb.bank_statement_rows.find_one({"id": row_id}, {"_id": 0})
    if not row:
        raise HTTPException(404, "Row not found")
    if row.get("matched_journal_id"):
        raise HTTPException(400, "Row is already matched to a JE")
    counter = await sdb.accounts.find_one({"id": payload.counterpart_account_id}, {"_id": 0})
    if not counter:
        raise HTTPException(404, "Counterpart account not found")

    amt = float(row["amount"])
    money_in = amt > 0
    bank_id = row["account_id"]
    if money_in:
        lines = [
            {"account_id": bank_id, "debit": abs(amt), "credit": 0, "description": "Bank credit"},
            {"account_id": counter["id"], "debit": 0, "credit": abs(amt), "description": row.get("description") or "Recorded from bank statement"},
        ]
    else:
        lines = [
            {"account_id": counter["id"], "debit": abs(amt), "credit": 0, "description": row.get("description") or "Recorded from bank statement"},
            {"account_id": bank_id, "debit": 0, "credit": abs(amt), "description": "Bank debit"},
        ]
    je = await _post_journal(
        user, row["date"],
        payload.narration or row.get("description") or "Recorded from bank statement",
        lines,
        reference=payload.reference or row.get("reference"),
        project_id=payload.project_id, vendor_id=payload.vendor_id, client_id=payload.client_id,
        source="bank_statement", source_id=row["id"],
    )
    await sdb.bank_statement_rows.update_one(
        {"id": row_id},
        {"$set": {"status": "matched",
                  "matched_journal_id": je["id"],
                  "matched_at": iso_now(),
                  "matched_by": user["user_id"]}},
    )
    return {"ok": True, "journal": je}


# ==========================================================================
# Bank reconciliation summary  (Dashboard KPI card)
# ==========================================================================
@router.get("/bank-reconciliation/summary")
async def bank_reconciliation_summary(request: Request,
                                      session_token: Optional[str] = Cookie(default=None),
                                      authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    if not has_permission(user, "finance.read"):
        raise HTTPException(403, "Missing permission: finance.read")
    accs = await sdb.accounts.find({"$or": [{"is_bank": True}, {"name": "Cash"},
                                             {"name": "Petty Cash"}]},
                                    {"_id": 0}).to_list(50)
    out = []
    for a in accs:
        stats = {"unmatched": 0, "auto_matched": 0, "matched": 0, "reconciled": 0, "ignored": 0}
        async for r in sdb.bank_statement_rows.find(
            {"account_id": a["id"]}, {"_id": 0, "status": 1},
        ):
            s = r.get("status") or "unmatched"
            stats[s] = stats.get(s, 0) + 1
        out.append({"account": a, **stats})
    return {"accounts": out}
