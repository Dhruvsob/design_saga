"""A busy account's ledger opens on 'All time': exact totals, newest lines shown (DB-01)."""

import asyncio
import os
import uuid

from motor.motor_asyncio import AsyncIOMotorClient


def test_large_ledger_shows_latest_lines_with_exact_balance(monkeypatch):
    import core.db as db_module
    import core.scoped_db as scoped_db_module
    import routes.accounting as acc
    from core.scoped_db import set_scope_from_user, clear_scope
    org = f"org_test_{uuid.uuid4().hex[:8]}"
    user = {"org_id": org, "role": "Admin", "user_id": f"u_{org}"}

    async def require(*_a, **_k):
        return user

    async def main():
        client = AsyncIOMotorClient(os.environ["MONGO_URL"])
        db = client[os.environ["DB_NAME"]]
        for module in (db_module, scoped_db_module, acc):
            monkeypatch.setattr(module, "db", db)
        monkeypatch.setattr(acc, "require_user", require)
        monkeypatch.setattr(acc, "LEDGER_DISPLAY_ROWS", 100)
        set_scope_from_user(user)
        try:
            await db.accounts.insert_one({"id": f"bank_{org}", "org_id": org, "name": "Bank", "type": "asset", "opening_balance": 1000})
            await db.journal_entries.insert_many([{
                "id": f"je{i}_{org}", "org_id": org, "date": f"2025-{1 + i % 12:02d}-{1 + i % 28:02d}", "narration": f"n{i}",
                "lines": [{"account_id": f"bank_{org}", "account_name": "Bank", "account_type": "asset", "debit": 10, "credit": 0},
                          {"account_id": "x", "account_name": "Fees", "account_type": "income", "debit": 0, "credit": 10}]}
                for i in range(250)])
            r = await acc.account_ledger(f"bank_{org}", None)
            assert r["line_count"] == 250 and r["earlier_lines_hidden"] == 150 and len(r["rows"]) == 100
            assert r["closing_balance"] == 1000 + 2500 and r["total_debit"] == 2500
            assert r["rows"][-1]["balance"] == 3500                  # running balance stays exact
            assert [x["date"] for x in r["rows"]] == sorted(x["date"] for x in r["rows"])   # oldest to newest
        finally:
            clear_scope()
            await db.accounts.delete_many({"org_id": org})
            await db.journal_entries.delete_many({"org_id": org})
            client.close()

    asyncio.run(main())
