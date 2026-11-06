"""One paid leave per month for every employee (DS-098)."""
import asyncio

import pytest

import core.attendance_engine as engine
import routes.attendance as att


class _Cursor:
    def __init__(self, rows):
        self._rows = iter(rows)

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return next(self._rows)
        except StopIteration:
            raise StopAsyncIteration


def _summary(monkeypatch, policy, leave_days, leave_type="casual"):
    rows = [{"employee_id": "e1", "date": d, "status": "leave", "leave_type": leave_type} for d in leave_days]

    class Att:
        def find(self, *_a, **_k):
            return _Cursor(rows)

    class SDB:
        attendance = Att()

    monkeypatch.setattr(engine, "sdb", SDB())
    emp = {"id": "e1", "monthly_salary": 26000, "payroll_basis_days": 26, "weekly_offs": [6]}
    return asyncio.run(engine.monthly_summary(emp, 2027, 3, policy, holiday_dates=set()))


@pytest.mark.parametrize("policy", [{}, {"monthly_paid_leave_allowance": None}, {"monthly_paid_leave_allowance": ""}])
def test_missing_or_empty_allowance_means_one_paid_leave(monkeypatch, policy):
    s = _summary(monkeypatch, policy, ["2027-03-03", "2027-03-04"])
    assert s["monthly_paid_leave_allowance"] == 1
    assert s["paid_leave_allowance_used"] == 1
    assert s["excess_ordinary_leave_days"] == 1
    assert s["lop_deduction"] == 1000.0          # one day at 26,000 / 26


def test_first_leave_in_a_month_is_free(monkeypatch):
    s = _summary(monkeypatch, {"monthly_paid_leave_allowance": 1}, ["2027-03-10"])
    assert s["excess_ordinary_leave_days"] == 0 and s["lop_deduction"] == 0


def test_unpaid_leave_is_always_deducted(monkeypatch):
    s = _summary(monkeypatch, {"monthly_paid_leave_allowance": 1}, ["2027-03-10"], leave_type="unpaid")
    assert s["lop_deduction"] == 1000.0


def test_stored_null_does_not_override_default(monkeypatch):
    async def stored():
        return {"monthly_paid_leave_allowance": None, "grace_minutes": 20}

    class Pol:
        async def find_one(self, *_a, **_k):
            return await stored()

    class SDB:
        attendance_policies = Pol()

    monkeypatch.setattr(att, "sdb", SDB())
    p = asyncio.run(att._get_attendance_policy())
    assert p["monthly_paid_leave_allowance"] == 1 and p["grace_minutes"] == 20
