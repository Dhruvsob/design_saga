"""Attendance & Payroll calculation engine.

Ported from the Jewellers ERP `attendance_service.monthly_summary` /
`payroll_preview` business logic and adapted to this ERP's MongoDB
multi-tenant architecture (`sdb`).

Key rules (Jewellers logic):
- Day precedence (no accidental deductions):
    worked > holiday > weekly-off > leave > absent > upcoming
- `payable_days` / `lop_days` drive salary math.
- Late arrivals are NEVER auto-converted to half-day. They are penalised
  via a configurable Rs. fine which an admin can waive by approving the
  late arrival. If the fine system is OFF, a *rejected* late arrival can
  deduct a half/full day (configurable legacy penalty).
- Short / hourly leave deducts `hourly_rate x hours`
  (hourly rate = per-day-rate / full-day-hours).

Salary sources (merged, non-destructive):
- primary : existing salary structure `emp.salary.net_monthly`
- fallback: flat `emp.monthly_salary` (Jewellers style)
- basis   : `emp.payroll_basis_days` (default 26)
"""
import calendar
from datetime import date as _date, datetime, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

from core.scoped_db import sdb

IST = ZoneInfo("Asia/Kolkata")

WORKED_STATUSES = {"present", "late", "half_day", "pending_approval"}

DEFAULT_LATE_CATEGORIES = [
    "traffic", "public_transport", "vehicle_breakdown",
    "medical", "family_emergency", "weather", "personal", "other",
]


def now_ist() -> datetime:
    return datetime.now(IST)


def effective_monthly_salary(emp: dict) -> float:
    """Net monthly from the salary structure, else flat monthly_salary."""
    sal = emp.get("salary") or {}
    net = float(sal.get("net_monthly") or 0)
    if net > 0:
        return net
    return float(emp.get("monthly_salary") or 0)


def emp_name(emp: dict) -> str:
    n = f"{emp.get('first_name', '')} {emp.get('last_name', '')}".strip()
    return n or emp.get("name") or emp.get("employee_id") or emp.get("id", "")


async def get_holiday_dates(year: int) -> set:
    """All active holiday ISO dates for a year (exact + recurring)."""
    out = set()
    async for r in sdb.holidays.find({"active": True}, {"_id": 0, "date": 1, "recurring": 1}):
        try:
            d = _date.fromisoformat(r["date"])
        except Exception:
            continue
        if r.get("recurring"):
            try:
                out.add(d.replace(year=year).isoformat())
            except ValueError:
                pass  # e.g. Feb-29 on non-leap year
        elif d.year == year:
            out.add(r["date"])
    return out


