"""Payroll routes — pays employee, auto-posts JE to Accounting.

`POST /api/employees/{eid}/pay-salary` computes net salary from the employee
salary structure (already stored under `emp.salary.net_monthly`) and posts a
balanced journal entry (DR Employee Salary  CR Cash/Bank) via
`accounting._post_journal`. Idempotent per (employee_id, year, month) — a
`payroll_runs` doc guards against double payment.
"""
from fastapi import APIRouter, HTTPException, Request, Cookie, Header, Query
from fastapi.responses import StreamingResponse
from typing import Literal, Optional
from pydantic import BaseModel
from datetime import date as _date
import io
import math
import calendar
from fpdf import FPDF
from pymongo.errors import DuplicateKeyError

from core.pdf_brand import brand_primary_hex
from core.db import db
from core.period_lock import assert_period_open
from core.scoped_db import sdb
from core.helpers import business_today, now_utc, iso_now, new_id
from core.deps import require_user
from core.downloads import content_disposition
from core.rbac import has_permission
from core.tenancy import DEFAULT_ORG_ID
from core.tenancy import user_org_id
from core.audit import audit
from core.locks import doc_lock
from core import attendance_engine as engine
from routes.accounting import _post_journal
from routes.attendance import _get_attendance_policy

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
    payment_date: Optional[str] = None
    payment_method: Literal["cash", "bank_transfer", "upi", "cheque", "online", "other"] = "bank_transfer"
    reference: Optional[str] = None
    notes: Optional[str] = None
    # Jewellers logic — deduct LOP days, late fines and short-leave hours
    # computed from the attendance engine before posting the JE.
    apply_attendance_deductions: Optional[bool] = True


def _payroll_period_key(org_id: str, employee_id: str, year: int, month: int) -> str:
    return f"{org_id}:{employee_id}:{year:04d}-{month:02d}"


def _archived_period_key(period_key: str, run_id: str, why: str) -> str:
    """Unique key for a run that no longer holds its month.

    Never unset period_key: production still carries a legacy unique index on
    (org_id, period_key), under which a missing key counts as null and only one
    such run per company is allowed.
    """
    return f"{period_key}#{why}-{run_id}"


async def _assert_payroll_reviews_resolved(employee_id: str, year: int, month: int) -> None:
    start = _date(year, month, 1).isoformat()
    end = _date(year + (1 if month == 12 else 0),
                1 if month == 12 else month + 1, 1).isoformat()
    pending_attendance = await sdb.attendance.count_documents({
        "employee_id": employee_id,
        "date": {"$gte": start, "$lt": end},
        "$or": [
            {"approval_status": "pending"},
            {"late_approval_status": "pending"},
        ],
    })
    pending_corrections = await sdb.attendance_corrections.count_documents({
        "employee_id": employee_id,
        "date": {"$gte": start, "$lt": end},
        "status": "pending",
    })
    pending_leaves = await sdb.leaves.count_documents({
        "employee_id": employee_id,
        "status": "pending",
        "from_date": {"$lt": end},
        "to_date": {"$gte": start},
    })
    unresolved = pending_attendance + pending_corrections + pending_leaves
    if unresolved:
        raise HTTPException(
            status_code=409,
            detail=(f"Resolve {unresolved} pending attendance/leave request(s) "
                    "before paying this salary period."),
        )


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
    net = engine.rupee(gross - deductions_total)

    return {
        "basic": basic, "hra": hra, "conveyance": conveyance,
        "medical": medical, "special": special, "other_earning": other_earning,
        "additions": round(additions, 2),
        "gross": round(gross, 2),
        "pf": pf, "esi": esi, "pt": pt, "tds": tds,
        "other_deduction": other_deduction_std,
        "extra_deductions": round(deductions_extra, 2),
        "deductions_total": round(deductions_total, 2),
        "round_off": round(net - (gross - deductions_total), 2),
        "net": net,
    }


async def _apply_attendance_deductions(emp: dict, breakdown: dict,
                                       year: int, month: int) -> dict:
    """Merge attendance-engine deductions (LOP / late fine / short leave)
    into an existing salary breakdown. Jewellers ERP logic."""
    policy = await _get_attendance_policy()
    s = await engine.monthly_summary(emp, year, month, policy)
    att_ded = round(float(s["lop_deduction"]) + float(s["late_fine"])
                    + float(s["short_leave_deduction"]), 2)
    breakdown = dict(breakdown)
    # Jewellers fallback: if no salary structure is configured, pay from the
    # flat monthly salary used by the attendance engine.
    flat = float(s["employee"].get("monthly_salary") or 0)
    if (breakdown.get("gross") or 0) <= 0 and flat > 0:
        breakdown["basic"] = flat
        breakdown["gross"] = round(flat + float(breakdown.get("additions") or 0), 2)
    breakdown["payable_days"] = s["payable_days"]
    breakdown["lop_days"] = s["lop_days"]
    breakdown["monthly_paid_leave_allowance"] = s["monthly_paid_leave_allowance"]
    breakdown["paid_leave_allowance_used"] = s["paid_leave_allowance_used"]
    breakdown["excess_ordinary_leave_days"] = s["excess_ordinary_leave_days"]
    breakdown["lop_deduction"] = s["lop_deduction"]
    breakdown["late_fine"] = s["late_fine"]
    breakdown["short_leave_hours"] = s["short_leave_hours"]
    breakdown["short_leave_deduction"] = s["short_leave_deduction"]
    breakdown["attendance_deductions"] = att_ded
    # Transparency: the formula inputs and a reason for every deducted day.
    breakdown["per_day_rate"] = s.get("per_day_rate")
    breakdown["hourly_rate"] = s.get("hourly_rate")
    breakdown["basis_days"] = int(emp.get("payroll_basis_days") or 30)
    breakdown["monthly_salary_used"] = flat
    breakdown["attendance_summary"] = s.get("summary") or {}
    lines = []
    per_day = float(s.get("per_day_rate") or 0)
    for d in s.get("daily") or []:
        status = d.get("status")
        if status in ("absent", "unpaid_leave"):
            lines.append({"date": d.get("date"), "reason": "Absent" if status == "absent" else "Unpaid leave",
                          "kind": "lop", "days": 1, "amount": engine.rupee(per_day)})
        elif status == "half_day":
            lines.append({"date": d.get("date"), "reason": "Half day", "kind": "lop", "days": 0.5,
                          "amount": engine.rupee(per_day / 2)})
        fine = float(d.get("late_fine_amount") or 0)
        if fine > 0 and not d.get("late_fine_waived"):
            lines.append({"date": d.get("date"), "kind": "late",
                          "reason": f"Late by {d.get('late_minutes') or 0} min", "amount": engine.rupee(fine)})
        if float(d.get("short_leave_hours") or 0) > 0:
            lines.append({"date": d.get("date"), "kind": "short_leave",
                          "reason": f"Short leave {d['short_leave_hours']:g} h",
                          "amount": engine.rupee(float(s.get("hourly_rate") or 0) * float(d["short_leave_hours"]))})
    breakdown["deduction_lines"] = lines[:93]
    breakdown["deductions_total"] = round(breakdown["deductions_total"] + att_ded, 2)
    exact = breakdown["gross"] - breakdown["deductions_total"]
    breakdown["net"] = engine.rupee(exact)
    breakdown["round_off"] = round(breakdown["net"] - exact, 2)
    return breakdown


