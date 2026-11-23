"""Who paid a money-in entry: the client, or a vendor (incentive / commission).

One rule for every screen and document (owner, 2026-11-23). A receipt is a
vendor incentive when it comes from the vendor module, names a vendor, or
credits a commission / incentive account. Such money never counts as the
client's payment: not on the project, not on the client's statement or
ledger, not on the receipt PDF, whatever client the entry was tagged with.

Receipts on a project that carry no client (older milestone collections)
belong to the project's client.
"""
from __future__ import annotations

import re
from typing import Optional

from core.limits import MAX_LIST_ROWS
from core.scoped_db import sdb

COMMISSION_NAME = re.compile(r"commission|incentive", re.IGNORECASE)
CLIENT_MONEY_IN_SOURCES = ("income", "invoice_payment", "milestone_payment",
                           "other_receivable_income")


async def commission_account_ids(db=None) -> set:
    """Vendor commission / incentive accounts in this workspace (code 3010 or
    named so, including renamed defaults and the advances account)."""
    rows = await (db or sdb).accounts.find(
        {"$or": [{"code": "3010"}, {"name": {"$regex": "commission|incentive", "$options": "i"}}]},
        {"_id": 0, "id": 1, "name": 1, "code": 1}).to_list(MAX_LIST_ROWS)
    return {a["id"] for a in rows
            if a.get("code") == "3010" or COMMISSION_NAME.search(str(a.get("name") or ""))}


def is_commission_receipt(journal: dict, commission_ids: set) -> bool:
    return (str(journal.get("source") or "").startswith("commission_income")
            or bool(journal.get("vendor_id"))
            or any(line.get("account_id") in commission_ids for line in journal.get("lines") or []))


def payer(journal: dict, commission_ids: set) -> str:
    """'vendor' for incentives, 'client' otherwise."""
    return "vendor" if is_commission_receipt(journal, commission_ids) else "client"


async def client_project_ids(client_id: str, db=None) -> list[str]:
    return [p["id"] async for p in (db or sdb).projects.find({"client_id": client_id}, {"_id": 0, "id": 1})]


def client_receipt_query(client_id: str, project_ids: list[str], sources=CLIENT_MONEY_IN_SOURCES) -> dict:
    """Money-in journals that may be this client's payments (filter with
    is_commission_receipt afterwards)."""
    either = [{"client_id": client_id}]
    if project_ids:
        either.append({"project_id": {"$in": project_ids},
                       "client_id": {"$in": [None, ""]}})
    return {"source": {"$in": list(sources)}, "$or": either}


async def project_client_id(project_id: Optional[str], db=None) -> Optional[str]:
    if not project_id:
        return None
    project = await (db or sdb).projects.find_one({"id": project_id}, {"_id": 0, "client_id": 1})
    return (project or {}).get("client_id") or None


def signed_cash_in(journal: dict) -> float:
    """Cash received by a money-in entry: debits to cash/bank lines, or minus
    the credits on its reversal."""
    is_reversal = str(journal.get("source") or "").endswith("_reversal")
    side = "credit" if is_reversal else "debit"
    cash = sum(float(line.get(side) or 0) for line in journal.get("lines") or []
               if line.get("account_type") == "asset"
               and line.get("account_name") != "Accounts Receivable")
    return -cash if is_reversal else cash


def split_project_receipts(journals: list, commission_ids: set) -> tuple[float, float]:
    """(client fee received, vendor commission received) for one project.

    A reversal copies the original's accounts and vendor, so it is classified
    the same way and only undoes its own kind. Owner, 2026-11-23: commission
    must never reduce the client's outstanding fee.
    """
    client = commission = 0.0
    for je in journals or []:
        signed = signed_cash_in(je)
        if is_commission_receipt(je, commission_ids):
            commission += signed
        else:
            client += signed
    return round(client, 2), round(commission, 2)
