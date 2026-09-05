"""Payroll routes — pays employee, auto-posts JE to Accounting.

`POST /api/employees/{eid}/pay-salary` computes net salary from the employee
salary structure (already stored under `emp.salary.net_monthly`) and posts a
balanced journal entry (DR Employee Salary  CR Cash/Bank) via
`accounting._post_journal`. Idempotent per (employee_id, year, month) — a
`payroll_runs` doc guards against double payment.
"""
from fastapi import APIRouter, HTTPException, Request, Cookie, Header
from fastapi.responses import StreamingResponse
from typing import Optional
from pydantic import BaseModel
from datetime import date as _date
import io
import calendar
from fpdf import FPDF

from core.db import db
from core.scoped_db import sdb
from core.helpers import now_utc, iso_now, new_id
from core.deps import require_user
from core.rbac import has_permission
from core.tenancy import DEFAULT_ORG_ID
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
    payment_method: Optional[str] = "bank_transfer"
    reference: Optional[str] = None
    notes: Optional[str] = None
    # Jewellers logic — deduct LOP days, late fines and short-leave hours
    # computed from the attendance engine before posting the JE.
    apply_attendance_deductions: Optional[bool] = True


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
    breakdown["lop_deduction"] = s["lop_deduction"]
    breakdown["late_fine"] = s["late_fine"]
    breakdown["short_leave_hours"] = s["short_leave_hours"]
    breakdown["short_leave_deduction"] = s["short_leave_deduction"]
    breakdown["attendance_deductions"] = att_ded
    breakdown["deductions_total"] = round(breakdown["deductions_total"] + att_ded, 2)
    breakdown["net"] = round(breakdown["gross"] - breakdown["deductions_total"], 2)
    return breakdown