@router.get("/employees/{eid}/salary/preview")
async def preview_salary(eid: str, year: int, month: int, request: Request,
                         bonus: float = 0, incentives: float = 0, overtime: float = 0,
                         advances_recovered: float = 0, other_deductions: float = 0,
                         session_token: Optional[str] = Cookie(default=None),
                         authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    if not has_permission(user, "payroll.read"):
        raise HTTPException(status_code=403, detail="Missing permission: payroll.read")
    emp = await sdb.employees.find_one({"id": eid}, {"_id": 0})
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")

    # Attendance-based day count (payroll-ready)
    ym_start = _date(year, month, 1).isoformat()
    ym_end = (_date(year + (1 if month == 12 else 0), 1 if month == 12 else month + 1, 1)).isoformat()
    counts = {"present": 0, "half_day": 0, "leave": 0, "absent": 0, "holiday": 0, "week_off": 0}
    async for rec in sdb.attendance.find({"employee_id": eid, "date": {"$gte": ym_start, "$lt": ym_end}}, {"_id": 0}):
        s = rec.get("status") or "absent"
        counts[s] = counts.get(s, 0) + 1

    extras = {"bonus": bonus, "incentives": incentives, "overtime": overtime,
              "advances_recovered": advances_recovered, "other_deductions": other_deductions}
    breakdown = _compute_net(emp.get("salary"), extras)
    breakdown = await _apply_attendance_deductions(emp, breakdown, year, month)

    # Already paid check
    paid = await sdb.payroll_runs.find_one({"employee_id": eid, "year": year, "month": month,
                                           "status": "paid"},
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
    emp = await sdb.employees.find_one({"id": eid}, {"_id": 0})
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")
    if payload.month < 1 or payload.month > 12:
        raise HTTPException(status_code=400, detail="month must be 1..12")
    payment_date = payload.payment_date or business_today().isoformat()
    try:
        _date.fromisoformat(payment_date)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="payment_date must be YYYY-MM-DD")
    await _assert_payroll_reviews_resolved(eid, payload.year, payload.month)

    # Idempotent guard
    exists = await sdb.payroll_runs.find_one(
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
    from routes import employee_advances as _adv
    recovered = round(float(payload.advances_recovered or 0), 2)
    if recovered < 0:
        raise HTTPException(status_code=400, detail="Advance recovery cannot be negative")
    if recovered > 0:
        outstanding = float(await _adv.outstanding_for(eid))
        if recovered > outstanding + 0.004:
            raise HTTPException(status_code=400, detail=(
                f"Only Rs. {outstanding:,.2f} of advances is outstanding for this employee. "
                "Record the advance first (Employee > Advances) or reduce the recovery."))
    breakdown = _compute_net(emp.get("salary"), extras)
    if payload.apply_attendance_deductions:
        breakdown = await _apply_attendance_deductions(emp, breakdown, payload.year, payload.month)
    net = breakdown["net"]
    if net <= 0:
        raise HTTPException(status_code=400, detail="Net salary must be > 0")

    # Resolve salary account
    salary_acc_id = payload.salary_account_id
    if not salary_acc_id:
        acc = await sdb.accounts.find_one(
            {"name": "Employee Salary"}, {"_id": 0, "id": 1, "type": 1})
        if not acc:
            raise HTTPException(status_code=500, detail="'Employee Salary' account missing — seed COA")
        salary_acc_id = acc["id"]
    else:
        acc = await sdb.accounts.find_one(
            {"id": salary_acc_id}, {"_id": 0, "id": 1, "type": 1})
    paid_from = await sdb.accounts.find_one(
        {"id": payload.paid_from_account_id},
        {"_id": 0, "id": 1, "type": 1, "name": 1, "is_bank": 1})
    if not acc or str(acc.get("type") or "").lower() != "expense":
        raise HTTPException(status_code=400, detail="Salary account must be an expense account")
    if not paid_from or str(paid_from.get("type") or "").lower() != "asset":
        raise HTTPException(status_code=400, detail="Paid-from account must be a cash/bank asset account")
    if salary_acc_id == payload.paid_from_account_id:
        raise HTTPException(status_code=400, detail="Salary and paid-from accounts must be different")
    from core.finance import validate_method_account
    validate_method_account(payload.payment_method, paid_from, label="salary payments")

    emp_name = f"{emp.get('first_name','')} {emp.get('last_name','')}".strip() or emp.get("employee_id") or eid
    narration = f"Salary {payload.year}-{payload.month:02d} — {emp_name}"
    lines = [
        {"account_id": salary_acc_id, "debit": round(net + recovered, 2), "credit": 0,
         "description": f"Payroll — {emp_name}"},
        {"account_id": payload.paid_from_account_id, "debit": 0, "credit": net, "description": "Paid"},
    ]
    if recovered > 0:
        # The recovered part of salary settles the employee's advance, not cash.
        adv_account = await _adv.advances_account()
        lines.append({"account_id": adv_account["id"], "debit": 0, "credit": recovered,
                      "description": f"Advance recovered — {emp_name}"})
    date_str = payment_date
    run_id = new_id("pr_")
    run = {
        "id": run_id,
        "employee_id": eid,
        "employee_name": emp_name,
        "year": payload.year,
        "month": payload.month,
        "period_key": _payroll_period_key(
            user.get("org_id") or "org_default", eid, payload.year, payload.month),
        "breakdown": breakdown,
        "extras": extras,
        "net": net,
        "salary_account_id": salary_acc_id,
        "paid_from_account_id": payload.paid_from_account_id,
        "paid_from_account_name": paid_from.get("name"),
        "payment_date": payment_date,
        "payment_method": payload.payment_method,
        "reference": payload.reference,
        "notes": payload.notes,
        "journal_id": None,
        "status": "processing",
        "created_at": iso_now(),
        "paid_by": user["user_id"],
        "paid_by_name": user.get("name"),
    }
    try:
        await sdb.payroll_runs.insert_one(dict(run))
    except DuplicateKeyError:
        prior = await sdb.payroll_runs.find_one(
            {"period_key": run["period_key"]}, {"_id": 0})
        if prior and prior.get("status") == "paid":
            raise HTTPException(400, f"Salary already paid for {payload.year}-{payload.month:02d}")
        if prior and prior.get("status") == "processing":
            # A process can stop after the balanced journal is inserted but
            # before the payroll row is finalized. Recover that exact run
            # instead of posting salary twice or leaving it stuck forever.
            je = await sdb.journal_entries.find_one(
                {"source": "payroll", "source_id": prior["id"],
                 "reversed": {"$ne": True}}, {"_id": 0})
            if je:
                paid_at = prior.get("paid_at") or iso_now()
                await sdb.payroll_runs.update_one(
                    {"id": prior["id"], "status": "processing"},
                    {"$set": {"journal_id": je["id"], "status": "paid",
                              "paid_at": paid_at}},
                )
                prior.update({"journal_id": je["id"], "status": "paid",
                              "paid_at": paid_at})
                return {"run": prior, "journal": je, "recovered": True}
        raise HTTPException(409, "Salary payment for this period is already being processed")

    try:
        je = await _post_journal(
            user, date_str, narration, lines,
            reference=payload.reference or f"PAYROLL-{payload.year}-{payload.month:02d}",
            employee_id=eid, source="payroll", source_id=run_id,
        )
    except Exception:
        await sdb.payroll_runs.delete_one(
            {"id": run_id, "status": "processing", "journal_id": None})
        raise

    paid_at = iso_now()
    finalized = await sdb.payroll_runs.update_one(
        {"id": run_id, "status": "processing", "journal_id": None},
        {"$set": {"journal_id": je["id"], "status": "paid", "paid_at": paid_at}},
    )
    if finalized.modified_count != 1:
        raise HTTPException(
            500, "Salary journal posted but payroll finalization needs administrator review")
    run.update({"journal_id": je["id"], "status": "paid", "paid_at": paid_at})
    if recovered > 0:
        run["advance_recoveries"] = await _adv.apply_recovery(
            eid, run_id, payload.year, payload.month, recovered, payment_date)
        await sdb.payroll_runs.update_one(
            {"id": run_id}, {"$set": {"advance_recoveries": run["advance_recoveries"]}})
    await audit(user, "payroll.payment", target=run_id, target_type="payroll_run",
                meta={"employee_id": eid, "year": payload.year, "month": payload.month,
                      "payment_date": payment_date, "payment_method": payload.payment_method,
                      "paid_from_account_id": payload.paid_from_account_id},
                org_id=user_org_id(user))
    return {"run": run, "journal": je}


@router.get("/payroll/runs")
async def list_runs(request: Request, employee_id: Optional[str] = None,
                    year: Optional[int] = Query(None, ge=2000, le=2100), month: Optional[int] = Query(None, ge=1, le=12),
                    session_token: Optional[str] = Cookie(default=None),
                    authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    if not has_permission(user, "payroll.read"):
        raise HTTPException(status_code=403, detail="Missing permission: payroll.read")
    q: dict = {}
    if employee_id: q["employee_id"] = employee_id
    if year: q["year"] = year
    if month: q["month"] = month
    rows = await sdb.payroll_runs.find(q, {"_id": 0}).sort("paid_at", -1).to_list(None)
    return rows


@router.post("/payroll/runs/{run_id}/reverse")
async def reverse_salary_payment(run_id: str, request: Request,
                                 session_token: Optional[str] = Cookie(default=None),
                                 authorization: Optional[str] = Header(default=None)):
    """Cancel a mistaken salary payment by balanced reversal, never hard deletion."""
    user = await require_user(request, session_token, authorization)
    if not has_permission(user, "payroll.create") or not has_permission(user, "finance.update"):
        raise HTTPException(status_code=403, detail="Payroll create and finance update permissions are required")
    async with doc_lock(sdb.payroll_runs, run_id):
        run = await sdb.payroll_runs.find_one({"id": run_id}, {"_id": 0})
        if not run:
            raise HTTPException(status_code=404, detail="Payroll run not found")
        if run.get("status") != "paid":
            raise HTTPException(status_code=409, detail="Only a paid salary can be reversed")
        journal = await sdb.journal_entries.find_one(
            {"id": run.get("journal_id"), "source": "payroll", "source_id": run_id},
            {"_id": 0},
        )
        if not journal:
            raise HTTPException(status_code=409, detail="Linked payroll journal is missing; administrator review required")
        from routes.accounting import _hide_reversed_pair, _reverse_journal_entry
        # A cancelled salary leaves the Daybook and ledgers entirely: the reversal is
        # dated with the payment and both stay only in the audit trail.
        if journal.get("reversed") and journal.get("reversal_je_id"):
            reversal = await sdb.journal_entries.find_one(
                {"id": journal["reversal_je_id"]}, {"_id": 0})
            if not reversal:
                raise HTTPException(status_code=409, detail="Payroll reversal needs administrator review")
            await _hide_reversed_pair(user, journal, "payroll_cancel")
        else:
            reversal = await _reverse_journal_entry(
                user, journal, action="payroll_cancel",
                reversal_date=journal.get("date"), hide_from_books=True)
        changed_at = iso_now()
        result = await sdb.payroll_runs.update_one(
            {"id": run_id, "status": "paid"},
            {"$set": {"status": "reversed", "reversed_at": changed_at,
                      "reversed_by": user["user_id"], "reversal_journal_id": reversal["id"],
                      "original_period_key": run.get("period_key"),
                      "period_key": _archived_period_key(
                          run.get("period_key") or run_id, run_id, "reversed")}},
        )
        if result.modified_count != 1:
            raise HTTPException(status_code=409, detail="Payroll run changed; refresh and retry")
        # money recovered from this salary is owed again
        from routes.employee_advances import restore_recovery
        await restore_recovery(run_id)
    await audit(user, "payroll.payment.reverse", target=run_id, target_type="payroll_run",
                meta={"employee_id": run.get("employee_id"),
                      "reversal_journal_id": reversal["id"]},
                org_id=user_org_id(user))
    return {"ok": True, "status": "reversed", "reversal_journal_id": reversal["id"]}


class SalaryCorrectionIn(BaseModel):
    net: float                          # the amount actually paid
    bonus: Optional[float] = None       # part of net shown as bonus on the slip
    payment_date: str
    paid_from_account_id: str
    payment_method: Literal["cash", "bank_transfer", "upi", "cheque", "online", "other"] = "cash"
    reference: Optional[str] = None
    notes: Optional[str] = None


def _corrected_breakdown(run: dict, net: float, bonus: Optional[float]) -> tuple:
    """Rebuild the slip so earnings - deductions equals the corrected net."""
    breakdown = dict(run.get("breakdown") or {})
    extras = dict(run.get("extras") or {})
    old_net = float(run.get("net") or 0)
    old_bonus = float(extras.get("bonus") or 0)
    new_bonus = old_bonus if bonus is None else float(bonus)
    delta_bonus = round(new_bonus - old_bonus, 2)
    extras["bonus"] = new_bonus
    breakdown["additions"] = round(float(breakdown.get("additions") or 0) + delta_bonus, 2)
    breakdown["gross"] = round(float(breakdown.get("gross") or 0) + delta_bonus, 2)
    rest = round(net - (old_net + delta_bonus), 2)
    if rest > 0:
        breakdown["other_earning"] = round(float(breakdown.get("other_earning") or 0) + rest, 2)
        breakdown["gross"] = round(breakdown["gross"] + rest, 2)
    elif rest < 0:
        breakdown["other_deduction"] = round(float(breakdown.get("other_deduction") or 0) - rest, 2)
        breakdown["deductions_total"] = round(float(breakdown.get("deductions_total") or 0) - rest, 2)
    breakdown["net"] = net
    return breakdown, extras


@router.post("/payroll/runs/{run_id}/correct")
async def correct_salary_payment(run_id: str, payload: SalaryCorrectionIn, request: Request,
                                 session_token: Optional[str] = Cookie(default=None),
                                 authorization: Optional[str] = Header(default=None)):
    """Edit a salary already paid (amount, bonus, date, account).

    The old payment leaves the books (kept in the audit trail) and the corrected
    one is posted in its place, so the Daybook and employee sheet show one entry.
    """
    user = await require_user(request, session_token, authorization)
    if not has_permission(user, "payroll.create") or not has_permission(user, "finance.update"):
        raise HTTPException(status_code=403, detail="Payroll create and finance update permissions are required")
    net = round(float(payload.net or 0), 2)
    if not math.isfinite(net) or net <= 0:
        raise HTTPException(status_code=400, detail="Amount paid must be greater than zero")
    if payload.bonus is not None and (not math.isfinite(float(payload.bonus)) or payload.bonus < 0 or payload.bonus > net):
        raise HTTPException(status_code=400, detail="Bonus must be between zero and the amount paid")
    try:
        _date.fromisoformat(payload.payment_date)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="payment_date must be YYYY-MM-DD")
    async with doc_lock(sdb.payroll_runs, run_id):
        run = await sdb.payroll_runs.find_one({"id": run_id}, {"_id": 0})
        if not run:
            raise HTTPException(status_code=404, detail="Payroll run not found")
        if run.get("status") not in {"paid", "reversed"}:
            raise HTTPException(status_code=409, detail="This payment was already replaced; edit the latest one")
        if float((run.get("extras") or {}).get("advances_recovered") or 0) > 0:
            raise HTTPException(status_code=409, detail=(
                "This salary also recovered an advance. Cancel it and pay again instead."))
        other = await sdb.payroll_runs.find_one(
            {"employee_id": run["employee_id"], "year": run["year"], "month": run["month"],
             "status": {"$in": ["paid", "processing"]}, "id": {"$ne": run_id}}, {"_id": 0, "id": 1})
        if other:
            raise HTTPException(status_code=409, detail="Another payment for this month is recorded; edit that one")
        journal = await sdb.journal_entries.find_one(
            {"id": run.get("journal_id"), "source": "payroll", "source_id": run_id}, {"_id": 0})
        if not journal:
            raise HTTPException(status_code=409, detail="Linked payroll journal is missing; administrator review required")
        # The old payment leaves the books on its own date: refuse up front if
        # that period is closed, before the replacement is written.
        await assert_period_open(journal.get("date"), "The salary being edited")
        await assert_period_open(payload.payment_date, "The corrected salary")
        paid_from = await sdb.accounts.find_one(
            {"id": payload.paid_from_account_id},
            {"_id": 0, "id": 1, "type": 1, "name": 1, "is_bank": 1, "active": 1})
        if not paid_from or paid_from.get("active") is False or str(paid_from.get("type") or "").lower() != "asset":
            raise HTTPException(status_code=400, detail="Paid-from account must be a cash/bank asset account")
        from core.finance import validate_method_account
        validate_method_account(payload.payment_method, paid_from, label="salary payments")
        salary_acc_id = run.get("salary_account_id")
        if not salary_acc_id:
            raise HTTPException(status_code=409, detail="Salary account missing on this run")

        breakdown, extras = _corrected_breakdown(run, net, payload.bonus)
        emp_name = run.get("employee_name") or run["employee_id"]
        new_run_id = new_id("pr_")
        new_run = {
            **{k: run.get(k) for k in ("employee_id", "employee_name", "year", "month", "salary_account_id")},
            "id": new_run_id,
            "breakdown": breakdown, "extras": extras, "net": net,
            "paid_from_account_id": paid_from["id"], "paid_from_account_name": paid_from.get("name"),
            "payment_date": payload.payment_date, "payment_method": payload.payment_method,
            "reference": payload.reference, "notes": payload.notes,
            "journal_id": None, "status": "processing", "corrected_from_run_id": run_id,
            "period_key": _archived_period_key(
                (run.get("original_period_key") or run.get("period_key") or run_id).split("#")[0], new_run_id, "pending"),
            "created_at": iso_now(), "paid_by": user["user_id"], "paid_by_name": user.get("name"),
        }
        await sdb.payroll_runs.insert_one(dict(new_run))
        try:
            je = await _post_journal(
                user, payload.payment_date, f"Salary {run['year']}-{run['month']:02d} — {emp_name}",
                [{"account_id": salary_acc_id, "debit": net, "credit": 0, "description": f"Payroll — {emp_name}"},
                 {"account_id": paid_from["id"], "debit": 0, "credit": net, "description": "Paid"}],
                reference=payload.reference or f"PAYROLL-{run['year']}-{run['month']:02d}",
                employee_id=run["employee_id"], source="payroll", source_id=new_run_id,
            )
        except Exception:
            await sdb.payroll_runs.delete_one({"id": new_run_id, "status": "processing"})
            raise

        from routes.accounting import _hide_reversed_pair, _reverse_journal_entry
        if journal.get("reversed"):
            await _hide_reversed_pair(user, journal, "payroll_correction")
        else:
            await _reverse_journal_entry(user, journal, action="payroll_correction",
                                         reversal_date=journal.get("date"), hide_from_books=True)
        changed_at = iso_now()
        period_key = (run.get("original_period_key") or run.get("period_key") or "").split("#")[0] or _payroll_period_key(
            user.get("org_id") or "org_default", run["employee_id"], run["year"], run["month"])
        await sdb.payroll_runs.update_one(
            {"id": run_id},
            {"$set": {"status": "corrected", "corrected_at": changed_at, "corrected_by": user["user_id"],
                      "corrected_to_run_id": new_run_id, "original_period_key": period_key,
                      "period_key": _archived_period_key(period_key, run_id, "corrected")}},
        )
        await sdb.payroll_runs.update_one(
            {"id": new_run_id},
            {"$set": {"journal_id": je["id"], "status": "paid", "paid_at": changed_at,
                      "period_key": period_key}},
        )
        new_run.update({"journal_id": je["id"], "status": "paid", "paid_at": changed_at, "period_key": period_key})
    await audit(user, "payroll.payment.correct", target=run_id, target_type="payroll_run",
                meta={"employee_id": run["employee_id"], "old_net": run.get("net"), "new_net": net,
                      "new_run_id": new_run_id, "payment_date": payload.payment_date},
                org_id=user_org_id(user))
    return {"run": new_run, "journal": je}


# ==================================================================
# SALARY SLIP PDF — company-branded, monthly earnings/deductions
# ==================================================================
def _safe(s) -> str:
    """Latin-1 sanitise for FPDF Helvetica."""
    if s is None:
        return ""
    s = str(s)
    repl = {
        "\u2013": "-", "\u2014": "-", "\u2018": "'", "\u2019": "'",
        "\u201C": '"', "\u201D": '"', "\u2022": "*", "\u2026": "...",
        "\u20B9": "Rs.", "\u2122": "TM", "\u00A9": "(c)",
    }
    for k, v in repl.items():
        s = s.replace(k, v)
    return s.encode("latin-1", "replace").decode("latin-1")


def _hex_to_rgb(h: str):
    try:
        h = (h or "").lstrip("#")
        if len(h) == 3:
            h = "".join(c * 2 for c in h)
        return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    except Exception:
        return 0, 47, 167


def _fmt_amt(n: float) -> str:
    try:
        return f"{float(n or 0):,.2f}"
    except Exception:
        return "0.00"


def _generate_salary_slip_pdf(emp: dict, run: dict, org: dict,
                              attendance: dict) -> bytes:
    from core.pdf_brand import Brand, BrandedPDF, draw_letterhead
    month_label = calendar.month_name[run["month"]]
    brand = Brand(org)
    primary = brand.primary
    pdf = BrandedPDF(brand, "Salary Slip", f"{month_label} {run['year']}", bottom_margin=20)
    pdf.add_page()
    draw_letterhead(pdf, "Salary Slip", [
        ("Pay period", f"{month_label} {run['year']}"),
        ("Paid on", _display_date(run.get("payment_date") or run.get("paid_at"))),
        ("Status", "Reversed" if run.get("status") == "reversed" else "Paid"),
    ])
    pdf.set_text_color(0, 0, 0)

    # === Employee block ===
    emp_name = f"{emp.get('first_name','')} {emp.get('last_name','')}".strip() or emp.get("employee_id") or ""
    _kv(pdf, "Employee Name", emp_name, "Employee ID", emp.get("employee_id") or "-")
    _kv(pdf, "Department", emp.get("department") or "-", "Designation",
        emp.get("designation") or emp.get("role_title") or "-")
    _kv(pdf, "Date of Joining", _display_date(emp.get("joining_date")) if emp.get("joining_date") else "-",
         "Pay Period", f"{month_label} {run['year']}")
    _kv(pdf, "Bank A/C", _mask_account((emp.get("bank") or {}).get("account_number")),
         "PAN", emp.get("pan") or "-")
    pdf.ln(2)

    # === Attendance summary (same figures the salary was calculated from) ===
    boxes = [
        ("Days in month", calendar.monthrange(run["year"], run["month"])[1]),
        ("Present", attendance.get("present", 0)),
        ("Offs & holidays", attendance.get("offs", 0)),
        ("Paid leave", attendance.get("paid_leave", 0)),
        ("Unpaid leave", attendance.get("unpaid_leave", 0)),
        ("Absent", attendance.get("absent", 0)),
        ("Half days", attendance.get("half_day", 0)),
    ]
    width = 180 / len(boxes)
    pdf.set_fill_color(240, 240, 240)
    pdf.set_font("Helvetica", "B", 8)
    for i, (label, _v) in enumerate(boxes):
        pdf.cell(width, 7, label, 1, 1 if i == len(boxes) - 1 else 0, "C", fill=True)
    pdf.set_font("Helvetica", "", 10)
    for i, (_label, value) in enumerate(boxes):
        pdf.cell(width, 7, _count(value), 1, 1 if i == len(boxes) - 1 else 0, "C")
    if attendance.get("paid_days") is not None:
        pdf.set_font("Helvetica", "I", 8)
        pdf.set_text_color(90, 90, 90)
        note = (f"Paid days {_count(attendance['paid_days'])} · loss of pay "
                f"{_count(attendance.get('lop_days', 0))} day(s)")
        if attendance.get("as_of_today"):
            note = ("Attendance as recorded today; salary was calculated on the attendance at payment. " + note)
        pdf.multi_cell(0, 4.5, _safe(note), 0, "R")
        pdf.set_text_color(0, 0, 0)
    pdf.ln(2)

    # === Earnings / Deductions tables (side by side) ===
    breakdown = run.get("breakdown") or {}
    earn_rows = [
        ("Basic",         breakdown.get("basic")),
        ("HRA",           breakdown.get("hra")),
        ("Conveyance",    breakdown.get("conveyance")),
        ("Medical",       breakdown.get("medical")),
        ("Special Allow", breakdown.get("special")),
        ("Other Earning", breakdown.get("other_earning")),
    ]
    additions = breakdown.get("additions") or 0
    if additions:
        earn_rows.append(("Bonus / OT / Incentives", additions))
    ded_rows = [
        ("PF",              breakdown.get("pf")),
        ("ESI",             breakdown.get("esi")),
        ("Prof. Tax",       breakdown.get("pt")),
        ("TDS",             breakdown.get("tds")),
        ("Other Deduction", breakdown.get("other_deduction")),
    ]
    extra_ded = breakdown.get("extra_deductions") or 0
    if extra_ded:
        ded_rows.append(("Advances / Recovery", extra_ded))
    round_off = float(breakdown.get("round_off") or 0)
    if round_off > 0:
        earn_rows.append(("Round off", round_off))
    elif round_off < 0:
        ded_rows.append(("Round off", -round_off))
    # Attendance-engine deductions (Jewellers logic)
    if breakdown.get("lop_deduction"):
        lop = _count(breakdown.get("lop_days", 0))
        ded_rows.append((f"Loss of Pay ({lop} day{'' if lop == '1' else 's'})", breakdown.get("lop_deduction")))
    if breakdown.get("late_fine"):
        ded_rows.append(("Late Fine", breakdown.get("late_fine")))
    if breakdown.get("short_leave_deduction"):
        ded_rows.append((f"Short Leave ({_count(breakdown.get('short_leave_hours', 0))} h)", breakdown.get("short_leave_deduction")))

    # header row
    pdf.set_fill_color(*primary)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(90, 7, "EARNINGS", 1, 0, "L", fill=True)
    pdf.cell(90, 7, "DEDUCTIONS", 1, 1, "L", fill=True)

    pdf.set_text_color(0, 0, 0)
    pdf.set_font("Helvetica", "", 10)
    n = max(len(earn_rows), len(ded_rows))
    for i in range(n):
        e = earn_rows[i] if i < len(earn_rows) else ("", 0)
        d = ded_rows[i] if i < len(ded_rows) else ("", 0)
        pdf.cell(60, 6, _safe(e[0]), 1, 0, "L")
        pdf.cell(30, 6, _fmt_amt(e[1]) if e[0] else "", 1, 0, "R")   # empty filler rows stay blank
        pdf.cell(60, 6, _safe(d[0]), 1, 0, "L")
        pdf.cell(30, 6, _fmt_amt(d[1]) if d[0] else "", 1, 1, "R")

    # Totals row
    pdf.set_font("Helvetica", "B", 10)
    pdf.set_fill_color(240, 240, 240)
    pdf.cell(60, 7, "GROSS", 1, 0, "L", fill=True)
    pdf.cell(30, 7, _fmt_amt(breakdown.get("gross")), 1, 0, "R", fill=True)
    pdf.cell(60, 7, "TOTAL DEDUCTIONS", 1, 0, "L", fill=True)
    pdf.cell(30, 7, _fmt_amt(breakdown.get("deductions_total")), 1, 1, "R", fill=True)

    pdf.ln(3)

    # === Net Pay callout ===
    pdf.set_fill_color(*primary)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Helvetica", "B", 13)
    pdf.cell(0, 12, _safe(f"  NET PAY:  Rs. {_fmt_amt(run.get('net'))}"), 1, 1, "L", fill=True)

    # Amount in words (simple version)
    pdf.set_text_color(0, 0, 0)
    pdf.set_font("Helvetica", "I", 9)
    method = (run.get("payment_method") or "bank_transfer").replace("_", " ")
    paid_line = f"Paid on {_display_date(run.get('payment_date') or run.get('paid_at'))} by {method}"
    if run.get("paid_from_account_name"):
        paid_line += f" from {run['paid_from_account_name']}"
    if run.get("reference"):
        paid_line += f"  (Ref: {run['reference']})"
    pdf.cell(0, 6, _safe(paid_line), ln=1)

    if run.get("notes"):
        pdf.ln(1)
        pdf.set_font("Helvetica", "", 9)
        pdf.multi_cell(0, 5, _safe(f"Notes: {run['notes']}"))
    from core.pdf_brand import draw_signatory
    pdf.ln(6)
    if pdf.get_y() > 240:
        pdf.add_page()
    draw_signatory(pdf, 125, 70)
    return pdf.to_bytes()


def _mask_account(value) -> str:
    digits = str(value or "").strip()
    if not digits:
        return "-"
    return ("X" * max(0, min(len(digits) - 4, 8))) + digits[-4:]


def _display_date(value) -> str:
    raw = str(value or "").strip()[:10]
    try:
        return _date.fromisoformat(raw).strftime("%d/%m/%Y")
    except ValueError:
        return raw or "-"


def _count(value) -> str:
    """1.0 -> '1', 2.5 -> '2.5' (half days)."""
    try:
        v = float(value or 0)
    except (TypeError, ValueError):
        return "0"
    return str(int(v)) if v.is_integer() else f"{v:g}"


def _slip_attendance(summary: dict, breakdown: dict) -> dict:
    """Engine summary -> slip boxes. Days with no punch are absent, late counts as present."""
    s = summary or {}
    return {
        "present": float(s.get("present") or 0) + float(s.get("late") or 0) + float(s.get("site_visit") or 0),
        "offs": float(s.get("week_off") or 0) + float(s.get("holidays") or 0),
        "paid_leave": s.get("paid_leave") or 0,
        "unpaid_leave": s.get("unpaid_leave") or 0,
        "absent": s.get("absent") or 0,
        "half_day": s.get("half_day") or 0,
        "paid_days": breakdown.get("payable_days"),
        "lop_days": breakdown.get("lop_days") or 0,
    }


def _kv(pdf, k1, v1, k2, v2):
    pdf.set_font("Helvetica", "B", 9)
    pdf.cell(32, 6, _safe(k1) + ":", 0, 0, "L")
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(63, 6, _safe(v1), 0, 0, "L")
    pdf.set_font("Helvetica", "B", 9)
    pdf.cell(32, 6, _safe(k2) + ":", 0, 0, "L")
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 6, _safe(v2), 0, 1, "L")


@router.get("/payroll/runs/{run_id}/slip.pdf")
async def salary_slip_pdf(run_id: str, request: Request,
                          session_token: Optional[str] = Cookie(default=None),
                          authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    # Own slip allowed, else needs payroll.read
    run = await sdb.payroll_runs.find_one({"id": run_id}, {"_id": 0})
    if not run:
        raise HTTPException(404, "Payroll run not found")
    emp = await sdb.employees.find_one({"id": run["employee_id"]}, {"_id": 0})
    if not emp:
        raise HTTPException(404, "Employee not found")
    is_self = (user.get("employee_id") and user["employee_id"] == emp.get("employee_id")) \
              or (emp.get("user_id") == user.get("user_id"))
    if not is_self and not has_permission(user, "payroll.read"):
        raise HTTPException(403, "Missing permission: payroll.read")

    # Attendance boxes: the summary saved when the salary was paid (what the
    # deductions were calculated from); older runs fall back to the engine now.
    breakdown = run.get("breakdown") or {}
    summary = breakdown.get("attendance_summary")
    if not summary:
        policy = await _get_attendance_policy()
        calc = await engine.monthly_summary(emp, run["year"], run["month"], policy)
        summary = calc["summary"]
        breakdown = {**breakdown, "payable_days": breakdown.get("payable_days", calc.get("payable_days")),
                     "lop_days": breakdown.get("lop_days", calc.get("lop_days"))}
    counts = _slip_attendance(summary, breakdown)
    counts["as_of_today"] = not (run.get("breakdown") or {}).get("attendance_summary")

    # Org branding
    org = await db.organizations.find_one(
        {"org_id": run.get("org_id") or emp.get("org_id") or DEFAULT_ORG_ID},
        {"_id": 0},
    )
    pdf_bytes = _generate_salary_slip_pdf(emp, run, org, counts)
    fname = f"salary_slip_{emp.get('employee_id','emp')}_{run['year']}_{run['month']:02d}.pdf"
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": content_disposition(
            "inline", fname, "salary-slip.pdf")},
    )


