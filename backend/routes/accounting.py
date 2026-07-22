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
from core.helpers import now_utc, iso_now, new_id
from core.deps import require_user
from core.rbac import has_permission
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
    count = await db.accounts.count_documents({})
    if count > 0:
        return
    for name, typ, code in DEFAULT_COA:
        await db.accounts.insert_one({
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
    rows = await db.accounts.find(q, {"_id": 0}).sort("code", 1).to_list(1000)
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
    await db.accounts.insert_one(dict(doc))
    return await db.accounts.find_one({"id": doc["id"]}, {"_id": 0})


@router.patch("/accounts/{acc_id}")
async def update_account(acc_id: str, payload: AccountIn, request: Request,
                         session_token: Optional[str] = Cookie(default=None),
                         authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    if not has_permission(user, "invoices.update"):
        raise HTTPException(status_code=403, detail="Missing permission")
    upd = {k: v for k, v in payload.model_dump().items() if v is not None}
    upd["updated_at"] = iso_now()
    await db.accounts.update_one({"id": acc_id}, {"$set": upd})
    return await db.accounts.find_one({"id": acc_id}, {"_id": 0})


@router.delete("/accounts/{acc_id}")
async def deactivate_account(acc_id: str, request: Request,
                             session_token: Optional[str] = Cookie(default=None),
                             authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    if not has_permission(user, "invoices.update"):
        raise HTTPException(status_code=403, detail="Missing permission")
    # Soft delete — audit-safe
    await db.accounts.update_one({"id": acc_id}, {"$set": {"active": False, "deactivated_at": iso_now()}})
    return {"ok": True}


# ==================================================
# Journal entries (double-entry, source of truth)
# ==================================================
async def _post_journal(user: dict, date: str, narration: str, lines: list,
                        reference: str = None, project_id: str = None,
                        client_id: str = None, vendor_id: str = None,
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
    accs = {a["id"]: a async for a in db.accounts.find({"id": {"$in": acc_ids}}, {"_id": 0})}
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
        "source": source,          # manual | income | expense | payroll | invoice
        "source_id": source_id,
        "total": total_debit,
        "lines": resolved_lines,
        "created_at": iso_now(),
        "created_by": user["user_id"],
        "created_by_name": user.get("name"),
    }
    await db.journal_entries.insert_one(dict(doc))
    return await db.journal_entries.find_one({"id": doc["id"]}, {"_id": 0})


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
    )


@router.get("/journal-entries")
async def list_journal(request: Request,
                       from_date: Optional[str] = None, to_date: Optional[str] = None,
                       account_id: Optional[str] = None,
                       project_id: Optional[str] = None,
                       client_id: Optional[str] = None,
                       vendor_id: Optional[str] = None,
                       source: Optional[str] = None,
                       session_token: Optional[str] = Cookie(default=None),
                       authorization: Optional[str] = Header(default=None)):
    await require_user(request, session_token, authorization)
    q: dict = {}
    if from_date or to_date:
        d = {}
        if from_date: d["$gte"] = from_date
        if to_date: d["$lte"] = to_date
        q["date"] = d
    if account_id: q["lines.account_id"] = account_id
    if project_id: q["project_id"] = project_id
    if client_id: q["client_id"] = client_id
    if vendor_id: q["vendor_id"] = vendor_id
    if source: q["source"] = source
    rows = await db.journal_entries.find(q, {"_id": 0}).sort("date", -1).limit(1000).to_list(1000)
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
        client_id=payload.client_id, source="income",
    )

    # If linked to a milestone, mark it paid
    if payload.milestone_id:
        await db.payment_milestones.update_one(
            {"id": payload.milestone_id},
            {"$set": {"status": "paid", "paid_amount": payload.amount,
                      "paid_at": iso_now(), "journal_id": je["id"]}}
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
        gst_acc = await db.accounts.find_one({"name": "GST Payable"}, {"_id": 0, "id": 1})
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
        vendor_id=payload.vendor_id, source="expense",
    )
    # Attach bill_url on the journal entry for audit
    if payload.bill_url:
        await db.journal_entries.update_one({"id": je["id"]}, {"$set": {"bill_url": payload.bill_url}})
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
    acc = await db.accounts.find_one({"id": acc_id}, {"_id": 0})
    if not acc:
        raise HTTPException(status_code=404, detail="Account not found")

    q: dict = {"lines.account_id": acc_id}
    if from_date or to_date:
        d = {}
        if from_date: d["$gte"] = from_date
        if to_date: d["$lte"] = to_date
        q["date"] = d
    entries = await db.journal_entries.find(q, {"_id": 0}).sort("date", 1).to_list(2000)

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
                        session_token: Optional[str] = Cookie(default=None),
                        authorization: Optional[str] = Header(default=None)):
    await require_user(request, session_token, authorization)
    client = await db.clients.find_one({"id": client_id}, {"_id": 0})

    # Project totals for this client
    projects = await db.projects.find({"client_id": client_id}, {"_id": 0}).to_list(200)
    total_project_value = sum(float(p.get("budget") or 0) for p in projects)

    # All received income for this client (from journal source=income)
    entries = await db.journal_entries.find(
        {"client_id": client_id, "source": "income"}, {"_id": 0},
    ).sort("date", 1).to_list(1000)
    received = sum(float(e.get("total") or 0) for e in entries)

    # Outstanding milestones
    milestones = await db.payment_milestones.find(
        {"project_id": {"$in": [p["id"] for p in projects]}}, {"_id": 0},
    ).sort("due_date", 1).to_list(500)
    outstanding = sum(float(m.get("amount") or 0) for m in milestones
                       if m.get("status") != "paid")

    return {
        "client": client,
        "projects": projects,
        "total_project_value": round(total_project_value, 2),
        "received": round(received, 2),
        "outstanding": round(outstanding, 2),
        "milestones": milestones,
        "transactions": entries,
    }


@router.get("/accounting/ledger/vendor/{vendor_id}")
async def vendor_ledger(vendor_id: str, request: Request,
                        session_token: Optional[str] = Cookie(default=None),
                        authorization: Optional[str] = Header(default=None)):
    await require_user(request, session_token, authorization)
    vendor = await db.vendors_acc.find_one({"id": vendor_id}, {"_id": 0})
    entries = await db.journal_entries.find(
        {"vendor_id": vendor_id}, {"_id": 0},
    ).sort("date", 1).to_list(1000)
    total_purchase = sum(float(e.get("total") or 0) for e in entries if e.get("source") == "expense")
    return {"vendor": vendor, "transactions": entries,
            "total_purchase": round(total_purchase, 2)}


@router.get("/accounting/ledger/project/{project_id}")
async def project_ledger(project_id: str, request: Request,
                         session_token: Optional[str] = Cookie(default=None),
                         authorization: Optional[str] = Header(default=None)):
    await require_user(request, session_token, authorization)
    project = await db.projects.find_one({"id": project_id}, {"_id": 0})
    entries = await db.journal_entries.find({"project_id": project_id}, {"_id": 0}).sort("date", 1).to_list(1000)

    revenue = 0.0
    expense = 0.0
    for e in entries:
        for l in e["lines"]:
            if l["account_type"] == "income":
                revenue += l["credit"] - l["debit"]
            elif l["account_type"] == "expense":
                expense += l["debit"] - l["credit"]

    milestones = await db.payment_milestones.find({"project_id": project_id}, {"_id": 0}).to_list(200)

    return {
        "project": project,
        "revenue": round(revenue, 2),
        "expense": round(expense, 2),
        "profit": round(revenue - expense, 2),
        "milestones": milestones,
        "transactions": entries,
    }


# ==================================================
# Reports
# ==================================================
@router.get("/accounting/reports/pl")
async def profit_and_loss(request: Request,
                          from_date: Optional[str] = None, to_date: Optional[str] = None,
                          project_id: Optional[str] = None,
                          session_token: Optional[str] = Cookie(default=None),
                          authorization: Optional[str] = Header(default=None)):
    await require_user(request, session_token, authorization)
    q: dict = {}
    if from_date or to_date:
        d = {}
        if from_date: d["$gte"] = from_date
        if to_date: d["$lte"] = to_date
        q["date"] = d
    if project_id: q["project_id"] = project_id
    entries = await db.journal_entries.find(q, {"_id": 0}).to_list(5000)

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
        "from": from_date, "to": to_date, "project_id": project_id,
        "income": [{"name": k, "amount": round(v, 2)} for k, v in income_by_acc.items()],
        "expense": [{"name": k, "amount": round(v, 2)} for k, v in expense_by_acc.items()],
        "total_income": total_income, "total_expense": total_expense,
        "net_profit": round(total_income - total_expense, 2),
    }


