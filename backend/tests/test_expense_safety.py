"""Regression coverage for recoverable expense reimbursement posting."""

import asyncio
from types import SimpleNamespace

from routes import accounting, expenses
from models.expense import ReimburseIn


def _matches(row, query):
    return all(row.get(key) == value for key, value in query.items())


class _Collection:
    def __init__(self, rows=()):
        self.rows = [dict(row) for row in rows]

    async def find_one(self, query, *_args, **_kwargs):
        return next((dict(row) for row in self.rows if _matches(row, query)), None)

    async def update_one(self, query, update):
        for row in self.rows:
            if _matches(row, query):
                row.update(update.get("$set", {}))
                return SimpleNamespace(matched_count=1)
        return SimpleNamespace(matched_count=0)


def test_reimbursement_retry_recovers_existing_journal(monkeypatch):
    claims = _Collection([{
        "id": "exp_1", "status": "approved", "title": "Site travel",
        "claimant_name": "Employee",
        "lines": [{"category": "Travel", "amount": 1000, "tax_rate": 0}],
    }])
    journals = _Collection([{
        "id": "je_existing", "idempotency_key": "org_a:expense:exp_1",
    }])
    monkeypatch.setattr(expenses, "sdb", SimpleNamespace(
        expenses=claims, journal_entries=journals,
    ))

    async def account(*_args, **_kwargs):
        return "expense_account"

    async def no_audit(*_args, **_kwargs):
        return None

    async def unexpected_post(*_args, **_kwargs):
        raise AssertionError("Retry posted a duplicate reimbursement journal")

    monkeypatch.setattr(expenses, "_ensure_account", account)
    monkeypatch.setattr(expenses, "audit", no_audit)
    monkeypatch.setattr(accounting, "_post_journal", unexpected_post)

    result = asyncio.run(expenses._reimburse_locked(
        {"user_id": "admin", "name": "Admin", "org_id": "org_a"},
        "exp_1",
        ReimburseIn(paid_from_account_id="bank", paid_on="2026-10-18"),
    ))

    assert result["journal"]["id"] == "je_existing"
    assert claims.rows[0]["status"] == "reimbursed"
    assert claims.rows[0]["reimbursement_journal_id"] == "je_existing"