# ==================================================================
# JEWELLERS ERP PORTED — Payroll Preview + On-demand Payslip
# ==================================================================
@router.get("/payroll/preview")
async def payroll_preview_all(year: int, month: int, request: Request,
                              session_token: Optional[str] = Cookie(default=None),
                              authorization: Optional[str] = Header(default=None)):
    """Attendance-linked monthly payroll preview across all employees.
    net = monthly - (LOP deduction + late fines + short-leave deduction)."""
    user = await require_user(request, session_token, authorization)
    if not has_permission(user, "payroll.read"):
        raise HTTPException(status_code=403, detail="Missing permission: payroll.read")
    if month < 1 or month > 12:
        raise HTTPException(400, "month must be 1..12")
    policy = await _get_attendance_policy()
    data = await engine.payroll_preview(year, month, policy)
    # Flag employees already paid this month
    paid_ids = set()
    async for r in sdb.payroll_runs.find({"year": year, "month": month, "status": "paid"},
                                         {"_id": 0, "employee_id": 1}):
        paid_ids.add(r["employee_id"])
    for row in data["employees"]:
        row["already_paid"] = row["employee_id"] in paid_ids
    return data


def _generate_attendance_payslip_pdf(s: dict, org: dict) -> bytes:
    """Salary-impact payslip built from the attendance engine summary
    (works before payment — Jewellers 'my payslip' style)."""
    branding = (org or {}).get("branding") or {}
    primary = _hex_to_rgb(brand_primary_hex(branding))

    emp = s["employee"]
    summ = s["summary"]
    month_label = f"{calendar.month_name[s['month']]} {s['year']}"

    from core.pdf_brand import Brand, BrandedPDF, draw_letterhead
    pdf = BrandedPDF(Brand(org), "Salary Slip", month_label, bottom_margin=20)
    pdf.add_page()
    draw_letterhead(pdf, "Salary Slip", [
        ("Pay period", month_label),
        ("Basis", "Attendance"),
        ("Note", "Not a payment receipt"),
    ])
    pdf.set_text_color(0, 0, 0)

    _kv(pdf, "Employee", emp.get("name") or "-", "Emp. Code", emp.get("employee_id") or "-")
    _kv(pdf, "Department", emp.get("department") or "-", "Designation", emp.get("designation") or "-")
    _kv(pdf, "Monthly Salary", f"Rs. {_fmt_amt(s.get('employee', {}).get('monthly_salary'))}",
        "Basis Days", str(emp.get("payroll_basis_days") or 30))
    _kv(pdf, "Per-day Rate", f"Rs. {_fmt_amt(s.get('per_day_rate'))}",
        "Payable Days", str(s.get("payable_days")))
    pdf.ln(2)

    # Attendance summary table
    pdf.set_fill_color(240, 240, 240)
    pdf.set_font("Helvetica", "B", 8)
    heads = ["Present", "Late", "Half", "Paid Lv", "Unpaid", "W-Off", "Holiday", "Absent", "LOP"]
    vals = [summ["present"], summ["late"], summ["half_day"], summ["paid_leave"],
            summ["unpaid_leave"], summ["week_off"], summ["holidays"], summ["absent"], s["lop_days"]]
    w = 180 / len(heads)
    for h in heads:
        pdf.cell(w, 7, h, 1, 0, "C", fill=True)
    pdf.ln()
    pdf.set_font("Helvetica", "", 9)
    for v in vals:
        pdf.cell(w, 7, str(v), 1, 0, "C")
    pdf.ln(10)

    # Earnings / Deductions
    pdf.set_fill_color(*primary)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(90, 7, "EARNINGS", 1, 0, "L", fill=True)
    pdf.cell(90, 7, "DEDUCTIONS", 1, 1, "L", fill=True)
    pdf.set_text_color(0, 0, 0)
    pdf.set_font("Helvetica", "", 10)
    earn_rows = [("Gross Salary", s["employee"].get("monthly_salary"))]
    ded_rows = [
        (f"Loss of Pay ({s['lop_days']} d)", s.get("lop_deduction")),
        ("Late Fine", s.get("late_fine")),
        (f"Short Leave ({s.get('short_leave_hours', 0)}h)", s.get("short_leave_deduction")),
    ]
    n = max(len(earn_rows), len(ded_rows))
    for i in range(n):
        e = earn_rows[i] if i < len(earn_rows) else ("", "")
        d = ded_rows[i] if i < len(ded_rows) else ("", "")
        pdf.cell(60, 6, _safe(e[0]), 1, 0, "L")
        pdf.cell(30, 6, _fmt_amt(e[1]) if e[0] else "", 1, 0, "R")
        pdf.cell(60, 6, _safe(d[0]), 1, 0, "L")
        pdf.cell(30, 6, _fmt_amt(d[1]) if d[0] else "", 1, 1, "R")
    pdf.set_font("Helvetica", "B", 10)
    pdf.set_fill_color(240, 240, 240)
    pdf.cell(60, 7, "TOTAL", 1, 0, "L", fill=True)
    pdf.cell(30, 7, _fmt_amt(s["employee"].get("monthly_salary")), 1, 0, "R", fill=True)
    pdf.cell(60, 7, "TOTAL DEDUCTIONS", 1, 0, "L", fill=True)
    pdf.cell(30, 7, _fmt_amt(s.get("deduction")), 1, 1, "R", fill=True)
    pdf.ln(3)

    pdf.set_fill_color(*primary)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Helvetica", "B", 13)
    pdf.cell(0, 12, _safe(f"  NET PAYABLE:  Rs. {_fmt_amt(s.get('net_payable'))}"), 1, 1, "L", fill=True)

    if not s.get("salary_configured"):
        pdf.set_text_color(180, 100, 0)
        pdf.set_font("Helvetica", "I", 9)
        pdf.ln(2)
        pdf.cell(0, 6, _safe("Note: monthly salary is not configured for this employee."), ln=1)
    return pdf.to_bytes()