@router.get("/accounting/reports/trial-balance")
async def trial_balance(request: Request, as_of: Optional[str] = None,
                        session_token: Optional[str] = Cookie(default=None),
                        authorization: Optional[str] = Header(default=None)):
    await require_user(request, session_token, authorization)
    q = {}
    if as_of: q["date"] = {"$lte": as_of}
    entries = await db.journal_entries.find(q, {"_id": 0}).to_list(10000)

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
        "as_of": as_of,
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
    accs = await db.accounts.find({"$or": [{"is_bank": True}, {"name": "Cash"}, {"name": "Petty Cash"}]},
                                  {"_id": 0}).to_list(50)
    cash_bank = []
    for a in accs:
        # sum all movements for that account
        agg = await db.journal_entries.aggregate([
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
    entries_month = await db.journal_entries.find(
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
    ms = await db.payment_milestones.find({"status": {"$ne": "paid"}}, {"_id": 0, "amount": 1, "due_date": 1, "status": 1}).to_list(500)
    outstanding = round(sum(float(m.get("amount") or 0) for m in ms), 2)
    overdue = round(sum(float(m.get("amount") or 0) for m in ms
                       if (m.get("due_date") or "") < today), 2)

    # Upcoming payments (next 30 days)
    horizon = (now_utc().date() + timedelta(days=30)).isoformat()
    upcoming = [m for m in ms if today <= (m.get("due_date") or "") <= horizon]

    # Recent transactions
    recent = await db.journal_entries.find({}, {"_id": 0}).sort("created_at", -1).limit(10).to_list(10)

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
# Balance Sheet  (Assets = Liabilities + Equity + Net Income)
# ==================================================
@router.get("/accounting/reports/balance-sheet")
async def balance_sheet(request: Request, as_of: Optional[str] = None,
                        session_token: Optional[str] = Cookie(default=None),
                        authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    if not has_permission(user, "finance.read"):
        raise HTTPException(status_code=403, detail="Missing permission: finance.read")
    q = {}
    if as_of: q["date"] = {"$lte": as_of}
    entries = await db.journal_entries.find(q, {"_id": 0}).to_list(20000)

    accs = await db.accounts.find({}, {"_id": 0}).to_list(500)
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
    return {
        "as_of": as_of,
        "assets": {"rows": assets, "total": total_assets},
        "liabilities": {"rows": liabilities, "total": total_liabilities},
        "equity": {"rows": equity, "total": total_equity,
                   "net_income": net_income,
                   "total_with_net_income": round(total_equity + net_income, 2)},
        "total_assets": total_assets,
        "total_liabilities_and_equity": total_liab_eq,
        "balanced": abs(total_assets - total_liab_eq) < 0.01,
    }


# ==================================================
# Cash Flow  (indirect-ish, aggregated by source)
# ==================================================
@router.get("/accounting/reports/cash-flow")
async def cash_flow_statement(request: Request,
                              from_date: Optional[str] = None,
                              to_date: Optional[str] = None,
                              session_token: Optional[str] = Cookie(default=None),
                              authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    if not has_permission(user, "finance.read"):
        raise HTTPException(status_code=403, detail="Missing permission: finance.read")

    # Cash & bank accounts
    cash_accs = await db.accounts.find({"$or": [{"is_bank": True},
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
        async for e in db.journal_entries.find(opening_q, {"_id": 0, "lines": 1}):
            for l in e["lines"]:
                if l["account_id"] in cash_ids:
                    opening += l["debit"] - l["credit"]

    # Inflows / outflows within the period, bucketed by journal source.
    inflows: dict = {"income": 0.0, "client_payment": 0.0, "other": 0.0}
    outflows: dict = {"expense": 0.0, "vendor_payment": 0.0, "payroll": 0.0, "other": 0.0}
    async for e in db.journal_entries.find(period_q, {"_id": 0}):
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
    async for inv in db.invoices.find({"status": {"$in": ["sent", "overdue", "partially_paid"]},
                                       "doc_type": {"$ne": "quotation"}},
                                      {"_id": 0}):
        amt = float(inv.get("total") or 0)
        receivables_total += amt
        if (inv.get("due_date") or "") < today:
            receivables_overdue += amt

    # Payables = unpaid vendor bills
    payables_total = 0.0
    payables_overdue = 0.0
    async for b in db.vendor_bills.find({"status": {"$in": ["received", "partially_paid", "overdue"]}},
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
    async for e in db.journal_entries.find(
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
    async for e in db.journal_entries.find(
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
    data = await profit_and_loss(request, from_date, to_date, project_id,
                                 session_token, authorization)
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
    data = await trial_balance(request, as_of, session_token, authorization)
    return _csv_response("trial-balance.csv", data["rows"],
                         ["account_name", "account_type", "debit", "credit", "balance"])


@router.get("/accounting/reports/balance-sheet.csv")
async def export_bs_csv(request: Request, as_of: Optional[str] = None,
                        session_token: Optional[str] = Cookie(default=None),
                        authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    if not has_permission(user, "finance.read"):
        raise HTTPException(status_code=403, detail="Missing permission")
    data = await balance_sheet(request, as_of, session_token, authorization)
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
    data = await cash_flow_statement(request, from_date, to_date, session_token, authorization)
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
    async for e in db.journal_entries.find(q, {"_id": 0}).sort("date", 1):
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
    rows = await db.payment_milestones.find({"project_id": project_id}, {"_id": 0}).sort("due_date", 1).to_list(200)
    return rows


@router.post("/projects/{project_id}/milestones")
async def add_milestone(project_id: str, payload: MilestoneIn, request: Request,
                        session_token: Optional[str] = Cookie(default=None),
                        authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    if not has_permission(user, "projects.update"):
        raise HTTPException(status_code=403, detail="Missing permission")
    proj = await db.projects.find_one({"id": project_id}, {"_id": 0})
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")

    amount = payload.amount
    if amount is None and payload.percent is not None:
        amount = round(float(proj.get("budget") or 0) * float(payload.percent) / 100.0, 2)

    doc = {
        "id": new_id("ms_"),
        "project_id": project_id,
        "name": payload.name,
        "percent": payload.percent,
        "amount": amount,
        "due_date": payload.due_date,
        "status": "pending",
        "notes": payload.notes,
        "created_at": iso_now(),
        "created_by": user["user_id"],
    }
    await db.payment_milestones.insert_one(dict(doc))
    return await db.payment_milestones.find_one({"id": doc["id"]}, {"_id": 0})


@router.patch("/milestones/{ms_id}")
async def update_milestone(ms_id: str, payload: MilestoneUpdate, request: Request,
                           session_token: Optional[str] = Cookie(default=None),
                           authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    if not has_permission(user, "projects.update"):
        raise HTTPException(status_code=403, detail="Missing permission")
    upd = {k: v for k, v in payload.model_dump().items() if v is not None}
    upd["updated_at"] = iso_now()
    await db.payment_milestones.update_one({"id": ms_id}, {"$set": upd})
    return await db.payment_milestones.find_one({"id": ms_id}, {"_id": 0})


@router.delete("/milestones/{ms_id}")
async def delete_milestone(ms_id: str, request: Request,
                           session_token: Optional[str] = Cookie(default=None),
                           authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    if not has_permission(user, "projects.update"):
        raise HTTPException(status_code=403, detail="Missing permission")
    await db.payment_milestones.delete_one({"id": ms_id})
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
@router.post("/accounting/seed-coa")
async def seed_coa(request: Request,
                   session_token: Optional[str] = Cookie(default=None),
                   authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    if not has_permission(user, "invoices.create"):
        raise HTTPException(status_code=403, detail="Missing permission")
    await _seed_coa_if_empty()
    n = await db.accounts.count_documents({})
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