@router.get("/employees/{eid}/salary/preview")
async def preview_salary(eid: str, year: int, month: int, request: Request,
                         bonus: float = 0, incentives: float = 0, overtime: float = 0,
                         advances_recovered: float = 0, other_deductions: float = 0,
                         session_token: Optional[str] = Cookie(default=None),
                         authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    if not (has_permission(user, "payroll.read") or has_permission(user, "employees.read")):
        raise HTTPException(status_code=403, detail="Missing permission")
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
    paid = await sdb.payroll_runs.find_one({"employee_id": eid, "year": year, "month": month},
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
    breakdown = _compute_net(emp.get("salary"), extras)
    if payload.apply_attendance_deductions:
        breakdown = await _apply_attendance_deductions(emp, breakdown, payload.year, payload.month)
    net = breakdown["net"]
    if net <= 0:
        raise HTTPException(status_code=400, detail="Net salary must be > 0")

    # Resolve salary account
    salary_acc_id = payload.salary_account_id
    if not salary_acc_id:
        acc = await sdb.accounts.find_one({"name": "Employee Salary"}, {"_id": 0, "id": 1})
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
    await sdb.payroll_runs.insert_one(dict(run))
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
    rows = await sdb.payroll_runs.find(q, {"_id": 0}).sort("paid_at", -1).to_list(500)
    return rows


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
    branding = (org or {}).get("branding") or {}
    org_name = ((org or {}).get("display_name") or (org or {}).get("name") or "DESIGN SAGA").upper()
    org_tagline = branding.get("tagline") or "Architecture & Interior Design Studio"
    footer = branding.get("pdf_footer") or "This is a computer-generated document. No signature required."
    primary = _hex_to_rgb(branding.get("primary_color") or "#002FA7")

    pdf = FPDF(format="A4", unit="mm")
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)

    # === HEADER band ===
    pdf.set_fill_color(*primary)
    pdf.rect(0, 0, 210, 30, style="F")
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Helvetica", "B", 22)
    pdf.set_xy(12, 8)
    pdf.cell(0, 10, _safe(org_name), ln=1)
    pdf.set_font("Helvetica", "", 9)
    pdf.set_x(12)
    pdf.cell(0, 5, _safe(org_tagline), ln=1)
    if (org or {}).get("gstin"):
        pdf.set_x(12)
        pdf.cell(0, 5, _safe(f"GSTIN: {org['gstin']}"), ln=1)

    # === Slip Title ===
    pdf.set_y(38)
    pdf.set_text_color(0, 0, 0)
    pdf.set_font("Helvetica", "B", 15)
    month_label = calendar.month_name[run["month"]]
    pdf.cell(0, 8, _safe(f"SALARY SLIP · {month_label.upper()} {run['year']}"),
             ln=1, align="C")
    pdf.ln(2)

    # === Employee block ===
    emp_name = f"{emp.get('first_name','')} {emp.get('last_name','')}".strip() or emp.get("employee_id") or ""
    _kv(pdf, "Employee Name", emp_name, "Employee ID", emp.get("employee_id") or "-")
    _kv(pdf, "Department", emp.get("department") or "-", "Designation", emp.get("designation") or "-")
    _kv(pdf, "Date of Joining", (emp.get("joining_date") or "-"),
         "Pay Period", f"{month_label} {run['year']}")
    _kv(pdf, "Bank A/C", (emp.get("bank") or {}).get("account_number") or "-",
         "PAN", emp.get("pan") or "-")
    pdf.ln(2)

    # === Attendance summary ===
    pdf.set_fill_color(240, 240, 240)
    pdf.set_font("Helvetica", "B", 9)
    pdf.cell(37, 7, "Working Days", 1, 0, "C", fill=True)
    pdf.cell(37, 7, "Present", 1, 0, "C", fill=True)
    pdf.cell(37, 7, "Leaves", 1, 0, "C", fill=True)
    pdf.cell(37, 7, "Absent", 1, 0, "C", fill=True)
    pdf.cell(37, 7, "Half-days", 1, 1, "C", fill=True)
    pdf.set_font("Helvetica", "", 10)
    working_days = calendar.monthrange(run["year"], run["month"])[1]
    pdf.cell(37, 7, str(working_days), 1, 0, "C")
    pdf.cell(37, 7, str(attendance.get("present", 0)), 1, 0, "C")
    pdf.cell(37, 7, str(attendance.get("leave", 0)), 1, 0, "C")
    pdf.cell(37, 7, str(attendance.get("absent", 0)), 1, 0, "C")
    pdf.cell(37, 7, str(attendance.get("half_day", 0)), 1, 1, "C")
    pdf.ln(3)

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
    # Attendance-engine deductions (Jewellers logic)
    if breakdown.get("lop_deduction"):
        ded_rows.append((f"Loss of Pay ({breakdown.get('lop_days', 0)} d)", breakdown.get("lop_deduction")))
    if breakdown.get("late_fine"):
        ded_rows.append(("Late Fine", breakdown.get("late_fine")))
    if breakdown.get("short_leave_deduction"):
        ded_rows.append((f"Short Leave ({breakdown.get('short_leave_hours', 0)}h)", breakdown.get("short_leave_deduction")))

    # header row
    pdf.set_fill_color(*primary)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(95, 7, "EARNINGS", 1, 0, "L", fill=True)
    pdf.cell(95, 7, "DEDUCTIONS", 1, 1, "L", fill=True)

    pdf.set_text_color(0, 0, 0)
    pdf.set_font("Helvetica", "", 10)
    n = max(len(earn_rows), len(ded_rows))
    for i in range(n):
        e = earn_rows[i] if i < len(earn_rows) else ("", 0)
        d = ded_rows[i] if i < len(ded_rows) else ("", 0)
        pdf.cell(65, 6, _safe(e[0]), 1, 0, "L")
        pdf.cell(30, 6, _fmt_amt(e[1]), 1, 0, "R")
        pdf.cell(65, 6, _safe(d[0]), 1, 0, "L")
        pdf.cell(30, 6, _fmt_amt(d[1]), 1, 1, "R")

    # Totals row
    pdf.set_font("Helvetica", "B", 10)
    pdf.set_fill_color(240, 240, 240)
    pdf.cell(65, 7, "GROSS", 1, 0, "L", fill=True)
    pdf.cell(30, 7, _fmt_amt(breakdown.get("gross")), 1, 0, "R", fill=True)
    pdf.cell(65, 7, "TOTAL DEDUCTIONS", 1, 0, "L", fill=True)
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
    pdf.cell(0, 6, _safe(f"Paid on {(run.get('paid_at') or '')[:10]} via {run.get('payment_method') or 'bank_transfer'}"),
             ln=1)

    if run.get("notes"):
        pdf.ln(1)
        pdf.set_font("Helvetica", "", 9)
        pdf.multi_cell(0, 5, _safe(f"Notes: {run['notes']}"))

    # Footer
    pdf.ln(8)
    pdf.set_text_color(120, 120, 120)
    pdf.set_font("Helvetica", "I", 8)
    pdf.cell(0, 5, _safe(footer), ln=1, align="C")

    output = pdf.output(dest="S")
    if isinstance(output, str):
        return output.encode("latin-1")
    return bytes(output)


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

    # Attendance snapshot for that month
    ym_start = _date(run["year"], run["month"], 1).isoformat()
    ym_end = (_date(run["year"] + (1 if run["month"] == 12 else 0),
                    1 if run["month"] == 12 else run["month"] + 1, 1)).isoformat()
    counts = {"present": 0, "half_day": 0, "leave": 0, "absent": 0,
              "holiday": 0, "week_off": 0}
    async for rec in sdb.attendance.find(
            {"employee_id": run["employee_id"], "date": {"$gte": ym_start, "$lt": ym_end}},
            {"_id": 0}):
        s = rec.get("status") or "absent"
        counts[s] = counts.get(s, 0) + 1

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
        headers={"Content-Disposition": f'inline; filename="{fname}"'},
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
    if not (has_permission(user, "payroll.read") or has_permission(user, "employees.read")):
        raise HTTPException(status_code=403, detail="Missing permission")
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
    org_name = ((org or {}).get("display_name") or (org or {}).get("name") or "DESIGN SAGA").upper()
    org_tagline = branding.get("tagline") or "Architecture & Interior Design Studio"
    footer = branding.get("pdf_footer") or "This is a system-generated salary slip. No signature required."
    primary = _hex_to_rgb(branding.get("primary_color") or "#002FA7")

    emp = s["employee"]
    summ = s["summary"]
    month_label = f"{calendar.month_name[s['month']]} {s['year']}"

    pdf = FPDF(format="A4", unit="mm")
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)

    # Header band
    pdf.set_fill_color(*primary)
    pdf.rect(0, 0, 210, 30, style="F")
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Helvetica", "B", 20)
    pdf.set_xy(12, 8)
    pdf.cell(0, 10, _safe(org_name), ln=1)
    pdf.set_font("Helvetica", "", 9)
    pdf.set_x(12)
    pdf.cell(0, 5, _safe(org_tagline), ln=1)

    pdf.set_y(38)
    pdf.set_text_color(0, 0, 0)
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 8, _safe(f"SALARY SLIP · {month_label.upper()}"), ln=1, align="C")
    pdf.ln(2)

    _kv(pdf, "Employee", emp.get("name") or "-", "Emp. Code", emp.get("employee_id") or "-")
    _kv(pdf, "Department", emp.get("department") or "-", "Designation", emp.get("designation") or "-")
    _kv(pdf, "Monthly Salary", f"Rs. {_fmt_amt(s.get('employee', {}).get('monthly_salary'))}",
        "Basis Days", str(emp.get("payroll_basis_days") or 26))
    _kv(pdf, "Per-day Rate", f"Rs. {_fmt_amt(s.get('per_day_rate'))}",
        "Payable Days", str(s.get("payable_days")))
    pdf.ln(2)

    # Attendance summary table
    pdf.set_fill_color(240, 240, 240)
    pdf.set_font("Helvetica", "B", 8)
    heads = ["Present", "Late", "Half", "Paid Lv", "Unpaid", "W-Off", "Holiday", "Absent", "LOP"]
    vals = [summ["present"], summ["late"], summ["half_day"], summ["paid_leave"],
            summ["unpaid_leave"], summ["week_off"], summ["holidays"], summ["absent"], s["lop_days"]]
    w = 190 / len(heads)
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
    pdf.cell(95, 7, "EARNINGS", 1, 0, "L", fill=True)
    pdf.cell(95, 7, "DEDUCTIONS", 1, 1, "L", fill=True)
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
        pdf.cell(65, 6, _safe(e[0]), 1, 0, "L")
        pdf.cell(30, 6, _fmt_amt(e[1]) if e[0] else "", 1, 0, "R")
        pdf.cell(65, 6, _safe(d[0]), 1, 0, "L")
        pdf.cell(30, 6, _fmt_amt(d[1]) if d[0] else "", 1, 1, "R")
    pdf.set_font("Helvetica", "B", 10)
    pdf.set_fill_color(240, 240, 240)
    pdf.cell(65, 7, "TOTAL", 1, 0, "L", fill=True)
    pdf.cell(30, 7, _fmt_amt(s["employee"].get("monthly_salary")), 1, 0, "R", fill=True)
    pdf.cell(65, 7, "TOTAL DEDUCTIONS", 1, 0, "L", fill=True)
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

    pdf.ln(8)
    pdf.set_text_color(120, 120, 120)
    pdf.set_font("Helvetica", "I", 8)
    pdf.cell(0, 5, _safe(footer), ln=1, align="C")

    output = pdf.output(dest="S")
    if isinstance(output, str):
        return output.encode("latin-1")
    return bytes(output)


