"""Close & export an accounting period.

Workflow (one screen in Accounting → Setup):
  1. Check    - read-only integrity checks for the period (balanced entries,
                source links, Cash/Bank pairing, pending money items).
  2. Export   - one Excel workbook with the period's books and a manifest
                (record counts, totals, SHA-256 of every sheet and of the file).
  3. Close    - Admin locks the books up to the period end. Nothing dated on or
                before that day can be posted, deleted or corrected in place;
                a reversal dated today is still allowed.
  4. Reopen   - Admin only, with a written reason; audited.

Exporting never deletes anything. Closed years stay fully visible in every
report, ledger and search - the lock only stops them changing.
"""
import hashlib
import json
from datetime import date as _date, datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Cookie, Header, HTTPException, Request
from fastapi.responses import Response
from pydantic import Field

from core.audit import audit
from core.db import db
from core.deps import require_user
from core.downloads import content_disposition
from core.finance import resolve_period
from core.helpers import business_today, iso_now, new_id
from core.period_lock import locked_through
from core.rbac import has_permission
from core.scoped_db import current_org_id, sdb
from core.xlsx import build_xlsx
from models.base import FiniteModel

router = APIRouter()

SCHEMA = "design-saga-period-export/1"
EXPORT_VALID_DAYS = 7
MAX_EXPORT_ROWS = 200000


class CloseIn(FiniteModel):
    through_date: str
    export_id: str
    reason: Optional[str] = Field(default=None, max_length=500)
    acknowledge_warnings: bool = False


class ReopenIn(FiniteModel):
    # New lock date (earlier than the current one) or None to unlock everything.
    locked_through: Optional[str] = None
    reason: str = Field(min_length=10, max_length=500)


def _iso(day: Optional[str], name: str) -> str:
    try:
        return _date.fromisoformat(str(day)[:10]).isoformat()
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail=f"{name} must be a date like 2026-03-31")


def _dmy(value) -> str:
    if not value:
        return ""
    text = str(value)
    try:
        if len(text) > 10:
            dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone(timedelta(hours=5, minutes=30))).strftime("%d/%m/%Y %H:%M")
        return _date.fromisoformat(text[:10]).strftime("%d/%m/%Y")
    except ValueError:
        return text


def _num(value) -> float:
    try:
        return round(float(value or 0), 2)
    except (TypeError, ValueError):
        return 0.0


def _pick(doc: dict, *keys):
    for k in keys:
        if doc.get(k) not in (None, ""):
            return doc.get(k)
    return None


def _require_perm(user: dict, perm: str) -> dict:
    if not has_permission(user, perm):
        raise HTTPException(status_code=403, detail=(
            "Only an administrator can close or reopen books" if perm == "*.*" else f"Missing permission: {perm}"))
    return user


def _range(fy: Optional[str], from_date: Optional[str], to_date: Optional[str]):
    start, end, label = resolve_period(fy=fy, from_date=from_date, to_date=to_date)
    if not end:
        raise HTTPException(status_code=400, detail="Choose the period's last day")
    return (_iso(start, "From date") if start else None), _iso(end, "To date"), label


def _in_range(field: str, start: Optional[str], end: str) -> dict:
    cond = {"$lte": end}
    if start:
        cond["$gte"] = start
    return {field: cond}


async def _names() -> dict:
    out = {"project": {}, "client": {}, "vendor": {}, "employee": {}, "account": {}}
    async for p in sdb.projects.find({}, {"_id": 0, "id": 1, "name": 1}):
        out["project"][p["id"]] = p.get("name")
    async for c in sdb.clients.find({}, {"_id": 0, "id": 1, "name": 1}):
        out["client"][c["id"]] = c.get("name")
    async for v in sdb.vendors_acc.find({}, {"_id": 0, "id": 1, "name": 1}):
        out["vendor"][v["id"]] = v.get("name")
    async for e in sdb.employees.find({}, {"_id": 0, "id": 1, "first_name": 1, "last_name": 1, "employee_id": 1}):
        out["employee"][e["id"]] = " ".join(x for x in [e.get("first_name"), e.get("last_name")] if x) or e.get("employee_id")
    async for a in sdb.accounts.find({}, {"_id": 0}):
        out["account"][a["id"]] = a
    return out


