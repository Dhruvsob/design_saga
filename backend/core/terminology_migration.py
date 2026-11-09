"""Owner instruction (08/11/2026): say "incentive / vendor incentive", never
"commission", anywhere in the ERP - including the chart of accounts.

Renames the two default accounts in every company, idempotently, at startup:
  "Vendor Commission Income" -> "Vendor Incentive Income"
  "Commission Advances"      -> "Vendor Incentive Advances"
Only the label changes (account id, code, type, balances and amounts are
untouched). Journal lines keep a display copy of the account name, so those
copies are relabelled too; nothing is posted, reversed or deleted. When a
company already has an account with the new name, the old one is labelled
"... (old)" so names stay unique. Each rename writes an audit row.
"""
import logging

from core.audit import audit
from core.helpers import iso_now

log = logging.getLogger(__name__)

RENAMES = {"Vendor Commission Income": "Vendor Incentive Income",
           "Commission Advances": "Vendor Incentive Advances"}


async def rename_commission_accounts(db) -> int:
    renamed = 0
    legacy = await db.accounts.find(
        {"name": {"$in": list(RENAMES)}}, {"_id": 0, "id": 1, "org_id": 1, "name": 1, "active": 1}
    ).to_list(None)
    # Active accounts first, so the one in use gets the clean name.
    legacy.sort(key=lambda a: 0 if a.get("active") is not False else 1)
    for acc in legacy:
        org_id, target = acc.get("org_id"), RENAMES[acc["name"]]
        taken = await db.accounts.find_one(
            {"org_id": org_id, "name": target, "id": {"$ne": acc["id"]}}, {"_id": 0, "id": 1})
        new_name = f"{target} (old)" if taken else target
        n = 2
        while taken and await db.accounts.find_one({"org_id": org_id, "name": new_name, "id": {"$ne": acc["id"]}}, {"_id": 0, "id": 1}):
            new_name, n = f"{target} (old {n})", n + 1
        result = await db.accounts.update_one(
            {"id": acc["id"], "org_id": org_id, "name": acc["name"]},
            {"$set": {"name": new_name, "renamed_from": acc["name"], "updated_at": iso_now()}})
        if not result.modified_count:
            continue
        relabelled = 0
        async for je in db.journal_entries.find(
                {"org_id": org_id, "lines.account_id": acc["id"]}, {"_id": 0, "id": 1, "lines": 1}):
            lines = [dict(l, account_name=new_name) if l.get("account_id") == acc["id"] else l
                     for l in je.get("lines") or []]
            await db.journal_entries.update_one({"id": je["id"], "org_id": org_id}, {"$set": {"lines": lines}})
            relabelled += 1
        await audit(None, "account.rename_terminology", target=acc["id"], target_type="account",
                    meta={"from": acc["name"], "to": new_name, "journals_relabelled": relabelled}, org_id=org_id)
        log.info("Renamed account %s -> %s in %s (%d journal labels)", acc["name"], new_name, org_id, relabelled)
        renamed += 1
    return renamed
