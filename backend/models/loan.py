"""Loan / EMI models — enterprise amortization support."""
from pydantic import Field
from typing import Optional, List, Literal
from models.base import FiniteModel


class LoanCreateIn(FiniteModel):
    lender_name: str = Field(min_length=1, max_length=120)
    lender_contact: Optional[str] = None
    loan_type: Literal["business", "term", "personal", "equipment", "other"] = "business"
    principal: float = Field(gt=0)
    interest_rate_pa: float = Field(ge=0, le=100)          # annual %
    tenure_months: int = Field(gt=0, le=600)
    start_date: str                                         # ISO YYYY-MM-DD
    emi_day: Optional[int] = Field(default=None, ge=1, le=31)  # day-of-month
    disbursement_account_id: str                            # Bank/Cash (asset)
    interest_expense_account_id: Optional[str] = None       # defaults to auto "Interest Expense"
    loan_account_id: Optional[str] = None                   # if empty, auto-create liability
    account_number: Optional[str] = None
    reference: Optional[str] = None
    notes: Optional[str] = None


class LoanUpdateIn(FiniteModel):
    lender_contact: Optional[str] = None
    account_number: Optional[str] = None
    reference: Optional[str] = None
    notes: Optional[str] = None
    emi_day: Optional[int] = None


class PayEMIIn(FiniteModel):
    schedule_index: int                                     # 0-based row in schedule
    paid_from_account_id: str                               # bank/cash
    paid_on: Optional[str] = None                           # ISO date, default today
    extra_principal: Optional[float] = Field(default=0, ge=0)  # partial prepayment
    reference: Optional[str] = None
    notes: Optional[str] = None


class PrepayIn(FiniteModel):
    amount: float = Field(gt=0)
    paid_from_account_id: str
    paid_on: Optional[str] = None
    notes: Optional[str] = None
