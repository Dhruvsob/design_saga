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

from core.db import db
from core.scoped_db import sdb
from core.helpers import now_utc, iso_now, new_id
from core.deps import require_user
from core.rbac import has_permission
from core.tenancy import user_org_id
from core.finance import resolve_period, current_fy_label, fy_choices, fy_range
from models.accounting import (
    AccountIn, JournalIn, IncomeIn, ExpenseIn,
    MilestoneIn, MilestoneUpdate,
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


# ==================================================
# Chart of Accounts
# ==================================================
async def _seed_coa_if_empty():
    """Idempotent seed — inserts only the DEFAULT_COA accounts that are missing.
    Runs on every /accounts fetch so newly-shipped default accounts (e.g. new
    income categories) show up on existing installations without a migration."""
    existing_names = {a["name"] async for a in sdb.accounts.find({}, {"_id": 0, "name": 1})}
    for name, typ, code in DEFAULT_COA:
        if name in existing_names:
            continue
        await sdb.accounts.insert_one({
            "id": new_id("acc_"),
            "name": name,
            "type": typ,
            "code": code,
            "is_bank": name.lower().startswith("bank") or name.lower() in ("cash", "petty cash"),
            "opening_balance": 0.0,
            "active": True,
            "created_at": iso_now(),
            "seeded": True,
        })


@router.get("/accounts")
async def list_accounts(request: Request,
                        type: Optional[str] = None,
                        session_token: Optional[str] = Cookie(default=None),
                        authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    if not has_permission(user, "finance.read"):
        raise HTTPException(status_code=403, detail="Missing permission: finance.read")
    await _seed_coa_if_empty()
    q = {"active": True}
    if type: q["type"] = type
    rows = await sdb.accounts.find(q, {"_id": 0}).sort("code", 1).to_list(1000)
    return rows


@router.post("/accounts")
async def create_account(payload: AccountIn, request: Request,
                         session_token: Optional[str] = Cookie(default=None),
                         authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    if not has_permission(user, "invoices.create"):
        raise HTTPException(status_code=403, detail="Missing permission")
    if payload.type not in ACCOUNT_TYPES:
        raise HTTPException(status_code=400, detail="Invalid account type")
    doc = payload.model_dump()
    doc["id"] = new_id("acc_")
    doc["created_at"] = iso_now()
    doc["created_by"] = user["user_id"]
    doc.setdefault("active", True)
    doc.setdefault("opening_balance", 0.0)
    await sdb.accounts.insert_one(dict(doc))
    return await sdb.accounts.find_one({"id": doc["id"]}, {"_id": 0})


@router.patch("/accounts/{acc_id}")
async def update_account(acc_id: str, payload: AccountIn, request: Request,
                         session_token: Optional[str] = Cookie(default=None),
                         authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    if not has_permission(user, "invoices.update"):
        raise HTTPException(status_code=403, detail="Missing permission")
    upd = {k: v for k, v in payload.model_dump().items() if v is not None}
    upd["updated_at"] = iso_now()
    await sdb.accounts.update_one({"id": acc_id}, {"$set": upd})
    return await sdb.accounts.find_one({"id": acc_id}, {"_id": 0})


@router.delete("/accounts/{acc_id}")
async def deactivate_account(acc_id: str, request: Request,
                             session_token: Optional[str] = Cookie(default=None),
                             authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    if not has_permission(user, "invoices.update"):
        raise HTTPException(status_code=403, detail="Missing permission")
    # Soft delete — audit-safe
    await sdb.accounts.update_one({"id": acc_id}, {"$set": {"active": False, "deactivated_at": iso_now()}})
    return {"ok": True}


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


async def post_receipt_je(user: dict, *, amount: float, date: str, narration: str,
                          source: str, source_id: str, reference: str = None,
                          project_id: str = None, client_id: str = None) -> Optional[dict]:
    """Auto-post DR Bank / CR Income for a payment received (invoice/milestone).
    Idempotent on (source, source_id). Returns the JE or None if COA missing."""
    existing = await sdb.journal_entries.find_one(
        {"source": source, "source_id": source_id, "reversed": {"$ne": True}}, {"_id": 0})
    if existing:
        return existing
    bank, income = await default_receipt_accounts()
    if not bank or not income:
        return None
    lines = [
        {"account_id": bank["id"], "debit": amount, "credit": 0, "description": "Received"},
        {"account_id": income["id"], "debit": 0, "credit": amount, "description": "Revenue"},
    ]
    return await _post_journal(user, date, narration, lines, reference=reference,
                               project_id=project_id, client_id=client_id,
                               source=source, source_id=source_id)


async def reverse_receipt_je(user: dict, *, source: str, source_id: str,
                             narration: str) -> Optional[dict]:
    """Post a balanced reversing JE for a previously auto-posted receipt
    (e.g. invoice un-marked as paid). Idempotent."""
    orig = await sdb.journal_entries.find_one(
        {"source": source, "source_id": source_id, "reversed": {"$ne": True}}, {"_id": 0})
    if not orig:
        return None
    rev_lines = [
        {"account_id": l["account_id"], "debit": l["credit"], "credit": l["debit"],
         "description": f"Reversal · {l.get('description') or ''}".strip()}
        for l in orig["lines"]
    ]
    rev = await _post_journal(user, now_utc().date().isoformat(), narration, rev_lines,
                              reference=orig.get("reference"),
                              project_id=orig.get("project_id"),
                              client_id=orig.get("client_id"),
                              source=f"{source}_reversal", source_id=source_id)
    await sdb.journal_entries.update_one(
        {"id": orig["id"]}, {"$set": {"reversed": True, "reversal_je_id": rev["id"]}})
    return rev


async def _post_journal(user: dict, date: str, narration: str, lines: list,
                        reference: str = None, project_id: str = None,
                        client_id: str = None, vendor_id: str = None,
                        employee_id: str = None,
                        source: str = "manual", source_id: str = None) -> dict:
    """Persist a balanced journal entry. `lines` = [{account_id, debit, credit, description}, ...]"""
    total_debit = sum(float(l.get("debit") or 0) for l in lines)
    total_credit = sum(float(l.get("credit") or 0) for l in lines)
    if round(total_debit, 2) != round(total_credit, 2):
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
        if not acc:
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
        "narration": narration,
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
    await sdb.journal_entries.insert_one(dict(doc))
    return await sdb.journal_entries.find_one({"id": doc["id"]}, {"_id": 0})


@router.post("/journal-entries")
async def create_journal(payload: JournalIn, request: Request,
                         session_token: Optional[str] = Cookie(default=None),
                         authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    if not has_permission(user, "invoices.create"):
        raise HTTPException(status_code=403, detail="Missing permission")
    lines = [l.model_dump() for l in payload.lines]
    return await _post_journal(
        user, payload.date, payload.narration, lines,
        reference=payload.reference, project_id=payload.project_id,
        client_id=payload.client_id, vendor_id=payload.vendor_id,
        employee_id=payload.employee_id,
    )


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
                       session_token: Optional[str] = Cookie(default=None),
                       authorization: Optional[str] = Header(default=None)):
    await require_user(request, session_token, authorization)
    fd, td, _ = resolve_period(fy, from_date, to_date)
    q: dict = {}
    if fd or td:
        d = {}
        if fd: d["$gte"] = fd
        if td: d["$lte"] = td
        q["date"] = d
    if account_id: q["lines.account_id"] = account_id
    if project_id: q["project_id"] = project_id
    if client_id: q["client_id"] = client_id
    if vendor_id: q["vendor_id"] = vendor_id
    if employee_id: q["employee_id"] = employee_id
    if source: q["source"] = source
    rows = await sdb.journal_entries.find(q, {"_id": 0}).sort("date", -1).limit(1000).to_list(1000)
    return rows


# ==================================================
# Income (payment received) — convenience wrapper
# ==================================================
@router.post("/accounting/income")
async def create_income(payload: IncomeIn, request: Request,
                        session_token: Optional[str] = Cookie(default=None),
                        authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    if not has_permission(user, "invoices.create"):
        raise HTTPException(status_code=403, detail="Missing permission")
    if payload.amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be > 0")
    narration = payload.notes or f"Payment received via {payload.payment_method}"
    lines = [
        {"account_id": payload.bank_account_id, "debit": payload.amount, "credit": 0,
         "description": "Received"},
        {"account_id": payload.income_account_id, "debit": 0, "credit": payload.amount,
         "description": "Revenue"},
    ]
    je = await _post_journal(
        user, payload.date, narration, lines,
        reference=payload.reference, project_id=payload.project_id,
        client_id=payload.client_id, vendor_id=payload.vendor_id,
        employee_id=payload.employee_id,
        source="invoice_payment" if payload.invoice_id else "income",
        source_id=payload.invoice_id or payload.milestone_id,
    )

    # If linked to a milestone, mark it paid
    if payload.milestone_id:
        await sdb.payment_milestones.update_one(
            {"id": payload.milestone_id},
            {"$set": {"status": "paid", "paid_amount": payload.amount,
                      "paid_at": iso_now(), "journal_id": je["id"]}}
        )
    # If linked to an invoice, mark it paid (closes the
    # Client → Invoice → Payment → Accounting loop)
    if payload.invoice_id:
        await sdb.invoices.update_one(
            {"id": payload.invoice_id},
            {"$set": {"status": "paid", "paid_date": payload.date,
                      "journal_id": je["id"], "updated_at": iso_now()}}
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
    if not has_permission(user, "invoices.create"):
        raise HTTPException(status_code=403, detail="Missing permission")
    if payload.amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be > 0")

    narration = payload.notes or f"Expense — {payload.payment_method}"
    base_amt = float(payload.amount)
    gst_amt = float(payload.gst or 0)
    total = round(base_amt + gst_amt, 2)

    lines = [
        {"account_id": payload.expense_account_id, "debit": base_amt, "credit": 0,
         "description": "Expense"},
    ]
    if gst_amt > 0:
        gst_acc = await sdb.accounts.find_one({"name": "GST Payable"}, {"_id": 0, "id": 1})
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

    q: dict = {"lines.account_id": acc_id}
    if from_date or to_date:
        d = {}
        if from_date: d["$gte"] = from_date
        if to_date: d["$lte"] = to_date
        q["date"] = d
    entries = await sdb.journal_entries.find(q, {"_id": 0}).sort("date", 1).to_list(2000)

    rows, running = [], float(acc.get("opening_balance") or 0)
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
    return {"account": acc, "opening_balance": float(acc.get("opening_balance") or 0),
            "closing_balance": round(running, 2),
            "total_debit": round(total_debit, 2), "total_credit": round(total_credit, 2),
            "rows": rows}


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
            {field: entity_id, "date": {"$lt": from_date}}, {"_id": 0}
        ):
            opening += _entity_net(e)

    # Period entries
    q: dict = {field: entity_id}
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
    await require_user(request, session_token, authorization)
    # If FY supplied but as_of not, treat as_of = fy end.
    if fy and not as_of:
        _, as_of = fy_range(fy)
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
    today = now_utc().date().isoformat()
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
    for e in entries_month:
        for l in e["lines"]:
            if l["account_type"] == "income":
                income_month += l["credit"] - l["debit"]
                if e["date"] == today and e.get("source") == "income":
                    today_collections += l["credit"] - l["debit"]
            elif l["account_type"] == "expense":
                expense_month += l["debit"] - l["credit"]
                if l["account_name"] == "Employee Salary":
                    salary_month += l["debit"] - l["credit"]

    # Outstanding = pending milestones amount
    ms = await sdb.payment_milestones.find({"status": {"$ne": "paid"}}, {"_id": 0, "amount": 1, "due_date": 1, "status": 1}).to_list(500)
    outstanding = round(sum(float(m.get("amount") or 0) for m in ms), 2)
    overdue = round(sum(float(m.get("amount") or 0) for m in ms
                       if (m.get("due_date") or "") < today), 2)

    # Upcoming payments (next 30 days)
    horizon = (now_utc().date() + timedelta(days=30)).isoformat()
    upcoming = [m for m in ms if today <= (m.get("due_date") or "") <= horizon]

    # Recent transactions
    recent = await sdb.journal_entries.find({}, {"_id": 0}).sort("created_at", -1).limit(10).to_list(10)

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
    q: dict = {}
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
        _, as_of = fy_range(fy)
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
    """Close a small imbalance by parking the delta on 'Opening Balance Adjustment'.

    Strategy — cannot fix imbalance via a balanced JE (both sides cancel), so we
    directly adjust the `opening_balance` of the reserved equity account
    'Opening Balance Adjustment'. This keeps the audit trail intact:
    every original journal entry is preserved untouched.

    Requires `finance.create` permission.
    """
    user = await require_user(request, session_token, authorization)
    if not has_permission(user, "finance.create"):
        raise HTTPException(status_code=403, detail="Missing permission: finance.create")

    # Recompute current delta
    bs = await balance_sheet(request, as_of=as_of,
                             session_token=session_token,
                             authorization=authorization)
    delta = float(bs.get("delta") or 0)
    if abs(delta) < 0.01:
        return {"ok": True, "delta": 0.0, "adjusted": False,
                "message": "Balance sheet already balanced."}

    await _seed_coa_if_empty()
    adj_acc = await sdb.accounts.find_one({"name": "Opening Balance Adjustment"}, {"_id": 0})
    if not adj_acc:
        raise HTTPException(500, "Opening Balance Adjustment account missing")

    # If assets > liab+eq by `delta`, we need liab+eq up by `delta`.
    # Adjustment account is equity: increasing its opening_balance raises equity.
    new_opening = round(float(adj_acc.get("opening_balance") or 0) + delta, 2)
    await sdb.accounts.update_one(
        {"id": adj_acc["id"]},
        {"$set": {"opening_balance": new_opening,
                  "reconciled_at": iso_now(),
                  "reconciled_by": user["user_id"]}}
    )
    return {"ok": True, "delta": delta, "adjusted": True,
            "adjustment_amount": delta,
            "adjustment_account_id": adj_acc["id"],
            "new_opening_balance": new_opening,
            "message": f"Parked ₹{delta} on 'Opening Balance Adjustment' to reconcile."}


# ==================================================
# Cash Flow  (indirect-ish, aggregated by source)
# ==================================================
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
                    opening += l["debit"] - l["credit"]

    # Inflows / outflows within the period, bucketed by journal source.
    inflows: dict = {"income": 0.0, "client_payment": 0.0, "other": 0.0}
    outflows: dict = {"expense": 0.0, "vendor_payment": 0.0, "payroll": 0.0, "other": 0.0}
    async for e in sdb.journal_entries.find(period_q, {"_id": 0}):
        net = 0.0
        for l in e["lines"]:
            if l["account_id"] in cash_ids:
                net += l["debit"] - l["credit"]
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

    total_in = round(sum(inflows.values()), 2)
    total_out = round(sum(outflows.values()), 2)
    net_change = round(total_in - total_out, 2)
    closing = round(opening + net_change, 2)

    return {
        "from": from_date, "to": to_date,
        "opening_balance": round(opening, 2),
        "inflows": {k: round(v, 2) for k, v in inflows.items()},
        "outflows": {k: round(v, 2) for k, v in outflows.items()},
        "total_inflow": total_in,
        "total_outflow": total_out,
        "net_change": net_change,
        "closing_balance": closing,
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
    today = now_utc().date().isoformat()
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
    now = now_utc().date()
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
    w = csv.writer(buf)
    w.writerow(headers)
    for r in rows:
        w.writerow([r.get(h, "") for h in headers])
    return FastAPIResponse(
        content=buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/accounting/reports/pl.csv")
async def export_pl_csv(request: Request,
                        from_date: Optional[str] = None, to_date: Optional[str] = None,
                        project_id: Optional[str] = None,
                        session_token: Optional[str] = Cookie(default=None),
                        authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    if not has_permission(user, "finance.read"):
        raise HTTPException(status_code=403, detail="Missing permission")
    data = await profit_and_loss(request, from_date=from_date, to_date=to_date,
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
                        session_token: Optional[str] = Cookie(default=None),
                        authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    if not has_permission(user, "finance.read"):
        raise HTTPException(status_code=403, detail="Missing permission")
    data = await trial_balance(request, as_of=as_of,
                               session_token=session_token, authorization=authorization)
    return _csv_response("trial-balance.csv", data["rows"],
                         ["account_name", "account_type", "debit", "credit", "balance"])


@router.get("/accounting/reports/balance-sheet.csv")
async def export_bs_csv(request: Request, as_of: Optional[str] = None,
                        session_token: Optional[str] = Cookie(default=None),
                        authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    if not has_permission(user, "finance.read"):
        raise HTTPException(status_code=403, detail="Missing permission")
    data = await balance_sheet(request, as_of=as_of,
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
                        session_token: Optional[str] = Cookie(default=None),
                        authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    if not has_permission(user, "finance.read"):
        raise HTTPException(status_code=403, detail="Missing permission")
    data = await cash_flow_statement(request, from_date=from_date, to_date=to_date,
                                     session_token=session_token, authorization=authorization)
    rows = [{"section": "", "line": "Opening balance", "amount": data["opening_balance"]}]
    for k, v in data["inflows"].items():  rows.append({"section": "Inflow",  "line": k, "amount": v})
    rows.append({"section": "", "line": "Total inflow", "amount": data["total_inflow"]})
    for k, v in data["outflows"].items(): rows.append({"section": "Outflow", "line": k, "amount": v})
    rows.append({"section": "", "line": "Total outflow", "amount": data["total_outflow"]})
    rows.append({"section": "", "line": "Net change", "amount": data["net_change"]})
    rows.append({"section": "", "line": "Closing balance", "amount": data["closing_balance"]})
    return _csv_response("cash-flow.csv", rows, ["section", "line", "amount"])


@router.get("/journal-entries.csv")
async def export_journal_csv(request: Request,
                             from_date: Optional[str] = None, to_date: Optional[str] = None,
                             project_id: Optional[str] = None, client_id: Optional[str] = None,
                             vendor_id: Optional[str] = None, source: Optional[str] = None,
                             session_token: Optional[str] = Cookie(default=None),
                             authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    if not has_permission(user, "finance.read"):
        raise HTTPException(status_code=403, detail="Missing permission")
    q: dict = {}
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
    upd["updated_at"] = iso_now()
    # Milestone marked paid → accounting is the source of truth: auto-post
    # the receipt JE (idempotent) so books & dashboards stay reconciled.
    if upd.get("status") == "paid" and existing_ms.get("status") != "paid":
        amount = float(upd.get("amount") or existing_ms.get("amount") or 0)
        if amount > 0:
            proj = await sdb.projects.find_one(
                {"id": existing_ms.get("project_id")}, {"_id": 0, "client_id": 1, "name": 1})
            je = await post_receipt_je(
                user, amount=amount, date=now_utc().date().isoformat(),
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
    return await sdb.payment_milestones.find_one({"id": ms_id}, {"_id": 0})


@router.delete("/milestones/{ms_id}")
async def delete_milestone(ms_id: str, request: Request,
                           session_token: Optional[str] = Cookie(default=None),
                           authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    if not has_permission(user, "projects.update"):
        raise HTTPException(status_code=403, detail="Missing permission")
    await sdb.payment_milestones.delete_one({"id": ms_id})
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
                    or now_utc().date().isoformat())
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
    if not has_permission(user, "invoices.create"):
        raise HTTPException(status_code=403, detail="Missing permission")
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
