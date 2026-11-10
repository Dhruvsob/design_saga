"""Auto paid-leave rules (10/11/2026).

One free paid leave per month. The first eligible absence — explicit absent
record or a past day with no record — is auto-converted to free paid leave
unless an approved ordinary leave already consumed the monthly allowance.
Later absences deduct salary. Pre-joining / post-exit proration days and the
still-running current day never consume the free day.
"""
import asyncio
import calendar
from datetime import date as _date
from types import SimpleNamespace

import pytest

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


def _summary(monkeypatch, rows, emp, y, m, policy=None):
    monkeypatch.setattr(engine, "sdb", SimpleNamespace(
        attendance=SimpleNamespace(find=lambda q, p=None: _Cursor(rows))))
    return asyncio.run(engine.monthly_summary(
        emp, y, m, policy or {"monthly_paid_leave_allowance": 1}, holiday_dates=set()))


def _emp(**extra):
    return {"id": "emp_1", "first_name": "Asha", "monthly_salary": 30000,
            "payroll_basis_days": 30, "joining_date": "2026-01-01", **extra}


def _month_rows(y, m, overrides=None, start_day=1):
    """Present records for every working day (Sundays off), with per-day
    overrides: a dict replaces the record, None means no record at all."""
    overrides = overrides or {}
    _, n = calendar.monthrange(y, m)
    rows = []
    for d in range(start_day, n + 1):
        dt = _date(y, m, d)
        if dt.weekday() == 6:
            continue
        if d in overrides:
            if overrides[d] is None:
                continue
            rows.append({"employee_id": "emp_1", "date": dt.isoformat(), **overrides[d]})
        else:
            rows.append({"employee_id": "emp_1", "date": dt.isoformat(),
                         "status": "present", "working_minutes": 480})
    return rows


def _day(result, iso):
    return next(d for d in result["daily"] if d["date"] == iso)


def test_three_absences_one_free_two_deducted(monkeypatch):
    # Spec example: 3 absent days -> 1 paid leave + 2 unpaid, deduct 2 days.
    rows = _month_rows(2026, 10, {5: {"status": "absent"},
                                  6: {"status": "absent"},
                                  7: {"status": "absent"}})
    s = _summary(monkeypatch, rows, _emp(), 2026, 10)
    assert s["summary"]["auto_paid_leave"] == 1
    assert s["summary"]["paid_leave"] == 1
    assert s["summary"]["absent"] == 2
    assert s["lop_days"] == 2
    assert s["lop_deduction"] == 2000          # 30000 / 30 * 2
    assert _day(s, "2026-10-05")["status"] == "paid_leave"
    assert _day(s, "2026-10-05")["auto_paid_leave"] is True
    assert _day(s, "2026-10-06")["status"] == "absent"


def test_emergency_no_record_day_uses_free_leave(monkeypatch):
    rows = _month_rows(2026, 10, {6: None})    # never checked in on the 6th
    s = _summary(monkeypatch, rows, _emp(), 2026, 10)
    assert s["summary"]["auto_paid_leave"] == 1
    assert s["summary"]["absent"] == 0
    assert s["lop_days"] == 0
    d = _day(s, "2026-10-06")
    assert d["status"] == "paid_leave" and d["auto_paid_leave"] is True


def test_approved_leave_consumes_allowance_before_later_absence(monkeypatch):
    rows = _month_rows(2026, 10, {5: {"status": "leave", "leave_type": "casual"},
                                  10: {"status": "absent"}})
    s = _summary(monkeypatch, rows, _emp(), 2026, 10)
    assert s["summary"]["paid_leave"] == 1     # the approved leave
    assert s["summary"]["auto_paid_leave"] == 0
    assert _day(s, "2026-10-10")["status"] == "absent"
    assert s["lop_days"] == 1


def test_earlier_absence_consumes_allowance_before_approved_leave(monkeypatch):
    rows = _month_rows(2026, 10, {5: {"status": "absent"},
                                  10: {"status": "leave", "leave_type": "casual"}})
    s = _summary(monkeypatch, rows, _emp(), 2026, 10)
    assert _day(s, "2026-10-05")["status"] == "paid_leave"      # auto, free
    assert _day(s, "2026-10-10")["status"] == "unpaid_leave"    # allowance gone
    assert s["summary"]["auto_paid_leave"] == 1
    assert s["lop_days"] == 1


def test_statutory_leave_does_not_block_auto_conversion(monkeypatch):
    rows = _month_rows(2026, 10, {5: {"status": "leave", "leave_type": "maternity"},
                                  12: {"status": "absent"}})
    s = _summary(monkeypatch, rows, _emp(), 2026, 10)
    assert s["summary"]["paid_leave"] == 2     # statutory + auto-converted
    assert s["summary"]["auto_paid_leave"] == 1
    assert s["lop_days"] == 0


def test_days_before_joining_never_consume_the_free_day(monkeypatch):
    # Joined Oct 14: the proration absences of Oct 1-13 stay absent and the
    # real absence on Oct 20 still gets the free day.
    rows = _month_rows(2026, 10, {20: {"status": "absent"}}, start_day=14)
    s = _summary(monkeypatch, rows, _emp(joining_date="2026-10-14"), 2026, 10)
    assert _day(s, "2026-10-01")["status"] == "absent"
    assert _day(s, "2026-10-01")["auto_paid_leave"] is False
    assert _day(s, "2026-10-20")["status"] == "paid_leave"
    assert s["summary"]["auto_paid_leave"] == 1


def test_zero_allowance_disables_auto_conversion(monkeypatch):
    rows = _month_rows(2026, 10, {5: {"status": "absent"}})
    s = _summary(monkeypatch, rows, _emp(), 2026, 10,
                 policy={"monthly_paid_leave_allowance": 0})
    assert _day(s, "2026-10-05")["status"] == "absent"
    assert s["summary"]["auto_paid_leave"] == 0
    assert s["lop_days"] == 1


def test_two_absences_with_allowance_two_are_both_free(monkeypatch):
    rows = _month_rows(2026, 10, {5: {"status": "absent"}, 9: {"status": "absent"}})
    s = _summary(monkeypatch, rows, _emp(), 2026, 10,
                 policy={"monthly_paid_leave_allowance": 2})
    assert s["summary"]["auto_paid_leave"] == 2
    assert s["lop_days"] == 0


def test_today_without_checkin_does_not_consume_free_day(monkeypatch):
    today = engine.now_ist().date()
    if today.day == 1 or today.weekday() == 6:
        pytest.skip("needs a working day with at least one prior day in the month")
    overrides = {today.day: None}
    rows = [r for r in _month_rows(today.year, today.month, overrides)
            if r["date"] < today.isoformat()]
    s = _summary(monkeypatch, rows, _emp(), today.year, today.month)
    d = _day(s, today.isoformat())
    assert d["status"] == "absent" and d["auto_paid_leave"] is False
