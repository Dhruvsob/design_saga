"""Per-document mutual exclusion for financial state transitions.

FerretDB/PostgreSQL deployments do not give us multi-document transactions
for every flow, so posting routes (GRN, EMI, prepayment, reimbursement)
claim a short-lived lock field on the parent document with an atomic
conditional update. Only one request can hold the lock; others receive 409.
Stale locks (crashed worker) expire after ``ttl_seconds``.
"""
from contextlib import asynccontextmanager
from datetime import timedelta

from fastapi import HTTPException

from .helpers import iso, new_id, now_utc

LOCK_FIELDS = {"_lock": 0, "_lock_at": 0}


@asynccontextmanager
async def doc_lock(coll, doc_id: str, ttl_seconds: int = 60):
    token = new_id("lock_")
    now = now_utc()
    stale = iso(now - timedelta(seconds=ttl_seconds))
    res = await coll.update_one(
        {"id": doc_id, "$or": [{"_lock": {"$exists": False}},
                               {"_lock": None},
                               {"_lock_at": {"$lt": stale}}]},
        {"$set": {"_lock": token, "_lock_at": iso(now)}},
    )
    if res.matched_count == 0:
        exists = await coll.count_documents({"id": doc_id})
        if not exists:
            raise HTTPException(404, "Record not found")
        raise HTTPException(
            409, "Another update to this record is in progress. Please retry.")
    try:
        yield token
    finally:
        await coll.update_one({"id": doc_id, "_lock": token},
                              {"$unset": {"_lock": "", "_lock_at": ""}})
