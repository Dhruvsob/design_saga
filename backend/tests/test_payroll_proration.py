"""Mid-month joining and leaving (hand-worked, 2026-11-20).

Rs. 85,000 a month, 30-day basis (Rs. 2,833.33 a day), Sundays off,
Gandhi Jayanti (2 Oct 2026) a holiday. October 2026 has 31 days; 1 Oct is
a Thursday, so Sundays fall on 4, 11, 18 and 25 Oct.

Joining 16 Oct: 1-15 Oct are outside employment (15 days, including the
holiday and two Sundays) -> 15 LOP days -> Rs. 85,000 - Rs. 42,500 = Rs. 42,500.
Before the fix the holiday and both Sundays were paid (12 LOP days ->
Rs. 51,000), an overpayment of Rs. 8,500.

Leaving on 10 Oct (last working day): 11-31 Oct (21 days, including Sundays
11, 18, 25) are unpaid -> Rs. 85,000 - Rs. 59,500 = Rs. 25,500.
"""
import asyncio
import calendar
from datetime import date as _date
from types import SimpleNamespace

import core.attendance_engine as engine


class _Cursor:
    def __init__(self, rows):
        self._rows = rows

    def __aiter__(self):
        self._it = iter(self._rows)
        return self

    async def __anext__(self):
        try:
            return next(self._it)
        except StopIteration:
            raise StopAsyncIteration


HOLIDAYS = {"2026-10-02"}


def _present(first: int, last: int):
    rows = []
    for d in range(first, last + 1):
        day = _date(2026, 10, d)
        if day.weekday() == 6 or day.isoformat() in HOLIDAYS:
            continue
        rows.append({"employee_id": "emp_1", "date": day.isoformat(),
                     "status": "present", "working_minutes": 480})
    return rows


def _summary(monkeypatch, rows, **emp):
    monkeypatch.setattr(engine, "sdb", SimpleNamespace(
        attendance=SimpleNamespace(find=lambda q, p=None: _Cursor(rows))))
    base = {"id": "emp_1", "first_name": "Fixture", "monthly_salary": 85000,
            "payroll_basis_days": 30, **emp}
    return asyncio.run(engine.monthly_summary(
        base, 2026, 10, {"monthly_paid_leave_allowance": 1}, holiday_dates=HOLIDAYS))


def test_mid_month_joiner_is_not_paid_for_sundays_or_holidays_before_joining(monkeypatch):
    assert calendar.monthrange(2026, 10)[1] == 31
    s = _summary(monkeypatch, _present(16, 31), joining_date="2026-10-16")
    assert s["lop_days"] == 15
    assert s["summary"]["not_employed"] == 15
    assert s["lop_deduction"] == 42500
    assert s["net_payable"] == 42500
    sunday = next(d for d in s["daily"] if d["date"] == "2026-10-04")
    assert sunday["status"] == "absent" and sunday["outside_employment"] is True
    holiday = next(d for d in s["daily"] if d["date"] == "2026-10-02")
    assert holiday["status"] == "absent" and holiday["outside_employment"] is True
    # Sundays after joining stay paid weekly-offs.
    assert next(d for d in s["daily"] if d["date"] == "2026-10-18")["status"] == "week_off"


def test_leaver_is_not_paid_for_days_after_the_exit_date(monkeypatch):
    s = _summary(monkeypatch, _present(1, 10), joining_date="2025-01-01", exit_date="2026-10-10")
    assert s["lop_days"] == 21
    assert s["net_payable"] == 25500
    assert next(d for d in s["daily"] if d["date"] == "2026-10-11")["outside_employment"] is True
    # The holiday inside the employment window is still paid.
    assert next(d for d in s["daily"] if d["date"] == "2026-10-02")["status"] == "holiday"


def test_full_month_employee_is_unchanged(monkeypatch):
    s = _summary(monkeypatch, _present(1, 31), joining_date="2025-01-01")
    assert s["lop_days"] == 0
    assert s["summary"]["not_employed"] == 0
    assert s["net_payable"] == 85000


def test_a_day_actually_worked_outside_the_window_is_still_paid(monkeypatch):
    # Data entry slip: a recorded working day counts even if the joining
    # date was entered a day late.
    rows = _present(16, 31) + [{"employee_id": "emp_1", "date": "2026-10-15",
                                "status": "present", "working_minutes": 480}]
    s = _summary(monkeypatch, rows, joining_date="2026-10-16")
    assert s["lop_days"] == 14
    assert next(d for d in s["daily"] if d["date"] == "2026-10-15")["outside_employment"] is False
