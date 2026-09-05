"""Purchase Order + Goods Receipt Note (GRN) models.

Flow
----
1. PO created & sent to vendor (status: sent).
2. Goods arrive → GRN records the actual delivered qty.
3. Vendor sends bill → link bill.po_id → app auto 3-way matches
   (PO qty, GRN qty, Bill qty/amount) and flags variances.
"""
from pydantic import BaseModel, Field
from typing import Optional, List, Literal


class POLineIn(BaseModel):
    item_name: str
    description: Optional[str] = None
    quantity: float = Field(gt=0)
    unit: Optional[str] = "nos"
    unit_price: float = Field(ge=0)
    tax_rate: float = Field(default=0, ge=0, le=100)


class POCreateIn(BaseModel):
    vendor_id: str
    project_id: Optional[str] = None
    order_date: Optional[str] = None                   # ISO date, default today
    expected_delivery: Optional[str] = None
    delivery_address: Optional[str] = None
    payment_terms: Optional[str] = "Net 30"
    lines: List[POLineIn] = Field(min_length=1)
    notes: Optional[str] = None
    reference: Optional[str] = None


class POUpdateIn(BaseModel):
    expected_delivery: Optional[str] = None
    delivery_address: Optional[str] = None
    payment_terms: Optional[str] = None
    notes: Optional[str] = None
    lines: Optional[List[POLineIn]] = None
    status: Optional[Literal["draft", "sent", "partial", "received", "closed", "cancelled"]] = None


class GRNLineIn(BaseModel):
    po_line_id: str
    received_qty: float = Field(ge=0)
    rejected_qty: Optional[float] = 0
    remarks: Optional[str] = None


class GRNCreateIn(BaseModel):
    po_id: str
    received_date: Optional[str] = None
    received_by: Optional[str] = None
    inventory_account_id: Optional[str] = None         # if empty, auto-create/select "Inventory"
    lines: List[GRNLineIn] = Field(min_length=1)
    delivery_challan_no: Optional[str] = None
    notes: Optional[str] = None
