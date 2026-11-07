"""Employee advances (mandate 08): give, recover through payroll, cancel.

Giving an advance moves money out of Cash/Bank into the "Employee Advances"
asset (money the employee owes) - it is not a salary expense. Payroll recovers
it: salary expense is booked at net + recovered, Cash/Bank is credited with
the net actually paid and Employee Advances with the recovery. A payroll
reversal restores the recovered amounts. Recoveries can never exceed what is
outstanding, and amounts are exact to the paisa.
"""
from __future__ import annotations

from datetime import date as _date
from decimal import Decimal
from typing import Literal, Optional

from fastapi import APIRouter, Cookie, Header, HTTPException, Request
from pydantic import BaseModel, Field, field_validator

from core.audit import audit
from core.deps import require_user
from core.helpers import iso_now, new_id
from core.locks import doc_lock
from core.money import round_paise, to_decimal
from core.rbac import has_permission
from core.scoped_db import sdb
from core.tenancy import user_org_id

router = APIRouter()
ACCOUNT_NAME = "Employee Advances"


class AdvanceIn(BaseModel):
    amount: float = Field(gt=0, le=100_000_000)
    date: str
    reason: str = Field(default="", max_length=500)
    bank_account_id: str
    payment_method: Literal["cash", "bank_transfer", "upi", "cheque", "online", "other"] = "cash"
    reference: Optional[str] = Field(default=None, max_length=120)
    monthly_recovery: Optional[float] = Field(default=None, ge=0, le=100_000_000)

    @field_validator("date")
    @classmethod
    def _iso(cls, value: str) -> str:
        _date.fromisoformat(value)
        return value


def _d(value) -> Decimal:
    return round_paise(to_decimal(value or 0))


def _require(user: dict, perm: str):
    if not has_permission(user, perm):
        raise HTTPException(status_code=403, detail=f"Missing permission: {perm}")


async def advances_account() -> dict:
    from routes.accounting import _ensure_named_account, _seed_coa_if_empty
    await _seed_coa_if_empty()
    return await _ensure_named_account(ACCOUNT_NAME, "asset")


async def outstanding_for(employee_id: str) -> Decimal:
    total = Decimal(0)
    async for adv in sdb.employee_advances.find(
            {"employee_id": employee_id, "status": "open"}, {"_id": 0, "amount": 1, "recovered_amount": 1}):
        total += _d(adv.get("amount")) - _d(adv.get("recovered_amount"))
    return round_paise(total)


async def apply_recovery(employee_id: str, run_id: str, year: int, month: int,
                         amount, on_date: str) -> list:
    """Allocate a payroll recovery oldest-first. Caller has already checked it fits."""
    left = _d(amount)
    applied = []
    rows = await sdb.employee_advances.find(
        {"employee_id": employee_id, "status": "open"}, {"_id": 0}).sort("date", 1).to_list(None)
    for adv in rows:
        if left <= 0:
            break
        due = _d(adv.get("amount")) - _d(adv.get("recovered_amount"))
        if due <= 0:
            continue
        part = min(due, left)
        recovered = _d(adv.get("recovered_amount")) + part
        status = "closed" if recovered >= _d(adv.get("amount")) else "open"
        await sdb.employee_advances.update_one(
            {"id": adv["id"], "recovered_amount": adv.get("recovered_amount", 0)},
            {"$set": {"recovered_amount": float(recovered), "status": status, "updated_at": iso_now()},
             "$push": {"recoveries": {"payroll_run_id": run_id, "year": year, "month": month,
                                      "amount": float(part), "date": on_date, "active": True}}})
        applied.append({"advance_id": adv["id"], "amount": float(part)})
        left -= part
    return applied


async def restore_recovery(run_id: str) -> None:
    """Undo the recoveries made by a payroll run that has been reversed."""
    rows = await sdb.employee_advances.find({"recoveries.payroll_run_id": run_id}, {"_id": 0}).to_list(None)
    for adv in rows:
        give_back = Decimal(0)
        recs = []
        for r in adv.get("recoveries") or []:
            if r.get("payroll_run_id") == run_id and r.get("active", True):
                give_back += _d(r.get("amount"))
                r = {**r, "active": False, "reversed_at": iso_now()}
            recs.append(r)
        recovered = max(Decimal(0), _d(adv.get("recovered_amount")) - give_back)
        status = adv.get("status") if adv.get("status") == "cancelled" else (
            "closed" if recovered >= _d(adv.get("amount")) else "open")
        await sdb.employee_advances.update_one(
            {"id": adv["id"]},
            {"$set": {"recovered_amount": float(recovered), "status": status,
                      "recoveries": recs, "updated_at": iso_now()}})


def _pack(adv: dict) -> dict:
    adv = dict(adv)
    adv["outstanding"] = float(_d(adv.get("amount")) - _d(adv.get("recovered_amount"))) \
        if adv.get("status") != "cancelled" else 0.0
    return adv


