"""Vendor-domain models: bills, payments, ratings, documents.

Kept separate from `models/accounting.py` (which owns the core double-entry
primitives). Vendor master itself continues to live in `models/accounting.py`
as `VendorIn` to preserve backward compatibility with existing imports and
seeded data (`db.vendors_acc`).

All new schemas ship with an optional `org_id` — the app is single-org today
but every new document is written multi-tenant ready.
"""
from pydantic import BaseModel, Field
from typing import List, Optional


AGENCY_TYPES = [
    "vendor", "agency", "contractor", "sub_contractor",
    "supplier", "consultant", "freelancer", "other",
]

VENDOR_BILL_STATUSES = ["draft", "received", "partially_paid", "paid", "overdue", "cancelled"]


# ---------- Bills ----------
class VendorBillItem(BaseModel):
    description: str
    quantity: float = 1
    rate: float = 0
    amount: float = 0                          # server-computed = qty * rate


class VendorBillIn(BaseModel):
    vendor_id: str
    bill_number: Optional[str] = None          # vendor's own invoice/bill number
    bill_date: str                              # YYYY-MM-DD
    due_date: Optional[str] = None
    project_id: Optional[str] = None
    task_id: Optional[str] = None
    items: List[VendorBillItem] = []
    tax_rate: Optional[float] = 0.0            # GST %
    tds_rate: Optional[float] = 0.0            # TDS %
    notes: Optional[str] = None
    attachments: Optional[List[dict]] = None   # [{label, url, type}]
    status: Optional[str] = "received"
    org_id: Optional[str] = None


class VendorBillUpdate(BaseModel):
    bill_number: Optional[str] = None
    bill_date: Optional[str] = None
    due_date: Optional[str] = None
    project_id: Optional[str] = None
    task_id: Optional[str] = None
    items: Optional[List[VendorBillItem]] = None
    tax_rate: Optional[float] = None
    tds_rate: Optional[float] = None
    notes: Optional[str] = None
    attachments: Optional[List[dict]] = None
    status: Optional[str] = None


# ---------- Payments ----------
class VendorPaymentIn(BaseModel):
    vendor_id: str
    amount: float
    payment_date: str                          # YYYY-MM-DD
    paid_from_account_id: str                  # which cash/bank account
    payment_method: Optional[str] = "bank_transfer"
    project_id: Optional[str] = None
    bill_ids: Optional[List[str]] = None       # settle these bills (FIFO if omitted)
    reference: Optional[str] = None
    notes: Optional[str] = None
    org_id: Optional[str] = None


# ---------- Rating ----------
class VendorRatingIn(BaseModel):
    project_id: Optional[str] = None
    task_id: Optional[str] = None
    quality: Optional[float] = Field(default=None, ge=0, le=5)
    timeliness: Optional[float] = Field(default=None, ge=0, le=5)
    cost: Optional[float] = Field(default=None, ge=0, le=5)
    communication: Optional[float] = Field(default=None, ge=0, le=5)
    comment: Optional[str] = None


# ---------- Documents (attachments on vendor master) ----------
class VendorDocumentIn(BaseModel):
    label: str
    url: str
    kind: Optional[str] = None                 # gst_certificate | pan | agreement | insurance | other
    expires_on: Optional[str] = None           # YYYY-MM-DD


# ---------- Update (partial edit of vendor master) ----------
class VendorUpdate(BaseModel):
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
