"""Accounting & Finance routes — double-entry bookkeeping.

Core primitives:
- `accounts` collection: Chart of Accounts (assets/liabilities/income/expense/equity)
- `journal_entries` collection: every financial event lands here (one entry ⇒ N lines
  where SUM(debit) == SUM(credit))
- `payment_milestones`, `vendors_acc` collections for project payment plan + vendor master
- Convenience wrappers: `POST /accounting/income` and `/expense` auto-build a balanced
  journal entry so users don't have to think in DR/CR.
- Everything flows into ledgers + reports derived on-read (no denormalized totals).

Feeds the Finance Dashboard, Client/Project/Vendor ledgers, P&L, Trial Balance,
GST/TDS aggregations.
"""
from fastapi import APIRouter, HTTPException, Request, Cookie, Header, Depends
from typing import Optional
from datetime import date as _date, timedelta
import math
import re
import hashlib

from core.db import db
from core.scoped_db import current_org_id, sdb
from core.helpers import business_today, now_utc, iso_now, new_id
from core.deps import require_user
from core.downloads import content_disposition
from core.rbac import has_permission
from core.tenancy import user_org_id
from core.audit import audit
from core.locks import doc_lock
from models.base import FiniteModel
from pymongo.errors import DuplicateKeyError
from core.finance import (
    resolve_period, current_fy_label, fy_choices, fy_range, require_asset_account,
)
from models.accounting import (
    AccountIn, JournalIn, IncomeIn, ExpenseIn, NonOperatingTransactionIn,
    MilestoneIn, MilestoneUpdate, OtherReceivableIn, OtherReceivableUpdate,
    CollectionReceiptIn,
    ACCOUNT_TYPES, DEFAULT_COA, PAYMENT_METHODS,
)


# Router-level RBAC — every accounting route requires finance.read.
async def _require_finance_read(
    request: Request,
    session_token: Optional[str] = Cookie(default=None),
    authorization: Optional[str] = Header(default=None),
):
    user = await require_user(request, session_token, authorization)
    if not has_permission(user, "finance.read"):
        raise HTTPException(status_code=403, detail="Missing permission: finance.read")
    return user


router = APIRouter(dependencies=[Depends(_require_finance_read)])


def _linked_journal_key(org_id: str, source: str, source_id: Optional[str]) -> Optional[str]:
    if not source_id or source == "manual":
        return None
    return f"{org_id}:{source}:{source_id}"


def _require_full_linked_payment(kind: str, actual: float, expected: float) -> None:
    actual = round(float(actual), 2)
    expected = round(float(expected), 2)
    if actual != expected:
        raise HTTPException(
            status_code=400,
            detail=f"Linked {kind} payment must equal the {kind} amount ({expected:.2f})",
        )


def _cash_collection_source(source: str) -> bool:
    base = source[:-9] if source.endswith("_reversal") else source
    return base in {"income", "invoice_payment", "milestone_payment", "commission_income"}


def _milestone_due_bucket(due_date: Optional[str], today: _date,
                          horizon: _date) -> str:
    """Classify an unpaid project milestone for the collections dashboard."""
    if not due_date:
        return "no_due_date"
    try:
        due = _date.fromisoformat(due_date)
    except (TypeError, ValueError):
        return "no_due_date"
    if due < today:
        return "overdue"
    if due <= horizon:
        return "due_30"
    return "later"


def _collection_status(due_date: Optional[str], amount: float, received: float,
                       today: _date, horizon: _date) -> str:
    """One status vocabulary for every Money In source."""
    amount = round(max(0.0, float(amount or 0)), 2)
    received = round(max(0.0, float(received or 0)), 2)
    if amount > 0 and received + 0.01 >= amount:
        return "received"
    if received > 0:
        return "partially_received"
    if not due_date:
        return "no_due_date"
    try:
        due = _date.fromisoformat(due_date)
    except (TypeError, ValueError):
        return "no_due_date"
    if due < today:
        return "overdue"
    if due == today:
        return "due_today"
    if due <= horizon:
        return "upcoming"
    return "later"


# ==================================================
# Chart of Accounts
# ==================================================
def _default_account_id(org_id: str, name: str) -> str:
    digest = hashlib.sha256(f"{org_id}:{name.casefold()}".encode("utf-8")).hexdigest()[:20]
    return f"acc_default_{digest}"


async def _seed_coa_if_empty():
    """Idempotent seed — inserts only the DEFAULT_COA accounts that are missing.
    Runs on every /accounts fetch so newly-shipped default accounts (e.g. new
    income categories) show up on existing installations without a migration."""
    existing_names = {a["name"] async for a in sdb.accounts.find({}, {"_id": 0, "name": 1})}
    org_id = current_org_id() or "org_default"
    for name, typ, code in DEFAULT_COA:
        if name in existing_names:
            continue
        account_id = _default_account_id(org_id, name)
        try:
            await sdb.accounts.update_one(
                {"id": account_id},
                {"$setOnInsert": {
                    "id": account_id,
                    "name": name,
                    "type": typ,
                    "code": code,
                    "is_bank": name.lower().startswith("bank") or name.lower() in ("cash", "petty cash"),
                    "opening_balance": 0.0,
                    "active": True,
                    "created_at": iso_now(),
                    "seeded": True,
                }},
                upsert=True,
            )
        except DuplicateKeyError:
            # A concurrent first request inserted the same deterministic account.
            pass


@router.get("/accounts")
async def list_accounts(request: Request,
                        type: Optional[str] = None,
                        include_inactive: bool = False,
                        include_balances: bool = False,
                        session_token: Optional[str] = Cookie(default=None),
                        authorization: Optional[str] = Header(default=None)):
    """List accounts. By default only active accounts are returned so
    stale/unused accounts don't clutter dropdowns. Set `include_inactive=1`
    on the Chart of Accounts screen to also see deactivated accounts."""
    await require_user(request, session_token, authorization)
    await _seed_coa_if_empty()
    q: dict = {} if include_inactive else {"active": {"$ne": False}}
    if type: q["type"] = type
    rows = await sdb.accounts.find(q, {"_id": 0}).sort("code", 1).to_list(1000)
    if include_balances and rows:
        account_ids = [row["id"] for row in rows]
        movements = await sdb.journal_entries.aggregate([
            {"$unwind": "$lines"},
            {"$match": {"lines.account_id": {"$in": account_ids}}},
            {"$group": {
                "_id": "$lines.account_id",
                "debit": {"$sum": "$lines.debit"},
                "credit": {"$sum": "$lines.credit"},
            }},
        ]).to_list(len(account_ids))
        by_id = {item["_id"]: item for item in movements}
        for row in rows:
            movement = by_id.get(row["id"], {})
            opening = float(row.get("opening_balance") or 0)
            row["current_balance"] = round(
                opening + _movement_for(
                    row["type"],
                    float(movement.get("debit") or 0),
                    float(movement.get("credit") or 0),
                ),
                2,
            )
    return rows