@router.get("/employees/{eid}/advances")
async def list_advances(eid: str, request: Request,
                        session_token: Optional[str] = Cookie(default=None),
                        authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    _require(user, "payroll.read")
    if not await sdb.employees.find_one({"id": eid}, {"_id": 1}):
        raise HTTPException(status_code=404, detail="Employee not found")
    rows = await sdb.employee_advances.find({"employee_id": eid}, {"_id": 0}).sort("date", -1).to_list(None)
    items = [_pack(r) for r in rows]
    open_rows = [r for r in items if r["status"] == "open"]
    suggested = sum(min(r["outstanding"], r.get("monthly_recovery") or r["outstanding"]) for r in open_rows)
    return {"items": items, "outstanding": float(await outstanding_for(eid)),
            "suggested_recovery": round(suggested, 2)}


@router.post("/employees/{eid}/advances")
async def give_advance(eid: str, payload: AdvanceIn, request: Request,
                       session_token: Optional[str] = Cookie(default=None),
                       authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    _require(user, "payroll.create")
    emp = await sdb.employees.find_one({"id": eid}, {"_id": 0})
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")
    from core.finance import validate_method_account
    from routes.accounting import _post_journal
    bank = await sdb.accounts.find_one({"id": payload.bank_account_id},
                                       {"_id": 0, "id": 1, "type": 1, "name": 1, "is_bank": 1})
    if not bank or str(bank.get("type") or "").lower() != "asset":
        raise HTTPException(status_code=400, detail="Pay the advance from a cash or bank account")
    validate_method_account(payload.payment_method, bank, label="advances")
    if payload.monthly_recovery and payload.monthly_recovery > payload.amount:
        raise HTTPException(status_code=400, detail="Monthly recovery cannot be more than the advance")
    account = await advances_account()
    amount = float(_d(payload.amount))
    name = f"{emp.get('first_name', '')} {emp.get('last_name', '')}".strip() or emp.get("employee_id") or eid
    adv_id = new_id("adv_")
    je = await _post_journal(
        user, payload.date, f"Advance to {name}" + (f" - {payload.reason}" if payload.reason else ""),
        [{"account_id": account["id"], "debit": amount, "credit": 0, "description": f"Advance - {name}"},
         {"account_id": bank["id"], "debit": 0, "credit": amount, "description": "Paid"}],
        reference=payload.reference or f"ADV-{adv_id[-6:].upper()}",
        employee_id=eid, source="employee_advance", source_id=adv_id)
    doc = {
        "id": adv_id, "employee_id": eid, "employee_name": name, "amount": amount,
        "date": payload.date, "reason": payload.reason, "payment_method": payload.payment_method,
        "bank_account_id": bank["id"], "bank_account_name": bank.get("name"),
        "reference": payload.reference, "monthly_recovery": payload.monthly_recovery,
        "recovered_amount": 0.0, "recoveries": [], "status": "open", "journal_id": je["id"],
        "created_at": iso_now(), "created_by": user["user_id"], "created_by_name": user.get("name"),
    }
    await sdb.employee_advances.insert_one(dict(doc))
    await audit(user, "employee_advance.create", target=adv_id, target_type="employee_advance",
                meta={"employee_id": eid, "amount": amount}, org_id=user_org_id(user))
    return _pack(doc)


@router.post("/employees/{eid}/advances/{adv_id}/cancel")
async def cancel_advance(eid: str, adv_id: str, request: Request,
                         session_token: Optional[str] = Cookie(default=None),
                         authorization: Optional[str] = Header(default=None)):
    """Cancel a mistaken advance with a balancing journal (never a hard delete)."""
    user = await require_user(request, session_token, authorization)
    _require(user, "payroll.create")
    _require(user, "finance.update")
    async with doc_lock(sdb.employee_advances, adv_id):
        adv = await sdb.employee_advances.find_one({"id": adv_id, "employee_id": eid}, {"_id": 0})
        if not adv:
            raise HTTPException(status_code=404, detail="Advance not found")
        if adv.get("status") == "cancelled":
            return _pack(adv)
        if _d(adv.get("recovered_amount")) > 0:
            raise HTTPException(status_code=409, detail=(
                "Part of this advance was already recovered in payroll. Reverse that salary payment first."))
        je = await sdb.journal_entries.find_one({"id": adv.get("journal_id")}, {"_id": 0})
        from routes.accounting import _reverse_journal_entry
        reversal = None
        if je and not je.get("reversed"):
            reversal = await _reverse_journal_entry(user, je, action="employee_advance_cancel")
        await sdb.employee_advances.update_one(
            {"id": adv_id}, {"$set": {"status": "cancelled", "cancelled_at": iso_now(),
                                      "cancelled_by": user["user_id"],
                                      "reversal_journal_id": (reversal or {}).get("id")}})
    await audit(user, "employee_advance.cancel", target=adv_id, target_type="employee_advance",
                meta={"employee_id": eid}, org_id=user_org_id(user))
    return _pack(await sdb.employee_advances.find_one({"id": adv_id}, {"_id": 0}))
