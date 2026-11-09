"""Default account names lose the word 'commission'; labels only, idempotent, unique names."""

import asyncio
import os
import uuid

from motor.motor_asyncio import AsyncIOMotorClient

from core import terminology_migration as tm


def test_rename_commission_accounts(monkeypatch):
    import core.audit as audit_module
    org = f"org_test_{uuid.uuid4().hex[:8]}"
    other = f"org_test_{uuid.uuid4().hex[:8]}"

    async def main():
        client = AsyncIOMotorClient(os.environ["MONGO_URL"])
        db = client[os.environ["DB_NAME"]]
        monkeypatch.setattr(audit_module, "db", db)
        try:
            await db.accounts.insert_many([
                # like DESIGN SAGA: new name already in use, old one inactive and unused
                {"id": f"a1_{org}", "org_id": org, "code": "3010", "name": "Vendor Commission Income", "type": "income", "active": False},
                {"id": f"a2_{org}", "org_id": org, "code": "3010", "name": "Vendor Incentive Income", "type": "income"},
                {"id": f"a3_{org}", "org_id": org, "code": "2302", "name": "Commission Advances", "type": "liability"},
                # like the demo company: old name still in use
                {"id": f"b1_{other}", "org_id": other, "code": "3010", "name": "Vendor Commission Income", "type": "income"},
            ])
            await db.journal_entries.insert_one({"id": f"je_{other}", "org_id": other, "total": 500, "lines": [
                {"account_id": "cash", "account_name": "Cash", "debit": 500, "credit": 0},
                {"account_id": f"b1_{other}", "account_name": "Vendor Commission Income", "debit": 0, "credit": 500}]})
            assert await tm.rename_commission_accounts(db) >= 3
            names = {a["id"]: a["name"] async for a in db.accounts.find({"org_id": {"$in": [org, other]}})}
            assert names[f"a1_{org}"] == "Vendor Incentive Income (old)"
            assert names[f"a2_{org}"] == "Vendor Incentive Income"
            assert names[f"a3_{org}"] == "Vendor Incentive Advances"
            assert names[f"b1_{other}"] == "Vendor Incentive Income"
            je = await db.journal_entries.find_one({"id": f"je_{other}"})
            assert [l["account_name"] for l in je["lines"]] == ["Cash", "Vendor Incentive Income"]
            assert [l["credit"] for l in je["lines"]] == [0, 500]           # amounts untouched
            assert await db.accounts.count_documents({"org_id": {"$in": [org, other]}, "name": {"$regex": "ommission"}}) == 0
            await tm.rename_commission_accounts(db)                          # second run: nothing changes
            assert names == {a["id"]: a["name"] async for a in db.accounts.find({"org_id": {"$in": [org, other]}})}
            assert await db.audit_log.count_documents({"org_id": org, "action": "account.rename_terminology"}) == 2
        finally:
            for name in ("accounts", "journal_entries", "audit_log"):
                await db[name].delete_many({"org_id": {"$in": [org, other]}})
            client.close()

    asyncio.run(main())