@router.post("/accounts")
async def create_account(payload: AccountIn, request: Request,
                         session_token: Optional[str] = Cookie(default=None),
                         authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    if not has_permission(user, "finance.create"):
        raise HTTPException(status_code=403, detail="Missing permission: finance.create")
    if payload.type not in ACCOUNT_TYPES:
        raise HTTPException(status_code=400, detail="Invalid account type")
    doc = payload.model_dump()
    doc["name"] = doc["name"].strip()
    if not doc["name"]:
        raise HTTPException(status_code=400, detail="Account name is required")
    duplicate = await sdb.accounts.find_one(
        {"name": {"$regex": f"^{re.escape(doc['name'])}$", "$options": "i"}},
        {"_id": 0, "id": 1},
    )
    if duplicate:
        raise HTTPException(status_code=409, detail="An account with this name already exists")
    if doc.get("code"):
        doc["code"] = str(doc["code"]).strip()
        if await sdb.accounts.find_one(
            {"code": doc["code"], "active": {"$ne": False}}, {"_id": 0, "id": 1}
        ):
            raise HTTPException(status_code=409, detail="This account code is already in use")
    opening = float(doc.get("opening_balance") or 0)
    if not math.isfinite(opening):
        raise HTTPException(status_code=400, detail="Opening balance must be finite")
    doc["opening_balance"] = round(opening, 2)
    doc["id"] = new_id("acc_")
    doc["created_at"] = iso_now()
    doc["created_by"] = user["user_id"]
    doc.setdefault("active", True)
    doc.setdefault("opening_balance", 0.0)
    # Auto-assign next code within the account type if not provided.
    if not doc.get("code"):
        doc["code"] = await _next_account_code(doc["type"])
    await sdb.accounts.insert_one(dict(doc))
    return await sdb.accounts.find_one({"id": doc["id"]}, {"_id": 0})


@router.patch("/accounts/{acc_id}")
async def update_account(acc_id: str, payload: AccountIn, request: Request,
                         session_token: Optional[str] = Cookie(default=None),
                         authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    if not has_permission(user, "finance.update"):
        raise HTTPException(status_code=403, detail="Missing permission: finance.update")
    existing = await sdb.accounts.find_one({"id": acc_id}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Account not found")
    upd = {k: v for k, v in payload.model_dump().items() if v is not None}
    if upd.get("type") not in ACCOUNT_TYPES:
        raise HTTPException(status_code=400, detail="Invalid account type")
    upd["name"] = upd["name"].strip()
    if not upd["name"]:
        raise HTTPException(status_code=400, detail="Account name is required")
    duplicate = await sdb.accounts.find_one(
        {"id": {"$ne": acc_id},
         "name": {"$regex": f"^{re.escape(upd['name'])}$", "$options": "i"}},
        {"_id": 0, "id": 1},
    )
    if duplicate:
        raise HTTPException(status_code=409, detail="An account with this name already exists")
    if upd.get("code"):
        upd["code"] = str(upd["code"]).strip()
        if await sdb.accounts.find_one(
            {"id": {"$ne": acc_id}, "code": upd["code"], "active": {"$ne": False}},
            {"_id": 0, "id": 1},
        ):
            raise HTTPException(status_code=409, detail="This account code is already in use")
    opening = float(upd.get("opening_balance") or 0)
    if not math.isfinite(opening):
        raise HTTPException(status_code=400, detail="Opening balance must be finite")
    upd["opening_balance"] = round(opening, 2)
    has_activity = await sdb.journal_entries.find_one(
        {"lines.account_id": acc_id}, {"_id": 0, "id": 1})
    if has_activity:
        if upd.get("type") != existing.get("type"):
            raise HTTPException(
                status_code=409,
                detail="Account type cannot change after journal activity exists",
            )
        if upd["opening_balance"] != round(float(existing.get("opening_balance") or 0), 2):
            raise HTTPException(
                status_code=409,
                detail="Opening balance cannot change after journal activity exists; post a documented adjustment instead",
            )
    upd["updated_at"] = iso_now()
    upd["updated_by"] = user["user_id"]
    await sdb.accounts.update_one({"id": acc_id}, {"$set": upd})
    await audit(
        user, "account.update", target=acc_id, target_type="account",
        meta={"fields": [key for key in upd if key not in {"updated_at", "updated_by"}]},
        org_id=user_org_id(user),
    )
    return await sdb.accounts.find_one({"id": acc_id}, {"_id": 0})


@router.delete("/accounts/{acc_id}")
async def deactivate_account(acc_id: str, request: Request,
                             session_token: Optional[str] = Cookie(default=None),
                             authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    if not has_permission(user, "finance.delete"):
        raise HTTPException(status_code=403, detail="Missing permission: finance.delete")
    # Soft delete — audit-safe
    await sdb.accounts.update_one({"id": acc_id}, {"$set": {"active": False, "deactivated_at": iso_now()}})
    return {"ok": True}


async def _next_account_code(acc_type: str) -> str:
    """Return the next unused account code within a type's numeric range.

    Uses the type's 1000-block: asset 1xxx, liability 2xxx, income 3xxx,
    expense 4xxx, equity 5xxx. Falls back to the highest existing code in
    the tenant + 1 so codes stay monotonically increasing.
    """
    prefix = {"asset": 1, "liability": 2, "income": 3, "expense": 4, "equity": 5}.get(acc_type, 9)
    low = prefix * 1000
    high = low + 999
    max_code = low
    async for a in sdb.accounts.find({"type": acc_type}, {"_id": 0, "code": 1}):
        try:
            c = int(a.get("code") or 0)
            if low <= c <= high and c > max_code:
                max_code = c
        except (TypeError, ValueError):
            continue
    return str(max_code + 1 if max_code >= low else low + 1)


# ==================================================
# Journal entries (double-entry, source of truth)
# ==================================================
async def default_receipt_accounts():
    """Resolve (bank_account, income_account) for auto-posted receipts.
    Tenant-scoped via sdb. Seeds the default COA if the org has none."""
    await _seed_coa_if_empty()
    bank = await sdb.accounts.find_one(
        {"type": "asset", "active": {"$ne": False},
         "name": {"$regex": "bank", "$options": "i"}}, {"_id": 0})
    if not bank:
        bank = await sdb.accounts.find_one(
            {"type": "asset", "active": {"$ne": False},
             "name": {"$regex": "cash", "$options": "i"}}, {"_id": 0})
    income = await sdb.accounts.find_one(
        {"type": "income", "active": {"$ne": False},
         "name": {"$regex": "design|professional|consult", "$options": "i"}}, {"_id": 0})
    if not income:
        income = await sdb.accounts.find_one(
            {"type": "income", "active": {"$ne": False}}, {"_id": 0})
    return bank, income


async def _invoice_accrual_accounts():
    """Resolve the control accounts used when an invoice is issued."""
    await _seed_coa_if_empty()
    receivable = await sdb.accounts.find_one(
        {"name": "Accounts Receivable", "type": "asset", "active": {"$ne": False}},
        {"_id": 0},
    )
    gst_payable = await sdb.accounts.find_one(
        {"name": "GST Payable", "type": "liability", "active": {"$ne": False}},
        {"_id": 0},
    )
    _bank, income = await default_receipt_accounts()
    return receivable, income, gst_payable


def _invoice_accrual_amounts(invoice: dict) -> tuple[float, float, float]:
    total = round(float(invoice.get("total") or 0), 2)
    tax = round(float(invoice.get("tax") or 0), 2)
    subtotal = round(float(invoice.get("subtotal") or (total - tax)), 2)
    if total <= 0 or subtotal < 0 or tax < 0 or round(subtotal + tax, 2) != total:
        raise HTTPException(status_code=400, detail="Invoice totals are invalid for accounting")
    return subtotal, tax, total


async def post_invoice_accrual_je(user: dict, invoice: dict) -> dict:
    """Recognise an issued invoice once, without touching cash."""
    invoice_id = invoice.get("id")
    existing = await sdb.journal_entries.find_one(
        {"source": "invoice_issue", "source_id": invoice_id,
         "reversed": {"$ne": True}}, {"_id": 0})
    if existing:
        return existing

    receivable, income, gst_payable = await _invoice_accrual_accounts()
    if not receivable or not income:
        raise HTTPException(status_code=409, detail="Invoice accounting accounts are unavailable")
    subtotal, tax, total = _invoice_accrual_amounts(invoice)
    if tax > 0 and not gst_payable:
        raise HTTPException(status_code=409, detail="GST Payable account is unavailable")

    lines = [
        {"account_id": receivable["id"], "debit": total, "credit": 0,
         "description": "Invoice receivable"},
        {"account_id": income["id"], "debit": 0, "credit": subtotal,
         "description": "Invoice revenue"},
    ]
    if tax > 0:
        lines.append({"account_id": gst_payable["id"], "debit": 0, "credit": tax,
                      "description": "Output GST"})
    return await _post_journal(
        user,
        invoice.get("issue_date") or business_today().isoformat(),
        f"Invoice {invoice.get('number') or invoice_id} issued"
        + (f" - {invoice.get('client_name')}" if invoice.get("client_name") else ""),
        lines,
        reference=invoice.get("number"), project_id=invoice.get("project_id"),
        client_id=invoice.get("client_id"), source="invoice_issue", source_id=invoice_id,
    )


async def reverse_invoice_accrual_je(user: dict, invoice: dict) -> Optional[dict]:
    """Reverse invoice recognition while retaining the immutable journal trail."""
    return await reverse_receipt_je(
        user, source="invoice_issue", source_id=invoice.get("id"),
        narration=f"Invoice {invoice.get('number') or invoice.get('id')} issue reversed",
        reset_source=False,
    )


async def post_receipt_je(user: dict, *, amount: float, date: str, narration: str,
                          source: str, source_id: str, reference: str = None,
                          project_id: str = None, client_id: str = None) -> Optional[dict]:
    """Post a receipt once; issued invoices settle A/R, legacy flows credit income."""
    existing = await sdb.journal_entries.find_one(
        {"source": source, "source_id": source_id, "reversed": {"$ne": True}}, {"_id": 0})
    if existing:
        return existing
    bank, credit_account = await default_receipt_accounts()
    if source == "invoice_payment":
        active_accrual = await sdb.journal_entries.find_one(
            {"source": "invoice_issue", "source_id": source_id,
             "reversed": {"$ne": True}}, {"_id": 0, "id": 1})
        if active_accrual:
            credit_account = await sdb.accounts.find_one(
                {"name": "Accounts Receivable", "type": "asset",
                 "active": {"$ne": False}}, {"_id": 0})
    if not bank or not credit_account:
        return None
    lines = [
        {"account_id": bank["id"], "debit": amount, "credit": 0, "description": "Received"},
        {"account_id": credit_account["id"], "debit": 0, "credit": amount,
         "description": "Accounts receivable settled" if source == "invoice_payment" and
         credit_account.get("name") == "Accounts Receivable" else "Revenue"},
    ]
    return await _post_journal(user, date, narration, lines, reference=reference,
                               project_id=project_id, client_id=client_id,
                               source=source, source_id=source_id)


async def reverse_receipt_je(user: dict, *, source: str, source_id: str,
                             narration: str,
                             reset_source: bool = True) -> Optional[dict]:
    """Post a balanced reversing JE for a previously auto-posted receipt
    (e.g. invoice un-marked as paid). Idempotent.

    Also — critically — resets the source invoice/milestone back to
    Unpaid/Pending and clears its `journal_id` so the source document
    matches the accounting. Pass `reset_source=False` if the caller has
    already handled the source reset itself.
    """
    originals = await sdb.journal_entries.find(
        {"source": source, "source_id": source_id, "reversed": {"$ne": True}},
        {"_id": 0}).sort("date", 1).to_list(5000)
    if not originals:
        # Even if there's no active JE, still make sure source status/journal_id
        # is cleaned up (idempotent safety net).
        if reset_source:
            await _reset_source_after_reversal(source, source_id)
        return None
    reversals = []
    for orig in originals:
        rev_lines = [
            {"account_id": line["account_id"], "debit": line["credit"],
             "credit": line["debit"],
             "description": f"Reversal · {line.get('description') or ''}".strip()}
            for line in orig["lines"]
        ]
        rev = await _post_journal(
            user, business_today().isoformat(), narration, rev_lines,
            reference=orig.get("reference"), project_id=orig.get("project_id"),
            client_id=orig.get("client_id"), source=f"{source}_reversal",
            source_id=orig["id"])
        await sdb.journal_entries.update_one(
            {"id": orig["id"]}, {
                "$set": {"reversed": True, "reversal_je_id": rev["id"],
                         "reversed_at": iso_now(), "reversed_by": user["user_id"]},
                "$unset": {"idempotency_key": ""},
            })
        reversals.append(rev)
    if reset_source:
        await _reset_source_after_reversal(source, source_id)
    return reversals[-1] if reversals else None


async def _reset_source_after_reversal(source: str, source_id: str):
    """Reset the source document (invoice / milestone) after a payment reversal.

    Marks it back to Unpaid/Pending and clears the linked `journal_id`. Idempotent —
    safe to call even when the source has already been reset."""
    if not source or not source_id:
        return
    if source == "invoice_payment":
        invoice = await sdb.invoices.find_one({"id": source_id}, {"_id": 0})
        if not invoice:
            return
        active = await sdb.journal_entries.find(
            {"source": source, "source_id": source_id, "reversed": {"$ne": True}},
            {"_id": 0, "id": 1, "total": 1}).to_list(5000)
        received = round(sum(float(row.get("total") or 0) for row in active), 2)
        total = float(invoice.get("total") or 0)
        status = "paid" if total > 0 and received + 0.01 >= total \
            else "partially_paid" if received > 0 else "sent"
        await sdb.invoices.update_one(
            {"id": source_id},
            {"$set": {"status": status, "paid_amount": received,
                      "paid_date": invoice.get("paid_date") if received > 0 else None,
                      "journal_id": active[-1]["id"] if active else None,
                      "updated_at": iso_now()}},
        )
    elif source == "milestone_payment":
        milestone = await sdb.payment_milestones.find_one({"id": source_id}, {"_id": 0})
        if not milestone:
            return
        active = await sdb.journal_entries.find(
            {"source": source, "source_id": source_id, "reversed": {"$ne": True}},
            {"_id": 0, "id": 1, "total": 1}).to_list(5000)
        received = round(sum(float(row.get("total") or 0) for row in active), 2)
        amount = float(milestone.get("amount") or 0)
        status = "paid" if amount > 0 and received + 0.01 >= amount \
            else "invoiced" if received > 0 else "pending"
        await sdb.payment_milestones.update_one(
            {"id": source_id},
            {"$set": {"status": status, "paid_amount": received,
                      "paid_at": milestone.get("paid_at") if received > 0 else None,
                      "journal_id": active[-1]["id"] if active else None,
                      "updated_at": iso_now()}},
        )


async def _post_journal(user: dict, date: str, narration: str, lines: list,
                        reference: str = None, project_id: str = None,
                        client_id: str = None, vendor_id: str = None,
                        employee_id: str = None,
                        source: str = "manual", source_id: str = None,
                        idempotency_suffix: str = None) -> dict:
    """Persist a balanced journal entry. `lines` = [{account_id, debit, credit, description}, ...]"""
    try:
        _date.fromisoformat(date)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Journal date must be YYYY-MM-DD")
    if not str(narration or "").strip():
        raise HTTPException(status_code=400, detail="Journal narration is required")
    if len(lines or []) < 2:
        raise HTTPException(status_code=400, detail="Journal must contain at least two lines")

    for line in lines:
        if not line.get("account_id"):
            raise HTTPException(status_code=400, detail="Every journal line requires an account")
        try:
            debit = float(line.get("debit") or 0)
            credit = float(line.get("credit") or 0)
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="Journal amounts must be numbers")
        if not math.isfinite(debit) or not math.isfinite(credit):
            raise HTTPException(status_code=400, detail="Journal amounts must be finite")
        if debit < 0 or credit < 0:
            raise HTTPException(status_code=400, detail="Journal amounts cannot be negative")
        if (debit > 0) == (credit > 0):
            raise HTTPException(
                status_code=400,
                detail="Each journal line must contain exactly one positive debit or credit",
            )

    total_debit = round(sum(float(l.get("debit") or 0) for l in lines), 2)
    total_credit = round(sum(float(l.get("credit") or 0) for l in lines), 2)
    if total_debit != total_credit:
        raise HTTPException(status_code=400,
                            detail=f"Journal not balanced: debit={total_debit} credit={total_credit}")
    if total_debit == 0:
        raise HTTPException(status_code=400, detail="Journal amount is zero")

    # Attach account meta to each line for read-optimised ledgers
    acc_ids = list({l["account_id"] for l in lines})
    accs = {a["id"]: a async for a in sdb.accounts.find({"id": {"$in": acc_ids}}, {"_id": 0})}
    resolved_lines = []
    for l in lines:
        acc = accs.get(l["account_id"])
        if not acc or acc.get("active") is False:
            raise HTTPException(status_code=400, detail=f"Unknown account_id: {l['account_id']}")
        resolved_lines.append({
            "account_id": l["account_id"],
            "account_name": acc["name"],
            "account_type": acc["type"],
            "debit": float(l.get("debit") or 0),
            "credit": float(l.get("credit") or 0),
            "description": l.get("description") or "",
        })

    doc = {
        "id": new_id("je_"),
        "date": date,
        "narration": narration.strip(),
        "reference": reference,
        "project_id": project_id,
        "client_id": client_id,
        "vendor_id": vendor_id,
        "employee_id": employee_id,
        "source": source,          # manual | income | expense | payroll | invoice
        "source_id": source_id,
        "total": total_debit,
        "lines": resolved_lines,
        "created_at": iso_now(),
        "created_by": user["user_id"],
        "created_by_name": user.get("name"),
    }
    idempotency_key = _linked_journal_key(
        user_org_id(user) or "org_default", source, source_id)
    if idempotency_key and idempotency_suffix:
        # Parent records with many legitimate postings (loan EMIs) key each
        # posting individually while keeping source_id = parent id.
        idempotency_key = f"{idempotency_key}:{idempotency_suffix}"
    if idempotency_key:
        doc["idempotency_key"] = idempotency_key
    try:
        await sdb.journal_entries.insert_one(dict(doc))
    except DuplicateKeyError:
        raise HTTPException(
            status_code=409,
            detail="This linked transaction has already been posted.",
        )
    return await sdb.journal_entries.find_one({"id": doc["id"]}, {"_id": 0})


@router.post("/journal-entries")
async def create_journal(payload: JournalIn, request: Request,
                         session_token: Optional[str] = Cookie(default=None),
                         authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    if not has_permission(user, "finance.create"):
        raise HTTPException(status_code=403, detail="Missing permission: finance.create")
    lines = [l.model_dump() for l in payload.lines]
    return await _post_journal(
        user, payload.date, payload.narration, lines,
        reference=payload.reference, project_id=payload.project_id,
        client_id=payload.client_id, vendor_id=payload.vendor_id,
        employee_id=payload.employee_id,
    )


def _party_ledger_name(prefix: str, party_name: Optional[str]) -> str:
    party = " ".join(str(party_name or "").split())
    if len(party) < 2:
        raise HTTPException(status_code=400, detail="Person or party name is required")
    return f"{prefix} - {party}"


async def _ensure_named_account(
    name: str, account_type: str, *, create_if_missing: bool = True
) -> dict:
    existing = await sdb.accounts.find_one(
        {"name": {"$regex": f"^{re.escape(name)}$", "$options": "i"},
         "active": {"$ne": False}},
        {"_id": 0},
    )
    if existing:
        if existing.get("type") != account_type:
            raise HTTPException(
                status_code=409,
                detail=f"{name} already exists with account type {existing.get('type')}",
            )
        return existing

    inactive = await sdb.accounts.find_one(
        {"name": {"$regex": f"^{re.escape(name)}$", "$options": "i"}}, {"_id": 0}
    )
    if inactive:
        raise HTTPException(status_code=409, detail=f"{name} is inactive; restore it first")
    if not create_if_missing:
        raise HTTPException(status_code=404, detail=f"No outstanding ledger exists for {name}")

    org_id = current_org_id() or "org_default"
    account_id = _default_account_id(org_id, name)
    try:
        await sdb.accounts.update_one(
            {"id": account_id},
            {"$setOnInsert": {
                "id": account_id,
                "name": name,
                "type": account_type,
                "code": await _next_account_code(account_type),
                "is_bank": False,
                "opening_balance": 0.0,
                "active": True,
                "created_at": iso_now(),
                "system_generated": True,
            }},
            upsert=True,
        )
    except DuplicateKeyError:
        pass
    account = await sdb.accounts.find_one({"id": account_id}, {"_id": 0})
    if not account:
        account = await sdb.accounts.find_one(
            {"name": {"$regex": f"^{re.escape(name)}$", "$options": "i"}}, {"_id": 0}
        )
    if not account:
        raise HTTPException(status_code=409, detail="Could not create the required ledger account")
    return account


async def _current_account_balance(account: dict) -> float:
    movement = await sdb.journal_entries.aggregate([
        {"$unwind": "$lines"},
        {"$match": {"lines.account_id": account["id"]}},
        {"$group": {
            "_id": None,
            "debit": {"$sum": "$lines.debit"},
            "credit": {"$sum": "$lines.credit"},
        }},
    ]).to_list(1)
    totals = movement[0] if movement else {}
    return round(
        float(account.get("opening_balance") or 0)
        + _movement_for(
            account["type"],
            float(totals.get("debit") or 0),
            float(totals.get("credit") or 0),
        ),
        2,
    )


@router.post("/accounting/non-operating")
async def create_non_operating_transaction(
    payload: NonOperatingTransactionIn,
    request: Request,
    session_token: Optional[str] = Cookie(default=None),
    authorization: Optional[str] = Header(default=None),
):
    """Post common balance-sheet movements without exposing debit/credit mechanics."""
    user = await require_user(request, session_token, authorization)
    if not has_permission(user, "finance.create"):
        raise HTTPException(status_code=403, detail="Missing permission: finance.create")

    bank = await require_asset_account(payload.bank_account_id, "Cash/bank account")
    if not bank.get("is_bank") and bank.get("name") not in {"Cash", "Petty Cash"}:
        raise HTTPException(status_code=400, detail="Select an actual cash or bank account")
    await _seed_coa_if_empty()

    amount = round(float(payload.amount), 2)
    kind = payload.kind
    if kind == "owner_investment":
        counter = await _ensure_named_account("Owner Capital", "equity")
        debit_account, credit_account = bank, counter
        narration = "Capital introduced by owner"
    elif kind == "owner_withdrawal":
        counter = await _ensure_named_account("Owner Drawings", "equity")
        debit_account, credit_account = counter, bank
        narration = "Personal withdrawal by owner"
    elif kind == "gold_purchase":
        counter = await _ensure_named_account("Investments - Gold", "asset")
        debit_account, credit_account = counter, bank
        narration = "Gold investment purchased"
    elif kind in {"money_given", "repayment_received"}:
        name = _party_ledger_name("Advance to", payload.party_name)
        counter = await _ensure_named_account(
            name, "asset", create_if_missing=kind == "money_given"
        )
        debit_account, credit_account = (
            (counter, bank) if kind == "money_given" else (bank, counter)
        )
        narration = (
            f"Money given to {payload.party_name.strip()}"
            if kind == "money_given"
            else f"Repayment received from {payload.party_name.strip()}"
        )
    else:
        name = _party_ledger_name("Loan from", payload.party_name)
        counter = await _ensure_named_account(
            name, "liability", create_if_missing=kind == "money_received"
        )
        debit_account, credit_account = (
            (bank, counter) if kind == "money_received" else (counter, bank)
        )
        narration = (
            f"Money received from {payload.party_name.strip()}"
            if kind == "money_received"
            else f"Repayment paid to {payload.party_name.strip()}"
        )

    if kind in {"repayment_received", "repayment_paid"}:
        outstanding = await _current_account_balance(counter)
        if amount > outstanding + 0.009:
            raise HTTPException(
                status_code=409,
                detail=f"Repayment exceeds the outstanding balance of {outstanding:.2f}",
            )

    if payload.notes and payload.notes.strip():
        narration = f"{narration} - {payload.notes.strip()}"
    journal = await _post_journal(
        user,
        payload.date,
        narration,
        [
            {"account_id": debit_account["id"], "debit": amount, "credit": 0,
             "description": narration},
            {"account_id": credit_account["id"], "debit": 0, "credit": amount,
             "description": narration},
        ],
        reference=payload.reference,
        source="non_operating",
    )
    await audit(
        user,
        "accounting.non_operating.create",
        target=journal["id"],
        target_type="journal_entry",
        meta={"kind": kind, "amount": amount, "counter_account_id": counter["id"]},
        org_id=user_org_id(user),
    )
    return {"journal": journal, "counter_account": counter}


@router.get("/journal-entries")
async def list_journal(request: Request,
                       from_date: Optional[str] = None, to_date: Optional[str] = None,
                       fy: Optional[str] = None,
                       account_id: Optional[str] = None,
                       project_id: Optional[str] = None,
                       client_id: Optional[str] = None,
                       vendor_id: Optional[str] = None,
                       employee_id: Optional[str] = None,
                       source: Optional[str] = None,
                       include_related: bool = False,
                       q: Optional[str] = None,
                       limit: int = 200,
                       offset: int = 0,
                       session_token: Optional[str] = Cookie(default=None),
                       authorization: Optional[str] = Header(default=None)):
    """List journal entries with rich filters + pagination.

    Filters: date range (or FY), account, project, client, vendor, employee,
    source, and a free-text `q` that matches narration/reference/account name.
    Pagination via offset/limit (default 200, max 500) — returns
    `{items, total, limit, offset}` so the UI can page through arbitrarily
    large books. When no pagination params are supplied and total <= 500
    we return the raw array to stay backward-compatible with legacy callers.
    """
    await require_user(request, session_token, authorization)
    fd, td, _ = resolve_period(fy, from_date, to_date)
    query: dict = {"voided_from_view": {"$ne": True}}
    if fd or td:
        d = {}
        if fd: d["$gte"] = fd
        if td: d["$lte"] = td
        query["date"] = d
    if account_id: query["lines.account_id"] = account_id
    if project_id:
        # Support commission-multi-project JEs which store project_ids array
        query["$or"] = [{"project_id": project_id}, {"project_ids": project_id}]
    if client_id: query["client_id"] = client_id
    if vendor_id: query["vendor_id"] = vendor_id
    if employee_id: query["employee_id"] = employee_id
    if source:
        if include_related and source in {"income", "expense"}:
            query["source"] = {"$in": [source, f"{source}_reversal", f"{source}_reinstatement"]}
        else:
            query["source"] = source
    if q:
        needle = q.strip()
        if needle:
            regex = {"$regex": needle, "$options": "i"}
            # Match narration, reference, or any line's account_name/description
            _or = [
                {"narration": regex}, {"reference": regex},
                {"lines.account_name": regex},
                {"lines.description": regex},
            ]
            if "$or" in query:
                query = {"$and": [query, {"$or": _or}]}
            else:
                query["$or"] = _or

    limit = max(1, min(int(limit or 200), 500))
    offset = max(0, int(offset or 0))
    paginated = (offset > 0) or (limit != 200)

    total = None
    if paginated:
        total = await sdb.journal_entries.count_documents(query)

    rows = await sdb.journal_entries.find(query, {"_id": 0}) \
        .sort("date", -1).skip(offset).limit(limit).to_list(limit)

    if paginated:
        return {"items": rows, "total": total or 0, "limit": limit, "offset": offset}
    return rows


# ==================================================
# Single transaction: view / edit / delete / reverse
# ==================================================
class JournalEditIn(FiniteModel):
    date: Optional[str] = None
    narration: Optional[str] = None
    reference: Optional[str] = None
    amount: Optional[float] = None


class JournalCorrectionIn(FiniteModel):
    date: str
    narration: str
    reference: Optional[str] = None
    amount: float


def _can_void_from_journal(je: dict) -> bool:
    """Return whether a journal can be cancelled without orphaning its source record."""
    source = je.get("source") or "manual"
    if source in {"invoice_issue"} or source.endswith(("_reversal", "_reinstatement")):
        return False
    if not je.get("source_id"):
        return source in {"manual", "income", "expense", "non_operating"}
    return source in {"invoice_payment", "milestone_payment", "other_receivable_income"}


async def _sync_other_receivable_after_reversal(journal_entry_id: str) -> None:
    """Keep a manual collection reminder aligned with its reversed receipt."""
    receipt = await sdb.collection_receipts.find_one(
        {"journal_entry_id": journal_entry_id}, {"_id": 0})
    if not receipt or receipt.get("status") == "reversed":
        return
    changed_at = iso_now()
    await sdb.collection_receipts.update_one(
        {"id": receipt["id"]},
        {"$set": {"status": "reversed", "reversed_at": changed_at}},
    )
    source_id = receipt.get("source_id")
    if not source_id:
        return
    active = await sdb.collection_receipts.find(
        {"source_id": source_id, "source_type": "other_receivable",
         "status": "received"},
        {"_id": 0, "amount": 1, "date": 1},
    ).to_list(5000)
    received = round(sum(float(row.get("amount") or 0) for row in active), 2)
    source = await sdb.collection_receivables.find_one(
        {"id": source_id}, {"_id": 0, "amount": 1})
    if not source:
        return
    amount = float(source.get("amount") or 0)
    status = ("received" if amount > 0 and received + 0.01 >= amount
              else "partially_received" if received > 0 else "pending")
    await sdb.collection_receivables.update_one(
        {"id": source_id},
        {"$set": {"received_amount": received, "status": status,
                  "last_received_at": max((row.get("date") or "" for row in active),
                                          default=None),
                  "updated_at": changed_at}},
    )


async def _reverse_journal_entry(user: dict, je: dict, *, action: str = "reverse",
                                 reversal_date: Optional[str] = None,
                                 hide_from_books: bool = False) -> dict:
    """Create the balancing entry used by Reverse, Delete and Correct."""
    if je.get("reversed"):
        raise HTTPException(status_code=409, detail="This transaction has already been reversed.")
    source = je.get("source") or "manual"
    if source.endswith(("_reversal", "_reinstatement")):
        raise HTTPException(
            status_code=409,
            detail="You cannot directly reverse a system reversal/reinstatement entry.",
        )
    if source == "invoice_issue":
        raise HTTPException(
            status_code=409,
            detail="Change the invoice to Draft or Cancelled so its receivable is reversed safely.",
        )

    rev_lines = [
        {
            "account_id": line["account_id"],
            "debit": line.get("credit") or 0,
            "credit": line.get("debit") or 0,
            "description": f"Reversal · {line.get('description') or ''}".strip(),
        }
        for line in je.get("lines") or []
    ]
    rev = await _post_journal(
        user,
        reversal_date or business_today().isoformat(),
        f"Reversal of: {je.get('narration') or je['id']}",
        rev_lines,
        reference=je.get("reference"),
        project_id=je.get("project_id"),
        client_id=je.get("client_id"),
        vendor_id=je.get("vendor_id"),
        employee_id=je.get("employee_id"),
        source=f"{source}_reversal",
        source_id=je["id"],
    )
    changed_at = iso_now()
    original_updates = {
        "reversed": True,
        "reversal_je_id": rev["id"],
        "reversed_at": changed_at,
        "reversed_by": user["user_id"],
    }
    reversal_updates = {"reversal_action": action}
    if hide_from_books:
        original_updates.update({
            "voided_from_view": True,
            "voided_at": changed_at,
            "voided_by": user["user_id"],
            "void_reason": action,
        })
        reversal_updates.update({
            "voided_from_view": True,
            "voided_at": changed_at,
            "voided_by": user["user_id"],
            "void_reason": action,
        })
    await sdb.journal_entries.update_one(
        {"id": je["id"]},
        {"$set": original_updates, "$unset": {"idempotency_key": ""}},
    )
    await sdb.journal_entries.update_one(
        {"id": rev["id"]}, {"$set": reversal_updates},
    )
    if source in {"invoice_payment", "milestone_payment"} and je.get("source_id"):
        await _reset_source_after_reversal(source, je["source_id"])
    elif source == "other_receivable_income":
        await _sync_other_receivable_after_reversal(je["id"])
    await audit(
        user,
        f"journal.{action}",
        target=je["id"],
        target_type="journal_entry",
        meta={"reversal_je_id": rev["id"], "total": je.get("total")},
        org_id=user_org_id(user),
    )
    return rev


@router.get("/journal-entries/{je_id}")
async def get_journal(je_id: str, request: Request,
                      session_token: Optional[str] = Cookie(default=None),
                      authorization: Optional[str] = Header(default=None)):
    je = await sdb.journal_entries.find_one({"id": je_id}, {"_id": 0})
    if not je:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return je


@router.patch("/journal-entries/{je_id}")
async def edit_journal(je_id: str, payload: JournalEditIn, request: Request,
                       session_token: Optional[str] = Cookie(default=None),
                       authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    if not has_permission(user, "finance.update"):
        raise HTTPException(status_code=403, detail="Missing permission: finance.update")
    je = await sdb.journal_entries.find_one({"id": je_id}, {"_id": 0})
    if not je:
        raise HTTPException(status_code=404, detail="Transaction not found")
    if (je.get("source") or "").endswith(("_reversal", "_reinstatement")):
        raise HTTPException(status_code=409, detail="System reversal/reinstatement entries cannot be edited.")

    updates: dict = {}
    if payload.date is not None and payload.date != je.get("date"):
        raise HTTPException(
            status_code=409,
            detail="Posted transaction dates cannot be changed in place. Reverse the entry and record a corrected one.",
        )
    if payload.narration is not None:
        if not payload.narration.strip():
            raise HTTPException(status_code=400, detail="Narration is required")
        updates["narration"] = payload.narration.strip()
    if payload.reference is not None:
        updates["reference"] = payload.reference

    if payload.amount is not None and round(float(payload.amount), 2) != round(float(je.get("total") or 0), 2):
        raise HTTPException(
            status_code=409,
            detail="Posted transaction amounts cannot be changed in place. Reverse the entry and record a corrected one.",
        )

    if not updates:
        return je
    updates["updated_at"] = iso_now()
    updates["updated_by"] = user["user_id"]
    await sdb.journal_entries.update_one({"id": je_id}, {"$set": updates})
    await audit(user, "journal.update", target=je_id, target_type="journal_entry",
                meta={"fields": [k for k in updates if k not in ("updated_at", "updated_by")]},
                org_id=user_org_id(user))
    return await sdb.journal_entries.find_one({"id": je_id}, {"_id": 0})


@router.delete("/journal-entries/{je_id}")
async def delete_journal(je_id: str, request: Request,
                         session_token: Optional[str] = Cookie(default=None),
                         authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    if not has_permission(user, "finance.delete"):
        raise HTTPException(status_code=403, detail="Missing permission: finance.delete")
    je = await sdb.journal_entries.find_one({"id": je_id}, {"_id": 0})
    if not je:
        raise HTTPException(status_code=404, detail="Transaction not found")
    if not _can_void_from_journal(je):
        raise HTTPException(
            status_code=409,
            detail=(
                "This entry is controlled by its invoice, expense, payroll, vendor, loan, or other "
                "source record. Cancel or delete it from that record so both records remain consistent."
            ),
        )
    reversal = await _reverse_journal_entry(
        user,
        je,
        action="delete",
        reversal_date=je.get("date"),
        hide_from_books=True,
    )
    return {
        "ok": True,
        "deleted": True,
        "reversal_je_id": reversal["id"],
        "detail": "Transaction removed from normal books; its balancing audit record was retained.",
    }


@router.post("/journal-entries/{je_id}/correct")
async def correct_journal(je_id: str, payload: JournalCorrectionIn, request: Request,
                          session_token: Optional[str] = Cookie(default=None),
                          authorization: Optional[str] = Header(default=None)):
    """Correct a simple posted entry by reversal and replacement, never mutation."""
    user = await require_user(request, session_token, authorization)
    if not has_permission(user, "finance.update"):
        raise HTTPException(status_code=403, detail="Missing permission: finance.update")
    je = await sdb.journal_entries.find_one({"id": je_id}, {"_id": 0})
    if not je:
        raise HTTPException(status_code=404, detail="Transaction not found")
    source = je.get("source") or "manual"
    if (source not in {"manual", "income", "expense", "non_operating"}
            or je.get("source_id") or len(je.get("lines") or []) != 2):
        raise HTTPException(
            status_code=409,
            detail="Correct this transaction from its original business record so linked data remains consistent.",
        )
    try:
        _date.fromisoformat(payload.date)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Journal date must be YYYY-MM-DD")
    narration = str(payload.narration or "").strip()
    reference = str(payload.reference or "").strip() or None
    amount = round(float(payload.amount), 2)
    if not narration:
        raise HTTPException(status_code=400, detail="Narration is required")
    if len(narration) > 500:
        raise HTTPException(status_code=400, detail="Narration must be 500 characters or fewer")
    if reference and len(reference) > 120:
        raise HTTPException(status_code=400, detail="Reference must be 120 characters or fewer")
    if not math.isfinite(amount) or amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be greater than zero")

    corrected_lines = []
    for line in je["lines"]:
        corrected_lines.append({
            "account_id": line["account_id"],
            "debit": amount if float(line.get("debit") or 0) > 0 else 0,
            "credit": amount if float(line.get("credit") or 0) > 0 else 0,
            "description": narration,
        })
    reversal = await _reverse_journal_entry(
        user,
        je,
        action="correction",
        reversal_date=je.get("date"),
        hide_from_books=True,
    )
    try:
        replacement = await _post_journal(
            user,
            payload.date,
            narration,
            corrected_lines,
            reference=reference,
            project_id=je.get("project_id"),
            client_id=je.get("client_id"),
            vendor_id=je.get("vendor_id"),
            employee_id=je.get("employee_id"),
            source=source,
        )
    except Exception:
        # Compensate a rare insert failure so the original financial effect remains intact.
        reinstatement = await _post_journal(
            user,
            je.get("date"),
            f"Correction rollback: {je.get('narration') or je_id}",
            [
                {
                    "account_id": line["account_id"],
                    "debit": line.get("debit") or 0,
                    "credit": line.get("credit") or 0,
                    "description": "Correction rollback",
                }
                for line in je["lines"]
            ],
            reference=je.get("reference"),
            project_id=je.get("project_id"),
            client_id=je.get("client_id"),
            vendor_id=je.get("vendor_id"),
            employee_id=je.get("employee_id"),
            source=f"{source}_reinstatement",
            source_id=reversal["id"],
        )
        changed_at = iso_now()
        await sdb.journal_entries.update_one(
            {"id": reinstatement["id"]},
            {"$set": {"voided_from_view": True, "void_reason": "correction_rollback"}},
        )
        await sdb.journal_entries.update_one(
            {"id": reversal["id"]},
            {"$set": {"undone": True, "undo_je_id": reinstatement["id"],
                      "undone_at": changed_at, "undone_by": user["user_id"]}},
        )
        await sdb.journal_entries.update_one(
            {"id": je_id},
            {"$set": {"reversed": False, "reinstatement_je_id": reinstatement["id"]},
             "$unset": {"reversal_je_id": "", "reversed_at": "", "reversed_by": "",
                        "voided_from_view": "", "voided_at": "", "voided_by": "",
                        "void_reason": ""}},
        )
        raise

    changed_at = iso_now()
    await sdb.journal_entries.update_one(
        {"id": je_id},
        {"$set": {"corrected": True, "corrected_at": changed_at,
                  "corrected_by": user["user_id"], "corrected_je_id": replacement["id"]}},
    )
    await sdb.journal_entries.update_one(
        {"id": replacement["id"]},
        {"$set": {"corrected_from_je_id": je_id}},
    )
    await audit(
        user,
        "journal.correct",
        target=je_id,
        target_type="journal_entry",
        meta={"reversal_je_id": reversal["id"], "replacement_je_id": replacement["id"],
              "old_total": je.get("total"), "new_total": amount},
        org_id=user_org_id(user),
    )
    return {"ok": True, "replacement": replacement, "reversal_je_id": reversal["id"]}


@router.post("/journal-entries/{je_id}/reverse")
async def reverse_journal(je_id: str, request: Request,
                          session_token: Optional[str] = Cookie(default=None),
                          authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    if not has_permission(user, "finance.update"):
        raise HTTPException(status_code=403, detail="Missing permission: finance.update")
    je = await sdb.journal_entries.find_one({"id": je_id}, {"_id": 0})
    if not je:
        raise HTTPException(status_code=404, detail="Transaction not found")
    rev = await _reverse_journal_entry(user, je)
    return {"ok": True, "reversal": rev}


@router.post("/journal-entries/{je_id}/undo-reversal")
async def undo_journal_reversal(je_id: str, request: Request,
                                session_token: Optional[str] = Cookie(default=None),
                                authorization: Optional[str] = Header(default=None)):
    """Reinstate a directly entered journal without deleting its audit history.

    `je_id` is the reversal entry. The reinstatement mirrors the original entry,
    so original + reversal + reinstatement has the same net effect as the
    original transaction. Source-driven documents use their own workflows
    because their business status must be restored together with accounting.
    """
    user = await require_user(request, session_token, authorization)
    if not has_permission(user, "finance.update"):
        raise HTTPException(status_code=403, detail="Missing permission: finance.update")

    reversal = await sdb.journal_entries.find_one({"id": je_id}, {"_id": 0})
    if not reversal:
        raise HTTPException(status_code=404, detail="Reversal entry not found")
    if not (reversal.get("source") or "").endswith("_reversal"):
        raise HTTPException(status_code=409, detail="This is not a reversal entry")

    original_id = reversal.get("source_id")
    original = await sdb.journal_entries.find_one({"id": original_id}, {"_id": 0})
    if reversal.get("undone") or reversal.get("undo_je_id"):
        undo_id = reversal.get("undo_je_id")
        # Heal an interrupted prior request where the reinstatement and
        # reversal marker were saved but the original marker was not cleared.
        if original and undo_id:
            await sdb.journal_entries.update_one(
                {"id": original_id, "reversal_je_id": je_id},
                {"$set": {"reversed": False, "reinstatement_je_id": undo_id,
                          "reinstated_at": reversal.get("undone_at") or iso_now(),
                          "reinstated_by": reversal.get("undone_by") or user["user_id"]},
                 "$unset": {"reversal_je_id": "", "reversed_at": "", "reversed_by": ""}},
            )
        return {"ok": True, "already_undone": True,
                "original": original_id, "reinstatement_je_id": undo_id}
    if not original or original.get("reversal_je_id") != je_id or not original.get("reversed"):
        raise HTTPException(status_code=409, detail="The linked original transaction is not in a reversible state")

    original_source = original.get("source") or "manual"
    if original_source not in {"manual", "income", "expense", "non_operating"}:
        raise HTTPException(
            status_code=409,
            detail="Undo this reversal from its original invoice, milestone, payroll, vendor, or other source workflow",
        )

    reinstatement_source = f"{original_source}_reinstatement"
    reinstatement = await sdb.journal_entries.find_one(
        {"source": reinstatement_source, "source_id": je_id}, {"_id": 0})
    if not reinstatement:
        try:
            reinstatement = await _post_journal(
                user,
                business_today().isoformat(),
                f"Reinstatement of: {original.get('narration') or original_id}",
                [
                    {
                        "account_id": line["account_id"],
                        "debit": line.get("debit") or 0,
                        "credit": line.get("credit") or 0,
                        "description": f"Reinstatement · {line.get('description') or ''}".strip(),
                    }
                    for line in original.get("lines") or []
                ],
                reference=original.get("reference"),
                project_id=original.get("project_id"),
                client_id=original.get("client_id"),
                vendor_id=original.get("vendor_id"),
                employee_id=original.get("employee_id"),
                source=reinstatement_source,
                source_id=je_id,
            )
        except HTTPException as exc:
            if exc.status_code != 409:
                raise
            reinstatement = await sdb.journal_entries.find_one(
                {"source": reinstatement_source, "source_id": je_id}, {"_id": 0})
            if not reinstatement:
                raise
    changed_at = iso_now()
    await sdb.journal_entries.update_one(
        {"id": je_id, "undone": {"$ne": True}},
        {"$set": {"undone": True, "undo_je_id": reinstatement["id"],
                  "undone_at": changed_at, "undone_by": user["user_id"]}},
    )
    await sdb.journal_entries.update_one(
        {"id": original_id, "reversal_je_id": je_id},
        {"$set": {"reversed": False, "reinstatement_je_id": reinstatement["id"],
                  "reinstated_at": changed_at, "reinstated_by": user["user_id"]},
         "$unset": {"reversal_je_id": "", "reversed_at": "", "reversed_by": ""}},
    )
    await audit(
        user, "journal.reversal.undo", target=je_id, target_type="journal_entry",
        meta={"original_je_id": original_id, "reinstatement_je_id": reinstatement["id"],
              "total": original.get("total")},
        org_id=user_org_id(user),
    )
    return {"ok": True, "original": original_id, "reinstatement": reinstatement}



# ==================================================
# Income (payment received) — convenience wrapper
# ==================================================
@router.post("/accounting/income")
async def create_income(payload: IncomeIn, request: Request,
                        session_token: Optional[str] = Cookie(default=None),
                        authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    if not has_permission(user, "finance.create"):
        raise HTTPException(status_code=403, detail="Missing permission: finance.create")
    if payload.amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be > 0")
    if payload.invoice_id and payload.milestone_id:
        raise HTTPException(status_code=400, detail="Link either an invoice or a milestone, not both")

    bank = await sdb.accounts.find_one(
        {"id": payload.bank_account_id}, {"_id": 0, "id": 1, "type": 1})
    income = await sdb.accounts.find_one(
        {"id": payload.income_account_id}, {"_id": 0, "id": 1, "type": 1})
    if not bank or bank.get("type") != "asset":
        raise HTTPException(status_code=400, detail="Received-into account must be a cash/bank asset account")
    if not income or income.get("type") != "income":
        raise HTTPException(status_code=400, detail="Income account must be an income account")
    if bank["id"] == income["id"]:
        raise HTTPException(status_code=400, detail="Bank and income accounts must be different")

    source = "income"
    source_id = None
    receipt_suffix = None
    project_id = payload.project_id
    client_id = payload.client_id
    linked = None
    received_before = 0.0
    if payload.invoice_id:
        linked = await sdb.invoices.find_one({"id": payload.invoice_id}, {"_id": 0})
        if not linked or linked.get("doc_type", "invoice") == "quotation":
            raise HTTPException(status_code=404, detail="Invoice not found")
        if linked.get("status") == "paid":
            raise HTTPException(status_code=409, detail="Invoice is already paid")
        expected = round(max(0.0, float(linked.get("total") or 0)
                             - float(linked.get("paid_amount") or 0)), 2)
        if payload.amount > expected + 0.01:
            raise HTTPException(status_code=400,
                                detail=f"Amount exceeds invoice balance ({expected:.2f})")
        source, source_id = "invoice_payment", payload.invoice_id
        project_id = linked.get("project_id")
        client_id = linked.get("client_id")
    elif payload.milestone_id:
        linked = await sdb.payment_milestones.find_one(
            {"id": payload.milestone_id}, {"_id": 0})
        if not linked:
            raise HTTPException(status_code=404, detail="Milestone not found")
        if linked.get("status") == "paid":
            raise HTTPException(status_code=409, detail="Milestone is already paid")
        expected = max(0.0, float(linked.get("amount") or 0)
                       - float(linked.get("paid_amount") or 0))
        if payload.amount > expected + 0.01:
            raise HTTPException(status_code=400,
                                detail=f"Amount exceeds milestone balance ({expected:.2f})")
        source, source_id = "milestone_payment", payload.milestone_id
        project_id = linked.get("project_id")

    if source_id:
        active_receipts = await sdb.journal_entries.find(
            {"source": source, "source_id": source_id, "reversed": {"$ne": True}},
            {"_id": 0, "total": 1},
        ).to_list(5000)
        accounted_received = round(sum(float(row.get("total") or 0)
                                       for row in active_receipts), 2)
        received_before = max(round(float(linked.get("paid_amount") or 0), 2),
                              accounted_received)
        linked_total = float((linked.get("total") if payload.invoice_id
                              else linked.get("amount")) or 0)
        if payload.amount > max(0.0, linked_total - received_before) + 0.01:
            raise HTTPException(
                status_code=400,
                detail=f"Amount exceeds outstanding balance ({max(0.0, linked_total - received_before):.2f})",
            )
        supplied_key = (request.headers.get("idempotency-key") or "").strip()[:100]
        receipt_suffix = (hashlib.sha256(supplied_key.encode("utf-8")).hexdigest()[:24]
                          if supplied_key else new_id("receipt_"))
        idem_key = f"{_linked_journal_key(user_org_id(user) or 'org_default', source, source_id)}:{receipt_suffix}"
        existing = await sdb.journal_entries.find_one(
            {"idempotency_key": idem_key, "reversed": {"$ne": True}},
            {"_id": 0, "id": 1},
        )
        if existing:
            # Recover the source document if a worker stopped after the
            # balanced journal insert but before its final status update.
            if payload.milestone_id:
                paid_total = accounted_received
                new_status = "paid" if paid_total + 0.01 >= float(linked.get("amount") or 0) else "invoiced"
                await sdb.payment_milestones.update_one(
                    {"id": payload.milestone_id},
                    {"$set": {"status": new_status, "paid_amount": paid_total,
                              "paid_at": iso_now(), "journal_id": existing["id"]}},
                )
                return await sdb.journal_entries.find_one(
                    {"id": existing["id"]}, {"_id": 0})
            if payload.invoice_id:
                paid_total = accounted_received
                new_status = "paid" if paid_total + 0.01 >= float(linked.get("total") or 0) else "partially_paid"
                await sdb.invoices.update_one(
                    {"id": payload.invoice_id},
                    {"$set": {"status": new_status, "paid_amount": paid_total,
                              "paid_date": payload.date,
                              "journal_id": existing["id"], "updated_at": iso_now()}},
                )
                return await sdb.journal_entries.find_one(
                    {"id": existing["id"]}, {"_id": 0})
            raise HTTPException(status_code=409, detail="This linked payment has already been posted")
    created_accrual = None
    if payload.invoice_id:
        prior_accrual = await sdb.journal_entries.find_one(
            {"source": "invoice_issue", "source_id": payload.invoice_id,
             "reversed": {"$ne": True}}, {"_id": 0, "id": 1})
        if not prior_accrual:
            created_accrual = await post_invoice_accrual_je(user, linked)
        receivable = await sdb.accounts.find_one(
            {"name": "Accounts Receivable", "type": "asset",
             "active": {"$ne": False}}, {"_id": 0})
        if not receivable:
            if created_accrual:
                await reverse_invoice_accrual_je(user, linked)
            raise HTTPException(status_code=409, detail="Accounts Receivable account is unavailable")
        income = receivable

    narration = payload.notes or f"Payment received via {payload.payment_method}"
    lines = [
        {"account_id": payload.bank_account_id, "debit": payload.amount, "credit": 0,
         "description": "Received"},
        {"account_id": income["id"] if payload.invoice_id else payload.income_account_id,
         "debit": 0, "credit": payload.amount,
         "description": "Accounts receivable settled" if payload.invoice_id else "Revenue"},
    ]
    try:
        je = await _post_journal(
            user, payload.date, narration, lines,
            reference=payload.reference, project_id=project_id,
            client_id=client_id, vendor_id=payload.vendor_id,
            employee_id=payload.employee_id,
            source=source, source_id=source_id,
            idempotency_suffix=receipt_suffix,
        )
    except Exception:
        if created_accrual:
            await reverse_invoice_accrual_je(user, linked)
        raise

    # If linked to a milestone, mark it paid
    if payload.milestone_id:
        paid_total = round(received_before + payload.amount, 2)
        new_status = "paid" if paid_total + 0.01 >= float(linked.get("amount") or 0) else "invoiced"
        await sdb.payment_milestones.update_one(
            {"id": payload.milestone_id},
            {"$set": {"status": new_status, "paid_amount": paid_total,
                      "paid_at": iso_now(), "journal_id": je["id"]}}
        )
    # If linked to an invoice, mark it paid (closes the
    # Client → Invoice → Payment → Accounting loop)
    if payload.invoice_id:
        paid_total = round(received_before + payload.amount, 2)
        new_status = "paid" if paid_total + 0.01 >= float(linked.get("total") or 0) else "partially_paid"
        await sdb.invoices.update_one(
            {"id": payload.invoice_id},
            {"$set": {"status": new_status, "paid_amount": paid_total,
                      "paid_date": payload.date,
                      "journal_id": je["id"],
                      "accrual_journal_id": (created_accrual or {}).get("id")
                          or (prior_accrual or {}).get("id")
                          or linked.get("accrual_journal_id"),
                      "updated_at": iso_now()}}
        )
    return je


# ==================================================
# Expense — convenience wrapper
# ==================================================
@router.post("/accounting/expense")
async def create_expense(payload: ExpenseIn, request: Request,
                         session_token: Optional[str] = Cookie(default=None),
                         authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    if not has_permission(user, "finance.create"):
        raise HTTPException(status_code=403, detail="Missing permission: finance.create")
    if payload.amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be > 0")
    expense_account = await sdb.accounts.find_one(
        {"id": payload.expense_account_id}, {"_id": 0, "id": 1, "type": 1})
    paid_from = await sdb.accounts.find_one(
        {"id": payload.paid_from_account_id}, {"_id": 0, "id": 1, "type": 1})
    if not expense_account or expense_account.get("type") != "expense":
        raise HTTPException(status_code=400, detail="Expense account must be an expense account")
    if not paid_from or paid_from.get("type") != "asset":
        raise HTTPException(status_code=400, detail="Paid-from account must be a cash/bank asset account")
    if expense_account["id"] == paid_from["id"]:
        raise HTTPException(status_code=400, detail="Expense and paid-from accounts must be different")

    narration = payload.notes or f"Expense — {payload.payment_method}"
    base_amt = float(payload.amount)
    gst_amt = float(payload.gst or 0)
    total = round(base_amt + gst_amt, 2)

    lines = [
        {"account_id": payload.expense_account_id, "debit": base_amt, "credit": 0,
         "description": "Expense"},
    ]
    if gst_amt > 0:
        await _seed_coa_if_empty()
        gst_acc = await sdb.accounts.find_one(
            {"name": "Input GST Credit", "type": "asset", "active": {"$ne": False}},
            {"_id": 0, "id": 1},
        )
        if gst_acc:
            lines.append({"account_id": gst_acc["id"], "debit": gst_amt, "credit": 0,
                          "description": "GST input"})
        else:
            lines[0]["debit"] += gst_amt  # collapse into expense if no GST account
    lines.append({"account_id": payload.paid_from_account_id, "debit": 0, "credit": total,
                  "description": "Paid"})

    je = await _post_journal(
        user, payload.date, narration, lines,
        reference=payload.reference, project_id=payload.project_id,
        vendor_id=payload.vendor_id, client_id=payload.client_id,
        employee_id=payload.employee_id, source="expense",
    )
    # Attach bill_url on the journal entry for audit
    if payload.bill_url:
        await sdb.journal_entries.update_one({"id": je["id"]}, {"$set": {"bill_url": payload.bill_url}})
        je["bill_url"] = payload.bill_url
    return je


# ==================================================
# Ledgers (derived from journal entries)
# ==================================================
def _movement_for(acc_type: str, debit: float, credit: float) -> float:
    """Net balance movement based on account type conventions."""
    if acc_type in ("asset", "expense"):
        return debit - credit
    # liability / income / equity
    return credit - debit


@router.get("/accounting/ledger/account/{acc_id}")
async def account_ledger(acc_id: str, request: Request,
                         from_date: Optional[str] = None, to_date: Optional[str] = None,
                         session_token: Optional[str] = Cookie(default=None),
                         authorization: Optional[str] = Header(default=None)):
    await require_user(request, session_token, authorization)
    acc = await sdb.accounts.find_one({"id": acc_id}, {"_id": 0})
    if not acc:
        raise HTTPException(status_code=404, detail="Account not found")

    q: dict = {"lines.account_id": acc_id, "voided_from_view": {"$ne": True}}
    if from_date or to_date:
        d = {}
        if from_date: d["$gte"] = from_date
        if to_date: d["$lte"] = to_date
        q["date"] = d
    entries = []
    async for entry in sdb.journal_entries.find(q, {"_id": 0}).sort("date", 1):
        entries.append(entry)
        if len(entries) > 10000:
            raise HTTPException(
                status_code=413,
                detail="Ledger contains more than 10,000 entries; select a narrower date range",
            )

    opening = float(acc.get("opening_balance") or 0)
    if from_date:
        async for prior in sdb.journal_entries.find(
            {"lines.account_id": acc_id, "date": {"$lt": from_date},
             "voided_from_view": {"$ne": True}},
            {"_id": 0, "lines": 1},
        ):
            for line in prior.get("lines") or []:
                if line.get("account_id") == acc_id:
                    opening += _movement_for(
                        acc["type"], float(line.get("debit") or 0),
                        float(line.get("credit") or 0),
                    )

    rows, running = [], opening
    for e in entries:
        for l in e["lines"]:
            if l["account_id"] != acc_id:
                continue
            running += _movement_for(acc["type"], l["debit"], l["credit"])
            rows.append({
                "date": e["date"], "narration": e["narration"], "reference": e.get("reference"),
                "debit": l["debit"], "credit": l["credit"], "balance": round(running, 2),
                "journal_id": e["id"], "source": e.get("source"),
                "project_id": e.get("project_id"), "client_id": e.get("client_id"), "vendor_id": e.get("vendor_id"),
            })
    total_debit = sum(r["debit"] for r in rows)
    total_credit = sum(r["credit"] for r in rows)
    return {"account": acc, "opening_balance": round(opening, 2),
            "closing_balance": round(running, 2),
            "total_debit": round(total_debit, 2), "total_credit": round(total_credit, 2),
            "rows": rows}


@router.get("/accounting/ledger/account/{acc_id}/csv")
async def account_ledger_csv(acc_id: str, request: Request,
                             from_date: Optional[str] = None, to_date: Optional[str] = None,
                             session_token: Optional[str] = Cookie(default=None),
                             authorization: Optional[str] = Header(default=None)):
    """CSV export of a single account's ledger (with running balance)."""
    data = await account_ledger(acc_id, request, from_date=from_date, to_date=to_date,
                                session_token=session_token, authorization=authorization)
    acc_name = (data.get("account") or {}).get("name", "account")
    rows = [{
        "date": r.get("date"),
        "narration": r.get("narration") or "",
        "reference": r.get("reference") or "",
        "debit": r.get("debit", 0),
        "credit": r.get("credit", 0),
        "balance": r.get("balance", 0),
    } for r in data.get("rows", [])]
    safe = "".join(c for c in acc_name if c.isalnum() or c in (" ", "-", "_")).strip().replace(" ", "-").lower()
    return _csv_response(f"ledger-{safe or 'account'}.csv", rows,
                         ["date", "narration", "reference", "debit", "credit", "balance"])



@router.get("/accounting/ledger/client/{client_id}")
async def client_ledger(client_id: str, request: Request,
                        fy: Optional[str] = None,
                        from_date: Optional[str] = None, to_date: Optional[str] = None,
                        session_token: Optional[str] = Cookie(default=None),
                        authorization: Optional[str] = Header(default=None)):
    await require_user(request, session_token, authorization)
    fd, td, label = resolve_period(fy, from_date, to_date)
    client = await sdb.clients.find_one({"id": client_id}, {"_id": 0})
    return await _entity_ledger("client", client_id, entity=client,
                                from_date=fd, to_date=td, label=label)


@router.get("/accounting/ledger/vendor/{vendor_id}")
async def vendor_ledger(vendor_id: str, request: Request,
                        fy: Optional[str] = None,
                        from_date: Optional[str] = None, to_date: Optional[str] = None,
                        session_token: Optional[str] = Cookie(default=None),
                        authorization: Optional[str] = Header(default=None)):
    await require_user(request, session_token, authorization)
    fd, td, label = resolve_period(fy, from_date, to_date)
    vendor = await sdb.vendors_acc.find_one({"id": vendor_id}, {"_id": 0})
    return await _entity_ledger("vendor", vendor_id, entity=vendor,
                                from_date=fd, to_date=td, label=label)


@router.get("/accounting/ledger/employee/{employee_id}")
async def employee_ledger(employee_id: str, request: Request,
                          fy: Optional[str] = None,
                          from_date: Optional[str] = None, to_date: Optional[str] = None,
                          session_token: Optional[str] = Cookie(default=None),
                          authorization: Optional[str] = Header(default=None)):
    await require_user(request, session_token, authorization)
    fd, td, label = resolve_period(fy, from_date, to_date)
    employee = await sdb.employees.find_one({"id": employee_id}, {"_id": 0})
    return await _entity_ledger("employee", employee_id, entity=employee,
                                from_date=fd, to_date=td, label=label)


@router.get("/accounting/ledger/project/{project_id}")
async def project_ledger(project_id: str, request: Request,
                         fy: Optional[str] = None,
                         from_date: Optional[str] = None, to_date: Optional[str] = None,
                         session_token: Optional[str] = Cookie(default=None),
                         authorization: Optional[str] = Header(default=None)):
    await require_user(request, session_token, authorization)
    fd, td, label = resolve_period(fy, from_date, to_date)
    project = await sdb.projects.find_one({"id": project_id}, {"_id": 0})
    base = await _entity_ledger("project", project_id, entity=project,
                                from_date=fd, to_date=td, label=label)
    # Extra project-specific block: milestones + P&L
    milestones = await sdb.payment_milestones.find({"project_id": project_id}, {"_id": 0}).to_list(200)
    revenue = 0.0
    expense = 0.0
    for e in base["entries"]:
        for l in e.get("lines") or []:
            if l["account_type"] == "income":
                revenue += l["credit"] - l["debit"]
            elif l["account_type"] == "expense":
                expense += l["debit"] - l["credit"]
    base.update({
        "milestones": milestones,
        "revenue": round(revenue, 2),
        "expense": round(expense, 2),
        "profit": round(revenue - expense, 2),
    })
    return base


# ------------------------------------------------------------------
# Unified entity-ledger helper — the engine behind Client / Vendor /
# Employee / Project ledgers. Computes opening + inflow + outflow +
# closing with a per-row running balance.
#
# Sign convention (money-owed-to-the-entity view):
#   * client:   invoice/inflow debit A/R → credit balance goes UP (they owe us)
#     received → asset/bank increases, A/R goes down (they owe us less)
#   Rather than modelling per-entity account we adopt a simpler
#   "net cash movement" convention:
#     - IN  (money we received FROM the entity) = income + asset in
#     - OUT (money we paid TO the entity)       = expense + asset out
# ------------------------------------------------------------------
async def _entity_ledger(entity_type: str, entity_id: str, entity: Optional[dict],
                         from_date: Optional[str], to_date: Optional[str],
                         label: str) -> dict:
    field = {
        "client": "client_id",
        "vendor": "vendor_id",
        "employee": "employee_id",
        "project": "project_id",
    }[entity_type]

    # Opening balance = net movement BEFORE from_date
    opening = 0.0
    if from_date:
        async for e in sdb.journal_entries.find(
            {field: entity_id, "date": {"$lt": from_date},
             "voided_from_view": {"$ne": True}}, {"_id": 0}
        ):
            opening += _entity_net(e)

    # Period entries
    q: dict = {field: entity_id, "voided_from_view": {"$ne": True}}
    if from_date or to_date:
        d = {}
        if from_date: d["$gte"] = from_date
        if to_date: d["$lte"] = to_date
        q["date"] = d
    entries_raw = await sdb.journal_entries.find(q, {"_id": 0}).sort("date", 1).to_list(5000)

    inflow = 0.0
    outflow = 0.0
    running = opening
    entries: list = []
    for e in entries_raw:
        net = _entity_net(e)
        if net > 0:
            inflow += net
        else:
            outflow += -net
        running += net
        entries.append({
            "id": e["id"],
            "date": e["date"],
            "narration": e["narration"],
            "reference": e.get("reference"),
            "source": e.get("source"),
            "inflow": round(net if net > 0 else 0, 2),
            "outflow": round(-net if net < 0 else 0, 2),
            "balance": round(running, 2),
            "lines": e.get("lines"),
            "project_id": e.get("project_id"),
            "client_id": e.get("client_id"),
            "vendor_id": e.get("vendor_id"),
            "employee_id": e.get("employee_id"),
        })

    return {
        "entity_type": entity_type,
        "entity_id": entity_id,
        "entity": entity,
        "period": {"from_date": from_date, "to_date": to_date, "label": label},
        "opening_balance": round(opening, 2),
        "inflow": round(inflow, 2),
        "outflow": round(outflow, 2),
        "net_movement": round(inflow - outflow, 2),
        "closing_balance": round(running, 2),
        "entries": entries,
    }


def _entity_net(entry: dict) -> float:
    """Net cash-flow direction for an entity-tagged journal entry.

    Positive = money INTO our business (i.e. from the entity — customer paid us, etc).
    Negative = money OUT of our business (i.e. to the entity — we paid a vendor, etc).
    Computed from the entry's cash/bank lines when present; falls back to
    Σ (income - expense) so income entries without a bank line still count.
    """
    cash_net = 0.0
    non_cash_net = 0.0
    for l in entry.get("lines") or []:
        t = l.get("account_type")
        d = float(l.get("debit") or 0)
        c = float(l.get("credit") or 0)
        if t == "asset":
            cash_net += d - c            # asset DR = money in
        elif t == "income":
            non_cash_net += c - d        # revenue CR = income booked
        elif t == "expense":
            non_cash_net += -(d - c)     # expense DR = outflow
    return round(cash_net if cash_net != 0 else non_cash_net, 2)


# ------------------------------------------------------------------
# FY / period utilities
# ------------------------------------------------------------------
@router.get("/accounting/fy/list")
async def list_financial_years(request: Request,
                               session_token: Optional[str] = Cookie(default=None),
                               authorization: Optional[str] = Header(default=None)):
    """Dropdown-ready list of FYs (5 past + current + 1 future)."""
    await require_user(request, session_token, authorization)
    return {"current": current_fy_label(), "choices": fy_choices()}


# ==================================================
# Reports
# ==================================================
@router.get("/accounting/reports/pl")
async def profit_and_loss(request: Request,
                          from_date: Optional[str] = None, to_date: Optional[str] = None,
                          fy: Optional[str] = None,
                          project_id: Optional[str] = None,
                          session_token: Optional[str] = Cookie(default=None),
                          authorization: Optional[str] = Header(default=None)):
    await require_user(request, session_token, authorization)
    fd, td, label = resolve_period(fy, from_date, to_date)
    q: dict = {}
    if fd or td:
        d = {}
        if fd: d["$gte"] = fd
        if td: d["$lte"] = td
        q["date"] = d
    if project_id: q["project_id"] = project_id
    entries = await sdb.journal_entries.find(q, {"_id": 0}).to_list(5000)

    income_by_acc: dict = {}
    expense_by_acc: dict = {}
    for e in entries:
        for l in e["lines"]:
            if l["account_type"] == "income":
                income_by_acc[l["account_name"]] = income_by_acc.get(l["account_name"], 0) + (l["credit"] - l["debit"])
            elif l["account_type"] == "expense":
                expense_by_acc[l["account_name"]] = expense_by_acc.get(l["account_name"], 0) + (l["debit"] - l["credit"])

    total_income = round(sum(income_by_acc.values()), 2)
    total_expense = round(sum(expense_by_acc.values()), 2)
    return {
        "from": fd, "to": td, "period_label": label, "project_id": project_id,
        "income": [{"name": k, "amount": round(v, 2)} for k, v in income_by_acc.items()],
        "expense": [{"name": k, "amount": round(v, 2)} for k, v in expense_by_acc.items()],
        "total_income": total_income, "total_expense": total_expense,
        "net_profit": round(total_income - total_expense, 2),
    }


@router.get("/accounting/reports/trial-balance")
async def trial_balance(request: Request, as_of: Optional[str] = None,
                        fy: Optional[str] = None,
                        session_token: Optional[str] = Cookie(default=None),
                        authorization: Optional[str] = Header(default=None)):
    """Trial Balance = opening balances + journal-entry movements.

    Includes each account's `opening_balance` on the natural side (assets/
    expenses → debit; liabilities/income/equity → credit) so Trial Balance
    stays consistent with Balance Sheet (which also starts from opening
    balances). No double-counting because JEs never adjust the opening
    balance field directly."""
    await require_user(request, session_token, authorization)
    # If FY supplied but as_of not, treat as_of = fy end. Explicit all-time
    # intentionally leaves the upper bound open.
    if fy and not as_of:
        _, as_of, _ = resolve_period(fy=fy)
    q = {}
    if as_of: q["date"] = {"$lte": as_of}
    entries = await sdb.journal_entries.find(q, {"_id": 0}).to_list(10000)

    per_acc: dict = {}
    for e in entries:
        for l in e["lines"]:
            k = l["account_id"]
            if k not in per_acc:
                per_acc[k] = {
                    "account_id": k, "account_name": l["account_name"], "account_type": l["account_type"],
                    "debit": 0.0, "credit": 0.0,
                }
            per_acc[k]["debit"] += l["debit"]
            per_acc[k]["credit"] += l["credit"]

    # Merge in opening balances so accounts w/ opening but no JEs still appear.
    async for a in sdb.accounts.find({}, {"_id": 0}):
        ob = float(a.get("opening_balance") or 0)
        if ob == 0 and a["id"] not in per_acc:
            continue
        row = per_acc.setdefault(a["id"], {
            "account_id": a["id"], "account_name": a["name"], "account_type": a["type"],
            "debit": 0.0, "credit": 0.0,
        })
        if ob != 0:
            if a["type"] in ("asset", "expense"):
                row["debit"] += ob if ob > 0 else 0
                row["credit"] += -ob if ob < 0 else 0
            else:
                row["credit"] += ob if ob > 0 else 0
                row["debit"] += -ob if ob < 0 else 0

    rows = []
    for a in per_acc.values():
        a["balance"] = round(_movement_for(a["account_type"], a["debit"], a["credit"]), 2)
        a["debit"] = round(a["debit"], 2); a["credit"] = round(a["credit"], 2)
        rows.append(a)
    rows.sort(key=lambda r: (r["account_type"], r["account_name"]))
    return {
        "as_of": as_of, "fy": fy,
        "rows": rows,
        "total_debit": round(sum(r["debit"] for r in rows), 2),
        "total_credit": round(sum(r["credit"] for r in rows), 2),
    }


# ==================================================
# Finance Dashboard
# ==================================================
@router.get("/accounting/dashboard")
async def finance_dashboard(request: Request,
                            session_token: Optional[str] = Cookie(default=None),
                            authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    if not has_permission(user, "finance.read"):
        raise HTTPException(status_code=403, detail="Missing permission: finance.read")
    today = business_today().isoformat()
    month_start = f"{now_utc().year}-{now_utc().month:02d}-01"

    # Cash / Bank balances (asset accounts flagged as is_bank OR Cash)
    accs = await sdb.accounts.find({"$or": [{"is_bank": True}, {"name": "Cash"}, {"name": "Petty Cash"}]},
                                  {"_id": 0}).to_list(50)
    cash_bank = []
    for a in accs:
        # sum all movements for that account
        agg = await sdb.journal_entries.aggregate([
            {"$unwind": "$lines"},
            {"$match": {"lines.account_id": a["id"]}},
            {"$group": {"_id": None,
                        "debit": {"$sum": "$lines.debit"},
                        "credit": {"$sum": "$lines.credit"}}},
        ]).to_list(1)
        d = agg[0]["debit"] if agg else 0.0
        c = agg[0]["credit"] if agg else 0.0
        bal = float(a.get("opening_balance") or 0) + _movement_for("asset", d, c)
        cash_bank.append({"account_id": a["id"], "name": a["name"], "balance": round(bal, 2)})

    total_cash_bank = round(sum(x["balance"] for x in cash_bank), 2)

    # This month P&L (income & expense from journal source)
    entries_month = await sdb.journal_entries.find(
        {"date": {"$gte": month_start}}, {"_id": 0}).to_list(5000)
    income_month = 0.0
    expense_month = 0.0
    salary_month = 0.0
    today_collections = 0.0
    # Sources that represent a real payment received today (Money In).
    for e in entries_month:
        src = e.get("source") or ""
        for l in e["lines"]:
            if l["account_type"] == "income":
                income_month += l["credit"] - l["debit"]
                if e["date"] == today and _cash_collection_source(src):
                    today_collections += l["credit"] - l["debit"]
            elif l["account_type"] == "expense":
                expense_month += l["debit"] - l["credit"]
                if l["account_name"] == "Employee Salary":
                    salary_month += l["debit"] - l["credit"]

    # Outstanding = unpaid invoices + pending milestones (single consistent
    # definition used everywhere: dashboard, clients, projects, accounting).
    outstanding_invoices = 0.0
    async for inv in sdb.invoices.find(
        {"status": {"$in": ["sent", "overdue", "partially_paid"]},
         "doc_type": {"$ne": "quotation"}},
        {"_id": 0, "total": 1, "paid_amount": 1, "due_date": 1, "status": 1},
    ):
        outstanding_invoices += max(0.0, float(inv.get("total") or 0)
                                    - float(inv.get("paid_amount") or 0))
    ms = await sdb.payment_milestones.find(
        {"status": {"$ne": "paid"}},
        {"_id": 0, "amount": 1, "paid_amount": 1, "due_date": 1,
         "status": 1, "project_id": 1, "name": 1},
    ).to_list(500)
    outstanding_ms = sum(max(0.0, float(m.get("amount") or 0)
                             - float(m.get("paid_amount") or 0)) for m in ms)
    outstanding = round(outstanding_invoices + outstanding_ms, 2)
    overdue = round(sum(max(0.0, float(m.get("amount") or 0)
                                - float(m.get("paid_amount") or 0)) for m in ms
                       if (m.get("due_date") or "") < today), 2)

    # Upcoming payments (next 30 days)
    horizon = (business_today() + timedelta(days=30)).isoformat()
    upcoming = [m for m in ms if today <= (m.get("due_date") or "") <= horizon]

    # Recent transactions
    recent = await sdb.journal_entries.find(
        {"voided_from_view": {"$ne": True}}, {"_id": 0}
    ).sort("created_at", -1).limit(10).to_list(10)

    return {
        "kpis": {
            "cash_bank": total_cash_bank,
            "cash_bank_by_account": cash_bank,
            "income_month": round(income_month, 2),
            "expense_month": round(expense_month, 2),
            "profit_month": round(income_month - expense_month, 2),
            "salary_month": round(salary_month, 2),
            "outstanding": outstanding,
            "overdue": overdue,
            "today_collections": round(today_collections, 2),
        },
        "upcoming_payments": upcoming,
        "recent_transactions": recent,
    }


@router.post("/accounting/receivables")
async def create_other_receivable(payload: OtherReceivableIn, request: Request,
                                  session_token: Optional[str] = Cookie(default=None),
                                  authorization: Optional[str] = Header(default=None)):
    """Create a collection reminder only.  No journal is posted here."""
    user = await require_user(request, session_token, authorization)
    if not has_permission(user, "finance.create"):
        raise HTTPException(status_code=403, detail="Missing permission: finance.create")
    doc = payload.model_dump()
    for collection_name, field in (("clients", "client_id"), ("vendors_acc", "vendor_id"),
                                   ("projects", "project_id")):
        value = doc.get(field)
        if value and not await getattr(sdb, collection_name).find_one({"id": value}, {"_id": 1}):
            raise HTTPException(status_code=404, detail=f"{field.removesuffix('_id').title()} not found")
    if doc.get("income_account_id"):
        account = await sdb.accounts.find_one(
            {"id": doc["income_account_id"], "type": "income", "active": {"$ne": False}},
            {"_id": 0, "id": 1})
        if not account:
            raise HTTPException(status_code=400, detail="Income account is unavailable")
    doc.update({"id": new_id("recv_"), "received_amount": 0.0, "status": "pending",
                "created_at": iso_now(), "created_by": user["user_id"],
                "updated_at": iso_now()})
    await sdb.collection_receivables.insert_one(dict(doc))
    await audit(user, "receivable.create", target=doc["id"], target_type="receivable",
                meta={"amount": doc["amount"], "due_date": doc.get("due_date")})
    return doc


@router.patch("/accounting/receivables/{receivable_id}")
async def update_other_receivable(receivable_id: str, payload: OtherReceivableUpdate,
                                  request: Request,
                                  session_token: Optional[str] = Cookie(default=None),
                                  authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    if not has_permission(user, "finance.update"):
        raise HTTPException(status_code=403, detail="Missing permission: finance.update")
    row = await sdb.collection_receivables.find_one({"id": receivable_id}, {"_id": 0})
    if not row:
        raise HTTPException(status_code=404, detail="Receivable not found")
    if float(row.get("received_amount") or 0) > 0:
        raise HTTPException(status_code=409,
                            detail="Reverse the linked receipt before changing this receivable")
    patch = payload.model_dump(exclude_unset=True)
    for collection_name, field in (("clients", "client_id"), ("vendors_acc", "vendor_id"),
                                   ("projects", "project_id")):
        value = patch.get(field)
        if value and not await getattr(sdb, collection_name).find_one(
                {"id": value}, {"_id": 1}):
            raise HTTPException(
                status_code=404,
                detail=f"{field.removesuffix('_id').title()} not found",
            )
    if patch.get("income_account_id"):
        account = await sdb.accounts.find_one(
            {"id": patch["income_account_id"], "type": "income",
             "active": {"$ne": False}}, {"_id": 0, "id": 1})
        if not account:
            raise HTTPException(status_code=400, detail="Income account is unavailable")
    patch["updated_at"] = iso_now()
    await sdb.collection_receivables.update_one({"id": receivable_id}, {"$set": patch})
    await audit(user, "receivable.update", target=receivable_id, target_type="receivable",
                meta={"fields": sorted(patch.keys())})
    return await sdb.collection_receivables.find_one({"id": receivable_id}, {"_id": 0})


@router.delete("/accounting/receivables/{receivable_id}")
async def delete_other_receivable(receivable_id: str, request: Request,
                                  session_token: Optional[str] = Cookie(default=None),
                                  authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    if not has_permission(user, "finance.delete"):
        raise HTTPException(status_code=403, detail="Missing permission: finance.delete")
    row = await sdb.collection_receivables.find_one({"id": receivable_id}, {"_id": 0})
    if not row:
        raise HTTPException(status_code=404, detail="Receivable not found")
    if float(row.get("received_amount") or 0) > 0:
        raise HTTPException(status_code=409,
                            detail="Reverse the linked receipt before deleting this receivable")
    await sdb.collection_receivables.update_one(
        {"id": receivable_id},
        {"$set": {"status": "cancelled", "cancelled_at": iso_now(),
                  "cancelled_by": user["user_id"], "updated_at": iso_now()}},
    )
    await audit(user, "receivable.cancel", target=receivable_id, target_type="receivable")
    return {"ok": True, "cancelled": True}


@router.post("/accounting/collections/receive")
async def receive_collection(payload: CollectionReceiptIn, request: Request,
                             session_token: Optional[str] = Cookie(default=None),
                             authorization: Optional[str] = Header(default=None)):
    """Record Money In through the existing source workflow and journal engine."""
    user = await require_user(request, session_token, authorization)
    if not has_permission(user, "finance.create"):
        raise HTTPException(status_code=403, detail="Missing permission: finance.create")
    idem = (request.headers.get("idempotency-key") or "").strip()[:100]
    request_key = (f"{user_org_id(user)}:{payload.source_type}:{payload.source_id}:{idem}"
                   if idem else None)
    if request_key:
        prior = await sdb.collection_receipts.find_one({"request_key": request_key}, {"_id": 0})
        if prior:
            return prior

    if payload.source_type == "vendor_commission":
        from models.vendor import CommissionReceiveIn
        from routes.vendors import _receive_commission_locked
        row = await sdb.vendor_commissions.find_one({"id": payload.source_id}, {"_id": 0})
        if not row or row.get("status") in ("cancelled", "reversed"):
            raise HTTPException(status_code=404, detail="Commission not found")
        outstanding = round(max(0.0, float(row.get("amount") or 0)
                                - float(row.get("received_amount") or 0)), 2)
        if payload.amount > outstanding + 0.01:
            raise HTTPException(status_code=400, detail=f"Amount exceeds pending commission ({outstanding:.2f})")
        bank = await require_asset_account(payload.bank_account_id, "Bank/cash account")
        commission_payload = CommissionReceiveIn(
            amount=payload.amount, received_date=payload.date,
            bank_account_id=payload.bank_account_id,
            payment_method=payload.payment_method, reference=payload.reference,
            notes=payload.notes, commission_ids=[payload.source_id],
        )
        async with doc_lock(sdb.vendors_acc, row["vendor_id"]):
            result = await _receive_commission_locked(
                user, row["vendor_id"], commission_payload, bank,
                idem=idem or None, request_key=request_key)
        receipt = {**result, "source_type": payload.source_type,
                   "source_id": payload.source_id, "amount": payload.amount}
        return receipt

    if payload.source_type in ("invoice", "milestone"):
        income_id = payload.income_account_id
        if not income_id:
            _bank, default_income = await default_receipt_accounts()
            income_id = (default_income or {}).get("id")
        if not income_id:
            raise HTTPException(status_code=409, detail="Income account is unavailable")
        linked = ({"invoice_id": payload.source_id} if payload.source_type == "invoice"
                  else {"milestone_id": payload.source_id})
        lock_collection = (sdb.invoices if payload.source_type == "invoice"
                           else sdb.payment_milestones)
        async with doc_lock(lock_collection, payload.source_id):
            je = await create_income(
                IncomeIn(date=payload.date, amount=payload.amount,
                         income_account_id=income_id, bank_account_id=payload.bank_account_id,
                         payment_method=payload.payment_method, reference=payload.reference,
                         notes=payload.notes, **linked),
                request, session_token, authorization,
            )
        return {"ok": True, "source_type": payload.source_type,
                "source_id": payload.source_id, "amount": payload.amount,
                "journal_entry_id": je.get("id")}

    async with doc_lock(sdb.collection_receivables, payload.source_id):
        row = await sdb.collection_receivables.find_one(
            {"id": payload.source_id, "status": {"$ne": "cancelled"}}, {"_id": 0})
        if not row:
            raise HTTPException(status_code=404, detail="Receivable not found")
        outstanding = round(max(0.0, float(row.get("amount") or 0)
                                - float(row.get("received_amount") or 0)), 2)
        if payload.amount > outstanding + 0.01:
            raise HTTPException(status_code=400, detail=f"Amount exceeds pending receivable ({outstanding:.2f})")
        bank = await require_asset_account(payload.bank_account_id, "Bank/cash account")
        income_id = payload.income_account_id or row.get("income_account_id")
        income = await sdb.accounts.find_one(
            {"id": income_id, "type": "income", "active": {"$ne": False}}, {"_id": 0})
        if not income:
            raise HTTPException(status_code=400, detail="Select an active income account")
        receipt_id = (f"cr_{hashlib.sha256(request_key.encode('utf-8')).hexdigest()[:24]}"
                      if request_key else new_id("cr_"))
        je = await _post_journal(
            user, payload.date, payload.notes or f"Collection received - {row.get('name')}",
            [{"account_id": bank["id"], "debit": payload.amount, "credit": 0,
              "description": "Received"},
             {"account_id": income["id"], "debit": 0, "credit": payload.amount,
              "description": income.get("name")}],
            reference=payload.reference, project_id=row.get("project_id"),
            client_id=row.get("client_id"), vendor_id=row.get("vendor_id"),
            source="other_receivable_income", source_id=receipt_id,
        )
        received = round(float(row.get("received_amount") or 0) + payload.amount, 2)
        status = "received" if received + 0.01 >= float(row.get("amount") or 0) else "partially_received"
        receipt = {
            "id": receipt_id, "source_type": payload.source_type,
            "source_id": payload.source_id, "amount": round(payload.amount, 2),
            "date": payload.date, "payment_method": payload.payment_method,
            "bank_account_id": payload.bank_account_id,
            "income_account_id": income["id"], "reference": payload.reference,
            "notes": payload.notes, "journal_entry_id": je["id"],
            "status": "received", "created_at": iso_now(),
            "created_by": user["user_id"],
        }
        if request_key:
            receipt["request_key"] = request_key
        await sdb.collection_receipts.insert_one(dict(receipt))
        await sdb.collection_receivables.update_one(
            {"id": payload.source_id},
            {"$set": {"received_amount": received, "status": status,
                      "last_received_at": payload.date, "updated_at": iso_now()}},
        )
        await audit(user, "receivable.receive", target=payload.source_id,
                    target_type="receivable",
                    meta={"receipt_id": receipt_id, "amount": payload.amount})
        return receipt


@router.get("/accounting/receivables")
async def project_receivables(request: Request,
                              session_token: Optional[str] = Cookie(default=None),
                              authorization: Optional[str] = Header(default=None)):
    """Unified Money In view over existing source-of-truth records."""
    user = await require_user(request, session_token, authorization)
    if not has_permission(user, "finance.read"):
        raise HTTPException(status_code=403, detail="Missing permission: finance.read")

    today = business_today()
    horizon = today + timedelta(days=30)
    milestones = await sdb.payment_milestones.find(
        {"status": {"$ne": "cancelled"}}, {"_id": 0}).to_list(5000)
    invoices = await sdb.invoices.find(
        {"doc_type": {"$ne": "quotation"}, "status": {"$nin": ["draft", "cancelled"]}},
        {"_id": 0}).to_list(5000)
    commissions = await sdb.vendor_commissions.find(
        {"status": {"$nin": ["cancelled", "reversed"]}}, {"_id": 0}).to_list(5000)
    other_rows = await sdb.collection_receivables.find(
        {"status": {"$ne": "cancelled"}}, {"_id": 0}).to_list(5000)

    project_ids = {row.get("project_id") for row in
                   [*milestones, *invoices, *commissions, *other_rows] if row.get("project_id")}
    projects = {p["id"]: p async for p in sdb.projects.find(
        {"id": {"$in": list(project_ids)}},
        {"_id": 0, "id": 1, "name": 1, "client_id": 1, "client_name": 1})} \
        if project_ids else {}
    client_ids = {row.get("client_id") for row in [*invoices, *other_rows] if row.get("client_id")}
    client_ids.update(p.get("client_id") for p in projects.values() if p.get("client_id"))
    clients = {c["id"]: c.get("name") async for c in sdb.clients.find(
        {"id": {"$in": list(client_ids)}}, {"_id": 0, "id": 1, "name": 1})} \
        if client_ids else {}
    vendor_ids = {row.get("vendor_id") for row in [*commissions, *other_rows] if row.get("vendor_id")}
    vendors = {v["id"]: v.get("name") async for v in sdb.vendors_acc.find(
        {"id": {"$in": list(vendor_ids)}}, {"_id": 0, "id": 1, "name": 1})} \
        if vendor_ids else {}

    rows = []

    def append_row(*, source_type: str, source_id: str, name: str, amount: float,
                   received: float = 0, due_date: Optional[str] = None,
                   project_id: Optional[str] = None, client_id: Optional[str] = None,
                   vendor_id: Optional[str] = None, reference: Optional[str] = None,
                   recognition: Optional[str] = None, income_account_id: Optional[str] = None,
                   origin: Optional[str] = None, reminder_date: Optional[str] = None):
        project = projects.get(project_id, {})
        status = _collection_status(due_date, amount, received, today, horizon)
        outstanding = round(max(0.0, float(amount or 0) - float(received or 0)), 2)
        days_overdue = 0
        if status == "overdue" and due_date:
            days_overdue = (today - _date.fromisoformat(due_date)).days
        rows.append({
            "id": source_id, "source_type": source_type, "name": name,
            "project_id": project_id, "project_name": project.get("name"),
            "client_id": client_id or project.get("client_id"),
            "client_name": clients.get(client_id or project.get("client_id"))
                or project.get("client_name"),
            "vendor_id": vendor_id, "vendor_name": vendors.get(vendor_id),
            "due_date": due_date, "status": status, "bucket": status,
            "amount": round(float(amount or 0), 2),
            "received_amount": round(float(received or 0), 2),
            "outstanding": outstanding, "days_overdue": days_overdue,
            "reference": reference, "recognition": recognition,
            "income_account_id": income_account_id, "origin": origin,
            "reminder_date": reminder_date,
        })

    for row in milestones:
        append_row(source_type="milestone", source_id=row["id"],
                   name=row.get("name") or "Project milestone",
                   amount=row.get("amount") or 0, received=row.get("paid_amount") or 0,
                   due_date=row.get("due_date"), project_id=row.get("project_id"))
    for row in invoices:
        received = row.get("paid_amount") or (row.get("total") if row.get("status") == "paid" else 0)
        append_row(source_type="invoice", source_id=row["id"],
                   name=f"Invoice {row.get('number') or row['id']}",
                   amount=row.get("total") or 0, received=received,
                   due_date=row.get("due_date"), project_id=row.get("project_id"),
                   client_id=row.get("client_id"), reference=row.get("number"))
    for row in commissions:
        append_row(source_type="vendor_commission", source_id=row["id"],
                   name=(f"Commission - {row.get('vendor_name') or vendors.get(row.get('vendor_id')) or 'Vendor'}"),
                   amount=row.get("amount") or 0, received=row.get("received_amount") or 0,
                   due_date=row.get("due_date"), project_id=row.get("project_id"),
                   vendor_id=row.get("vendor_id"), reference=row.get("reference") or row.get("bill_number"),
                   recognition=row.get("recognition") or "earned", origin=row.get("origin"),
                   reminder_date=row.get("reminder_date"))
    for row in other_rows:
        append_row(source_type="other_receivable", source_id=row["id"],
                   name=row.get("name") or "Other receivable", amount=row.get("amount") or 0,
                   received=row.get("received_amount") or 0, due_date=row.get("due_date"),
                   project_id=row.get("project_id"), client_id=row.get("client_id"),
                   vendor_id=row.get("vendor_id"), reference=row.get("reference"),
                   recognition="cash_basis", income_account_id=row.get("income_account_id"),
                   origin="manual_expected", reminder_date=row.get("reminder_date"))

    totals = {key: 0.0 for key in (
        "all", "overdue", "due_today", "upcoming", "later", "no_due_date",
        "partially_received", "received")}
    for row in rows:
        totals["received"] += row["received_amount"]
        if row["status"] != "received":
            totals["all"] += row["outstanding"]
            totals[row["status"]] += row["outstanding"]
    totals["due_30"] = totals["due_today"] + totals["upcoming"]
    rows.sort(key=lambda row: (row.get("status") == "received",
                               row.get("due_date") or "9999-12-31", row.get("name") or ""))
    return {"as_of": today.isoformat(), "horizon": horizon.isoformat(),
            "totals": {key: round(value, 2) for key, value in totals.items()},
            "count": len(rows), "rows": rows}


# ==================================================
# Dashboard Validation Report  (Admin-only)
# ==================================================
# Runs both engines side-by-side and surfaces discrepancies with root-cause
# hints. This is the "silent validation mode" the migration plan calls for:
# end-users still see one number; Admins can prove parity here before we
# strip the legacy code paths.
# ==================================================
@router.get("/accounting/dashboard/validation")
async def dashboard_validation(request: Request,
                               fy: Optional[str] = None,
                               from_date: Optional[str] = None,
                               to_date: Optional[str] = None,
                               session_token: Optional[str] = Cookie(default=None),
                               authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    if not has_permission(user, "*.*"):
        raise HTTPException(403, "Admin only")
    fd, td, label = resolve_period(fy, from_date, to_date)

    # --- Accounting-engine values (source of truth going forward) ---
    q: dict = {"voided_from_view": {"$ne": True}}
    if fd or td:
        d = {}
        if fd: d["$gte"] = fd
        if td: d["$lte"] = td
        q["date"] = d
    entries = await sdb.journal_entries.find(q, {"_id": 0}).to_list(20000)
    acc_income = 0.0
    acc_expense = 0.0
    for e in entries:
        for l in e["lines"]:
            if l["account_type"] == "income":
                acc_income += l["credit"] - l["debit"]
            elif l["account_type"] == "expense":
                acc_expense += l["debit"] - l["credit"]
    acc_profit = acc_income - acc_expense

    # --- Legacy calc (invoices + milestones) — pre-migration source ---
    inv_q: dict = {"doc_type": "invoice"}
    if fd or td:
        d = {}
        if fd: d["$gte"] = fd
        if td: d["$lte"] = (td + "\uffff")
        # Legacy invoices have no issue_date — fall back to created_at (full ISO)
        inv_q["$or"] = [{"issue_date": {k: v[:10] for k, v in d.items()}},
                        {"issue_date": {"$in": [None, ""]}, "created_at": d},
                        {"issue_date": {"$exists": False}, "created_at": d}]
    invoices = await sdb.invoices.find(inv_q, {"_id": 0}).to_list(5000)
    leg_revenue = sum(float(i.get("total") or 0) for i in invoices
                      if i.get("status") in ("paid", "sent", "overdue"))

    ms_q: dict = {}
    if fd or td:
        d = {}
        if fd: d["$gte"] = fd
        if td: d["$lte"] = td
        ms_q["due_date"] = d
    milestones = await sdb.payment_milestones.find(ms_q, {"_id": 0}).to_list(5000)
    leg_collected = sum(float(m.get("paid_amount") or 0) for m in milestones
                        if m.get("status") == "paid")
    leg_outstanding = sum(float(m.get("amount") or 0) for m in milestones
                          if m.get("status") != "paid")

    # --- Diagnostics ---
    # Invoices marked paid without a linked JE
    invoice_ids = [i["id"] for i in invoices if i.get("status") == "paid"]
    linked_jes = set()
    async for e in sdb.journal_entries.find(
        {"source": "invoice_payment", "source_id": {"$in": invoice_ids}},
        {"_id": 0, "source_id": 1},
    ):
        linked_jes.add(e.get("source_id"))
    orphan_invoices = [i for i in invoices
                       if i.get("status") == "paid" and i["id"] not in linked_jes]

    # Journal entries with income lines but no client/project link
    orphan_income = [e for e in entries
                     if any(l["account_type"] == "income" for l in e["lines"])
                     and not e.get("client_id") and not e.get("project_id")]

    diff_income = round(acc_income - leg_collected, 2)
    return {
        "period": {"from_date": fd, "to_date": td, "label": label},
        "accounting": {
            "income": round(acc_income, 2),
            "expense": round(acc_expense, 2),
            "profit": round(acc_profit, 2),
            "je_count": len(entries),
        },
        "legacy": {
            "revenue_invoiced": round(leg_revenue, 2),
            "collected_via_milestones": round(leg_collected, 2),
            "outstanding_via_milestones": round(leg_outstanding, 2),
            "invoice_count": len(invoices),
            "milestone_count": len(milestones),
        },
        "difference": {
            "income_vs_milestones": diff_income,
            "match_within_1pc": abs(diff_income) <= max(1.0, 0.01 * max(acc_income, leg_collected)),
        },
        "diagnostics": {
            "orphan_paid_invoices": [
                {"id": i["id"], "invoice_number": i.get("invoice_number"),
                 "total": i.get("total"), "issue_date": i.get("issue_date")}
                for i in orphan_invoices[:20]
            ],
            "orphan_income_je": [
                {"id": e["id"], "date": e["date"], "narration": e.get("narration"),
                 "total": e.get("total")}
                for e in orphan_income[:20]
            ],
        },
        "recommendation": (
            "PASS — accounting matches legacy within tolerance; safe to retire legacy calc."
            if abs(diff_income) <= max(1.0, 0.01 * max(acc_income, leg_collected))
            else "REVIEW — investigate diagnostics before switching UI to accounting values."
        ),
    }


# ==================================================
# Balance Sheet  (Assets = Liabilities + Equity + Net Income)
# ==================================================
@router.get("/accounting/reports/balance-sheet")
async def balance_sheet(request: Request, as_of: Optional[str] = None,
                        fy: Optional[str] = None,
                        session_token: Optional[str] = Cookie(default=None),
                        authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    if not has_permission(user, "finance.read"):
        raise HTTPException(status_code=403, detail="Missing permission: finance.read")
    if fy and not as_of:
        _, as_of, _ = resolve_period(fy=fy)
    q = {}
    if as_of: q["date"] = {"$lte": as_of}
    entries = await sdb.journal_entries.find(q, {"_id": 0}).to_list(20000)

    accs = await sdb.accounts.find({}, {"_id": 0}).to_list(500)
    by_id = {a["id"]: a for a in accs}
    balances: dict = {}
    for a in accs:
        balances[a["id"]] = float(a.get("opening_balance") or 0)

    income_total = 0.0
    expense_total = 0.0
    for e in entries:
        for l in e["lines"]:
            acc = by_id.get(l["account_id"])
            if not acc: continue
            t = acc["type"]
            balances[l["account_id"]] += _movement_for(t, l["debit"], l["credit"])
            if t == "income":  income_total  += l["credit"] - l["debit"]
            if t == "expense": expense_total += l["debit"] - l["credit"]

    def _bucket(type_):
        rows = [{"account_id": a["id"], "name": a["name"], "balance": round(balances[a["id"]], 2)}
                for a in accs if a["type"] == type_ and abs(balances[a["id"]]) > 0.001]
        return rows, round(sum(r["balance"] for r in rows), 2)

    assets, total_assets = _bucket("asset")
    liabilities, total_liabilities = _bucket("liability")
    equity, total_equity = _bucket("equity")
    net_income = round(income_total - expense_total, 2)
    total_liab_eq = round(total_liabilities + total_equity + net_income, 2)
    delta = round(total_assets - total_liab_eq, 2)

    # Count JEs whose lines don't balance (data-integrity signal for the UI)
    unbalanced_jes: list = []
    for e in entries:
        d = round(sum(float(l.get("debit") or 0) for l in e["lines"]), 2)
        c = round(sum(float(l.get("credit") or 0) for l in e["lines"]), 2)
        if abs(d - c) > 0.01:
            unbalanced_jes.append({"id": e.get("id"), "date": e.get("date"),
                                   "narration": e.get("narration"),
                                   "debit": d, "credit": c, "diff": round(d - c, 2)})

    return {
        "as_of": as_of,
        "assets": {"rows": assets, "total": total_assets},
        "liabilities": {"rows": liabilities, "total": total_liabilities},
        "equity": {"rows": equity, "total": total_equity,
                   "net_income": net_income,
                   "total_with_net_income": round(total_equity + net_income, 2)},
        "total_assets": total_assets,
        "total_liabilities_and_equity": total_liab_eq,
        "balanced": abs(delta) < 0.01,
        "delta": delta,
        "unbalanced_journal_entries": unbalanced_jes,
    }


# ==================================================
# Balance-Sheet reconciliation
# ==================================================
@router.post("/accounting/reports/balance-sheet/reconcile")
async def reconcile_balance_sheet(request: Request,
                                  as_of: Optional[str] = None,
                                  session_token: Optional[str] = Cookie(default=None),
                                  authorization: Optional[str] = Header(default=None)):
    """Retained for API compatibility; automatic opening-balance mutation is disabled."""
    user = await require_user(request, session_token, authorization)
    if not has_permission(user, "finance.create"):
        raise HTTPException(status_code=403, detail="Missing permission: finance.create")

    raise HTTPException(
        status_code=409,
        detail=(
            "Automatic balance-sheet adjustment is disabled because it changes opening balances. "
            "Review the reported unbalanced entries and correct them with documented reversals."
        ),
    )


# ==================================================
# Cash Flow  (indirect-ish, aggregated by source)
# ==================================================
def _cash_flow_bucket(entry: dict, cash_ids: set[str], net: float) -> tuple[str, str]:
    """Classify one cash-moving journal without changing accounting totals."""
    source = entry.get("source") or "manual"
    base_source = source[:-9] if source.endswith("_reversal") else source
    counter_lines = [
        line for line in (entry.get("lines") or [])
        if line.get("account_id") not in cash_ids
    ]
    counter_types = {line.get("account_type") for line in counter_lines}
    counter_names = " ".join(str(line.get("account_name") or "") for line in counter_lines).lower()

    if base_source in {"loan_disbursement", "loan_emi", "loan_prepay"}:
        activity = "financing"
    elif base_source == "non_operating" and counter_types.intersection({"equity", "liability"}):
        activity = "financing"
    elif base_source == "non_operating" and "asset" in counter_types:
        activity = "investing"
    else:
        activity = "operating"

    labels = {
        "income": "Direct income receipts",
        "invoice_payment": "Client invoice collections",
        "milestone_payment": "Project milestone collections",
        "commission_income": "Commission receipts",
        "expense": "Operating expenses",
        "recurring_expense": "Recurring expenses",
        "vendor_payment": "Vendor payments",
        "payroll": "Payroll",
        "salary": "Payroll",
        "loan_disbursement": "Loan proceeds",
        "loan_emi": "Loan repayments",
        "loan_prepay": "Loan prepayments",
        "bank_statement": "Bank statement entries",
    }
    label = labels.get(base_source)
    if base_source == "non_operating":
        if "owner capital" in counter_names:
            label = "Owner capital introduced"
        elif "owner drawings" in counter_names:
            label = "Owner drawings"
        elif "investments - gold" in counter_names:
            label = "Gold investments"
        elif "advance to -" in counter_names:
            label = "Advance repayments received" if net > 0 else "Advances paid"
        elif "loan from -" in counter_names:
            label = "Loans received" if net > 0 else "Loan repayments"
        else:
            label = "Other balance-sheet movements"
    if not label:
        label = "Other operating receipts" if net > 0 else "Other operating payments"
    return activity, label


@router.get("/accounting/reports/cash-flow")
async def cash_flow_statement(request: Request,
                              from_date: Optional[str] = None,
                              to_date: Optional[str] = None,
                              fy: Optional[str] = None,
                              session_token: Optional[str] = Cookie(default=None),
                              authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    if not has_permission(user, "finance.read"):
        raise HTTPException(status_code=403, detail="Missing permission: finance.read")
    from_date, to_date, _ = resolve_period(fy, from_date, to_date)

    # Cash & bank accounts
    cash_accs = await sdb.accounts.find({"$or": [{"is_bank": True},
                                                 {"name": "Cash"},
                                                 {"name": "Petty Cash"}]},
                                       {"_id": 0}).to_list(50)
    cash_ids = {a["id"] for a in cash_accs}
    account_split = {
        a["id"]: {
            "account_id": a["id"], "name": a.get("name") or "Cash account",
            "opening_balance": float(a.get("opening_balance") or 0),
            "inflow": 0.0, "outflow": 0.0,
        }
        for a in cash_accs
    }

    opening_q: dict = {}
    if from_date: opening_q["date"] = {"$lt": from_date}
    period_q: dict = {}
    if from_date or to_date:
        d = {}
        if from_date: d["$gte"] = from_date
        if to_date:   d["$lte"] = to_date
        period_q["date"] = d

    # Opening balance = sum of movements on cash accounts before from_date
    opening = 0.0
    for a in cash_accs:
        opening += float(a.get("opening_balance") or 0)
    if from_date:
        async for e in sdb.journal_entries.find(opening_q, {"_id": 0, "lines": 1}):
            for l in e["lines"]:
                if l["account_id"] in cash_ids:
                    movement = float(l.get("debit") or 0) - float(l.get("credit") or 0)
                    opening += movement
                    account_split[l["account_id"]]["opening_balance"] += movement

    # Inflows / outflows within the period, bucketed by journal source.
    inflows: dict = {"income": 0.0, "client_payment": 0.0, "other": 0.0}
    outflows: dict = {"expense": 0.0, "vendor_payment": 0.0, "payroll": 0.0, "other": 0.0}
    activity_lines: dict = {"operating": {}, "investing": {}, "financing": {}}
    async for e in sdb.journal_entries.find(period_q, {"_id": 0}):
        net = 0.0
        for l in e["lines"]:
            if l["account_id"] in cash_ids:
                debit = float(l.get("debit") or 0)
                credit = float(l.get("credit") or 0)
                net += debit - credit
                account_split[l["account_id"]]["inflow"] += debit
                account_split[l["account_id"]]["outflow"] += credit
        if abs(net) < 0.001:
            continue
        src = e.get("source") or "other"
        if net > 0:
            key = "income" if src == "income" else ("client_payment" if src == "invoice_payment" else "other")
            inflows[key] = inflows.get(key, 0.0) + net
        else:
            key = ("expense" if src == "expense"
                   else "vendor_payment" if src == "vendor_payment"
                   else "payroll" if src in ("payroll", "salary")
                   else "other")
            outflows[key] = outflows.get(key, 0.0) + (-net)
        activity, label = _cash_flow_bucket(e, cash_ids, net)
        line = activity_lines[activity].setdefault(label, {"inflow": 0.0, "outflow": 0.0})
        if net > 0:
            line["inflow"] += net
        else:
            line["outflow"] += -net

    total_in = round(sum(inflows.values()), 2)
    total_out = round(sum(outflows.values()), 2)
    net_change = round(total_in - total_out, 2)
    closing = round(opening + net_change, 2)

    activities = {}
    for activity, grouped in activity_lines.items():
        lines = []
        for label, values in grouped.items():
            inflow = round(values["inflow"], 2)
            outflow = round(values["outflow"], 2)
            lines.append({"label": label, "inflow": inflow, "outflow": outflow,
                          "net": round(inflow - outflow, 2)})
        lines.sort(key=lambda row: (-abs(row["net"]), row["label"]))
        activity_in = round(sum(row["inflow"] for row in lines), 2)
        activity_out = round(sum(row["outflow"] for row in lines), 2)
        activities[activity] = {
            "inflow": activity_in, "outflow": activity_out,
            "net": round(activity_in - activity_out, 2), "lines": lines,
        }

    cash_accounts = []
    for split in account_split.values():
        account_opening = round(split["opening_balance"], 2)
        account_inflow = round(split["inflow"], 2)
        account_outflow = round(split["outflow"], 2)
        account_net = round(account_inflow - account_outflow, 2)
        cash_accounts.append({
            "account_id": split["account_id"], "name": split["name"],
            "opening_balance": account_opening, "inflow": account_inflow,
            "outflow": account_outflow, "net_change": account_net,
            "closing_balance": round(account_opening + account_net, 2),
        })
    cash_accounts.sort(key=lambda row: row["name"].lower())

    return {
        "from": from_date, "to": to_date,
        "opening_balance": round(opening, 2),
        "inflows": {k: round(v, 2) for k, v in inflows.items()},
        "outflows": {k: round(v, 2) for k, v in outflows.items()},
        "total_inflow": total_in,
        "total_outflow": total_out,
        "net_change": net_change,
        "closing_balance": closing,
        "activities": activities,
        "cash_accounts": cash_accounts,
    }


# ==================================================
# Enhanced Financial Dashboard extension
#   Adds: receivables (invoices), payables (vendor bills), monthly trend
# ==================================================
@router.get("/accounting/dashboard/extended")
async def finance_dashboard_extended(request: Request,
                                     session_token: Optional[str] = Cookie(default=None),
                                     authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    if not has_permission(user, "finance.read"):
        raise HTTPException(status_code=403, detail="Missing permission: finance.read")

    # Receivables = unpaid invoices
    receivables_total = 0.0
    receivables_overdue = 0.0
    today = business_today().isoformat()
    async for inv in sdb.invoices.find({"status": {"$in": ["sent", "overdue", "partially_paid"]},
                                       "doc_type": {"$ne": "quotation"}},
                                      {"_id": 0}):
        amt = float(inv.get("total") or 0)
        receivables_total += amt
        if (inv.get("due_date") or "") < today:
            receivables_overdue += amt

    # Payables = unpaid vendor bills
    payables_total = 0.0
    payables_overdue = 0.0
    async for b in sdb.vendor_bills.find({"status": {"$in": ["received", "partially_paid", "overdue"]}},
                                        {"_id": 0}):
        out = float(b.get("outstanding") or b.get("total") or 0)
        payables_total += out
        if (b.get("due_date") or "") < today:
            payables_overdue += out

    # 12-month trend (income + expense per month)
    now = business_today()
    year_start_month = now.replace(day=1)
    months = []
    for i in range(11, -1, -1):
        y = year_start_month.year
        m = year_start_month.month - i
        while m <= 0:
            m += 12; y -= 1
        key = f"{y:04d}-{m:02d}"
        months.append({"key": key, "income": 0.0, "expense": 0.0})

    key_index = {m["key"]: m for m in months}
    async for e in sdb.journal_entries.find(
        {"date": {"$gte": months[0]["key"] + "-01"}}, {"_id": 0}
    ):
        mkey = (e.get("date") or "")[:7]
        bucket = key_index.get(mkey)
        if not bucket:
            continue
        for l in e["lines"]:
            if l["account_type"] == "income":
                bucket["income"] += l["credit"] - l["debit"]
            elif l["account_type"] == "expense":
                bucket["expense"] += l["debit"] - l["credit"]
    for m in months:
        m["income"] = round(m["income"], 2)
        m["expense"] = round(m["expense"], 2)
        m["profit"] = round(m["income"] - m["expense"], 2)

    # Expense breakdown by category — current month
    month_start = f"{now.year:04d}-{now.month:02d}-01"
    expense_by_cat: dict = {}
    async for e in sdb.journal_entries.find(
        {"date": {"$gte": month_start}}, {"_id": 0}
    ):
        for l in e["lines"]:
            if l["account_type"] == "expense":
                k = l["account_name"]
                expense_by_cat[k] = expense_by_cat.get(k, 0.0) + (l["debit"] - l["credit"])
    expense_breakdown = sorted(
        [{"category": k, "amount": round(v, 2)} for k, v in expense_by_cat.items() if v > 0],
        key=lambda x: -x["amount"],
    )[:10]

    return {
        "receivables": {"total": round(receivables_total, 2),
                        "overdue": round(receivables_overdue, 2)},
        "payables":    {"total": round(payables_total, 2),
                        "overdue": round(payables_overdue, 2)},
        "monthly_trend": months,
        "expense_breakdown": expense_breakdown,
    }


# ==================================================
# CSV Exports  (returns text/csv download)
# ==================================================
from fastapi.responses import Response as FastAPIResponse
import csv, io


def _csv_response(filename: str, rows: list, headers: list) -> FastAPIResponse:
    buf = io.StringIO()
    from core.csv_safe import SafeWriter
    w = SafeWriter(buf)
    w.writerow(headers)
    for r in rows:
        w.writerow([r.get(h, "") for h in headers])
    return FastAPIResponse(
        content=buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": content_disposition(
            "attachment", filename, "report.csv")},
    )


@router.get("/accounting/reports/pl.csv")
async def export_pl_csv(request: Request,
                        from_date: Optional[str] = None, to_date: Optional[str] = None,
                        fy: Optional[str] = None,
                        project_id: Optional[str] = None,
                        session_token: Optional[str] = Cookie(default=None),
                        authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    if not has_permission(user, "finance.read"):
        raise HTTPException(status_code=403, detail="Missing permission")
    data = await profit_and_loss(request, from_date=from_date, to_date=to_date, fy=fy,
                                 project_id=project_id,
                                 session_token=session_token, authorization=authorization)
    rows = [{"section": "Income", "account": r["name"], "amount": r["amount"]} for r in data["income"]]
    rows.append({"section": "", "account": "TOTAL INCOME", "amount": data["total_income"]})
    rows += [{"section": "Expense", "account": r["name"], "amount": r["amount"]} for r in data["expense"]]
    rows.append({"section": "", "account": "TOTAL EXPENSE", "amount": data["total_expense"]})
    rows.append({"section": "", "account": "NET PROFIT", "amount": data["net_profit"]})
    return _csv_response("profit-loss.csv", rows, ["section", "account", "amount"])


@router.get("/accounting/reports/trial-balance.csv")
async def export_tb_csv(request: Request, as_of: Optional[str] = None,
                        fy: Optional[str] = None,
                        session_token: Optional[str] = Cookie(default=None),
                        authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    if not has_permission(user, "finance.read"):
        raise HTTPException(status_code=403, detail="Missing permission")
    data = await trial_balance(request, as_of=as_of, fy=fy,
                               session_token=session_token, authorization=authorization)
    return _csv_response("trial-balance.csv", data["rows"],
                         ["account_name", "account_type", "debit", "credit", "balance"])


@router.get("/accounting/reports/balance-sheet.csv")
async def export_bs_csv(request: Request, as_of: Optional[str] = None,
                        fy: Optional[str] = None,
                        session_token: Optional[str] = Cookie(default=None),
                        authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    if not has_permission(user, "finance.read"):
        raise HTTPException(status_code=403, detail="Missing permission")
    data = await balance_sheet(request, as_of=as_of, fy=fy,
                               session_token=session_token, authorization=authorization)
    rows = []
    for r in data["assets"]["rows"]:      rows.append({"section": "Assets", "name": r["name"], "balance": r["balance"]})
    rows.append({"section": "", "name": "TOTAL ASSETS", "balance": data["assets"]["total"]})
    for r in data["liabilities"]["rows"]: rows.append({"section": "Liabilities", "name": r["name"], "balance": r["balance"]})
    rows.append({"section": "", "name": "TOTAL LIABILITIES", "balance": data["liabilities"]["total"]})
    for r in data["equity"]["rows"]:      rows.append({"section": "Equity", "name": r["name"], "balance": r["balance"]})
    rows.append({"section": "Equity", "name": "Net Income (period)", "balance": data["equity"]["net_income"]})
    rows.append({"section": "", "name": "TOTAL LIAB + EQ + NI", "balance": data["total_liabilities_and_equity"]})
    return _csv_response("balance-sheet.csv", rows, ["section", "name", "balance"])


@router.get("/accounting/reports/cash-flow.csv")
async def export_cf_csv(request: Request,
                        from_date: Optional[str] = None, to_date: Optional[str] = None,
                        fy: Optional[str] = None,
                        session_token: Optional[str] = Cookie(default=None),
                        authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    if not has_permission(user, "finance.read"):
        raise HTTPException(status_code=403, detail="Missing permission")
    data = await cash_flow_statement(request, from_date=from_date, to_date=to_date, fy=fy,
                                     session_token=session_token, authorization=authorization)
    rows = [{"section": "", "line": "Opening balance", "amount": data["opening_balance"]}]
    for k, v in data["inflows"].items():  rows.append({"section": "Inflow",  "line": k, "amount": v})
    rows.append({"section": "", "line": "Total inflow", "amount": data["total_inflow"]})
    for k, v in data["outflows"].items(): rows.append({"section": "Outflow", "line": k, "amount": v})
    rows.append({"section": "", "line": "Total outflow", "amount": data["total_outflow"]})
    for activity, detail in data.get("activities", {}).items():
        for line in detail.get("lines", []):
            rows.append({"section": f"{activity.title()} activities",
                         "line": line["label"], "amount": line["net"]})
        rows.append({"section": f"{activity.title()} activities",
                     "line": "Net cash flow", "amount": detail["net"]})
    for account in data.get("cash_accounts", []):
        rows.append({"section": "Cash and bank closing balances",
                     "line": account["name"], "amount": account["closing_balance"]})
    rows.append({"section": "", "line": "Net change", "amount": data["net_change"]})
    rows.append({"section": "", "line": "Closing balance", "amount": data["closing_balance"]})
    return _csv_response("cash-flow.csv", rows, ["section", "line", "amount"])


@router.get("/journal-entries.csv")
async def export_journal_csv(request: Request,
                             from_date: Optional[str] = None, to_date: Optional[str] = None,
                             fy: Optional[str] = None,
                             project_id: Optional[str] = None, client_id: Optional[str] = None,
                             vendor_id: Optional[str] = None, source: Optional[str] = None,
                             session_token: Optional[str] = Cookie(default=None),
                             authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    if not has_permission(user, "finance.read"):
        raise HTTPException(status_code=403, detail="Missing permission")
    from_date, to_date, _ = resolve_period(fy, from_date, to_date)
    q: dict = {"voided_from_view": {"$ne": True}}
    if from_date or to_date:
        d = {}
        if from_date: d["$gte"] = from_date
        if to_date:   d["$lte"] = to_date
        q["date"] = d
    if project_id: q["project_id"] = project_id
    if client_id:  q["client_id"] = client_id
    if vendor_id:  q["vendor_id"] = vendor_id
    if source:     q["source"] = source

    rows = []
    async for e in sdb.journal_entries.find(q, {"_id": 0}).sort("date", 1):
        for l in e["lines"]:
            rows.append({
                "date": e["date"],
                "reference": e.get("reference") or "",
                "narration": e.get("narration") or "",
                "source": e.get("source") or "",
                "account": l.get("account_name"),
                "account_type": l.get("account_type"),
                "debit": l.get("debit", 0),
                "credit": l.get("credit", 0),
                "project_id": e.get("project_id") or "",
                "client_id": e.get("client_id") or "",
                "vendor_id": e.get("vendor_id") or "",
            })
    return _csv_response("journal.csv", rows,
        ["date", "reference", "narration", "source", "account", "account_type",
         "debit", "credit", "project_id", "client_id", "vendor_id"])


# ==================================================
# Payment Milestones per project
# ==================================================
@router.get("/projects/{project_id}/milestones")
async def list_milestones(project_id: str, request: Request,
                          session_token: Optional[str] = Cookie(default=None),
                          authorization: Optional[str] = Header(default=None)):
    await require_user(request, session_token, authorization)
    rows = await sdb.payment_milestones.find({"project_id": project_id}, {"_id": 0}).sort("due_date", 1).to_list(200)
    return rows


@router.post("/projects/{project_id}/milestones")
async def add_milestone(project_id: str, payload: MilestoneIn, request: Request,
                        session_token: Optional[str] = Cookie(default=None),
                        authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    if not has_permission(user, "projects.update"):
        raise HTTPException(status_code=403, detail="Missing permission")
    proj = await sdb.projects.find_one({"id": project_id}, {"_id": 0})
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")

    amount = payload.amount
    if amount is None and payload.percent is not None:
        amount = round(float(proj.get("budget") or 0) * float(payload.percent) / 100.0, 2)
    if not amount or amount <= 0:
        raise HTTPException(
            status_code=400,
            detail="Milestone amount must be positive; set an amount or a project budget",
        )

    doc = {
        "id": new_id("ms_"),
        "project_id": project_id,
        "org_id": user_org_id(user),
        "name": payload.name,
        "percent": payload.percent,
        "amount": amount,
        "due_date": payload.due_date,
        "status": "pending",
        "notes": payload.notes,
        "created_at": iso_now(),
        "created_by": user["user_id"],
    }
    await sdb.payment_milestones.insert_one(dict(doc))
    await audit(user, "milestone.create", target=doc["id"], target_type="milestone",
                meta={"project_id": project_id, "amount": amount})
    return await sdb.payment_milestones.find_one({"id": doc["id"]}, {"_id": 0})


@router.patch("/milestones/{ms_id}")
async def update_milestone(ms_id: str, payload: MilestoneUpdate, request: Request,
                           session_token: Optional[str] = Cookie(default=None),
                           authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    if not has_permission(user, "projects.update"):
        raise HTTPException(status_code=403, detail="Missing permission")
    existing_ms = await sdb.payment_milestones.find_one({"id": ms_id}, {"_id": 0})
    if not existing_ms:
        raise HTTPException(status_code=404, detail="Milestone not found")
    upd = {k: v for k, v in payload.model_dump().items() if v is not None}
    if "status" in upd and upd["status"] not in {"pending", "invoiced", "paid"}:
        raise HTTPException(status_code=400, detail="Invalid milestone status")
    if existing_ms.get("status") == "paid" and {"amount", "percent"}.intersection(upd):
        raise HTTPException(status_code=409, detail="Reverse the payment before changing a paid milestone amount")
    if "percent" in upd and "amount" not in upd:
        project = await sdb.projects.find_one(
            {"id": existing_ms.get("project_id")}, {"_id": 0, "budget": 1})
        amount = round(float((project or {}).get("budget") or 0) * float(upd["percent"]) / 100.0, 2)
        if amount <= 0:
            raise HTTPException(
                status_code=400,
                detail="Cannot calculate this percentage without a positive project budget",
            )
        upd["amount"] = amount
    if upd.get("status") == "paid" and existing_ms.get("status") != "paid" \
            and not has_permission(user, "finance.create"):
        raise HTTPException(status_code=403, detail="Missing permission: finance.create")
    if upd.get("status") and upd["status"] != "paid" and existing_ms.get("status") == "paid" \
            and not has_permission(user, "finance.update"):
        raise HTTPException(status_code=403, detail="Missing permission: finance.update")
    upd["updated_at"] = iso_now()
    # Milestone marked paid → accounting is the source of truth: auto-post
    # the receipt JE (idempotent) so books & dashboards stay reconciled.
    if upd.get("status") == "paid" and existing_ms.get("status") != "paid":
        amount = float(upd.get("amount") or existing_ms.get("amount") or 0)
        if amount > 0:
            proj = await sdb.projects.find_one(
                {"id": existing_ms.get("project_id")}, {"_id": 0, "client_id": 1, "name": 1})
            je = await post_receipt_je(
                user, amount=amount, date=business_today().isoformat(),
                narration=f"Milestone payment · {existing_ms.get('name') or ms_id}"
                          + (f" · {proj.get('name')}" if proj else ""),
                source="milestone_payment", source_id=ms_id,
                project_id=existing_ms.get("project_id"),
                client_id=(proj or {}).get("client_id"))
            if je:
                upd["journal_id"] = je["id"]
                upd.setdefault("paid_amount", amount)
                upd.setdefault("paid_at", iso_now())
    elif upd.get("status") and upd["status"] != "paid" and existing_ms.get("status") == "paid":
        await reverse_receipt_je(user, source="milestone_payment", source_id=ms_id,
                                 narration=f"Milestone payment reversed · {existing_ms.get('name') or ms_id}")
        upd["journal_id"] = None
        upd["paid_amount"] = None
        upd["paid_at"] = None
    await sdb.payment_milestones.update_one({"id": ms_id}, {"$set": upd})
    await audit(user, "milestone.update", target=ms_id, target_type="milestone",
                meta={"fields": sorted(k for k in upd if k != "updated_at")})
    return await sdb.payment_milestones.find_one({"id": ms_id}, {"_id": 0})


@router.delete("/milestones/{ms_id}")
async def delete_milestone(ms_id: str, request: Request,
                           session_token: Optional[str] = Cookie(default=None),
                           authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    if not has_permission(user, "projects.update"):
        raise HTTPException(status_code=403, detail="Missing permission")
    milestone = await sdb.payment_milestones.find_one({"id": ms_id}, {"_id": 0})
    if not milestone:
        raise HTTPException(status_code=404, detail="Milestone not found")
    active_receipt = await sdb.journal_entries.find_one(
        {"source": "milestone_payment", "source_id": ms_id, "reversed": {"$ne": True}},
        {"_id": 0, "id": 1},
    )
    if milestone.get("status") == "paid" or active_receipt:
        raise HTTPException(
            status_code=409,
            detail="Reverse the milestone payment before deleting this milestone",
        )
    await sdb.payment_milestones.delete_one({"id": ms_id})
    await audit(user, "milestone.delete", target=ms_id, target_type="milestone",
                meta={"project_id": milestone.get("project_id"),
                      "amount": milestone.get("amount")})
    return {"ok": True}


# ==================================================
# Vendors master — moved to routes/vendors.py (Phase-2 enterprise vendor mgmt)
# The `db.vendors_acc` collection continues to be the source of truth so
# existing journal entries with `vendor_id` and the vendor_ledger endpoint
# above keep working unchanged.
# ==================================================


# ==================================================
# Meta / seed
# ==================================================
@router.post("/accounting/repair/orphan-invoices")
async def repair_orphan_invoices(request: Request,
                                 session_token: Optional[str] = Cookie(default=None),
                                 authorization: Optional[str] = Header(default=None)):
    """Post the missing receipt JEs for invoices already marked paid but never
    booked (legacy data). Idempotent — safe to run repeatedly. Admin only."""
    user = await require_user(request, session_token, authorization)
    if not has_permission(user, "*.*"):
        raise HTTPException(403, "Admin only")
    repaired, skipped = [], []
    async for inv in sdb.invoices.find(
            {"status": "paid", "doc_type": {"$ne": "quotation"}}, {"_id": 0}):
        existing = await sdb.journal_entries.find_one(
            {"source": "invoice_payment", "source_id": inv["id"],
             "reversed": {"$ne": True}}, {"_id": 0, "id": 1})
        if existing:
            continue
        amount = float(inv.get("total") or 0)
        if amount <= 0:
            skipped.append({"invoice_id": inv["id"], "reason": "zero total"})
            continue
        pay_date = (inv.get("paid_date") or (inv.get("created_at") or "")[:10]
                    or business_today().isoformat())
        je = await post_receipt_je(
            user, amount=amount, date=pay_date,
            narration=f"Invoice {inv.get('number') or inv['id']} payment received (repair)"
                      + (f" · {inv.get('client_name')}" if inv.get("client_name") else ""),
            source="invoice_payment", source_id=inv["id"],
            reference=inv.get("number"),
            project_id=inv.get("project_id"), client_id=inv.get("client_id"))
        if je:
            await sdb.invoices.update_one(
                {"id": inv["id"]},
                {"$set": {"journal_id": je["id"], "paid_date": pay_date}})
            repaired.append({"invoice_id": inv["id"], "number": inv.get("number"),
                             "amount": amount, "je_id": je["id"]})
        else:
            skipped.append({"invoice_id": inv["id"], "reason": "no COA accounts"})
    return {"ok": True, "repaired": repaired, "skipped": skipped,
            "repaired_count": len(repaired)}


@router.post("/accounting/seed-coa")
async def seed_coa(request: Request,
                   session_token: Optional[str] = Cookie(default=None),
                   authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    if not has_permission(user, "finance.create"):
        raise HTTPException(status_code=403, detail="Missing permission: finance.create")
    await _seed_coa_if_empty()
    n = await sdb.accounts.count_documents({})
    return {"ok": True, "accounts": n}


@router.get("/accounting/meta")
async def accounting_meta(request: Request,
                          session_token: Optional[str] = Cookie(default=None),
                          authorization: Optional[str] = Header(default=None)):
    await require_user(request, session_token, authorization)
    await _seed_coa_if_empty()
    return {
        "account_types": ACCOUNT_TYPES,
        "payment_methods": PAYMENT_METHODS,
    }
