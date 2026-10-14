"""Scheduled-job wrapper: single-run lease, retries, visible status.

`run_job(name, fn)` acquires a DB lease (so overlapping containers during a
rolling deploy cannot double-run a job), retries transient failures with
backoff, and records the outcome in `job_status` which the health endpoint
and external monitoring read. Jobs themselves must be idempotent (they are:
notification scans use dedup keys, recurring posts use per-date journal
idempotency keys), so a missed or repeated run simply catches up.
"""
import asyncio
import logging
import os
import socket
from datetime import timedelta

from .db import db
from .helpers import iso, now_utc

_log = logging.getLogger("jobs")
_OWNER = f"{socket.gethostname()}:{os.getpid()}"


async def _acquire(name: str, lease_seconds: int) -> bool:
    now = now_utc()
    stale = iso(now - timedelta(seconds=lease_seconds))
    try:
        await db.job_locks.insert_one({"name": name, "owner": None, "at": stale})
    except Exception:  # noqa: BLE001 - already exists
        pass
    res = await db.job_locks.update_one(
        {"name": name, "$or": [{"owner": None}, {"at": {"$lt": stale}}]},
        {"$set": {"owner": _OWNER, "at": iso(now)}})
    return res.modified_count == 1


async def _release(name: str):
    await db.job_locks.update_one({"name": name, "owner": _OWNER},
                                  {"$set": {"owner": None}})


async def run_job(name: str, fn, *, lease_seconds: int = 1800, retries: int = 3):
    if not await _acquire(name, lease_seconds):
        _log.info("[jobs] %s skipped: another instance holds the lease", name)
        return None
    started = iso(now_utc())
    await db.job_status.update_one({"name": name},
                                   {"$set": {"name": name, "last_started_at": started,
                                             "running": True}}, upsert=True)
    try:
        last_exc = None
        for attempt in range(1, retries + 1):
            try:
                result = await fn()
                await db.job_status.update_one({"name": name}, {"$set": {
                    "running": False, "last_success_at": iso(now_utc()),
                    "last_error": None, "consecutive_failures": 0, "attempts": attempt}})
                return result
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                _log.warning("[jobs] %s attempt %d failed: %s", name, attempt, type(exc).__name__)
                await asyncio.sleep(min(60, 5 * attempt))
        await db.job_status.update_one({"name": name}, {
            "$set": {"running": False, "last_failure_at": iso(now_utc()),
                     "last_error": f"{type(last_exc).__name__}: {str(last_exc)[:300]}"},
            "$inc": {"consecutive_failures": 1}})
        return None
    finally:
        await _release(name)


async def job_health(max_age_hours: int = 13) -> dict:
    rows = await db.job_status.find({}, {"_id": 0}).to_list(50)
    cutoff = iso(now_utc() - timedelta(hours=max_age_hours))
    unhealthy = [r["name"] for r in rows
                 if (r.get("consecutive_failures") or 0) > 0
                 or (r.get("last_success_at") or "") < cutoff]
    return {"ok": not unhealthy, "unhealthy": unhealthy, "jobs": rows}
