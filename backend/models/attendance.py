"""Attendance & Leave models — feeds Payroll."""
from pydantic import BaseModel, Field, field_validator
from typing import List, Literal, Optional
import re


ATTENDANCE_STATUSES = ["present", "late", "absent", "half_day", "leave", "holiday", "week_off", "pending_approval"]
LEAVE_TYPES = ["casual", "sick", "earned", "unpaid", "comp_off", "maternity", "paternity"]
LEAVE_STATUSES = ["pending", "approved", "rejected", "cancelled"]
_HHMM = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")


def _valid_hhmm(value: Optional[str]) -> Optional[str]:
    if value is not None and not _HHMM.fullmatch(value):
        raise ValueError("Time must be HH:MM in 24-hour format")
    return value

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
    # Site-visit fields (all optional — office check-in remains default)
    attendance_type: Literal["office", "site_visit", "client_meeting", "warehouse", "vendor_visit"] = "office"
    project_id: Optional[str] = Field(default=None, max_length=120)
    site_location: Optional[str] = Field(default=None, max_length=500)
    expected_time: Optional[str] = None
    reason: Optional[str] = Field(default=None, max_length=1000)
    # Late-arrival explanation captured at the moment of check-in
    late_reason: Optional[str] = None
    late_category: Optional[str] = None       # from policy.late_reason_categories
    # NEW — Geo-fencing (GPS)
    lat: Optional[float] = Field(default=None, ge=-90, le=90)
    lng: Optional[float] = Field(default=None, ge=-180, le=180)
    accuracy_m: Optional[float] = Field(default=None, ge=0, le=100000)
    force_outside: Optional[bool] = False    # Request approval anyway when outside
    # Device fingerprint (browser-side) for audit / fraud triage
    device_id: Optional[str] = None
    device_label: Optional[str] = None       # user-friendly label e.g. "Rahul's Chrome / Windows"
    user_agent: Optional[str] = None

    @field_validator("expected_time")
    @classmethod
    def _expected_time(cls, value):
        return _valid_hhmm(value)


class GeoLocationIn(BaseModel):
    """A named geo-fenced location the org has authorized for check-in."""
    name: str = Field(min_length=1, max_length=120)
    kind: Literal["office", "site", "warehouse", "client", "vendor"]
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)
    radius_m: int = Field(default=150, ge=10, le=5000)
    project_id: Optional[str] = None         # tie a site fence to a project
    address: Optional[str] = None
    is_active: Optional[bool] = True


class AttendancePolicyIn(BaseModel):
    """Company-level attendance policy (one per org)."""
    office_start: str = "10:00"              # HH:MM
    office_end: str = "19:00"
    grace_minutes: int = Field(default=15, ge=0, le=240)
    half_day_min_hours: float = Field(default=4.0, ge=0, le=24)
    full_day_min_hours: float = Field(default=8.0, ge=0, le=24)
    weekly_off_days: List[int] = [6]         # 0=Mon..6=Sun (default Sunday)
    holidays: List[dict] = []                # legacy inline holidays — new module lives in /api/holidays
    geo_fencing_enabled: bool = True
    require_geo_for_office: bool = True      # office check-in also requires geo?
    approval_required_when_outside: bool = True
    default_office_lat: Optional[float] = Field(default=None, ge=-90, le=90)
    default_office_lng: Optional[float] = Field(default=None, ge=-180, le=180)
    default_office_radius_m: Optional[int] = Field(default=150, ge=10, le=5000)
    # GPS accuracy — reject check-ins whose reported accuracy is worse than this
    # (larger radius = less accurate). Prevents cellular-tower fixes from
    # passing a 150-m office fence.
    max_gps_accuracy_m: Optional[float] = Field(default=100.0, gt=0, le=5000)
    require_late_reason: bool = True         # if late > grace, force a reason field
    # --- Late fine system (ported from Jewellers ERP) ---
    # Flat Rs. fine per late arrival; approving a late arrival WAIVES its fine.
    # A late arrival is never auto-converted to a half-day.
    late_fine_enabled: bool = True
    late_fine_amount: float = 100.0           # Rs. per late occurrence
    late_fine_daily_cap: float = 500.0        # 0 = no daily cap
    late_reason_categories: List[str] = [
        "traffic", "public_transport", "vehicle_breakdown",
        "medical", "family_emergency", "weather", "personal", "other",
    ]
    # Legacy penalty when the fine system is OFF and a late arrival is REJECTED
    late_rejection_penalty: str = "half_day"  # half_day | full_day | none

    @field_validator("office_start", "office_end")
    @classmethod
    def _policy_time(cls, value):
        return _valid_hhmm(value)

    @field_validator("weekly_off_days")
    @classmethod
    def _weekly_days(cls, value):
        if any(day < 0 or day > 6 for day in value):
            raise ValueError("Weekly-off days must be between 0 and 6")
        return sorted(set(value))


