"""Focused regression coverage for payroll payment safety."""

import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from routes import payroll
import routes.accounting as accounting
import routes.employee_advances as employee_advances


def test_payroll_period_key_is_stable_and_period_specific():
    assert payroll._payroll_period_key("org_a", "emp_a", 2026, 9) == "org_a:emp_a:2026-09"
    assert payroll._payroll_period_key("org_a", "emp_a", 2026, 9) != \
        payroll._payroll_period_key("org_a", "emp_a", 2026, 10)
    assert payroll._payroll_period_key("org_a", "emp_a", 2026, 9) != \
        payroll._payroll_period_key("org_a", "emp_b", 2026, 9)
    assert payroll._payroll_period_key("org_a", "emp_a", 2026, 9) != \
        payroll._payroll_period_key("org_b", "emp_a", 2026, 9)


def test_salary_payment_accepts_explicit_date_method_and_reference():
    payload = payroll.PaySalaryIn(
        year=2026, month=10, paid_from_account_id="bank_hdfc",
        payment_date="2026-10-31", payment_method="upi", reference="UTR-123",
    )
    assert payload.payment_date == "2026-10-31"
    assert payload.payment_method == "upi"
    assert payload.reference == "UTR-123"


def test_salary_payment_rejects_unknown_payment_method():
    with pytest.raises(ValidationError):
        payroll.PaySalaryIn(
            year=2026, month=10, paid_from_account_id="bank_hdfc",
            payment_method="crypto",
        )


def test_salary_reversal_balances_journal_and_reopens_period(monkeypatch):
    run = {
        "id": "run_1", "employee_id": "emp_1", "status": "paid",
        "journal_id": "je_1", "period_key": "org_a:emp_1:2026-10",
    }
    journal = {"id": "je_1", "source": "payroll", "source_id": "run_1"}

    class Runs:
        async def find_one(self, query, *_args):
            return dict(run) if query.get("id") == run["id"] else None

        async def update_one(self, query, update):
            if query.get("id") != run["id"] or query.get("status") != run["status"]:
                return SimpleNamespace(modified_count=0)
            run.update(update.get("$set", {}))
            for key in update.get("$unset", {}):
                run.pop(key, None)
            return SimpleNamespace(modified_count=1)

    class Journals:
        async def find_one(self, query, *_args):
            return dict(journal) if query.get("id") == journal["id"] else None

    async def user(*_args, **_kwargs):
        return {"user_id": "admin", "org_id": "org_a"}

    async def reverse(_user, row, **_kwargs):
        assert row["id"] == "je_1"
        return {"id": "je_reverse"}

    async def no_audit(*_args, **_kwargs):
        return None

    recovered = []

    async def restore_recovery(run_id):
        recovered.append(run_id)

    @asynccontextmanager
    async def unlocked(*_args, **_kwargs):
        yield

    monkeypatch.setattr(payroll, "require_user", user)
    monkeypatch.setattr(payroll, "has_permission", lambda *_args: True)
    monkeypatch.setattr(payroll, "sdb", SimpleNamespace(
        payroll_runs=Runs(), journal_entries=Journals()))
    monkeypatch.setattr(payroll, "doc_lock", unlocked)
    monkeypatch.setattr(payroll, "audit", no_audit)
    monkeypatch.setattr(accounting, "_reverse_journal_entry", reverse)
    monkeypatch.setattr(employee_advances, "restore_recovery", restore_recovery)

    result = asyncio.run(payroll.reverse_salary_payment("run_1", None))
    assert result["status"] == "reversed"
    assert run["status"] == "reversed"
    assert run["original_period_key"] == "org_a:emp_1:2026-10"
    assert run["period_key"] == "org_a:emp_1:2026-10#reversed-run_1"   # never unset (legacy index)
    assert recovered == ["run_1"]


def test_salary_reversal_heals_an_interrupted_prior_reversal(monkeypatch):
    """A journal reversed before the run update must finish as one cancelled salary."""
    run = {
        "id": "run_1", "employee_id": "emp_1", "status": "paid",
        "journal_id": "je_1", "period_key": "org_a:emp_1:2026-10",
    }
    journal = {"id": "je_1", "source": "payroll", "source_id": "run_1",
               "reversed": True, "reversal_je_id": "je_reverse"}
    reversal = {"id": "je_reverse", "source": "payroll_reversal", "source_id": "je_1"}

    class Runs:
        async def find_one(self, query, *_args):
            return dict(run) if query.get("id") == run["id"] else None

        async def update_one(self, query, update):
            if query.get("id") != run["id"] or query.get("status") != run["status"]:
                return SimpleNamespace(modified_count=0)
            run.update(update.get("$set", {}))
            return SimpleNamespace(modified_count=1)

    class Journals:
        async def find_one(self, query, *_args):
            return dict(journal) if query.get("id") == "je_1" else (
                dict(reversal) if query.get("id") == "je_reverse" else None)

    async def user(*_args, **_kwargs):
        return {"user_id": "admin", "org_id": "org_a"}

    async def unexpected_reverse(*_args, **_kwargs):
        raise AssertionError("An existing balanced reversal must not be posted twice")

    hidden = []

    async def hide(_user, row, reason):
        hidden.append((row["id"], reason))

    async def no_audit(*_args, **_kwargs):
        return None

    async def no_recovery(*_args, **_kwargs):
        return None

    @asynccontextmanager
    async def unlocked(*_args, **_kwargs):
        yield

    monkeypatch.setattr(payroll, "require_user", user)
    monkeypatch.setattr(payroll, "has_permission", lambda *_args: True)
    monkeypatch.setattr(payroll, "sdb", SimpleNamespace(
        payroll_runs=Runs(), journal_entries=Journals()))
    monkeypatch.setattr(payroll, "doc_lock", unlocked)
    monkeypatch.setattr(payroll, "audit", no_audit)
    monkeypatch.setattr(accounting, "_reverse_journal_entry", unexpected_reverse)
    monkeypatch.setattr(accounting, "_hide_reversed_pair", hide)
    monkeypatch.setattr(employee_advances, "restore_recovery", no_recovery)

    result = asyncio.run(payroll.reverse_salary_payment("run_1", None))

    assert result["status"] == "reversed"
    assert run["status"] == "reversed"
    assert run["reversal_journal_id"] == "je_reverse"
    assert hidden == [("je_1", "payroll_cancel")]
