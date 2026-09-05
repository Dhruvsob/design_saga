"""Tiny helpers shared across routes."""
from datetime import datetime, timezone
import uuid


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime) -> str:
    return dt.isoformat()


def iso_now() -> str:
    return iso(now_utc())


def new_id(prefix: str = "") -> str:
    return f"{prefix}{uuid.uuid4().hex[:12]}" if prefix else uuid.uuid4().hex[:12]


# ------------------------------------------------------------------
# Document numbering — atomic per-org counter (never reused after delete)
# ------------------------------------------------------------------
import re as _re


async def max_trailing_number(cursor, field: str = "number") -> int:
    """Largest trailing integer among existing doc numbers (e.g. INV-1042 -> 1042)."""
    mx = 0
    async for d in cursor:
        m = _re.search(r"(\d+)$", str(d.get(field) or ""))
        if m:
            mx = max(mx, int(m.group(1)))
    return mx


async def next_sequence(org_id: str, kind: str, seed: int = 1000) -> int:
    """Return the next number for `kind` in this org. First call seeds the counter
    from `seed` (max existing number) so history is respected and numbers are
    never reused when a document is deleted."""
    from pymongo import ReturnDocument
    from .db import db
    key = {"org_id": org_id or "org_default", "kind": kind}
    if not await db.counters.find_one(key):
        try:
            await db.counters.insert_one({**key, "seq": max(int(seed or 0), 1000)})
        except Exception:
            pass  # concurrent seed — fine
    doc = await db.counters.find_one_and_update(
        key, {"$inc": {"seq": 1}}, return_document=ReturnDocument.AFTER)
    return int(doc["seq"])
