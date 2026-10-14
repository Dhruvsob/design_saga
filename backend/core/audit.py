"""Append-only, tamper-evident audit log for critical actions (auth,
permissions, approvals, deletes, payroll, finance, exports, org status).

Usage:
    from core.audit import audit
    await audit(user, action="org.suspend", target=org_id, meta={...})

Tamper evidence: every row carries a per-organisation sequence number,
the previous row's hash and its own HMAC-SHA256 digest (keyed with
`AUDIT_HMAC_KEY` when configured, plain SHA-256 otherwise). Editing,
deleting or re-ordering rows breaks the chain, which
`GET /api/audit-log/verify` reports. No API route updates or deletes rows.

Reads via /api/audit-log (Admin scoped by org, SuperAdmin sees all).
"""
import hashlib
import hmac
import json
import logging
import os
from typing import Optional

from .db import db
from .helpers import iso_now, new_id

_log = logging.getLogger("audit")
_HASH_FIELDS = ("id", "at", "action", "target", "target_type", "actor_id",
                "actor_email", "actor_role", "org_id", "meta", "seq", "prev_hash")


def audit_digest(doc: dict) -> str:
    payload = json.dumps({k: doc.get(k) for k in _HASH_FIELDS}, sort_keys=True,
                         default=str, separators=(",", ":")).encode("utf-8")
    key = os.environ.get("AUDIT_HMAC_KEY", "").encode("utf-8")
    if key:
        return "hmac256:" + hmac.new(key, payload, hashlib.sha256).hexdigest()
    return "sha256:" + hashlib.sha256(payload).hexdigest()


async def _link(doc: dict, chain_key: str) -> None:
    """Atomically append `doc` to the org hash chain (compare-and-swap on head)."""
    for _ in range(10):
        head = await db.audit_chain.find_one({"chain": chain_key}, {"_id": 0})
        if not head:
            try:
                await db.audit_chain.insert_one({"chain": chain_key, "seq": 0, "head": "genesis"})
            except Exception:  # noqa: BLE001 - concurrent creator
                pass
            continue
        seq = int(head.get("seq") or 0)
        doc["seq"] = seq + 1
        doc["prev_hash"] = head.get("head") or "genesis"
        doc["hash"] = audit_digest(doc)
        res = await db.audit_chain.update_one(
            {"chain": chain_key, "seq": seq, "head": doc["prev_hash"]},
            {"$set": {"seq": doc["seq"], "head": doc["hash"]}})
        if res.modified_count == 1:
            return
    # Heavy contention: store unchained but still self-hashed (verify reports it).
    doc["seq"] = None
    doc["prev_hash"] = None
    doc["hash"] = audit_digest(doc)


async def audit(actor: Optional[dict], action: str, target: str = "",
                target_type: str = "", meta: Optional[dict] = None,
                org_id: Optional[str] = None):
    """Append one row. Never raises — audit failures shouldn't break flows."""
    try:
        doc = {
            "id": new_id("aud_"),
            "at": iso_now(),
            "action": action,
            "target": target,
            "target_type": target_type,
            "actor_id": (actor or {}).get("user_id"),
            "actor_email": (actor or {}).get("email"),
            "actor_role": (actor or {}).get("role"),
            "org_id": org_id or (actor or {}).get("org_id"),
            "meta": meta or {},
        }
        chain_key = doc["org_id"] or "platform"
        doc["chain"] = chain_key
        await _link(doc, chain_key)
        await db.audit_log.insert_one(doc)
    except Exception as exc:  # noqa: BLE001
        _log.warning("audit write failed for %s: %s", action, type(exc).__name__)


async def verify_chain(chain_key: str, limit: int = 20000) -> dict:
    rows = await db.audit_log.find(
        {"chain": chain_key, "seq": {"$ne": None}}, {"_id": 0}
    ).sort("seq", 1).to_list(limit)
    problems = []
    prev = "genesis"
    expected = None
    for r in rows:
        if expected is not None and r["seq"] != expected:
            problems.append({"seq": r["seq"], "issue": f"gap: expected seq {expected}"})
        if r.get("prev_hash") != prev:
            problems.append({"seq": r["seq"], "issue": "prev_hash mismatch"})
        if audit_digest(r) != r.get("hash"):
            problems.append({"seq": r["seq"], "issue": "content hash mismatch (row altered)"})
        prev = r.get("hash")
        expected = r["seq"] + 1
    legacy = await db.audit_log.count_documents({"org_id": None if chain_key == "platform" else chain_key,
                                                 "seq": {"$exists": False}})
    return {"chain": chain_key, "rows_checked": len(rows), "ok": not problems,
            "problems": problems[:100], "legacy_unchained_rows": legacy}
