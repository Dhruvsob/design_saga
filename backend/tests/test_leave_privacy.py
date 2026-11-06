"""Leave privacy (DS-089): staff never see sensitive leave categories or the HR policy table."""
import asyncio

import pytest
from fastapi import HTTPException

import routes.attendance as att

EMPLOYEE = {"user_id": "u_emp", "org_id": "org_a", "role": "Employee", "permissions": ["attendance.read"]}
HR = {"user_id": "u_hr", "org_id": "org_a", "role": "HR", "permissions": ["attendance.update", "employees.update"]}


def _as(monkeypatch, user):
    async def fake_user(*_a, **_k):
        return user
    monkeypatch.setattr(att, "require_user", fake_user)


def test_staff_meta_hides_sensitive_types_and_policy(monkeypatch):
    _as(monkeypatch, EMPLOYEE)
    meta = asyncio.run(att.attendance_meta(request=None))
    assert "maternity" not in meta["leave_types"] and "paternity" not in meta["leave_types"]
    assert "casual" in meta["leave_types"]
    assert meta["default_allowance"] == {} and meta["can_manage"] is False


def test_hr_meta_keeps_everything(monkeypatch):
    _as(monkeypatch, HR)
    meta = asyncio.run(att.attendance_meta(request=None))
    assert "maternity" in meta["leave_types"] and meta["default_allowance"]
    assert meta["can_manage"] is True


def test_staff_cannot_file_sensitive_leave_directly(monkeypatch):
    _as(monkeypatch, EMPLOYEE)

    async def no_lookup(*_a, **_k):
        raise AssertionError("must refuse before resolving the employee")
    monkeypatch.setattr(att, "_resolve_employee_id", no_lookup)
    payload = att.LeaveRequestIn(leave_type="maternity", from_date="2026-11-10", to_date="2026-11-12", reason="")
    with pytest.raises(HTTPException) as exc:
        asyncio.run(att.create_leave(payload, request=None))
    assert exc.value.status_code == 403 and "HR" in exc.value.detail


def test_staff_balance_lists_only_general_types(monkeypatch):
    _as(monkeypatch, EMPLOYEE)

    async def own(*_a, **_k):
        return "emp_1"

    async def rule():
        return {"allowances": {"casual": 12, "sick": 6, "maternity": 90, "paternity": 15, "unpaid": 0}}

    class Cursor:
        def __aiter__(self):
            self._rows = iter([{"leave_type": "casual", "days": 2}])
            return self

        async def __anext__(self):
            try:
                return next(self._rows)
            except StopIteration:
                raise StopAsyncIteration

    class Leaves:
        def find(self, *_a, **_k):
            return Cursor()

    class SDB:
        leaves = Leaves()

    monkeypatch.setattr(att, "_resolve_employee_id", own)
    monkeypatch.setattr(att, "_get_leave_rule", rule)
    monkeypatch.setattr(att, "sdb", SDB())
    out = asyncio.run(att.leave_balance("emp_1", year=2026, request=None))
    assert set(out["balance"]) == {"casual", "sick"}
    assert out["balance"]["casual"] == {"allowance": 12, "used": 2, "remaining": 10}