def _natural(acc_type: str, debit: float, credit: float) -> float:
    return debit - credit if acc_type in ("asset", "expense") else credit - debit


# ----------------------------------------------------------------- checks
async def _checks(start: Optional[str], end: str) -> dict:
    from routes.accounting import source_integrity_report
    blockers, warnings = [], []
    today = business_today().isoformat()
    lock = await locked_through()
    if end > today:
        blockers.append({"code": "future", "message": "The period has not ended yet."})
    if lock and end <= lock:
        blockers.append({"code": "already_closed", "message": f"The books are already closed up to {_dmy(lock)}."})

    entries = await sdb.journal_entries.find(
        {**_in_range("date", start, end), "voided_from_view": {"$ne": True}},
        {"_id": 0, "id": 1, "date": 1, "narration": 1, "lines": 1}).to_list(MAX_EXPORT_ROWS)
    unbalanced = []
    debit_total = credit_total = 0.0
    for e in entries:
        d = round(sum(float(l.get("debit") or 0) for l in e.get("lines") or []), 2)
        c = round(sum(float(l.get("credit") or 0) for l in e.get("lines") or []), 2)
        debit_total += d
        credit_total += c
        if abs(d - c) > 0.01:
            unbalanced.append({"id": e["id"], "date": e.get("date"), "narration": e.get("narration"), "diff": round(d - c, 2)})
    if unbalanced:
        blockers.append({"code": "unbalanced", "message": f"{len(unbalanced)} entries in this period do not balance.",
                         "rows": unbalanced[:20]})

    integrity = await source_integrity_report(as_of=end)
    counts = integrity.get("counts") or {}
    problems = {k: v for k, v in counts.items() if v and k not in {"journals_checked", "active_source_links"}}
    if problems:
        blockers.append({"code": "integrity",
                         "message": "The accounting check found linked-record problems: "
                                    + ", ".join(f"{k.replace('_', ' ')} {v}" for k, v in sorted(problems.items())),
                         "counts": problems})

    processing = await sdb.payroll_runs.count_documents({"status": "processing", **_in_range("payment_date", start, end)})
    if processing:
        blockers.append({"code": "payroll_processing",
                         "message": f"{processing} salary payment(s) are half-saved. Open Payroll and finish or cancel them."})
    approved = await sdb.expenses.count_documents(
        {**_in_range("date", start, end), "status": "approved"})
    if approved:
        warnings.append({"code": "expenses_unpaid",
                         "message": f"{approved} approved expense claim(s) in this period are not reimbursed yet. "
                                    "They can still be paid after closing, dated after the closing day."})
    open_dues = await sdb.collection_receivables.count_documents(
        {**_in_range("due_date", start, end), "status": {"$in": ["pending", "partially_received", "open", None]}})
    if open_dues:
        warnings.append({"code": "collections_open",
                         "message": f"{open_dues} collection(s) due in this period are not fully received. "
                                    "They stay in Collections Due; receipts will be dated after closing."})
    return {
        "from_date": start, "to_date": end, "locked_through": lock,
        "ok": not blockers, "blockers": blockers, "warnings": warnings,
        "entries": len(entries), "debit_total": round(debit_total, 2), "credit_total": round(credit_total, 2),
        "generated_at": iso_now(),
    }


