"""Attendance & Leave models — feeds Payroll."""
from pydantic import BaseModel
from typing import List, Optional


ATTENDANCE_STATUSES = ["present", "absent", "half_day", "leave", "holiday", "week_off"]
LEAVE_TYPES = ["casual", "sick", "earned", "unpaid", "comp_off", "maternity", "paternity"]
LEAVE_STATUSES = ["pending", "approved", "rejected", "cancelled"]

# Default annual leave allowance per type (used when creating an Employee LeaveBalance)
DEFAULT_LEAVE_ALLOWANCE = {
    "casual": 12,
    "sick": 12,
    "earned": 18,
    "comp_off": 0,
    "maternity": 90,
    "paternity": 15,
    "unpaid": 0,
}


class CheckInIn(BaseModel):
    employee_id: Optional[str] = None       # falls back to current user's employee mapping
    location: Optional[str] = ""
    notes: Optional[str] = ""


class CheckOutIn(BaseModel):
    employee_id: Optional[str] = None
    notes: Optional[str] = ""


class AttendanceOverrideIn(BaseModel):
    """Admin/HR override for a specific date (mark leave, half-day, etc.)."""
    employee_id: str
    date: str                                # YYYY-MM-DD
    status: str                              # from ATTENDANCE_STATUSES
    leave_type: Optional[str] = None
    notes: Optional[str] = ""


class LeaveRequestIn(BaseModel):
    employee_id: Optional[str] = None
    leave_type: str
    from_date: str
    to_date: str
    reason: Optional[str] = ""


class LeaveActionIn(BaseModel):
    action: str                              # approve | reject
    remarks: Optional[str] = ""


class LeaveRuleIn(BaseModel):
    """Configure per-org leave allowances (falls back to defaults)."""
    allowances: dict                         # {"casual": 12, "sick": 10, ...}
    working_days_per_week: Optional[int] = 6
    week_off_days: Optional[List[int]] = None  # 0=Mon .. 6=Sun (default [6] Sunday)