class CheckOutIn(BaseModel):
    employee_id: Optional[str] = None
    notes: Optional[str] = ""


class ApproveAttendanceIn(BaseModel):
    action: str                              # approve | reject
    remarks: Optional[str] = ""


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
    reason: Optional[str] = Field(default="", max_length=2000)


class LeaveActionIn(BaseModel):
    action: str                              # approve | reject
    remarks: Optional[str] = ""


class LeaveRuleIn(BaseModel):
    """Configure per-org leave allowances (falls back to defaults)."""
    allowances: dict                         # {"casual": 12, "sick": 10, ...}
    working_days_per_week: Optional[int] = 6
    week_off_days: Optional[List[int]] = None  # 0=Mon .. 6=Sun (default [6] Sunday)


# ==================================================
# Jewellers ERP ported models
# ==================================================
class ManualAttendanceIn(BaseModel):
    """Admin manually records/overrides a full attendance row for a date."""
    employee_id: str
    date: str                                # YYYY-MM-DD
    status: str                              # from ATTENDANCE_STATUSES
    check_in: Optional[str] = None           # ISO datetime
    check_out: Optional[str] = None
    late_reason: Optional[str] = None
    short_leave_hours: Optional[float] = 0
    notes: Optional[str] = None


class ShortLeaveIn(BaseModel):
    """Short / hourly leave — salary deducts hourly-rate x hours."""
    employee_id: str
    date: str                                # YYYY-MM-DD
    hours: float                             # > 0, <= 12
    reason: Optional[str] = None


class CorrectionIn(BaseModel):
    """Employee requests a fix for a missed / wrong punch."""
    employee_id: Optional[str] = None        # admins may raise for others
    date: str                                # YYYY-MM-DD
    requested_check_in: Optional[str] = None  # ISO datetime
    requested_check_out: Optional[str] = None
    reason: str = Field(min_length=1, max_length=2000)


class CorrectionReviewIn(BaseModel):
    status: str                              # approved | rejected
    review_notes: Optional[str] = None


class LateReviewIn(BaseModel):
    """Approve (waives fine) or reject (keeps fine) a late arrival."""
    status: str                              # approved | rejected
    review_notes: Optional[str] = None


class EmployeeAttendanceConfigIn(BaseModel):
    """Per-employee shift + payroll config (Jewellers 'Employee Setup')."""
    shift_start: Optional[str] = None        # "09:30"
    shift_end: Optional[str] = None
    grace_minutes: Optional[int] = Field(default=None, ge=0, le=240)
    weekly_offs: Optional[List[int]] = None  # [0..6], 0=Mon; None = use org policy
    half_day_min_minutes: Optional[int] = Field(default=None, ge=0, le=1440)
    full_day_min_minutes: Optional[int] = Field(default=None, ge=0, le=1440)
    monthly_salary: Optional[float] = Field(default=None, ge=0)
    payroll_basis_days: Optional[int] = Field(default=None, ge=1, le=366)

    @field_validator("shift_start", "shift_end")
    @classmethod
    def _shift_time(cls, value):
        return _valid_hhmm(value)

    @field_validator("weekly_offs")
    @classmethod
    def _employee_weekly_days(cls, value):
        if value is not None and any(day < 0 or day > 6 for day in value):
            raise ValueError("Weekly-off days must be between 0 and 6")
        return sorted(set(value)) if value is not None else value