async def monthly_summary(emp: dict, year: int, month: int,
                          policy: dict, holiday_dates: Optional[set] = None) -> dict:
    """Day-by-day monthly attendance summary with payable/LOP days,
    late-fine total and short-leave deduction. (Jewellers engine.)"""
    _, days_in_month = calendar.monthrange(year, month)
    start = _date(year, month, 1).isoformat()
    end = _date(year, month, days_in_month).isoformat()

    recs = {}
    async for r in sdb.attendance.find(
            {"employee_id": emp["id"], "date": {"$gte": start, "$lte": end}}, {"_id": 0}):
        recs[r["date"]] = r

    if holiday_dates is None:
        holiday_dates = await get_holiday_dates(year)

    weekly_offs = set(emp.get("weekly_offs") if emp.get("weekly_offs") is not None
                      else (policy.get("weekly_off_days") or [6]))

    fine_enabled = bool(policy.get("late_fine_enabled"))
    penalty_map = {"half_day": 0.5, "full_day": 1.0, "none": 0.0}
    late_penalty = penalty_map.get(policy.get("late_rejection_penalty") or "half_day", 0.5)

    summary = {k: 0 for k in [
        "present", "late", "late_pending", "late_rejected", "half_day", "absent",
        "paid_leave", "unpaid_leave", "week_off", "holidays", "site_visit",
        "working_days", "total_working_minutes",
    ]}
    daily = []
    payable = 0.0
    lop = 0.0
    late_fine_total = 0.0
    short_leave_hours_total = 0.0
    today = now_ist().date()

    for dnum in range(1, days_in_month + 1):
        cur = _date(year, month, dnum)
        iso_d = cur.isoformat()
        rec = recs.get(iso_d)
        rstatus = (rec or {}).get("status")
        is_weekly_off = cur.weekday() in weekly_offs
        is_holiday = iso_d in holiday_dates or rstatus == "holiday"
        worked = rec is not None and rstatus in WORKED_STATUSES

        # Precedence: worked > holiday > weekly-off > leave > absent > upcoming
        if worked:
            status = rstatus
        elif is_holiday:
            status = "holiday"
        elif is_weekly_off or rstatus == "week_off":
            status = "week_off"
        elif rec is not None and rstatus == "leave":
            status = "unpaid_leave" if (rec.get("leave_type") == "unpaid") else "paid_leave"
        elif rec is not None and rstatus == "absent":
            status = "absent"
        elif cur > today:
            status = "upcoming"
        else:
            status = "absent"

        wm = int((rec or {}).get("working_minutes")
                 or round(float((rec or {}).get("worked_hours") or 0) * 60))
        site_visit = bool(rec and (rec.get("attendance_type") or "office") != "office")

        if status in ("present", "pending_approval"):
            summary["site_visit" if site_visit else "present"] += 1
            summary["total_working_minutes"] += wm
            payable += 1
        elif status == "late":
            summary["late"] += 1
            summary["total_working_minutes"] += wm
            aps = (rec or {}).get("late_approval_status") or "not_required"
            if aps == "rejected" and not fine_enabled:
                # Legacy day-based penalty (only when the Rs. fine system is OFF)
                summary["late_rejected"] += 1
                payable += (1 - late_penalty)
                lop += late_penalty
            else:
                if aps == "pending":
                    summary["late_pending"] += 1
                elif aps == "rejected":
                    summary["late_rejected"] += 1
                payable += 1   # late day fully payable; lateness penalised via Rs. fine
        elif status == "half_day":
            summary["half_day"] += 1
            summary["total_working_minutes"] += wm
            payable += 0.5
            lop += 0.5
        elif status == "paid_leave":
            summary["paid_leave"] += 1
            payable += 1
        elif status == "unpaid_leave":
            summary["unpaid_leave"] += 1
            lop += 1
        elif status == "week_off":
            summary["week_off"] += 1
            payable += 1
        elif status == "holiday":
            summary["holidays"] += 1
            payable += 1
        elif status == "absent":
            summary["absent"] += 1
            lop += 1
        # "upcoming" contributes nothing

        # Rs. late fine (unwaived) + short/hourly leave accumulate for salary
        if rec is not None:
            if not rec.get("late_fine_waived"):
                late_fine_total += float(rec.get("late_fine_amount") or 0)
            short_leave_hours_total += float(rec.get("short_leave_hours") or 0)

        if not is_weekly_off and not is_holiday:
            summary["working_days"] += 1

        ci, co = (rec or {}).get("check_in"), (rec or {}).get("check_out")
        daily.append({
            "date": iso_d,
            "day": cur.strftime("%a"),
            "check_in": _hhmm_ist(ci),
            "check_out": _hhmm_ist(co),
            "working_minutes": wm,
            "status": status,
            "late_minutes": (rec or {}).get("late_minutes") or 0,
            "late_reason": (rec or {}).get("late_reason"),
            "late_category": (rec or {}).get("late_category"),
            "late_approval_status": (rec or {}).get("late_approval_status"),
            "late_fine_amount": float((rec or {}).get("late_fine_amount") or 0),
            "late_fine_waived": bool((rec or {}).get("late_fine_waived")),
            "short_leave_hours": float((rec or {}).get("short_leave_hours") or 0),
        })

    monthly = effective_monthly_salary(emp)
    basis = int(emp.get("payroll_basis_days") or 26)
    per_day = monthly / basis if basis else 0
    daily_hours = float(emp.get("full_day_min_minutes")
                        or (policy.get("full_day_min_hours") or 8) * 60) / 60.0
    hourly_rate = (per_day / daily_hours) if daily_hours else 0
    short_leave_deduction = round(hourly_rate * short_leave_hours_total, 2)
    lop_deduction = round(per_day * lop, 2)
    total_deduction = round(lop_deduction + late_fine_total + short_leave_deduction, 2)
    net_payable = round(max(monthly - total_deduction, 0), 2)

    return {
        "employee": {
            "id": emp["id"], "name": emp_name(emp),
            "employee_id": emp.get("employee_id"),
            "department": emp.get("department"),
            "designation": emp.get("designation") or emp.get("role_title"),
            "shift_start": emp.get("shift_start"), "shift_end": emp.get("shift_end"),
            "monthly_salary": monthly, "payroll_basis_days": basis,
        },
        "year": year, "month": month, "total_days": days_in_month,
        "summary": summary,
        "payable_days": round(payable, 2),
        "lop_days": round(lop, 2),
        "salary_configured": monthly > 0,
        "late_rejection_penalty": policy.get("late_rejection_penalty") or "half_day",
        "late_fine_enabled": fine_enabled,
        "late_fine": round(late_fine_total, 2),
        "short_leave_hours": round(short_leave_hours_total, 2),
        "hourly_rate": round(hourly_rate, 2),
        "short_leave_deduction": short_leave_deduction,
        "per_day_rate": round(per_day, 2),
        "lop_deduction": lop_deduction,
        "deduction": total_deduction,
        "net_payable": net_payable,
        "daily": daily,
    }


