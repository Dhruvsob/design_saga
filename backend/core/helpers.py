"""Tiny helpers shared across routes."""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import os
import uuid


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime) -> str:
    return dt.isoformat()


def iso_now() -> str:
    return iso(now_utc())


def business_today():
    """Current business date. Timestamps remain UTC; date workflows use IST."""
    tz = ZoneInfo(os.environ.get("BUSINESS_TIMEZONE", "Asia/Kolkata"))
    return now_utc().astimezone(tz).date()


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


def session_digest(token: str) -> str:
    """Sessions are stored as SHA-256 digests so a leaked database/backup does
    not yield usable bearer tokens. Lookups accept the legacy plaintext form
    until those 7-day sessions expire naturally."""
    import hashlib
    return "sha256:" + hashlib.sha256((token or "").encode("utf-8")).hexdigest()


def session_lookup_values(token: str) -> list:
    return [session_digest(token), token]
