"""Payroll routes — pays employee, auto-posts JE to Accounting.

`POST /api/employees/{eid}/pay-salary` computes net salary from the employee
salary structure (already stored under `emp.salary.net_monthly`) and posts a
balanced journal entry (DR Employee Salary  CR Cash/Bank) via
`accounting._post_journal`. Idempotent per (employee_id, year, month) — a
`payroll_runs` doc guards against double payment.
"""
from fastapi import APIRouter, HTTPException, Request, Cookie, Header
from typing import Optional
from pydantic import BaseModel
from datetime import date as _date

from core.db import db
from core.helpers import now_utc, iso_now, new_id
from core.deps import require_user
from core.rbac import has_permission
from routes.accounting import _post_journal

router = APIRouter()


class PaySalaryIn(BaseModel):
    year: int
    month: int
    paid_from_account_id: str          # Cash / Bank
    salary_account_id: Optional[str] = None   # defaults to "Employee Salary"
    bonus: Optional[float] = 0
    incentives: Optional[float] = 0
    overtime: Optional[float] = 0
    advances_recovered: Optional[float] = 0
    other_deductions: Optional[float] = 0
    payment_method: Optional[str] = "bank_transfer"
    reference: Optional[str] = None
    notes: Optional[str] = None


def _compute_net(salary: dict, extras: dict) -> dict:
    """Return {gross, deductions, additions, net}."""
    if not salary:
        salary = {}
    basic = float(salary.get("basic") or 0)
    hra = float(salary.get("hra") or 0)
    conveyance = float(salary.get("conveyance") or 0)
    medical = float(salary.get("medical") or 0)
    special = float(salary.get("special") or 0)
    other_earning = float(salary.get("other_earning") or 0)

    pf = float(salary.get("pf") or 0)
    esi = float(salary.get("esi") or 0)
    pt = float(salary.get("pt") or 0)
    tds = float(salary.get("tds") or 0)
    other_deduction_std = float(salary.get("other_deduction") or 0)

    additions = (
        float(extras.get("bonus") or 0)
        + float(extras.get("incentives") or 0)
        + float(extras.get("overtime") or 0)
    )
    deductions_extra = (
        float(extras.get("advances_recovered") or 0)
        + float(extras.get("other_deductions") or 0)
    )

    gross = basic + hra + conveyance + medical + special + other_earning + additions
    deductions_total = pf + esi + pt + tds + other_deduction_std + deductions_extra
    net = round(gross - deductions_total, 2)

    return {
        "basic": basic, "hra": hra, "conveyance": conveyance,
        "medical": medical, "special": special, "other_earning": other_earning,
        "additions": round(additions, 2),
        "gross": round(gross, 2),
        "pf": pf, "esi": esi, "pt": pt, "tds": tds,
        "other_deduction": other_deduction_std,
        "extra_deductions": round(deductions_extra, 2),
        "deductions_total": round(deductions_total, 2),
        "net": net,
    }


