"""Collection Due reminders: one schedule reflected in alerts, calendar, Google and Payment Reminders."""

import asyncio
import os
import uuid

from motor.motor_asyncio import AsyncIOMotorClient

from core import collection_reminders as cr


def test_occurrences_advance_main_and_repeats():
    row = {"reminder_date": "2026-11-20", "reminder_time": "09:30", "remind_before_days": 2, "repeat_every": "weekly"}
    occ = cr.occurrences(row)
    assert occ[0] == ("advance", "2026-11-18T09:30")
    assert occ[1] == ("main", "2026-11-20T09:30")
    assert occ[2] == ("repeat", "2026-11-27T09:30") and len(occ) == 2 + cr.MAX_REPEATS
    assert cr.occurrences({"reminder_date": "2026-11-20"}) == [("main", "2026-11-20T10:00")]   # default time
    assert cr.occurrences({"reminder_date": "2026-11-20", "reminder_time": "25:99"})[0][1].endswith("10:00")
    assert cr.occurrences({}) == []


def test_reminder_is_reflected_everywhere_and_closed_on_receipt(monkeypatch):
    import core.db as db_module
    import core.indexes as indexes_module
    import core.notifications as notifications_module
    import core.scoped_db as scoped_db_module
    from core.scoped_db import set_scope_from_user, clear_scope, sdb
    org = f"org_test_{uuid.uuid4().hex[:8]}"
    google = []

    async def fake_google(org_id, eid, op):
        google.append(op)
    monkeypatch.setattr(cr, "_queue_google", fake_google)
    monkeypatch.setattr(cr, "now_local_key", lambda: "2026-11-01T08:00")

    async def run():
        # Motor binds a client to the first event loop that uses it.  The wider
        # regression suite deliberately calls many async helpers through
        # ``asyncio.run()``, so reusing the application-global client here can
        # leave this test attached to a loop another test has already closed.
        # Keep this real-Mongo integration test isolated to its own client and
        # loop; production code still uses the singleton in ``core.db``.
        client = AsyncIOMotorClient(os.environ["MONGO_URL"])
        db = client[os.environ["DB_NAME"]]
        monkeypatch.setattr(db_module, "db", db)
        monkeypatch.setattr(scoped_db_module, "db", db)
        monkeypatch.setattr(notifications_module, "db", db)
        monkeypatch.setattr(indexes_module, "db", db)
        monkeypatch.setattr(cr, "db", db)
        await db.users.insert_many([
            {"user_id": f"u_{org}", "org_id": org, "role": "Admin", "name": "Owner"},
            {"user_id": f"director_{org}", "org_id": org, "role": "Director", "name": "Director"},
            {"user_id": f"accountant_{org}", "org_id": org, "role": "Accountant", "name": "Accountant"},
            {"user_id": f"employee_{org}", "org_id": org, "role": "Employee", "name": "Employee"},
        ])
        set_scope_from_user({"org_id": org, "role": "Admin", "user_id": f"u_{org}"})
        try:
            await sdb.collection_receivables.insert_one({
                "id": "recv_x", "name": "Design fee", "amount": 25000, "received_amount": 0,
                "status": "pending", "due_date": "2026-11-25", "reminder_date": "2026-11-20",
                "reminder_time": "09:30", "remind_before_days": 1, "repeat_every": "none"})
            out = await cr.refresh("other_receivable", "recv_x", f"u_{org}")
            assert out["active"] and out["alerts_added"] == 2
            ev = await sdb.calendar_events.find_one({"id": out["event_id"]})
            assert ev["date"] == "2026-11-20" and ev["start_time"] == "09:30" and ev["alert_minutes"] == [0, 1440]
            assert ev["visibility"] == "private"
            assert set(ev["attendee_ids"]) == {f"u_{org}", f"director_{org}"}
            assert ev["created_by"] == "system:collections"
            assert "25,000" in ev["title"]
            # Startup migration also repairs reminders created by older builds,
            # so an Accountant creator cannot retain personal Google access.
            await sdb.calendar_events.update_one({"id": out["event_id"]}, {"$set": {
                "attendee_ids": [f"accountant_{org}"],
                "created_by": f"accountant_{org}",
                "created_by_name": "Accountant",
            }})
            await indexes_module._migrate_collection_calendar_privacy()
            ev = await sdb.calendar_events.find_one({"id": out["event_id"]})
            assert set(ev["attendee_ids"]) == {f"u_{org}", f"director_{org}"}
            assert ev["created_by"] == "system:collections"
            doc = await sdb.payment_reminders.find_one({"source_id": "recv_x", "auto": True})
            assert doc["number"].startswith("PR-") and doc["amount_due"] == 25000
            # refresh again: nothing duplicated
            await cr.refresh("other_receivable", "recv_x")
            assert await sdb.reminder_alerts.count_documents({"source_id": "recv_x", "status": "pending"}) == 2
            assert await sdb.payment_reminders.count_documents({"source_id": "recv_x"}) == 1
            assert await sdb.calendar_events.count_documents({"source_id": "recv_x"}) == 1
            # time comes for the advance alert -> one notification, sound flag
            clear_scope()
            monkeypatch.setattr(cr, "now_local_key", lambda: "2026-11-19T09:30")
            assert await cr.process_due_alerts() == 1
            assert await cr.process_due_alerts() == 0
            n = await db.notifications.find_one({"org_id": org, "kind": "collection_reminder"})
            assert n and n["meta"]["sound"] is True and "Coming up" in n["title"]
            # money received in full -> everything closed
            set_scope_from_user({"org_id": org, "role": "Admin", "user_id": f"u_{org}"})
            await sdb.collection_receivables.update_one({"id": "recv_x"}, {"$set": {"received_amount": 25000, "status": "received"}})
            out = await cr.refresh("other_receivable", "recv_x")
            assert out == {"active": False}
            assert await sdb.reminder_alerts.count_documents({"source_id": "recv_x", "status": "pending"}) == 0
            assert await sdb.calendar_events.count_documents({"source_id": "recv_x"}) == 0
            doc = await sdb.payment_reminders.find_one({"source_id": "recv_x"})
            assert doc["status"] == "settled" and doc["amount_due"] == 0
            assert google == ["upsert", "upsert", "delete"]
        finally:
            clear_scope()
            for coll in ("users", "collection_receivables", "calendar_events", "payment_reminders",
                         "reminder_alerts", "notifications", "counters"):
                await db[coll].delete_many({"org_id": org})
            client.close()

    asyncio.run(run())
