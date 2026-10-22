"""Expense claim / approval models."""
from pydantic import Field, field_validator
from typing import Optional, List, Literal

from core.url_security import external_http_url
from models.base import FiniteModel


class ExpenseLineIn(FiniteModel):
    category: str                          # travel|meals|materials|utilities|site|office|other
    description: Optional[str] = None
    amount: float = Field(gt=0)
    date: Optional[str] = None
    receipt_url: Optional[str] = None
    tax_rate: Optional[float] = Field(default=0, ge=0, le=100)

    @field_validator("receipt_url")
    @classmethod
    def validate_receipt_url(cls, value):
        return external_http_url(value) if value is not None else None


class ExpenseCreateIn(FiniteModel):
    title: str = Field(min_length=1, max_length=200)
    lines: List[ExpenseLineIn] = Field(min_length=1)
    project_id: Optional[str] = None
    vendor_id: Optional[str] = None
    payment_mode: Optional[Literal["cash", "personal", "corporate_card", "bank_transfer"]] = "personal"
    reimburse_to_account_id: Optional[str] = None   # bank/cash account to reimburse from
    notes: Optional[str] = None


class ApprovalDecisionIn(FiniteModel):
    decision: Literal["approve", "reject"]
    comment: Optional[str] = None


class ReimburseIn(FiniteModel):
    paid_from_account_id: str                       # bank/cash
    paid_on: Optional[str] = None
    reference: Optional[str] = None
    notes: Optional[str] = None


class ExpensePolicyIn(FiniteModel):
    """Org-level rules — set once by Company Admin."""
    auto_approve_below: float = Field(default=0, ge=0)      # 0 = never auto approve
    l1_approver_role: Literal["ProjectManager", "Director", "Admin", "Accountant", "HR"] = "ProjectManager"
    l2_approver_role: Optional[Literal["Director", "Admin", "Accountant"]] = "Director"
    l1_threshold: float = Field(default=5000, ge=0)         # amount above this needs L1
    l2_threshold: float = Field(default=25000, ge=0)        # amount above this also needs L2
    require_receipt_above: float = Field(default=1000, ge=0)
    allowed_categories: Optional[List[str]] = None