@router.get("/employees/{eid}/salary/preview")
async def preview_salary(eid: str, year: int, month: int, request: Request,
                         bonus: float = 0, incentives: float = 0, overtime: float = 0,
                         advances_recovered: float = 0, other_deductions: float = 0,
                         session_token: Optional[str] = Cookie(default=None),
                         authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    if not (has_permission(user, "payroll.read") or has_permission(user, "employees.read")):
        raise HTTPException(status_code=403, detail="Missing permission")
    emp = await db.employees.find_one({"id": eid}, {"_id": 0})
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")

    # Attendance-based day count (payroll-ready)
    ym_start = _date(year, month, 1).isoformat()
    ym_end = (_date(year + (1 if month == 12 else 0), 1 if month == 12 else month + 1, 1)).isoformat()
    counts = {"present": 0, "half_day": 0, "leave": 0, "absent": 0, "holiday": 0, "week_off": 0}
    async for rec in db.attendance.find({"employee_id": eid, "date": {"$gte": ym_start, "$lt": ym_end}}, {"_id": 0}):
        s = rec.get("status") or "absent"
        counts[s] = counts.get(s, 0) + 1

    extras = {"bonus": bonus, "incentives": incentives, "overtime": overtime,
              "advances_recovered": advances_recovered, "other_deductions": other_deductions}
    breakdown = _compute_net(emp.get("salary"), extras)

    # Already paid check
    paid = await db.payroll_runs.find_one({"employee_id": eid, "year": year, "month": month},
                                          {"_id": 0, "id": 1, "paid_at": 1, "net": 1})
    return {
        "employee": {"id": emp["id"], "name": f"{emp.get('first_name','')} {emp.get('last_name','')}".strip(),
                     "employee_id": emp.get("employee_id")},
        "year": year, "month": month, "attendance": counts,
        "breakdown": breakdown,
        "already_paid": paid,
    }


@router.post("/employees/{eid}/pay-salary")
async def pay_salary(eid: str, payload: PaySalaryIn, request: Request,
                     session_token: Optional[str] = Cookie(default=None),
                     authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    if not has_permission(user, "payroll.create"):
        raise HTTPException(status_code=403, detail="Missing permission: payroll.create")
    emp = await db.employees.find_one({"id": eid}, {"_id": 0})
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")

    # Idempotent guard
    exists = await db.payroll_runs.find_one(
        {"employee_id": eid, "year": payload.year, "month": payload.month, "status": "paid"},
        {"_id": 0},
    )
    if exists:
        raise HTTPException(status_code=400, detail=f"Salary already paid for {payload.year}-{payload.month:02d}")

    extras = {
        "bonus": payload.bonus, "incentives": payload.incentives,
        "overtime": payload.overtime,
        "advances_recovered": payload.advances_recovered,
        "other_deductions": payload.other_deductions,
    }
    breakdown = _compute_net(emp.get("salary"), extras)
    net = breakdown["net"]
    if net <= 0:
        raise HTTPException(status_code=400, detail="Net salary must be > 0")

    # Resolve salary account
    salary_acc_id = payload.salary_account_id
    if not salary_acc_id:
        acc = await db.accounts.find_one({"name": "Employee Salary"}, {"_id": 0, "id": 1})
        if not acc:
            raise HTTPException(status_code=500, detail="'Employee Salary' account missing — seed COA")
        salary_acc_id = acc["id"]

    emp_name = f"{emp.get('first_name','')} {emp.get('last_name','')}".strip() or emp.get("employee_id") or eid
    narration = f"Salary {payload.year}-{payload.month:02d} — {emp_name}"
    lines = [
        {"account_id": salary_acc_id, "debit": net, "credit": 0, "description": f"Payroll — {emp_name}"},
        {"account_id": payload.paid_from_account_id, "debit": 0, "credit": net, "description": "Paid"},
    ]
    date_str = _date(payload.year, payload.month, 28).isoformat()   # end-of-month-ish
    je = await _post_journal(
        user, date_str, narration, lines,
        reference=payload.reference or f"PAYROLL-{payload.year}-{payload.month:02d}",
        source="payroll", source_id=eid,
    )

    run = {
        "id": new_id("pr_"),
        "employee_id": eid,
        "employee_name": emp_name,
        "year": payload.year,
        "month": payload.month,
        "breakdown": breakdown,
        "extras": extras,
        "net": net,
        "salary_account_id": salary_acc_id,
        "paid_from_account_id": payload.paid_from_account_id,
        "payment_method": payload.payment_method,
        "reference": payload.reference,
        "notes": payload.notes,
        "journal_id": je["id"],
        "status": "paid",
        "paid_at": iso_now(),
        "paid_by": user["user_id"],
        "paid_by_name": user.get("name"),
    }
    await db.payroll_runs.insert_one(dict(run))
    return {"run": run, "journal": je}


@router.get("/payroll/runs")
async def list_runs(request: Request, employee_id: Optional[str] = None,
                    year: Optional[int] = None, month: Optional[int] = None,
                    session_token: Optional[str] = Cookie(default=None),
                    authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    if not has_permission(user, "payroll.read"):
        raise HTTPException(status_code=403, detail="Missing permission: payroll.read")
    q: dict = {}
    if employee_id: q["employee_id"] = employee_id
    if year: q["year"] = year
    if month: q["month"] = month
    rows = await db.payroll_runs.find(q, {"_id": 0}).sort("paid_at", -1).to_list(500)
    return rows