@router.get("/payroll/payslip.pdf")
async def attendance_payslip_pdf(employee_id: str, year: int, month: int, request: Request,
                                 session_token: Optional[str] = Cookie(default=None),
                                 authorization: Optional[str] = Header(default=None)):
    """On-demand payslip from the attendance engine (no payment required).
    Employees can always download their own; HR needs payroll/employees read."""
    user = await require_user(request, session_token, authorization)
    emp = await sdb.employees.find_one({"id": employee_id}, {"_id": 0})
    if not emp:
        raise HTTPException(404, "Employee not found")
    is_self = (emp.get("user_id") == user.get("user_id")) or \
              ((emp.get("email") or "").lower() == (user.get("email") or "").lower())
    if not is_self and not (has_permission(user, "payroll.read") or has_permission(user, "employees.read")):
        raise HTTPException(403, "Missing permission")
    policy = await _get_attendance_policy()
    s = await engine.monthly_summary(emp, year, month, policy)
    org = await db.organizations.find_one(
        {"org_id": emp.get("org_id") or DEFAULT_ORG_ID}, {"_id": 0})
    pdf_bytes = _generate_attendance_payslip_pdf(s, org)
    fname = f"payslip_{(emp.get('employee_id') or employee_id)}_{year}_{month:02d}.pdf"
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{fname}"'},
    )