async def payroll_preview(year: int, month: int, policy: dict) -> dict:
    """Attendance-linked payroll preview for all active employees."""
    holiday_dates = await get_holiday_dates(year)
    emps = await sdb.employees.find(
        {"employment_status": {"$nin": ["terminated"]}}, {"_id": 0}).to_list(1000)
    rows = []
    total_net = 0.0
    unconfigured = 0
    for emp in emps:
        s = await monthly_summary(emp, year, month, policy, holiday_dates)
        summ = s["summary"]
        if not s["salary_configured"]:
            unconfigured += 1
        total_net += s["net_payable"]
        rows.append({
            "employee_id": emp["id"],
            "employee_name": s["employee"]["name"],
            "employee_code": emp.get("employee_id"),
            "department": emp.get("department"),
            "monthly_salary": s["employee"]["monthly_salary"],
            "payroll_basis_days": s["employee"]["payroll_basis_days"],
            "per_day_rate": s["per_day_rate"],
            "salary_configured": s["salary_configured"],
            "payable_days": s["payable_days"],
            "present": summ["present"], "late": summ["late"],
            "late_rejected": summ["late_rejected"], "half_day": summ["half_day"],
            "absent": summ["absent"], "paid_leave": summ["paid_leave"],
            "unpaid_leave": summ["unpaid_leave"], "week_off": summ["week_off"],
            "holidays": summ["holidays"], "site_visit": summ["site_visit"],
            "lop_days": s["lop_days"], "lop_deduction": s["lop_deduction"],
            "late_fine": s["late_fine"],
            "short_leave_hours": s["short_leave_hours"],
            "short_leave_deduction": s["short_leave_deduction"],
            "deduction": s["deduction"], "net_payable": s["net_payable"],
        })
    rows.sort(key=lambda r: (r["employee_name"] or "").lower())
    return {
        "year": year, "month": month, "employees": rows,
        "total_net_payable": round(total_net, 2),
        "employee_count": len(rows),
        "unconfigured_salary_count": unconfigured,
    }


def _hhmm_ist(iso_str: Optional[str]) -> Optional[str]:
    """Render a stored ISO timestamp as HH:MM in IST."""
    if not iso_str:
        return None
    try:
        dt = datetime.fromisoformat(str(iso_str).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            from datetime import timezone as _tz
            dt = dt.replace(tzinfo=_tz.utc)
        return dt.astimezone(IST).strftime("%H:%M")
    except Exception:
        return None