# ----------------------------------------------------------------- export
async def _workbook(start: Optional[str], end: str, user: dict, org_name: str):
    n = await _names()
    acc = n["account"]
    rng = _in_range("date", start, end)
    journals = await sdb.journal_entries.find(rng, {"_id": 0}).sort([("date", 1), ("created_at", 1)]).to_list(MAX_EXPORT_ROWS)

    def status(e):
        if e.get("voided_from_view"):
            return "Removed from books (" + str(e.get("void_reason") or "correction") + ")"
        if str(e.get("source") or "").endswith("_reversal"):
            return "Reversal"
        if e.get("reversed"):
            return "Reversed"
        return "Active"

    daybook = [["Date", "Date (raw)", "Voucher ID", "Narration", "Reference", "Source", "Source ID",
                "Project", "Client", "Vendor", "Employee", "Amount", "Status", "Reversed by / reversal of",
                "Created by", "Created at"]]
    lines = [["Voucher ID", "Date", "Account code", "Account", "Type", "Debit", "Credit", "Description",
              "Project", "Party", "Status"]]
    for e in journals:
        party = n["client"].get(e.get("client_id")) or n["vendor"].get(e.get("vendor_id")) or n["employee"].get(e.get("employee_id")) or ""
        st = status(e)
        daybook.append([_dmy(e.get("date")), e.get("date"), e.get("id"), e.get("narration"), e.get("reference"),
                        e.get("source"), e.get("source_id"), n["project"].get(e.get("project_id")) or "",
                        n["client"].get(e.get("client_id")) or "", n["vendor"].get(e.get("vendor_id")) or "",
                        n["employee"].get(e.get("employee_id")) or "", _num(e.get("total")), st,
                        e.get("reversal_je_id") or (e.get("source_id") if st == "Reversal" else ""),
                        e.get("created_by_name") or e.get("created_by"), _dmy(e.get("created_at"))])
        for l in e.get("lines") or []:
            a = acc.get(l.get("account_id")) or {}
            lines.append([e.get("id"), _dmy(e.get("date")), a.get("code"), l.get("account_name") or a.get("name"),
                          l.get("account_type") or a.get("type"), _num(l.get("debit")), _num(l.get("credit")),
                          l.get("description"), n["project"].get(e.get("project_id")) or "", party, st])

    # Trial balance / P&L: books as reports show them (removed pairs excluded).
    before, during = {}, {}
    q = {"voided_from_view": {"$ne": True}, "date": {"$lte": end}}
    async for e in sdb.journal_entries.find(q, {"_id": 0, "date": 1, "lines": 1}):
        bucket = during if (not start or e["date"] >= start) else before
        for l in e.get("lines") or []:
            d = bucket.setdefault(l["account_id"], [0.0, 0.0])
            d[0] += float(l.get("debit") or 0)
            d[1] += float(l.get("credit") or 0)
    tb = [["Code", "Account", "Type", "Opening balance", "Debit in period", "Credit in period", "Closing balance"]]
    pl_income, pl_expense = [], []
    tb_debit = tb_credit = 0.0
    for a in sorted(acc.values(), key=lambda x: (str(x.get("code") or ""), x.get("name") or "")):
        t = a.get("type")
        b = before.get(a["id"], [0.0, 0.0])
        d = during.get(a["id"], [0.0, 0.0])
        opening = _num(a.get("opening_balance")) + _natural(t, b[0], b[1])
        closing = opening + _natural(t, d[0], d[1])
        if abs(opening) < 0.005 and abs(d[0]) < 0.005 and abs(d[1]) < 0.005:
            continue
        tb_debit += d[0]
        tb_credit += d[1]
        tb.append([a.get("code"), a.get("name"), t, round(opening, 2), round(d[0], 2), round(d[1], 2), round(closing, 2)])
        if t == "income":
            pl_income.append([a.get("code"), a.get("name"), round(d[1] - d[0], 2)])
        elif t == "expense":
            pl_expense.append([a.get("code"), a.get("name"), round(d[0] - d[1], 2)])
    tb.append(["", "Total", "", "", round(tb_debit, 2), round(tb_credit, 2), ""])
    income = round(sum(r[2] for r in pl_income), 2)
    expense = round(sum(r[2] for r in pl_expense), 2)
    pl = [["Code", "Account", "Amount"], ["", "INCOME", ""], *pl_income, ["", "Total income", income],
          ["", "EXPENSES", ""], *pl_expense, ["", "Total expenses", expense], ["", "Net profit / (loss)", round(income - expense, 2)]]

    coa = [["Code", "Account", "Type", "Bank/cash", "Opening balance", "Active", "Account ID"]]
    for a in sorted(acc.values(), key=lambda x: str(x.get("code") or "")):
        coa.append([a.get("code"), a.get("name"), a.get("type"), bool(a.get("is_bank")),
                    _num(a.get("opening_balance")), a.get("active") is not False, a.get("id")])

    invoices = [["Number", "Date", "Client", "Project", "Status", "Subtotal", "Tax", "Total", "Received on invoice", "Invoice ID"]]
    async for inv in sdb.invoices.find({**_in_range("issue_date", start, end), "doc_type": {"$ne": "quotation"}}, {"_id": 0}).sort("issue_date", 1):
        invoices.append([inv.get("number"), _dmy(inv.get("issue_date")), inv.get("client_name") or n["client"].get(inv.get("client_id")),
                         n["project"].get(inv.get("project_id")) or "", inv.get("status"), _num(inv.get("subtotal")),
                         _num(inv.get("tax")), _num(inv.get("total")), _num(inv.get("paid_amount")), inv.get("id")])

    receipts = [["Date", "Amount", "Collection type", "Collection ID", "Cash/Bank", "Method", "Reference", "Status", "Voucher ID"]]
    async for r in sdb.collection_receipts.find(rng, {"_id": 0}).sort("date", 1):
        receipts.append([_dmy(r.get("date")), _num(r.get("amount")), r.get("source_type"), r.get("source_id"),
                         (acc.get(r.get("bank_account_id")) or {}).get("name"), r.get("payment_method"),
                         r.get("reference"), r.get("status"), r.get("journal_entry_id")])

    collections = [["Due date", "What", "Client / vendor", "Project", "Expected", "Received", "Still due", "Status", "Reference", "ID"]]
    async for r in sdb.collection_receivables.find({}, {"_id": 0}).sort("due_date", 1):
        if r.get("due_date") and (r["due_date"] > end or (start and r["due_date"] < start)):
            continue
        exp, got = _num(r.get("amount")), _num(r.get("received_amount"))
        collections.append([_dmy(r.get("due_date")), r.get("name"), n["client"].get(r.get("client_id")) or "",
                            n["project"].get(r.get("project_id")) or "", exp, got, round(exp - got, 2),
                            r.get("status"), r.get("reference"), r.get("id")])
    async for r in sdb.vendor_commissions.find({}, {"_id": 0}).sort("due_date", 1):
        if r.get("due_date") and (r["due_date"] > end or (start and r["due_date"] < start)):
            continue
        exp, got = _num(r.get("amount")), _num(r.get("received_amount"))
        collections.append([_dmy(r.get("due_date")), "Vendor incentive", n["vendor"].get(r.get("vendor_id")) or "",
                            n["project"].get(r.get("project_id")) or "", exp, got, round(exp - got, 2),
                            r.get("status"), r.get("reference"), r.get("id")])

    bills = [["Bill date", "Bill number", "Vendor", "Project", "Total", "Paid", "Status", "Bill ID"]]
    async for b in sdb.vendor_bills.find(_in_range("bill_date", start, end), {"_id": 0}).sort("bill_date", 1):
        bills.append([_dmy(b.get("bill_date")), b.get("bill_number"), n["vendor"].get(b.get("vendor_id")) or b.get("vendor_name"),
                      n["project"].get(b.get("project_id")) or "", _num(b.get("total")), _num(b.get("paid_amount")),
                      b.get("status"), b.get("id")])
    payments = [["Date", "Vendor", "Amount", "Paid from", "Method", "Reference", "Status", "Voucher ID", "Payment ID"]]
    async for p in sdb.vendor_payments.find(_in_range("payment_date", start, end), {"_id": 0}).sort("payment_date", 1):
        payments.append([_dmy(p.get("payment_date")), n["vendor"].get(p.get("vendor_id")) or p.get("vendor_name"),
                         _num(p.get("amount")), (acc.get(p.get("paid_from_account_id")) or {}).get("name"),
                         p.get("payment_method"), p.get("reference"), p.get("status"), p.get("journal_entry_id"), p.get("id")])
    payroll = [["Paid on", "Employee", "Salary month", "Net paid", "Paid from", "Method", "Reference", "Status", "Voucher ID", "Run ID"]]
    async for r in sdb.payroll_runs.find(_in_range("payment_date", start, end), {"_id": 0}).sort("payment_date", 1):
        payroll.append([_dmy(r.get("payment_date")), r.get("employee_name") or n["employee"].get(r.get("employee_id")),
                        f"{int(r.get('month') or 0):02d}/{r.get('year')}", _num(r.get("net")),
                        (acc.get(r.get("paid_from_account_id")) or {}).get("name"), r.get("payment_method"),
                        r.get("reference"), r.get("status"), r.get("journal_id"), r.get("id")])
    expenses = [["Date", "Title", "Category", "Employee", "Project", "Amount", "Status", "Receipt file", "Voucher ID", "Expense ID"]]
    attachments = [["Record", "Record ID", "Date", "File reference"]]
    async for x in sdb.expenses.find(rng, {"_id": 0}).sort("date", 1):
        receipt = _pick(x, "receipt_file_id", "receipt_url")
        expenses.append([_dmy(x.get("date")), _pick(x, "title", "description"), x.get("category"),
                         n["employee"].get(x.get("employee_id")) or x.get("submitted_by_name"),
                         n["project"].get(x.get("project_id")) or "", _num(x.get("amount")), x.get("status"),
                         "Yes" if receipt else "", _pick(x, "journal_entry_id", "journal_id"), x.get("id")])
        if receipt:
            attachments.append(["Expense receipt", x.get("id"), _dmy(x.get("date")), receipt])

    org = current_org_id() or "org_default"
    audit_rows = [["When", "Action", "Record type", "Record", "By", "Role"]]
    end_next = (_date.fromisoformat(end) + timedelta(days=1)).isoformat()
    aq = {"org_id": org, "at": {"$lt": end_next, **({"$gte": start} if start else {})}}
    async for row in db.audit_log.find(aq, {"_id": 0}).sort("at", 1).limit(MAX_EXPORT_ROWS):
        audit_rows.append([_dmy(row.get("at")), row.get("action"), row.get("target_type"), row.get("target"),
                           row.get("actor_email"), row.get("actor_role")])

    sheets = [("Daybook", daybook), ("Journal lines", lines), ("Trial balance", tb), ("Profit and loss", pl),
              ("Chart of accounts", coa), ("Invoices", invoices), ("Receipts", receipts),
              ("Collections due", collections), ("Vendor bills", bills), ("Vendor payments", payments),
              ("Payroll", payroll), ("Expenses", expenses), ("Attachments index", attachments), ("Audit log", audit_rows)]
    fingerprints = []
    for name, rows in sheets:
        digest = hashlib.sha256(json.dumps(rows, ensure_ascii=False, default=str).encode("utf-8")).hexdigest()
        fingerprints.append([name, len(rows) - 1, digest])
    active = [e for e in journals if not e.get("voided_from_view")]
    manifest = [
        ["Field", "Value"],
        ["Company", org_name], ["Organisation ID", org], ["Schema", SCHEMA],
        ["Period from", _dmy(start) if start else "Beginning"], ["Period to", _dmy(end)],
        ["Generated at (IST)", _dmy(iso_now())], ["Generated by", user.get("email") or user.get("user_id")],
        ["Entries in period (all, incl. removed pairs)", len(journals)],
        ["Entries in books", len(active)],
        ["Total debit (books)", round(sum(float(l.get("debit") or 0) for e in active for l in e.get("lines") or []), 2)],
        ["Total credit (books)", round(sum(float(l.get("credit") or 0) for e in active for l in e.get("lines") or []), 2)],
        ["Net profit / (loss)", round(income - expense, 2)],
        ["Note", "Text cells are stored as text, never as formulas. Exporting does not delete anything."],
        [], ["Sheet", "Rows", "SHA-256 of sheet rows"], *fingerprints,
    ]
    return build_xlsx([("Manifest", manifest), *sheets]), {s[0]: s[1] for s in fingerprints}


