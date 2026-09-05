"""Accounting models — double-entry compatible."""
from pydantic import BaseModel
from typing import List, Optional


ACCOUNT_TYPES = ["asset", "liability", "income", "expense", "equity"]

# Default Chart of Accounts (seeded on first-use per company)
DEFAULT_COA = [
    # Assets
    ("Cash", "asset", "1001"), ("Petty Cash", "asset", "1002"),
    ("Bank - Primary", "asset", "1101"), ("Fixed Assets", "asset", "1201"),
    ("Accounts Receivable", "asset", "1301"), ("Security Deposits", "asset", "1401"),
    # Liabilities
    ("Accounts Payable", "liability", "2001"), ("GST Payable", "liability", "2101"),
    ("TDS Payable", "liability", "2102"), ("Loans", "liability", "2201"),
    ("Employee Payables", "liability", "2301"),
    # Income
    ("Consultancy Income", "income", "3001"), ("Design Fees", "income", "3002"),
    ("Site Supervision Fees", "income", "3003"), ("Project Revenue", "income", "3004"),
    ("Interior Revenue", "income", "3005"),
    ("Vendor Commission Income", "income", "3010"),
    ("Referral Income", "income", "3011"),
    ("Incentive Income", "income", "3012"),
    ("Other Income", "income", "3099"),
    # Expenses
    ("Employee Salary", "expense", "4001"), ("Office Rent", "expense", "4002"),
    ("Electricity", "expense", "4003"), ("Internet", "expense", "4004"),
    ("Fuel", "expense", "4005"), ("Stationery", "expense", "4006"),
    ("Marketing", "expense", "4007"), ("Software Subscriptions", "expense", "4008"),
    ("Travel", "expense", "4009"), ("Food & Refreshments", "expense", "4010"),
    ("Office Maintenance", "expense", "4011"), ("Printing", "expense", "4012"),
    ("Courier", "expense", "4013"), ("Professional Fees", "expense", "4014"),
    ("Legal Fees", "expense", "4015"), ("CA Fees", "expense", "4016"),
    ("Miscellaneous Expenses", "expense", "4099"),
    # Equity
    ("Owner Capital", "equity", "5001"), ("Owner Drawings", "equity", "5002"),
    ("Retained Earnings", "equity", "5003"),
    ("Opening Balance Adjustment", "equity", "5099"),
]


PAYMENT_METHODS = ["cash", "bank_transfer", "upi", "cheque", "credit_card", "online", "other"]


class AccountIn(BaseModel):
    name: str
    type: str                                 # from ACCOUNT_TYPES
    code: Optional[str] = None
    parent_id: Optional[str] = None
    is_bank: Optional[bool] = False
    opening_balance: Optional[float] = 0.0
    active: Optional[bool] = True
    notes: Optional[str] = None


class JournalLine(BaseModel):
    account_id: str
    debit: Optional[float] = 0.0
    credit: Optional[float] = 0.0
    description: Optional[str] = None


class JournalIn(BaseModel):
    date: str                                # YYYY-MM-DD
    narration: str
    reference: Optional[str] = None
    project_id: Optional[str] = None
    client_id: Optional[str] = None
    vendor_id: Optional[str] = None
    employee_id: Optional[str] = None
    lines: List[JournalLine]


class IncomeIn(BaseModel):
    """Simple income entry (payment received). Auto-creates a journal entry."""
    date: str
    amount: float
    client_id: Optional[str] = None
    project_id: Optional[str] = None
    vendor_id: Optional[str] = None
    employee_id: Optional[str] = None
    income_account_id: str                    # which income account
    bank_account_id: str                      # cash / bank Rx into
    payment_method: Optional[str] = "bank_transfer"
    reference: Optional[str] = None
    invoice_id: Optional[str] = None
    milestone_id: Optional[str] = None
    notes: Optional[str] = None


class ExpenseIn(BaseModel):
    date: str
    amount: float
    expense_account_id: str
    paid_from_account_id: str                 # cash / bank Rx out
    vendor_id: Optional[str] = None
    project_id: Optional[str] = None
    client_id: Optional[str] = None
    employee_id: Optional[str] = None
    payment_method: Optional[str] = "bank_transfer"
    gst: Optional[float] = 0.0
    reference: Optional[str] = None
    bill_url: Optional[str] = None
    notes: Optional[str] = None


class MilestoneIn(BaseModel):
    project_id: str
    name: str
    percent: Optional[float] = None
    amount: Optional[float] = None
    due_date: Optional[str] = None
    notes: Optional[str] = None


class MilestoneUpdate(BaseModel):
    name: Optional[str] = None
    percent: Optional[float] = None
    amount: Optional[float] = None
    due_date: Optional[str] = None
    notes: Optional[str] = None
    status: Optional[str] = None              # pending | invoiced | paid


class VendorIn(BaseModel):
    # Identity
    name: str
    company: Optional[str] = None
    agency_type: Optional[str] = None         # agency|vendor|contractor|sub_contractor|supplier|consultant|other
    contact_person: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    pincode: Optional[str] = None
    # Compliance
    gstin: Optional[str] = None
    pan: Optional[str] = None
    tds_applicable: Optional[bool] = False
    tds_rate: Optional[float] = 0.0
    # Banking
    bank_name: Optional[str] = None
    bank_account_number: Optional[str] = None
    bank_ifsc: Optional[str] = None
    bank_branch: Optional[str] = None
    upi_id: Optional[str] = None
    # Categorisation & taxonomy
    category: Optional[str] = None            # e.g. Carpenter, Electrician, Marble, Lighting…
    tags: Optional[List[str]] = None
    # Meta
    rating: Optional[float] = 0.0             # aggregate 0-5
    active: Optional[bool] = True
    notes: Optional[str] = None
    # Multi-tenant ready (not enforced yet — see PRD)
    org_id: Optional[str] = None
