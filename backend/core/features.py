"""Feature-flag / business-mode gating.

Usage
-----
    from core.features import require_module

    @router.post("/purchase-orders")
    async def create_po(payload, request, ..., user=Depends(...)):
        await require_module(user, "purchase_orders")

Every business-mode-sensitive endpoint calls `require_module(user, key)`.
If the org's `features.modules[key]` is `False`, HTTP 403 is raised.
"""
from typing import Optional
from fastapi import HTTPException

from .db import db
from .tenancy import user_org_id, is_super_admin


MODULE_LABEL = {
    "purchase_orders":   "Purchase Orders",
    "procurement":       "Procurement",
    "inventory":         "Inventory",
    "material_tracking": "Material Tracking",
    "vendor_billing":    "Vendor Billing",
    "labour_billing":    "Labour Billing",
    "site_material":     "Site Material",
    "project_costing":   "Project Costing",
    "loans":             "Loans & EMI",
    "expenses":          "Expenses",
    "attendance":        "Attendance",
    "payroll":           "Payroll",
    "accounting":        "Accounting",
    "quotations":        "Quotations",
    "invoices":          "Invoices",
}


async def require_module(user: dict, module_key: str) -> None:
    """Raise HTTP 403 if the module is disabled for the user's org.

    Super admins bypass the check (they have no org context)."""
    if is_super_admin(user) and not user.get("org_id"):
        return
    oid = user_org_id(user)
    org = await db.organizations.find_one({"org_id": oid}, {"_id": 0, "features": 1})
    if not org:
        return   # default org bootstrap safety
    enabled = ((org.get("features") or {}).get("modules") or {}).get(module_key)
    if enabled is False:
        label = MODULE_LABEL.get(module_key, module_key)
        raise HTTPException(
            status_code=403,
            detail=f"{label} is not enabled for this workspace. "
                   f"Contact the Platform Owner to enable it.",
        )
