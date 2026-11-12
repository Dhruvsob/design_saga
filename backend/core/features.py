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
    from .entitlements import for_org_id
    ent = await for_org_id(user_org_id(user))
    if not ent:
        return   # default org bootstrap safety
    if ent["modules"].get(module_key) is False:
        label = MODULE_LABEL.get(module_key, module_key)
        why = (f"is not included in the {ent['plan_name']} plan"
               if module_key in ent["plan_excluded"] else "is not enabled for this workspace")
        raise HTTPException(
            status_code=403,
            detail=f"{label} {why}. Contact the Platform Owner to enable it.",
        )
