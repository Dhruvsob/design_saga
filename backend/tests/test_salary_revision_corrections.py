"""Immutable salary-revision correction regressions."""

import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import core.locks
import server


class _Employees:
    def __init__(self, employee):
        self.employee = employee
        self.updates = []

    async def find_one(self, *_args, **_kwargs):
        return self.employee

    async def update_one(self, query, update):
        self.updates.append((query, update))
        return SimpleNamespace(matched_count=1)


def _install(monkeypatch, employee, permissions=None):
    collection = _Employees(employee)
    audits = []

    async def require_user(*_args, **_kwargs):
        return {"user_id": "usr_admin", "name": "Admin",
                "permissions": permissions or ["payroll.create", "finance.update"]}

    async def audit_log(*args, **kwargs):
        audits.append((args, kwargs))

    @asynccontextmanager
    async def unlocked(*_args, **_kwargs):
        yield "lock_test"

    monkeypatch.setattr(server, "require_user", require_user)
    monkeypatch.setattr(server, "audit_log", audit_log)
    monkeypatch.setattr(server, "sdb", SimpleNamespace(employees=collection))
    monkeypatch.setattr(core.locks, "doc_lock", unlocked)
    return collection, audits


def _payload(net_basic=22000):
    return server.SalaryIncrementIn(
        effective_date="2026-10-01", reason="Correction", note="Entered wrongly",
        salary={"basic": net_basic}, apply_now=True,
    )


def test_latest_salary_revision_is_superseded_not_deleted(monkeypatch):
    employee = {
        "id": "emp_1", "salary": {"basic": 20000, "net_monthly": 20000},
        "salary_history": [{
            "id": "sinc_old", "effective_date": "2026-10-01",
            "changed_at": "2026-10-01T10:00:00Z", "previous_gross": 18000,
            "previous_net": 18000, "net_monthly": 20000,
            "salary": {"basic": 20000, "net_monthly": 20000},
        }],
    }
    collection, audits = _install(monkeypatch, employee)

    replacement = asyncio.run(server.supersede_salary_revision(
        "emp_1", "sinc_old", _payload(), object(), None, None,
    ))

    query, update = collection.updates[0]
    history = update["$set"]["salary_history"]
    assert query == {"id": "emp_1", "_lock": {"$exists": True}}
    assert len(history) == 2
    assert history[0]["superseded_by_revision_id"] == replacement["id"]
    assert history[1]["corrects_revision_id"] == "sinc_old"
    assert update["$set"]["salary"]["net_monthly"] == 22000
    assert audits[0][0][1] == "employee.salary_revision_correct"
    assert audits[0][1]["meta"]["original_revision_id"] == "sinc_old"


def test_historical_non_latest_revision_cannot_replace_current_salary(monkeypatch):
    employee = {
        "id": "emp_1", "salary": {"basic": 25000},
        "salary_history": [
            {"id": "sinc_old", "effective_date": "2026-04-01", "changed_at": "2026-04-01"},
            {"id": "sinc_latest", "effective_date": "2026-10-01", "changed_at": "2026-10-01"},
        ],
    }
    collection, audits = _install(monkeypatch, employee)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(server.supersede_salary_revision(
            "emp_1", "sinc_old", _payload(), object(), None, None,
        ))

    assert exc.value.status_code == 409
    assert collection.updates == []
    assert audits == []


def test_salary_revision_correction_requires_payroll_and_finance_permissions(monkeypatch):
    employee = {"id": "emp_1", "salary_history": []}
    collection, audits = _install(monkeypatch, employee, ["payroll.create"])

    with pytest.raises(HTTPException) as exc:
        asyncio.run(server.supersede_salary_revision(
            "emp_1", "sinc_old", _payload(), object(), None, None,
        ))

    assert exc.value.status_code == 403
    assert collection.updates == []
    assert audits == []
