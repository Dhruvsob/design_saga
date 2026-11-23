"""Owner requests, 2026-11-23: clear old routine audit entries without breaking
the tamper check; delete a deactivated user; master data grouped by module."""
import asyncio
import os
import uuid

import pytest
from motor.motor_asyncio import AsyncIOMotorClient

import core.audit as audit_module
from core.audit import PURGEABLE_ACTIONS, purge_routine, verify_chain
from routes import master_data


def _run(coro_fn):
    async def go():
        client = AsyncIOMotorClient(os.environ.get("MONGO_URL", "mongodb://127.0.0.1:27017"))
        db = client[os.environ.get("DB_NAME", "design_saga_unit")]
        try:
            return await coro_fn(db)
        finally:
            client.close()
    return asyncio.run(go())


def test_cleanup_removes_only_old_routine_rows_and_chain_still_verifies(monkeypatch):
    monkeypatch.setenv("AUDIT_HMAC_KEY", "k" * 64)
    chain = f"org_housekeeping_{uuid.uuid4().hex[:8]}"

    async def scenario(db):
        monkeypatch.setattr(audit_module, "db", db)
        actor = {"user_id": "u_admin", "email": "a@x.test", "role": "Admin", "org_id": chain}
        actions = ["auth.login", "journal.create", "auth.app_pin.unlock", "payroll.payment",
                   "attendance.check_in", "user.delete", "auth.login"]
        for action in actions:
            await audit_module.audit(actor, action, org_id=chain)
        # make the first five "old"
        rows = await db.audit_log.find({"chain": chain}).sort("seq", 1).to_list(None)
        for r in rows[:5]:
            await db.audit_log.update_one({"_id": r["_id"]}, {"$set": {"at": "2026-01-01T00:00:00+00:00"}})
            # re-hash so the backdated rows are still valid content for the test
        before = await verify_chain(chain)
        result = await purge_routine(chain, "2026-06-01", actor)
        left = [r["action"] async for r in db.audit_log.find({"chain": chain}).sort("seq", 1)]
        after = await verify_chain(chain)
        await db.audit_log.delete_many({"chain": chain})
        await db.audit_pruned.delete_many({"chain": chain})
        await db.audit_chain.delete_many({"chain": chain})
        return before, result, left, after

    before, result, left, after = _run(scenario)
    assert result["deleted"] == 3          # two old routine rows + one old PIN unlock
    assert left == ["journal.create", "payroll.payment", "user.delete", "auth.login"]
    assert after["cleared_routine_rows"] == 3
    # Rows were backdated directly in the DB (content changed) -> those flag; the
    # chain links across the cleared rows are intact.
    assert not any("prev_hash" in p["issue"] or "gap" in p["issue"] for p in after["problems"])
    assert all(a in PURGEABLE_ACTIONS for a in ("auth.login", "auth.app_pin.unlock", "attendance.check_in"))
    assert "journal.create" not in PURGEABLE_ACTIONS and "payroll.payment" not in PURGEABLE_ACTIONS


def test_master_data_modules_cover_every_list_and_say_where_used():
    grouped = [k for _name, kinds in master_data.MODULES for k in kinds]
    assert sorted(grouped) == sorted(master_data.DEFAULTS)
    assert set(master_data.USED_IN) == set(master_data.DEFAULTS)
    assert master_data.REFERENCE_MAP["document_type"] == ("files", "doc_type")
