"""Former staff leave the monthly sheet; mistaken employees can be deleted; hidden entries stay out of month totals."""

import asyncio
import inspect
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from core.attendance_engine import on_roll_for_month
import routes.accounting as accounting


def test_current_staff_are_always_on_the_sheet():
    assert on_roll_for_month({"employment_status": "active"}, 2026, 11)
    assert on_roll_for_month({}, 2026, 11)


def test_terminated_staff_show_only_up_to_the_month_they_left():
    hiren = {"employment_status": "terminated", "terminated_at": "2026-11-07T09:56:37+00:00"}
    assert on_roll_for_month(hiren, 2026, 10)                       # history stays
    assert not on_roll_for_month(hiren, 2026, 11, {"absent": 4})    # never worked that month
    assert on_roll_for_month(hiren, 2026, 11, {"present": 3})       # final month with work
    assert not on_roll_for_month(hiren, 2026, 12, {"present": 3})
    assert not on_roll_for_month({"employment_status": "terminated"}, 2026, 11)


def _server():
    import server
    return server


def _wire(monkeypatch, server, employee, history):
    deleted = {}

    class Coll:
        def __init__(self, name):
            self.name = name

        async def find_one(self, q, *_a):
            return dict(employee) if employee and q.get("id") == employee["id"] else None

        async def count_documents(self, q):
            return history.get(self.name, 0)

        async def delete_many(self, q):
            deleted[self.name] = q
            return SimpleNamespace(deleted_count=3 if self.name == "attendance" else 0)

        async def delete_one(self, q):
            deleted["employee"] = q

    class Db:
        def __getattr__(self, name):
            return Coll(name)

        def __getitem__(self, name):
            return Coll(name)

    async def user(*_a, **_k):
        return {"user_id": "owner"}

    async def noop(*_a, **_k):
        return None

    monkeypatch.setattr(server, "sdb", Db())
    monkeypatch.setattr(server, "require_user", user)
    monkeypatch.setattr(server, "has_permission", lambda *_a: True)
    monkeypatch.setattr(server, "audit_log", noop)
    return deleted


def test_terminated_employee_without_money_history_can_be_deleted(monkeypatch):
    server = _server()
    emp = {"id": "emp_h", "employment_status": "terminated", "first_name": "Hiren"}
    deleted = _wire(monkeypatch, server, emp, {})
    out = asyncio.run(server.delete_employee_permanently("emp_h", None))
    assert out["removed"] == {"attendance": 3}
    assert deleted["employee"] == {"id": "emp_h"}


def test_employee_with_salary_history_cannot_be_deleted(monkeypatch):
    server = _server()
    emp = {"id": "emp_j", "employment_status": "terminated"}
    deleted = _wire(monkeypatch, server, emp, {"payroll_runs": 2})
    with pytest.raises(HTTPException) as err:
        asyncio.run(server.delete_employee_permanently("emp_j", None))
    assert err.value.status_code == 409 and "salary payments" in err.value.detail
    assert "employee" not in deleted


def test_active_employee_must_be_terminated_first(monkeypatch):
    server = _server()
    _wire(monkeypatch, server, {"id": "emp_a", "employment_status": "active"}, {})
    with pytest.raises(HTTPException) as err:
        asyncio.run(server.delete_employee_permanently("emp_a", None))
    assert err.value.status_code == 409


def test_month_totals_and_statements_skip_hidden_entries():
    # Cancelled/corrected pairs are hidden; period reports must not see one half of a pair.
    for fn in (accounting.finance_dashboard, accounting.profit_and_loss, accounting.trial_balance,
               accounting.balance_sheet, accounting.cash_flow_statement,
               accounting.finance_dashboard_extended, accounting._current_account_balance,
               accounting.list_accounts):
        assert '"voided_from_view": {"$ne": True}' in inspect.getsource(fn), fn.__name__


def test_leave_needs_no_type_and_uses_the_monthly_free_leave():
    from models.attendance import LeaveRequestIn
    from core.attendance_engine import MONTHLY_ALLOWANCE_LEAVE_TYPES
    leave = LeaveRequestIn(from_date="2026-11-10", to_date="2026-11-12", reason="family function")
    assert leave.leave_type in MONTHLY_ALLOWANCE_LEAVE_TYPES