async def _org_name() -> str:
    org = await db.organizations.find_one({"org_id": current_org_id() or "org_default"}, {"_id": 0, "name": 1})
    return (org or {}).get("name") or "Company"


# ----------------------------------------------------------------- routes
@router.get("/accounting/periods")
async def period_status(request: Request, session_token: Optional[str] = Cookie(default=None),
                        authorization: Optional[str] = Header(default=None)):
    user = _require_perm(await require_user(request, session_token, authorization), "finance.read")
    history = await sdb.period_closes.find({}, {"_id": 0}).sort("at", -1).to_list(50)
    return {"locked_through": await locked_through(), "history": history}


@router.get("/accounting/periods/check")
async def period_check(request: Request, fy: Optional[str] = None, from_date: Optional[str] = None,
                       to_date: Optional[str] = None, session_token: Optional[str] = Cookie(default=None),
                       authorization: Optional[str] = Header(default=None)):
    user = _require_perm(await require_user(request, session_token, authorization), "finance.create")
    start, end, _ = _range(fy, from_date, to_date)
    return await _checks(start, end)


@router.post("/accounting/periods/export")
async def period_export(request: Request, fy: Optional[str] = None, from_date: Optional[str] = None,
                        to_date: Optional[str] = None, session_token: Optional[str] = Cookie(default=None),
                        authorization: Optional[str] = Header(default=None)):
    user = _require_perm(await require_user(request, session_token, authorization), "finance.create")
    start, end, _ = _range(fy, from_date, to_date)
    data, counts = await _workbook(start, end, user, await _org_name())
    sha = hashlib.sha256(data).hexdigest()
    export_id = new_id("pex_")
    await sdb.period_exports.insert_one({
        "id": export_id, "from_date": start, "to_date": end, "sha256": sha, "bytes": len(data),
        "counts": counts, "at": iso_now(), "by": user["user_id"], "by_email": user.get("email")})
    await audit(user, "accounting.period.export", target=export_id, target_type="period_export",
                meta={"from": start, "to": end, "sha256": sha, "rows": counts})
    name = f"books-{start or 'start'}-to-{end}.xlsx"
    return Response(content=data, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": content_disposition("attachment", name),
                             "X-Export-Id": export_id, "X-Export-Sha256": sha,
                             "Access-Control-Expose-Headers": "X-Export-Id, X-Export-Sha256"})


