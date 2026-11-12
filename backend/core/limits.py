"""Shared row limits and per-tenant plan limits.

Money, ledger, payroll and access-control reads load every row (to_list(None)) so totals
and permissions are never silently wrong. Plain display lists use MAX_LIST_ROWS, set far
above a studio's realistic volume, so records no longer drop off lists at 500-2,000 rows.
"""
from typing import Optional

from fastapi import HTTPException

MAX_LIST_ROWS = 20000


async def _tenant_limits(org_id: Optional[str]) -> dict:
    if not org_id:
        return {}
    from .entitlements import for_org_id
    return ((await for_org_id(org_id)) or {}).get("limits") or {}


async def enforce_project_limit(org_id: Optional[str]) -> None:
    """Refuse a new project (created, converted from a lead or a quotation) over the plan."""
    limit = (await _tenant_limits(org_id)).get("max_projects")
    if not limit:
        return
    from .scoped_db import sdb
    current = await sdb.projects.count_documents({})
    if current >= limit:
        raise HTTPException(status_code=402,
                            detail=f"Project limit reached ({current}/{limit}). Upgrade your plan.")


async def tenant_storage_quota_bytes(org_id: Optional[str]) -> Optional[int]:
    """The tenant's plan storage quota in bytes (None = platform default only)."""
    mb = (await _tenant_limits(org_id)).get("storage_mb")
    return int(mb) * 1024 * 1024 if mb else None
