"""Regression guards for the bug sweep of 07/11/2026."""

import pytest
from pydantic import ValidationError

import server
from routes import payroll
from routes.notifications import _dmy


def test_payslip_attendance_matches_what_salary_was_calculated_from():
    # Ritika: 3 unpaid leave days deducted, but the slip used to show Leaves 0 / Absent 0.
    summary = {"present": 12, "late": 3, "site_visit": 0, "absent": 0, "half_day": 0,
               "paid_leave": 1, "unpaid_leave": 3, "week_off": 4, "holidays": 8}
    boxes = payroll._slip_attendance(summary, {"payable_days": 28, "lop_days": 3.0})
    assert boxes["present"] == 15 and boxes["unpaid_leave"] == 3 and boxes["paid_leave"] == 1
    assert boxes["offs"] == 12 and boxes["paid_days"] == 28 and boxes["lop_days"] == 3.0
    assert payroll._count(3.0) == "3" and payroll._count(2.5) == "2.5"


def test_salary_slip_pdf_renders_with_engine_boxes():
    run = {"year": 2026, "month": 10, "net": 25000, "status": "paid",
           "breakdown": {"basic": 25000, "gross": 25000, "deductions_total": 0, "net": 25000}}
    emp = {"first_name": "Ritika", "joining_date": "2026-09-01"}
    pdf = payroll._generate_salary_slip_pdf(emp, run, {"name": "DESIGN SAGA"},
                                            payroll._slip_attendance({"present": 20}, run["breakdown"]))
    assert pdf[:4] == b"%PDF"


def test_part_paid_invoices_count_what_was_received():
    invoices = [
        {"total": 600000, "paid_amount": 10000, "status": "partially_paid"},
        {"total": 50000, "status": "paid"},
        {"total": 9999, "status": "draft"},
        {"total": 8888, "status": "cancelled"},
        {"total": 7777, "status": "sent", "doc_type": "quotation"},
    ]
    billed, received = server._invoice_money(invoices)
    assert billed == 650000 and received == 60000


def test_dates_must_be_real_calendar_dates():
    server.InvoiceIn(due_date="2026-11-30")
    server.InvoiceIn(due_date="")                 # optional stays optional
    for bad in ("31-10-2026", "2026-02-30", "tomorrow", "2026-11-30T10:00:00"):
        with pytest.raises(ValidationError):
            server.InvoiceIn(due_date=bad)


def test_negative_money_and_quantities_are_refused():
    with pytest.raises(ValidationError):
        server.SalaryStructure(basic=-25000)
    with pytest.raises(ValidationError):
        server.ProjectIn(name="Villa", budget=-5)


def test_notification_dates_read_dd_mm_yyyy():
    assert _dmy("2026-11-07") == "07/11/2026"
    assert _dmy("") == ""
