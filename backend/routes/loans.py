"""Loans & EMI module — full amortization + auto-JE posting.

Features
--------
* Create loan → generates amortization schedule, auto-creates a
  "Loan – <lender>" liability account, and posts the disbursement JE
  (DR Bank · CR Loan liability).
* Pay EMI (one click) → posts DR Loan / DR Interest Expense / CR Bank
  and stamps the schedule row as paid.
* Prepay → lump-sum reduction of remaining principal, schedule
  auto-recalculated.
* Loan ledger, per-loan outstanding, dashboard rollup.
* Every write scoped by org_id via sdb.
"""
from fastapi import APIRouter, HTTPException, Request, Cookie, Header
from typing import Optional, List
from datetime import date as _date, datetime, timedelta
from calendar import monthrange

from core.db import db
from core.scoped_db import sdb
from core.helpers import iso_now, now_utc, new_id
from core.deps import require_user
from core.rbac import has_permission
from core.tenancy import user_org_id
from core.audit import audit
from models.loan import LoanCreateIn, LoanUpdateIn, PayEMIIn, PrepayIn
from routes.accounting import _post_journal


router = APIRouter()


# ---------------------------------------------------------------
# Amortization
# ---------------------------------------------------------------
def _emi_amount(principal: float, rate_pa: float, tenure_months: int) -> float:
    """Standard reducing-balance EMI formula."""
    if rate_pa <= 0:
        return round(principal / tenure_months, 2)
    r = rate_pa / 12 / 100
    n = tenure_months
    emi = principal * r * ((1 + r) ** n) / (((1 + r) ** n) - 1)
    return round(emi, 2)


def _add_month(d: _date, months: int = 1) -> _date:
    y, m = d.year, d.month + months
    while m > 12:
        y += 1
        m -= 12
    day = min(d.day, monthrange(y, m)[1])
    return _date(y, m, day)


def _build_schedule(principal: float, rate_pa: float, tenure_months: int,
                    start_date: str, emi_day: Optional[int] = None) -> List[dict]:
    """Returns [{index, due_date, principal, interest, balance}, ...]."""
    emi = _emi_amount(principal, rate_pa, tenure_months)
    r = rate_pa / 12 / 100
    balance = principal
    start = _date.fromisoformat(start_date)
    schedule = []
    for i in range(tenure_months):
        interest = round(balance * r, 2) if r else 0
        principal_part = round(emi - interest, 2)
        if i == tenure_months - 1:
            # Adjust last row for rounding drift
            principal_part = round(balance, 2)
        balance = round(balance - principal_part, 2)
        due = _add_month(start, i + 1)
        if emi_day:
            try:
                due = _date(due.year, due.month, min(emi_day, monthrange(due.year, due.month)[1]))
            except Exception:
                pass
        schedule.append({
            "index": i,
            "due_date": due.isoformat(),
            "principal": principal_part,
            "interest": interest,
            "emi": round(principal_part + interest, 2),
            "balance_after": max(balance, 0),
            "paid": False,
            "paid_on": None,
            "journal_id": None,
        })
    return schedule


# ---------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------
async def _ensure_account(user: dict, name: str, type_: str,
                          category: Optional[str] = None) -> str:
    """Idempotently find or create a COA account for this org."""
    acc = await sdb.accounts.find_one({"name": name}, {"_id": 0})
    if acc:
        return acc["id"]
    doc = {
        "id": new_id("acc_"),
        "name": name,
        "type": type_,       # asset | liability | income | expense | equity
        "category": category or type_.title(),
        "is_bank": False,
        "created_at": iso_now(),
        "created_by": user["user_id"],
    }
    await sdb.accounts.insert_one(dict(doc))
    return doc["id"]


def _next_due(schedule: List[dict]) -> Optional[str]:
    for row in schedule:
        if not row.get("paid"):
            return row.get("due_date")
    return None


def _outstanding(schedule: List[dict]) -> float:
    for row in schedule:
        if not row.get("paid"):
            return float(row.get("balance_after", 0)) + float(row.get("principal", 0))
    return 0.0


def _totals(schedule: List[dict]) -> dict:
    paid_p = paid_i = pending_p = pending_i = 0.0
    for row in schedule:
        p = float(row.get("principal") or 0)
        i = float(row.get("interest") or 0)
        if row.get("paid"):
            paid_p += p
            paid_i += i
        else:
            pending_p += p
            pending_i += i
    return {
        "principal_paid": round(paid_p, 2),
        "interest_paid": round(paid_i, 2),
        "principal_pending": round(pending_p, 2),
        "interest_pending": round(pending_i, 2),
        "total_paid": round(paid_p + paid_i, 2),
        "total_pending": round(pending_p + pending_i, 2),
    }


