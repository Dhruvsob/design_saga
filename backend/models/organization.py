"""Organization (Tenant) models — the top-level SaaS boundary.

A single Design Saga deployment can host many independent companies
(tenants). Each Organization has its own users, projects, vendors, etc.
Complete data isolation is enforced at the query layer via
`core.tenancy.tenant_filter()`.
"""
from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List, Literal


BusinessMode = Literal["consultancy", "turnkey", "hybrid"]


# ------------------------------------------------------------------
# Feature preset by business mode
# ------------------------------------------------------------------
CONSULTANCY_MODULES = {
    # Enabled for all modes
    "crm": True, "clients": True, "projects": True, "quotations": True,
    "employees": True, "attendance": True, "payroll": True,
    "accounting": True, "vendor_commissions": True, "tasks": True,
    "documents": True, "reports": True, "loans": True, "expenses": True,
    "invoices": True,
    # Disabled for consultancy-only workspaces
    "procurement": False, "purchase_orders": False, "inventory": False,
    "material_tracking": False, "vendor_billing": False,
    "labour_billing": False, "site_material": False, "project_costing": False,
}
TURNKEY_ONLY = {
    "procurement": True, "purchase_orders": True, "inventory": True,
    "material_tracking": True, "vendor_billing": True,
    "labour_billing": True, "site_material": True, "project_costing": True,
}


def features_for_mode(mode: str) -> dict:
    """Return the default `features.modules` dict for a given business mode."""
    modules = dict(CONSULTANCY_MODULES)
    if mode in ("turnkey", "hybrid"):
        modules.update(TURNKEY_ONLY)
    return modules


class OrgBranding(BaseModel):
    logo_url: Optional[str] = None
    favicon_url: Optional[str] = None
    primary_color: Optional[str] = "#002FA7"      # Klein Blue default
    accent_color: Optional[str] = "#0A0A0A"
    tagline: Optional[str] = None
    email_header: Optional[str] = None
    pdf_footer: Optional[str] = None


class OrgAddress(BaseModel):
    line1: Optional[str] = None
    line2: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = "India"
    pincode: Optional[str] = None


class OrgCreateIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    slug: Optional[str] = None                    # Auto-generated if omitted
    display_name: Optional[str] = None
    admin_email: EmailStr
    admin_name: str = Field(min_length=1, max_length=120)
    admin_password: str = Field(min_length=8, max_length=128)
    business_mode: BusinessMode = "hybrid"        # consultancy | turnkey | hybrid
    phone: Optional[str] = None
    website: Optional[str] = None
    gstin: Optional[str] = None
    pan: Optional[str] = None
    industry: Optional[str] = "Architecture & Interior Design"
    plan: Optional[str] = "starter"               # starter | pro | enterprise
    address: Optional[OrgAddress] = None
    branding: Optional[OrgBranding] = None
    notes: Optional[str] = None


class OrgUpdateIn(BaseModel):
    name: Optional[str] = None
    display_name: Optional[str] = None
    business_mode: Optional[BusinessMode] = None
    phone: Optional[str] = None
    website: Optional[str] = None
    gstin: Optional[str] = None
    pan: Optional[str] = None
    industry: Optional[str] = None
    plan: Optional[str] = None
    address: Optional[OrgAddress] = None
    branding: Optional[OrgBranding] = None
    features: Optional[dict] = None
    notes: Optional[str] = None


class OrgStatusIn(BaseModel):
    action: str                                    # activate | suspend | deactivate


class BrandingUpdateIn(BaseModel):
    """Company Admin can update these fields for their own org."""
    display_name: Optional[str] = None
    branding: Optional[OrgBranding] = None
    address: Optional[OrgAddress] = None
    phone: Optional[str] = None
    website: Optional[str] = None
    email: Optional[EmailStr] = None
    gstin: Optional[str] = None
    pan: Optional[str] = None
    invoice_prefix: Optional[str] = None
    quotation_prefix: Optional[str] = None
    bank_details: Optional[dict] = None            # {bank, account, ifsc, upi}
    signature_url: Optional[str] = None
    stamp_url: Optional[str] = None


DEFAULT_FEATURES = {
    "modules": features_for_mode("hybrid"),   # all modules enabled
    "limits": {
        "max_users": 500,
        "max_projects": 10000,
        "storage_mb": 5000,
    },
}
