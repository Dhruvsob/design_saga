"""Append-only, tamper-evident audit log for critical actions (auth,
permissions, approvals, deletes, payroll, finance, exports, org status).

Usage:
    from core.audit import audit
    await audit(user, action="org.suspend", target=org_id, meta={...})

Tamper evidence: every row carries a per-organisation sequence number,
the previous row's hash and its own HMAC-SHA256 digest (keyed with
`AUDIT_HMAC_KEY`; production startup requires this key). Editing,
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


# Routine, high-volume events an admin may clear after a while (owner,
# 2026-11-23: the log filled with PIN unlocks and sign-ins). Everything else
# (money, payroll, permissions, deletions, exports) is kept: the audit trail
# of the books must be preserved for 8 years (Companies (Accounts) Rules, 2014).
PURGEABLE_ACTIONS = (
    "auth.app_pin.unlock", "auth.app_pin.lock", "auth.login", "auth.logout",
    "auth.login_failed", "auth.refresh", "attendance.check_in", "attendance.check_out",
    "google_calendar.sync", "notification.read",
)
MIN_KEEP_DAYS = 30


async def purge_routine(chain_key: str, before_iso: str, actor: dict) -> dict:
    """Delete routine rows older than `before_iso`, keeping a tiny stub of each
    (seq, hash, prev_hash) so the hash chain still verifies end to end."""
    q = {"chain": chain_key, "action": {"$in": list(PURGEABLE_ACTIONS)}, "at": {"$lt": before_iso}}
    stubs = []
    async for r in db.audit_log.find(q, {"_id": 0, "seq": 1, "hash": 1, "prev_hash": 1,
                                         "action": 1, "at": 1, "chain": 1}):
        stubs.append({**r, "org_id": None if chain_key == "platform" else chain_key,
                      "pruned_at": iso_now(), "pruned_by": (actor or {}).get("user_id")})
    for stub in stubs:
        # Upsert by (chain, seq): two clean-ups at once never duplicate a link.
        await db.audit_pruned.update_one({"chain": stub["chain"], "seq": stub["seq"]},
                                         {"$setOnInsert": dict(stub)}, upsert=True)
    if stubs:
        await db.audit_log.delete_many(q)
    return {"deleted": len(stubs)}


async def verify_chain(chain_key: str, limit: int = 20000) -> dict:
    rows = await db.audit_log.find(
        {"chain": chain_key, "seq": {"$ne": None}}, {"_id": 0}
    ).sort("seq", 1).to_list(limit)
    pruned_rows = getattr(db, "audit_pruned", None)
    pruned = await pruned_rows.find(
        {"chain": chain_key, "seq": {"$ne": None}}, {"_id": 0}).to_list(None) if pruned_rows is not None else []
    if pruned:
        # A cleared routine row leaves its link (seq, hashes): the chain is
        # still checked across it; only that row's content is gone.
        for stub in pruned:
            stub["_pruned"] = True
        rows = sorted([*rows, *pruned], key=lambda r: r["seq"])
    problems = []
    prev = "genesis"
    expected = None
    for r in rows:
        if expected is not None and r["seq"] != expected:
            problems.append({"seq": r["seq"], "issue": f"gap: expected seq {expected}"})
        if r.get("prev_hash") != prev:
            problems.append({"seq": r["seq"], "issue": "prev_hash mismatch"})
        if not r.get("_pruned") and audit_digest(r) != r.get("hash"):
            problems.append({"seq": r["seq"], "issue": "content hash mismatch (row altered)"})
        prev = r.get("hash")
        expected = r["seq"] + 1
    total_chained = await db.audit_log.count_documents(
        {"chain": chain_key, "seq": {"$ne": None}}) + len(pruned)
    unchained = await db.audit_log.count_documents(
        {"chain": chain_key, "seq": None})
    head = await db.audit_chain.find_one({"chain": chain_key}, {"_id": 0})
    if total_chained > limit:
        problems.append({"seq": None, "issue": f"verification limit exceeded: {total_chained} rows"})
    elif rows:
        if not head:
            problems.append({"seq": rows[-1]["seq"], "issue": "chain head missing"})
        elif int(head.get("seq") or 0) != rows[-1]["seq"] or head.get("head") != prev:
            problems.append({"seq": rows[-1]["seq"], "issue": "stored chain head mismatch"})
    elif head and (int(head.get("seq") or 0) != 0 or head.get("head") != "genesis"):
        problems.append({"seq": None, "issue": "chain head exists without matching rows"})
    if unchained:
        problems.append({"seq": None, "issue": f"{unchained} unchained row(s)"})
    legacy = await db.audit_log.count_documents({
        "org_id": None if chain_key == "platform" else chain_key,
        "seq": {"$exists": False},
    })
    return {"chain": chain_key, "rows_checked": len(rows), "ok": not problems,
            "cleared_routine_rows": len(pruned),
            "problems": problems[:100], "legacy_unchained_rows": legacy,
            "unchained_rows": unchained}