@router.get("/payroll/payslip.pdf")
async def attendance_payslip_pdf(employee_id: str, year: int, month: int, request: Request,
                                 session_token: Optional[str] = Cookie(default=None),
                                 authorization: Optional[str] = Header(default=None)):
    """On-demand payslip from the attendance engine (no payment required).
    Employees can always download their own; other users need payroll.read."""
    user = await require_user(request, session_token, authorization)
    emp = await sdb.employees.find_one({"id": employee_id}, {"_id": 0})
    if not emp:
        raise HTTPException(404, "Employee not found")
    is_self = (emp.get("user_id") == user.get("user_id")) or \
              ((emp.get("email") or "").lower() == (user.get("email") or "").lower())
    if not is_self and not has_permission(user, "payroll.read"):
        raise HTTPException(403, "Missing permission: payroll.read")
    policy = await _get_attendance_policy()
    s = await engine.monthly_summary(emp, year, month, policy)
    org = await db.organizations.find_one(
        {"org_id": emp.get("org_id") or DEFAULT_ORG_ID}, {"_id": 0})
    pdf_bytes = _generate_attendance_payslip_pdf(s, org)
    fname = f"payslip_{(emp.get('employee_id') or employee_id)}_{year}_{month:02d}.pdf"
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": content_disposition(
            "inline", fname, "payslip.pdf")},
    )