@router.post("/accounting/periods/close")
async def period_close(payload: CloseIn, request: Request, session_token: Optional[str] = Cookie(default=None),
                       authorization: Optional[str] = Header(default=None)):
    user = _require_perm(await require_user(request, session_token, authorization), "*.*")
    through = _iso(payload.through_date, "Closing date")
    export = await sdb.period_exports.find_one({"id": payload.export_id}, {"_id": 0})
    if not export or export.get("to_date") != through:
        raise HTTPException(status_code=409, detail="Download the Excel export for this exact period first.")
    try:
        made = datetime.fromisoformat(str(export["at"]).replace("Z", "+00:00"))
        if made.tzinfo is None:
            made = made.replace(tzinfo=timezone.utc)
    except ValueError:
        made = datetime(2000, 1, 1, tzinfo=timezone.utc)
    if datetime.now(timezone.utc) - made > timedelta(days=EXPORT_VALID_DAYS):
        raise HTTPException(status_code=409, detail="That export is more than a week old. Download a fresh one first.")
    lock = await locked_through()
    start = export.get("from_date")
    if lock and start and start > (_date.fromisoformat(lock) + timedelta(days=1)).isoformat():
        raise HTTPException(status_code=409, detail=(
            f"The export starts on {_dmy(start)} but the books are closed only up to {_dmy(lock)}. "
            "Export from the day after the last closing so no days are left out."))
    report = await _checks(start, through)
    if not report["ok"]:
        raise HTTPException(status_code=409, detail="Fix these first: " + " ".join(b["message"] for b in report["blockers"]))
    if report["warnings"] and not payload.acknowledge_warnings:
        raise HTTPException(status_code=409, detail="Please read and accept the warnings before closing.")
    org = current_org_id() or "org_default"
    result = await db.organizations.update_one(
        {"org_id": org, "$or": [{"books_locked_through": {"$exists": False}}, {"books_locked_through": None},
                                {"books_locked_through": {"$lt": through}}]},
        {"$set": {"books_locked_through": through, "books_locked_at": iso_now(), "books_locked_by": user["user_id"]}})
    if not result.matched_count:
        raise HTTPException(status_code=409, detail="The books were closed by someone else meanwhile. Refresh and check.")
    row = {"id": new_id("pcl_"), "action": "close", "locked_through": through, "previous": lock,
           "from_date": start, "export_id": export["id"], "export_sha256": export.get("sha256"),
           "warnings": [w["message"] for w in report["warnings"]], "reason": payload.reason,
           "entries": report["entries"], "debit_total": report["debit_total"],
           "at": iso_now(), "by": user["user_id"], "by_name": user.get("name") or user.get("email")}
    await sdb.period_closes.insert_one(dict(row))
    await audit(user, "accounting.period.close", target=row["id"], target_type="period_close",
                meta={"locked_through": through, "previous": lock, "export_sha256": export.get("sha256")})
    return {"ok": True, "locked_through": through, "close": row}