# ---------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------
@router.get("/loans")
async def list_loans(request: Request,
                     status: Optional[str] = None,
                     session_token: Optional[str] = Cookie(default=None),
                     authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    if not has_permission(user, "finance.read"):
        raise HTTPException(403, "Missing permission: finance.read")
    q = {}
    if status:
        q["status"] = status
    rows = await sdb.loans.find(q, {"_id": 0}).sort("created_at", -1).to_list(500)
    for r in rows:
        r["outstanding"] = _outstanding(r.get("schedule", []))
        r["next_due_date"] = _next_due(r.get("schedule", []))
        r["totals"] = _totals(r.get("schedule", []))
        # Trim schedule for list view
        r.pop("schedule", None)
    return rows


@router.get("/loans/{loan_id}")
async def get_loan(loan_id: str, request: Request,
                   session_token: Optional[str] = Cookie(default=None),
                   authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    if not has_permission(user, "finance.read"):
        raise HTTPException(403, "Missing permission: finance.read")
    loan = await sdb.loans.find_one({"id": loan_id}, {"_id": 0})
    if not loan:
        raise HTTPException(404, "Loan not found")
    loan["outstanding"] = _outstanding(loan.get("schedule", []))
    loan["next_due_date"] = _next_due(loan.get("schedule", []))
    loan["totals"] = _totals(loan.get("schedule", []))
    return loan


@router.post("/loans")
async def create_loan(payload: LoanCreateIn, request: Request,
                      session_token: Optional[str] = Cookie(default=None),
                      authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    if not has_permission(user, "finance.create"):
        raise HTTPException(403, "Missing permission: finance.create")

    # Resolve accounts
    loan_acc_id = payload.loan_account_id or await _ensure_account(
        user, f"Loan – {payload.lender_name}", "liability", category="Loans"
    )
    interest_acc_id = payload.interest_expense_account_id or await _ensure_account(
        user, "Interest Expense", "expense", category="Financial"
    )

    # Build amortization
    schedule = _build_schedule(
        payload.principal, payload.interest_rate_pa,
        payload.tenure_months, payload.start_date, payload.emi_day,
    )
    emi_amt = _emi_amount(payload.principal, payload.interest_rate_pa, payload.tenure_months)

    loan_id = new_id("loan_")
    doc = {
        "id": loan_id,
        "org_id": user_org_id(user),
        "lender_name": payload.lender_name.strip(),
        "lender_contact": payload.lender_contact,
        "loan_type": payload.loan_type,
        "principal": payload.principal,
        "interest_rate_pa": payload.interest_rate_pa,
        "tenure_months": payload.tenure_months,
        "start_date": payload.start_date,
        "emi_day": payload.emi_day,
        "emi_amount": emi_amt,
        "loan_account_id": loan_acc_id,
        "interest_expense_account_id": interest_acc_id,
        "disbursement_account_id": payload.disbursement_account_id,
        "account_number": payload.account_number,
        "reference": payload.reference,
        "notes": payload.notes,
        "schedule": schedule,
        "status": "active",
        "disbursement_journal_id": None,
        "created_at": iso_now(),
        "created_by": user["user_id"],
    }

    # Post disbursement JE: DR Bank / CR Loan Liability
    je = await _post_journal(
        user, payload.start_date,
        f"Loan disbursement – {payload.lender_name}",
        [
            {"account_id": payload.disbursement_account_id, "debit": payload.principal, "credit": 0,
             "description": f"Loan received from {payload.lender_name}"},
            {"account_id": loan_acc_id, "debit": 0, "credit": payload.principal,
             "description": f"Loan liability – {payload.lender_name}"},
        ],
        reference=payload.reference or f"LOAN-{loan_id}",
        source="loan_disbursement", source_id=loan_id,
    )
    doc["disbursement_journal_id"] = je["id"]

    await sdb.loans.insert_one(dict(doc))
    await audit(user, "loan.create", target=loan_id, target_type="loan",
                meta={"lender": payload.lender_name, "principal": payload.principal,
                      "tenure": payload.tenure_months, "rate": payload.interest_rate_pa})

    doc["outstanding"] = _outstanding(schedule)
    doc["next_due_date"] = _next_due(schedule)
    doc["totals"] = _totals(schedule)
    return doc


@router.patch("/loans/{loan_id}")
async def update_loan(loan_id: str, payload: LoanUpdateIn, request: Request,
                      session_token: Optional[str] = Cookie(default=None),
                      authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    if not has_permission(user, "finance.update"):
        raise HTTPException(403, "Missing permission: finance.update")
    loan = await sdb.loans.find_one({"id": loan_id}, {"_id": 0})
    if not loan:
        raise HTTPException(404, "Loan not found")
    up = {k: v for k, v in payload.dict(exclude_unset=True).items() if v is not None}
    up["updated_at"] = iso_now()
    await sdb.loans.update_one({"id": loan_id}, {"$set": up})
    return await sdb.loans.find_one({"id": loan_id}, {"_id": 0})


# ---------------------------------------------------------------
# EMI Payment
# ---------------------------------------------------------------
@router.post("/loans/{loan_id}/pay-emi")
async def pay_emi(loan_id: str, payload: PayEMIIn, request: Request,
                  session_token: Optional[str] = Cookie(default=None),
                  authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    if not has_permission(user, "finance.create"):
        raise HTTPException(403, "Missing permission: finance.create")
    loan = await sdb.loans.find_one({"id": loan_id}, {"_id": 0})
    if not loan:
        raise HTTPException(404, "Loan not found")
    schedule = loan.get("schedule", [])
    idx = payload.schedule_index
    if idx < 0 or idx >= len(schedule):
        raise HTTPException(400, "Invalid schedule_index")
    row = schedule[idx]
    if row.get("paid"):
        raise HTTPException(400, "This EMI is already paid")

    paid_on = payload.paid_on or _date.today().isoformat()
    principal_amt = float(row["principal"])
    interest_amt = float(row["interest"])
    extra = round(float(payload.extra_principal or 0), 2)
    total_amt = round(principal_amt + interest_amt + extra, 2)

    # Post JE: DR Loan Liability (principal + extra) · DR Interest Expense · CR Bank
    lines = [
        {"account_id": loan["loan_account_id"],
         "debit": round(principal_amt + extra, 2), "credit": 0,
         "description": f"EMI #{idx+1} principal"},
    ]
    if interest_amt > 0:
        lines.append({
            "account_id": loan["interest_expense_account_id"],
            "debit": interest_amt, "credit": 0,
            "description": f"EMI #{idx+1} interest",
        })
    lines.append({
        "account_id": payload.paid_from_account_id,
        "debit": 0, "credit": total_amt,
        "description": f"EMI #{idx+1} paid",
    })
    je = await _post_journal(
        user, paid_on,
        f"EMI #{idx+1} – {loan['lender_name']}",
        lines,
        reference=payload.reference or f"EMI-{loan_id}-{idx+1}",
        source="loan_emi", source_id=loan_id,
    )

    # Mark row paid + apply extra principal reduction on the next row's balance
    schedule[idx]["paid"] = True
    schedule[idx]["paid_on"] = paid_on
    schedule[idx]["journal_id"] = je["id"]
    schedule[idx]["extra_principal"] = extra
    schedule[idx]["paid_from_account_id"] = payload.paid_from_account_id
    schedule[idx]["notes"] = payload.notes

    if extra > 0:
        # Recompute tail: reduce remaining principal by `extra`
        # Simple approach: shrink upcoming rows' balance and, if fully covered, close remaining rows.
        remaining = extra
        for r in schedule[idx + 1:]:
            if remaining <= 0:
                break
            take = min(remaining, float(r["principal"]))
            r["principal"] = round(float(r["principal"]) - take, 2)
            r["emi"] = round(r["principal"] + float(r["interest"]), 2)
            r["balance_after"] = max(round(float(r["balance_after"]) - take, 2), 0)
            remaining = round(remaining - take, 2)
        # Drop trailing rows whose principal + interest == 0
        while schedule and schedule[-1].get("principal", 0) == 0 and schedule[-1].get("interest", 0) == 0 and not schedule[-1].get("paid"):
            schedule.pop()

    # Close loan if fully paid
    is_closed = all(r.get("paid") for r in schedule)
    status = "closed" if is_closed else "active"

    await sdb.loans.update_one(
        {"id": loan_id},
        {"$set": {"schedule": schedule, "status": status, "last_paid_at": iso_now()}},
    )
    await audit(user, "loan.pay_emi", target=loan_id, target_type="loan",
                meta={"schedule_index": idx, "amount": total_amt,
                      "extra_principal": extra, "journal_id": je["id"]})

    fresh = await sdb.loans.find_one({"id": loan_id}, {"_id": 0})
    fresh["outstanding"] = _outstanding(fresh.get("schedule", []))
    fresh["next_due_date"] = _next_due(fresh.get("schedule", []))
    fresh["totals"] = _totals(fresh.get("schedule", []))
    return {"loan": fresh, "journal": je}


@router.post("/loans/{loan_id}/prepay")
async def prepay(loan_id: str, payload: PrepayIn, request: Request,
                 session_token: Optional[str] = Cookie(default=None),
                 authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    if not has_permission(user, "finance.create"):
        raise HTTPException(403, "Missing permission: finance.create")
    loan = await sdb.loans.find_one({"id": loan_id}, {"_id": 0})
    if not loan:
        raise HTTPException(404, "Loan not found")
    schedule = loan.get("schedule", [])

    paid_on = payload.paid_on or _date.today().isoformat()
    # Post JE: DR Loan Liability / CR Bank
    je = await _post_journal(
        user, paid_on,
        f"Loan prepayment – {loan['lender_name']}",
        [
            {"account_id": loan["loan_account_id"], "debit": payload.amount, "credit": 0,
             "description": "Principal prepayment"},
            {"account_id": payload.paid_from_account_id, "debit": 0, "credit": payload.amount,
             "description": "Prepayment"},
        ],
        reference=f"PREPAY-{loan_id}",
        source="loan_prepay", source_id=loan_id,
    )

    # Reduce upcoming principal
    remaining = float(payload.amount)
    for r in schedule:
        if remaining <= 0:
            break
        if r.get("paid"):
            continue
        take = min(remaining, float(r["principal"]))
        r["principal"] = round(float(r["principal"]) - take, 2)
        r["emi"] = round(r["principal"] + float(r["interest"]), 2)
        r["balance_after"] = max(round(float(r["balance_after"]) - take, 2), 0)
        remaining = round(remaining - take, 2)
    while schedule and schedule[-1].get("principal", 0) == 0 and schedule[-1].get("interest", 0) == 0 and not schedule[-1].get("paid"):
        schedule.pop()

    is_closed = all(r.get("paid") for r in schedule) or not schedule
    status = "closed" if is_closed else "active"

    await sdb.loans.update_one(
        {"id": loan_id},
        {"$set": {"schedule": schedule, "status": status,
                  "last_prepayment_at": iso_now()}},
    )
    await audit(user, "loan.prepay", target=loan_id, target_type="loan",
                meta={"amount": payload.amount, "journal_id": je["id"]})
    return {"ok": True, "journal": je,
            "outstanding": _outstanding(schedule)}


@router.delete("/loans/{loan_id}")
async def delete_loan(loan_id: str, request: Request,
                      session_token: Optional[str] = Cookie(default=None),
                      authorization: Optional[str] = Header(default=None)):
    """Soft-close a loan (does not reverse historic JEs). Only allowed
    when no EMIs have been paid."""
    user = await require_user(request, session_token, authorization)
    if not has_permission(user, "finance.delete"):
        raise HTTPException(403, "Missing permission: finance.delete")
    loan = await sdb.loans.find_one({"id": loan_id}, {"_id": 0})
    if not loan:
        raise HTTPException(404, "Loan not found")
    if any(r.get("paid") for r in loan.get("schedule", [])):
        raise HTTPException(400, "Loan has posted EMIs — cannot delete. Reverse EMIs first.")
    await sdb.loans.delete_one({"id": loan_id})
    # Reverse disbursement JE
    if loan.get("disbursement_journal_id"):
        await sdb.journal_entries.delete_one({"id": loan["disbursement_journal_id"]})
    await audit(user, "loan.delete", target=loan_id, target_type="loan")
    return {"ok": True}


# ---------------------------------------------------------------
# Dashboard summary
# ---------------------------------------------------------------
@router.get("/loans/summary/dashboard")
async def loans_summary(request: Request,
                        session_token: Optional[str] = Cookie(default=None),
                        authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    if not has_permission(user, "finance.read"):
        raise HTTPException(403, "Missing permission")
    rows = await sdb.loans.find({"status": "active"}, {"_id": 0}).to_list(200)
    total_outstanding = 0.0
    next_due = None
    next_due_amount = 0
    for r in rows:
        total_outstanding += _outstanding(r.get("schedule", []))
        for row in r.get("schedule", []):
            if not row.get("paid"):
                if next_due is None or row["due_date"] < next_due:
                    next_due = row["due_date"]
                    next_due_amount = row.get("emi") or (row.get("principal", 0) + row.get("interest", 0))
                break
    return {
        "active_loans": len(rows),
        "total_outstanding": round(total_outstanding, 2),
        "next_emi_due_date": next_due,
        "next_emi_amount": round(next_due_amount, 2),
    }
