"""Same-workspace checks for IDs that arrive inside request bodies.

Path IDs are already resolved through tenant-scoped queries, but a body field
such as `client_id` or `paid_from_account_id` used to be stored as given. A
caller could therefore save a record in their own workspace that points at
another workspace's client, project, account or employee: no data is
disclosed (every read is scoped), but the reference is dangling, breaks
ledgers and reports, and a recurring expense built on it fails every run.

`ensure_in_tenant(client_id=..., project_id=...)` looks each non-empty ID up
through the scoped database (`sdb`), so it only finds records of the caller's
own workspace, and answers 400 naming the field otherwise.
"""
from typing import Iterable, Optional, Union

from fastapi import HTTPException

from core.scoped_db import sdb

# field -> (label, collections to look in, in order)
REFS = {
    "client_id": ("Client", ("clients",)),
    "project_id": ("Project", ("projects",)),
    "lead_id": ("Lead", ("leads",)),
    "vendor_id": ("Vendor", ("vendors_acc", "vendors")),
    "employee_id": ("Employee", ("employees",)),
    "assignee_id": ("Assignee", ("employees", "users")),
    "assignees": ("Assignee", ("employees", "users")),
    "project_manager_id": ("Project manager", ("employees", "users")),
    "account_id": ("Account", ("accounts",)),
    "expense_account_id": ("Expense account", ("accounts",)),
    "paid_from_account_id": ("Paid-from account", ("accounts",)),
    "salary_account_id": ("Salary account", ("accounts",)),
}

Value = Optional[Union[str, Iterable[str]]]


async def _exists(collections: tuple, value: str) -> bool:
    for coll in collections:
        key = "user_id" if coll == "users" else "id"
        if await sdb[coll].find_one({key: value}, {"_id": 0, key: 1}):
            return True
    return False


async def ensure_in_tenant(**refs: Value) -> None:
    """Raise 400 when a referenced record is not in the caller's workspace."""
    for field, value in refs.items():
        if not value:
            continue
        label, collections = REFS[field]
        values = [value] if isinstance(value, str) else [v for v in value if v]
        for v in values:
            if not isinstance(v, str) or not await _exists(collections, v):
                raise HTTPException(status_code=400, detail=f"{label} not found in this workspace")
