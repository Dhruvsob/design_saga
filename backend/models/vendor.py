"""Vendor-domain models: bills, payments, ratings, documents.

Kept separate from `models/accounting.py` (which owns the core double-entry
primitives). Vendor master itself continues to live in `models/accounting.py`
as `VendorIn` to preserve backward compatibility with existing imports and
seeded data (`db.vendors_acc`).

All new schemas ship with an optional `org_id` — the app is single-org today
but every new document is written multi-tenant ready.
"""
from pydantic import Field, field_validator
from typing import List, Optional
from datetime import date

from core.url_security import external_http_url
from models.base import FiniteModel


AGENCY_TYPES = [
    "vendor", "agency", "contractor", "sub_contractor",
    "supplier", "consultant", "freelancer", "other",
]

VENDOR_BILL_STATUSES = ["draft", "received", "partially_paid", "paid", "overdue", "cancelled"]

COMMISSION_TYPES = ["fixed", "percentage", "slab", "category", "project", "none"]
COMMISSION_STATUSES = ["pending", "invoiced", "received", "cancelled"]


# ---------- Commission Config (embedded on vendor master) ----------
class CommissionSlab(FiniteModel):
    min_purchase: float = Field(default=0, ge=0)
    max_purchase: Optional[float] = Field(default=None, ge=0)  # None = open-ended top slab
    percentage: float = Field(default=0, ge=0, le=100)


class CommissionConfig(FiniteModel):
    applicable: bool = False
    type: str = "percentage"                   # from COMMISSION_TYPES
    percentage: Optional[float] = Field(default=0.0, ge=0, le=100)
    fixed_amount: Optional[float] = Field(default=0.0, ge=0)
    slabs: Optional[List[CommissionSlab]] = None
    min_purchase: Optional[float] = Field(default=0.0, ge=0)
    effective_from: Optional[str] = None       # YYYY-MM-DD
    effective_to: Optional[str] = None
    notes: Optional[str] = None
    # Default income category label — surfaces on generated JEs.
    income_label: Optional[str] = "Vendor Commission Income"


class CommissionReceiveIn(FiniteModel):
    amount: float = Field(gt=0)
    received_date: str                          # YYYY-MM-DD
    bank_account_id: str                        # cash/bank account credited
    payment_method: Optional[str] = "bank_transfer"
    reference: Optional[str] = None
    notes: Optional[str] = None
    commission_ids: Optional[List[str]] = None  # settle specific commission rows (FIFO if empty)


# ---------- Bills ----------

def _validate_attachments(value):
    if value is None:
        return value
    if len(value) > 50:
        raise ValueError("Too many attachments")
    out = []
    for item in value:
        if not isinstance(item, dict):
            raise ValueError("Invalid attachment")
        clean = {k: (str(item[k])[:300] if item.get(k) is not None else None)
                 for k in ("label", "type", "name") if k in item}
        if item.get("url"):
            clean["url"] = external_http_url(item["url"])
        out.append(clean)
    return out


class VendorBillItem(FiniteModel):
    po_line_id: Optional[str] = None
    description: str = Field(max_length=500)
    quantity: float = Field(default=1, ge=0)
    rate: float = Field(default=0, ge=0)
    amount: float = 0                          # server-computed = qty * rate


class VendorBillIn(FiniteModel):
    vendor_id: str
    bill_number: Optional[str] = None          # vendor's own invoice/bill number
    bill_date: str                              # YYYY-MM-DD
    due_date: Optional[str] = None
    project_id: Optional[str] = None
    po_id: Optional[str] = None
    expense_account_id: Optional[str] = None
    task_id: Optional[str] = None
    items: List[VendorBillItem] = Field(default_factory=list)
    tax_rate: Optional[float] = Field(default=0.0, ge=0, le=100)   # GST %
    tds_rate: Optional[float] = Field(default=0.0, ge=0, le=100)   # TDS %
    notes: Optional[str] = None
    attachments: Optional[List[dict]] = None   # [{label, url, type}]
    status: Optional[str] = "received"
    _validate_attachments = field_validator("attachments")(_validate_attachments)
    org_id: Optional[str] = Field(default=None, exclude=True)  # server-assigned; client value ignored

    @field_validator("bill_date", "due_date")
    @classmethod
    def validate_bill_dates(cls, value):
        if value in (None, ""):
            return value
        try:
            date.fromisoformat(value)
        except (TypeError, ValueError):
            raise ValueError("Date must be YYYY-MM-DD")
        return value


class VendorBillUpdate(FiniteModel):
    bill_number: Optional[str] = None
    bill_date: Optional[str] = None
    due_date: Optional[str] = None
    project_id: Optional[str] = None
    po_id: Optional[str] = None
    expense_account_id: Optional[str] = None
    task_id: Optional[str] = None
    items: Optional[List[VendorBillItem]] = None
    tax_rate: Optional[float] = Field(default=None, ge=0, le=100)
    tds_rate: Optional[float] = Field(default=None, ge=0, le=100)
    notes: Optional[str] = None
    attachments: Optional[List[dict]] = None
    status: Optional[str] = None
    _validate_attachments = field_validator("attachments")(_validate_attachments)

    @field_validator("bill_date", "due_date")
    @classmethod
    def validate_bill_dates(cls, value):
        if value in (None, ""):
            return value
        try:
            date.fromisoformat(value)
        except (TypeError, ValueError):
            raise ValueError("Date must be YYYY-MM-DD")
        return value


# ---------- Payments ----------
class VendorPaymentIn(FiniteModel):
    vendor_id: str
    amount: float = Field(gt=0)
    payment_date: str                          # YYYY-MM-DD
    paid_from_account_id: str                  # which cash/bank account
    payment_method: Optional[str] = "bank_transfer"
    project_id: Optional[str] = None
    bill_ids: Optional[List[str]] = None       # settle these bills (FIFO if omitted)
    reference: Optional[str] = None
    notes: Optional[str] = None
    org_id: Optional[str] = Field(default=None, exclude=True)  # server-assigned; client value ignored


# ---------- Rating ----------
class VendorRatingIn(FiniteModel):
    project_id: Optional[str] = None
    task_id: Optional[str] = None
    quality: Optional[float] = Field(default=None, ge=0, le=5)
    timeliness: Optional[float] = Field(default=None, ge=0, le=5)
    cost: Optional[float] = Field(default=None, ge=0, le=5)
    communication: Optional[float] = Field(default=None, ge=0, le=5)
    comment: Optional[str] = None


# ---------- Documents (attachments on vendor master) ----------
class VendorDocumentIn(FiniteModel):
    label: str
    url: str
    kind: Optional[str] = None                 # gst_certificate | pan | agreement | insurance | other
    expires_on: Optional[str] = None           # YYYY-MM-DD

    _validate_url = field_validator("url")(external_http_url)


# ---------- Update (partial edit of vendor master) ----------
class VendorUpdate(FiniteModel):
    name: Optional[str] = None
    company: Optional[str] = None
    agency_type: Optional[str] = None
    contact_person: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    pincode: Optional[str] = None
    gstin: Optional[str] = None
    pan: Optional[str] = None
    tds_applicable: Optional[bool] = None
    tds_rate: Optional[float] = None
    bank_name: Optional[str] = None
    bank_account_number: Optional[str] = None
    bank_ifsc: Optional[str] = None
    bank_branch: Optional[str] = None
    upi_id: Optional[str] = None
    category: Optional[str] = None
    tags: Optional[List[str]] = None
    active: Optional[bool] = None
    notes: Optional[str] = None