@router.post("/accounting/periods/reopen")
async def period_reopen(payload: ReopenIn, request: Request, session_token: Optional[str] = Cookie(default=None),
                        authorization: Optional[str] = Header(default=None)):
    user = _require_perm(await require_user(request, session_token, authorization), "*.*")
    lock = await locked_through()
    if not lock:
        raise HTTPException(status_code=409, detail="No period is closed.")
    new_lock = _iso(payload.locked_through, "New closing date") if payload.locked_through else None
    if new_lock and new_lock >= lock:
        raise HTTPException(status_code=400, detail="To reopen, the new closing date must be earlier than the current one.")
    org = current_org_id() or "org_default"
    result = await db.organizations.update_one(
        {"org_id": org, "books_locked_through": lock},
        {"$set": {"books_locked_through": new_lock, "books_locked_at": iso_now(), "books_locked_by": user["user_id"]}})
    if not result.matched_count:
        raise HTTPException(status_code=409, detail="The closing date changed meanwhile. Refresh and check.")
    row = {"id": new_id("pcl_"), "action": "reopen", "locked_through": new_lock, "previous": lock,
           "reason": payload.reason.strip(), "at": iso_now(), "by": user["user_id"],
           "by_name": user.get("name") or user.get("email")}
    await sdb.period_closes.insert_one(dict(row))
    await audit(user, "accounting.period.reopen", target=row["id"], target_type="period_close",
                meta={"from": lock, "to": new_lock, "reason": row["reason"]})
    return {"ok": True, "locked_through": new_lock, "reopen": row}
