"""Closed accounting periods ("books closed up to <date>").

One rule, enforced where every journal is written (`_post_journal`) and where
an existing entry is taken out of the books (Delete / Correct / restatement):
nothing dated on or before the lock date may be added, removed or hidden.

A plain reversal dated today stays allowed - it corrects a closed period
without rewriting it, which is how closed books are meant to be corrected.

The lock date lives on the tenant's organisation record so one read answers
"is this period closed?"; the history of closes/reopens is kept in
`period_closes` with the person, reason and export fingerprint.
"""
from datetime import date as _date
from typing import Optional

from fastapi import HTTPException

from core.db import db
from core.scoped_db import current_org_id


def _display(iso: str) -> str:
    try:
        d = _date.fromisoformat(str(iso)[:10])
    except ValueError:
        return str(iso)
    return d.strftime("%d/%m/%Y")


async def locked_through(org_id: Optional[str] = None) -> Optional[str]:
    oid = org_id or current_org_id() or "org_default"
    org = await db.organizations.find_one({"org_id": oid}, {"_id": 0, "books_locked_through": 1})
    value = (org or {}).get("books_locked_through")
    return str(value)[:10] if value else None


def is_locked(day: Optional[str], lock: Optional[str]) -> bool:
    return bool(lock and day and str(day)[:10] <= lock)


async def assert_period_open(day: Optional[str], what: str = "This entry") -> None:
    """Refuse a change that would alter books already closed."""
    lock = await locked_through()
    if is_locked(day, lock):
        raise HTTPException(
            status_code=409,
            detail=(f"{what} is dated {_display(day)}, but the books are closed up to {_display(lock)}. "
                    "Date it after the closing date, reverse it with today's date, "
                    "or ask an administrator to reopen the period."),
        )
