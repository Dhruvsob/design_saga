"""Attendance + Leave routes.

- Employees: `POST /attendance/check-in`, `/check-out`, `GET /attendance/me/summary`
- HR/Admin: monthly sheet, override, leave approval, leave rule config
- Data shape kept payroll-friendly: `attendance` docs keyed by (employee_id, date).
"""
from fastapi import APIRouter, HTTPException, Request, Cookie, Header
from typing import Optional
from datetime import date as _date, datetime, timezone, timedelta

from core.db import db
from core.scoped_db import sdb
from core.helpers import now_utc, iso_now, new_id
from core.deps import require_user
from core.rbac import has_permission, has_any_permission
from core.access_control import merge_query, project_visibility_query
from models.attendance import (
    CheckInIn, CheckOutIn, AttendanceOverrideIn,
    LeaveRequestIn, LeaveActionIn, LeaveRuleIn, ApproveAttendanceIn,
    GeoLocationIn, AttendancePolicyIn,
    ManualAttendanceIn, ShortLeaveIn, CorrectionIn, CorrectionReviewIn,
    LateReviewIn, EmployeeAttendanceConfigIn,
    ATTENDANCE_STATUSES, LEAVE_TYPES, LEAVE_STATUSES, DEFAULT_LEAVE_ALLOWANCE,
)
from core import attendance_engine as engine
from core.audit import audit
from core.tenancy import user_org_id
from core.notifications import emit, emit_admins
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError
import math

router = APIRouter()


# ==================================================
# Attendance Policy
# ==================================================
DEFAULT_POLICY = {
    "office_start": "10:00",
    "office_end": "19:00",
    "grace_minutes": 15,
    "half_day_min_hours": 4.0,
    "full_day_min_hours": 8.0,
    "weekly_off_days": [6],
    "holidays": [],
    "geo_fencing_enabled": True,
    "require_geo_for_office": True,
    "approval_required_when_outside": True,
    "default_office_lat": None,
    "default_office_lng": None,
    "default_office_radius_m": 150,
    "max_gps_accuracy_m": 100.0,
    "require_late_reason": True,
    # --- Late fine system (Jewellers ERP logic) ---
    "late_fine_enabled": True,
    "late_fine_amount": 100.0,
    "late_fine_daily_cap": 500.0,
    "late_reason_categories": [
        "traffic", "public_transport", "vehicle_breakdown",
        "medical", "family_emergency", "weather", "personal", "other",
    ],
    "late_rejection_penalty": "half_day",
}

# How much of the device's reported GPS uncertainty we forgive when deciding if
# a user is inside a fence. Indoors, accurate fixes still drift 30-80m, which
# wrongly pushed in-office staff "outside" a 150m fence. Capped so a genuinely
# remote location (home is typically >1km away) can never sneak in.
GPS_TOLERANCE_CAP_M = 75.0
REVIEW_CLAIM_TTL_MINUTES = 10


def _initial_attendance_state(att_type: str, geo_needed: bool,
                              geo_result: dict, force_outside: bool) -> tuple[str, str]:
    """Choose the initial status without weakening out-of-fence approval."""
    if geo_needed and not geo_result.get("inside", False) and force_outside:
        return "pending_approval", "pending"
    if att_type == "office":
        return "present", "auto"
    if geo_needed and geo_result.get("inside") and geo_result.get("matched_location"):
        return "present", "auto"
    return "pending_approval", "pending"


def _parse_correction_datetime(value: str, label: str) -> datetime:
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        raise HTTPException(400, f"Corrected {label} must be a valid ISO datetime")
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=engine.IST)
    return dt


def _validate_correction_request(date_str: str, check_in: Optional[str],
                                 check_out: Optional[str]) -> None:
    """Reject malformed or cross-day correction timestamps."""
    try:
        requested_date = _date.fromisoformat(date_str)
    except (TypeError, ValueError):
        raise HTTPException(400, "date must be YYYY-MM-DD")
    if not check_in and not check_out:
        raise HTTPException(400, "At least one corrected punch time is required")

    parsed = []
    for label, value in (("check-in", check_in), ("check-out", check_out)):
        if not value:
            parsed.append(None)
            continue
        dt = _parse_correction_datetime(value, label)
        if dt.astimezone(engine.IST).date() != requested_date:
            raise HTTPException(400, f"Corrected {label} must be on {date_str}")
        parsed.append(dt)
    if parsed[0] and parsed[1] and parsed[1] <= parsed[0]:
        raise HTTPException(400, "Corrected check-out must be after check-in")


def _attendance_allows_leave(existing: Optional[dict]) -> bool:
    return not existing or (
        not existing.get("check_in")
        and existing.get("status") in (None, "absent", "leave")
    )


def _retryable_rejected_punch(existing: Optional[dict]) -> bool:
    return bool(
        existing
        and existing.get("approval_status") == "rejected"
        and existing.get("status") == "absent"
    )


def _weekly_off_days(employee: Optional[dict], policy: dict) -> list[int]:
    configured = (employee or {}).get("weekly_offs")
    return configured if configured is not None else (policy.get("weekly_off_days") or [6])


def _validate_manual_attendance(date_str: str, check_in: Optional[str],
                                check_out: Optional[str]) -> None:
    try:
        requested_date = _date.fromisoformat(date_str)
    except (TypeError, ValueError):
        raise HTTPException(400, "date must be YYYY-MM-DD")
    if check_out and not check_in:
        raise HTTPException(400, "Manual check-out requires a check-in")
    parsed = []
    for label, value in (("check-in", check_in), ("check-out", check_out)):
        if not value:
            parsed.append(None)
            continue
        dt = _parse_correction_datetime(value, label)
        if dt.astimezone(engine.IST).date() != requested_date:
            raise HTTPException(400, f"Manual {label} must be on {date_str}")
        parsed.append(dt)
    if parsed[0] and parsed[1] and parsed[1] <= parsed[0]:
        raise HTTPException(400, "Manual check-out must be after check-in")


def _without_compensation(summary: dict) -> dict:
    """Return attendance detail without compensation amounts."""
    hidden = {
        "salary_configured", "late_fine", "hourly_rate",
        "short_leave_deduction", "per_day_rate", "lop_deduction",
        "deduction", "net_payable",
    }
    safe = {k: v for k, v in summary.items() if k not in hidden}
    if isinstance(safe.get("employee"), dict):
        safe["employee"] = {
            k: v for k, v in safe["employee"].items() if k != "monthly_salary"
        }
    return safe


async def _claim_pending_review(collection, record_id: str) -> tuple[dict, str]:
    """Atomically claim a pending review; stale claims can be recovered."""
    token = new_id("review_")
    started = iso_now()
    stale_before = (now_utc() - timedelta(minutes=REVIEW_CLAIM_TTL_MINUTES)).isoformat()
    row = await collection.find_one_and_update(
        {
            "id": record_id,
            "status": "pending",
            "$or": [
                {"review_token": {"$exists": False}},
                {"review_started_at": {"$lt": stale_before}},
            ],
        },
        {"$set": {"review_token": token, "review_started_at": started}},
        return_document=ReturnDocument.AFTER,
    )
    if row:
        row.pop("_id", None)
        return row, token
    current = await collection.find_one({"id": record_id}, {"_id": 0})
    if not current:
        raise HTTPException(404, "Review record not found")
    if current.get("status") != "pending":
        raise HTTPException(400, f"Record already {current.get('status')}")
    raise HTTPException(409, "This record is already being reviewed")


async def _release_review_claim(collection, record_id: str, token: str) -> None:
    await collection.update_one(
        {"id": record_id, "status": "pending", "review_token": token},
        {"$unset": {"review_token": "", "review_started_at": ""}},
    )


async def _get_attendance_policy() -> dict:
    p = await sdb.attendance_policies.find_one({}, {"_id": 0})
    return {**DEFAULT_POLICY, **(p or {})}


async def _is_holiday(date_str: str):
    """Return (is_holiday, holiday_row_or_none).

    Considers both exact-date holidays and recurring holidays (same MM-DD).
    """
    try:
        d = _date.fromisoformat(date_str)
    except Exception:
        return False, None
    exact = await sdb.holidays.find_one(
        {"date": date_str, "active": True}, {"_id": 0}
    )
    if exact:
        return True, exact
    async for r in sdb.holidays.find({"recurring": True, "active": True}, {"_id": 0}):
        try:
            hd = _date.fromisoformat(r["date"])
        except Exception:
            continue
        if hd.month == d.month and hd.day == d.day:
            return True, r
    return False, None


@router.get("/attendance/policy")
async def get_att_policy(request: Request,
                         session_token: Optional[str] = Cookie(default=None),
                         authorization: Optional[str] = Header(default=None)):
    await require_user(request, session_token, authorization)
    return await _get_attendance_policy()


@router.put("/attendance/policy")
async def update_att_policy(payload: AttendancePolicyIn, request: Request,
                            session_token: Optional[str] = Cookie(default=None),
                            authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    if not has_any_permission(user, "*.*", "attendance.update"):
        raise HTTPException(403, "Admin only")
    up = payload.dict()
    up["updated_at"] = iso_now()
    up["updated_by"] = user["user_id"]
    up["org_id"] = user_org_id(user)
    await sdb.attendance_policies.update_one({}, {"$set": up}, upsert=True)
    await audit(user, "attendance_policy.update", target="policy", target_type="policy",
                meta={"office_start": up.get("office_start"),
                      "office_end": up.get("office_end")})
    return await _get_attendance_policy()


# ==================================================
# Geo-fenced Locations
# ==================================================
def _is_site_supervisor_employee(employee: Optional[dict]) -> bool:
    if not employee:
        return False
    designation = str(employee.get("designation") or "").strip().lower()
    department = str(employee.get("department") or "").strip().lower()
    return (
        "site supervisor" in designation
        or designation == "supervisor"
        or department in {"site execution", "site supervision"}
    )


async def _attendance_can_choose_any_project(user: dict) -> bool:
    if _can_manage_attendance(user):
        return True
    links = [{"user_id": user["user_id"]}]
    if user.get("email"):
        links.append({"email": user["email"]})
    employee = await sdb.employees.find_one(
        {"$or": links}, {"_id": 0, "designation": 1, "department": 1},
    )
    return _is_site_supervisor_employee(employee)


async def _attendance_project_query(user: dict) -> dict:
    """Projects a user may safely reference from an attendance punch."""
    active = {"archived": {"$ne": True}}
    if await _attendance_can_choose_any_project(user):
        return active

    visibility = await project_visibility_query(user)
    if not visibility:
        return active

    site_project_ids = await sdb.office_locations.distinct(
        "project_id",
        {"is_active": True, "kind": "site", "project_id": {"$nin": [None, ""]}},
    )
    attendance_visibility = {"$or": [visibility]}
    if site_project_ids:
        attendance_visibility["$or"].append({"id": {"$in": site_project_ids}})
    return merge_query(active, attendance_visibility)


async def _validate_attendance_project(user: dict, project_id: Optional[str]) -> Optional[dict]:
    if not project_id:
        return None
    project = await sdb.projects.find_one(
        {"id": project_id, "archived": {"$ne": True}},
        {"_id": 0, "id": 1, "name": 1},
    )
    if not project:
        raise HTTPException(400, "Selected project is unavailable")
    allowed_query = merge_query({"id": project_id}, await _attendance_project_query(user))
    if not await sdb.projects.find_one(allowed_query, {"_id": 0, "id": 1}):
        raise HTTPException(403, "You are not authorized to use this project for attendance")
    return project


def _require_attendance_access(user: dict) -> None:
    if not has_any_permission(
        user, "attendance.read", "attendance.create", "attendance.update", "attendance.approve",
    ):
        raise HTTPException(403, "Missing attendance permission")


@router.get("/attendance/project-options")
async def attendance_project_options(request: Request,
                                     session_token: Optional[str] = Cookie(default=None),
                                     authorization: Optional[str] = Header(default=None)):
    """Minimal project choices for site attendance, without exposing project details."""
    user = await require_user(request, session_token, authorization)
    _require_attendance_access(user)
    rows = await sdb.projects.find(
        await _attendance_project_query(user),
        {"_id": 0, "id": 1, "name": 1},
    ).sort("name", 1).to_list(500)
    return rows


@router.get("/attendance/locations")
async def list_locations(request: Request,
                         session_token: Optional[str] = Cookie(default=None),
                         authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    _require_attendance_access(user)
    rows = await sdb.office_locations.find({}, {"_id": 0}).sort("kind", 1).to_list(200)
    return rows


@router.post("/attendance/locations")
async def create_location(payload: GeoLocationIn, request: Request,
                          session_token: Optional[str] = Cookie(default=None),
                          authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    if not has_any_permission(user, "*.*", "attendance.update"):
        raise HTTPException(403, "Admin only")
    doc = payload.dict()
    doc["id"] = new_id("loc_")
    doc["created_at"] = iso_now()
    doc["created_by"] = user["user_id"]
    await sdb.office_locations.insert_one(dict(doc))
    return doc


@router.delete("/attendance/locations/{loc_id}")
async def delete_location(loc_id: str, request: Request,
                          session_token: Optional[str] = Cookie(default=None),
                          authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    if not has_any_permission(user, "*.*", "attendance.update"):
        raise HTTPException(403, "Admin only")
    r = await sdb.office_locations.delete_one({"id": loc_id})
    if not r.deleted_count:
        raise HTTPException(404, "Location not found")
    return {"ok": True}


# ==================================================
# Geo helpers
# ==================================================
def _haversine_m(lat1, lng1, lat2, lng2) -> float:
    """Distance between two lat/lng points in meters (WGS84 sphere)."""
    R = 6371000
    lat1r, lat2r = math.radians(lat1), math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1r) * math.cos(lat2r) * math.sin(dlng / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


async def _resolve_geo_fence(kind: str, lat: float, lng: float,
                             project_id: Optional[str] = None,
                             accuracy_m: Optional[float] = None) -> dict:
    """Find the nearest matching location and check if within radius.

    A capped GPS-accuracy tolerance is added to the radius so a real in-office
    fix with poor accuracy isn't wrongly rejected. Returns dict
    {inside, matched_location, distance_m, reason}.
    """
    q = {"is_active": True}
    if kind and kind != "any":
        q["kind"] = kind
    if project_id:
        q["$or"] = [{"project_id": project_id}, {"project_id": None}, {"project_id": {"$exists": False}}]
    locs = await sdb.office_locations.find(q, {"_id": 0}).to_list(200)
    best = None
    best_dist = None
    for loc in locs:
        d = _haversine_m(lat, lng, float(loc["lat"]), float(loc["lng"]))
        if best is None or d < best_dist:
            best = loc
            best_dist = d
    if best is None:
        return {"inside": False, "matched_location": None, "distance_m": None,
                "reason": f"No {kind} geo-fence configured"}
    radius = float(best.get("radius_m") or 150)
    tolerance = min(float(accuracy_m or 0), GPS_TOLERANCE_CAP_M)
    inside = best_dist <= (radius + tolerance)
    return {
        "inside": inside,
        "matched_location": {"id": best["id"], "name": best["name"],
                             "kind": best["kind"], "radius_m": best.get("radius_m")},
        "distance_m": round(best_dist, 1),
        "reason": None if inside else
                  f"You are {round(best_dist)}m from '{best['name']}' (allowed: {int(radius)}m)",
    }


@router.get("/attendance/geo-check")
async def geo_check(lat: float, lng: float, kind: str = "office",
                    project_id: Optional[str] = None,
                    accuracy_m: Optional[float] = None, request: Request = None,
                    session_token: Optional[str] = Cookie(default=None),
                    authorization: Optional[str] = Header(default=None)):
    """Quick check before check-in — tells UI whether user is inside a fence."""
    user = await require_user(request, session_token, authorization)
    _require_punch_permission(user)
    await _validate_attendance_project(user, project_id)
    return await _resolve_geo_fence(kind, lat, lng, project_id, accuracy_m)


# ==================================================
# Helpers
# ==================================================
def _late_minutes(office_start_hhmm: str, grace: int) -> int:
    """Best-effort lateness marker relative to office_start.
    Returns 0 if within grace, else minutes late."""
    try:
        h, m = office_start_hhmm.split(":")
        expected = int(h) * 60 + int(m) + int(grace or 0)
        local = engine.now_ist()
        actual = local.hour * 60 + local.minute
        return max(actual - expected, 0)
    except Exception:
        return 0


def _emp_shift_start(emp: dict, policy: dict) -> str:
    """Each employee's own shift start wins over the common policy office start."""
    return (emp or {}).get("shift_start") or policy.get("office_start") or "09:00"


def _emp_grace(emp: dict, policy: dict) -> int:
    """Per-employee grace override, else the common policy grace."""
    g = (emp or {}).get("grace_minutes")
    try:
        return int(g) if g is not None else int(policy.get("grace_minutes") or 0)
    except Exception:
        return int(policy.get("grace_minutes") or 0)


def _client_ip(request: Request) -> str:
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else ""


def _can_manage_attendance(user: dict) -> bool:
    return has_any_permission(user, "employees.update", "attendance.update", "attendance.approve")


def _can_edit_punches(user: dict) -> bool:
    return has_any_permission(user, "employees.update", "attendance.update")


def _require_punch_permission(user: dict) -> None:
    if not (has_permission(user, "attendance.create") or _can_edit_punches(user)):
        raise HTTPException(403, "Missing permission: attendance.create")


def _select_employee_id(user: dict, provided: Optional[str], own_id: Optional[str]) -> str:
    if provided and _can_edit_punches(user):
        return provided
    if provided and provided != own_id:
        raise HTTPException(403, "You can only manage your own attendance")
    if own_id:
        return own_id
    if _can_edit_punches(user):
        raise HTTPException(400, "Select an employee or link an employee profile to this account")
    raise HTTPException(400, "No employee profile is linked to this account")


async def _resolve_employee_id(user: dict, provided: Optional[str]) -> str:
    """Resolve self-service calls to the authenticated employee.

    Managers may explicitly target another employee; regular employees cannot
    act on a client-supplied employee id.
    """
    links = [{"user_id": user["user_id"]}]
    if user.get("email"):
        links.append({"email": user["email"]})
    emp = await sdb.employees.find_one({"$or": links}, {"_id": 0, "id": 1})
    resolved = _select_employee_id(user, provided, (emp or {}).get("id"))
    if provided and _can_edit_punches(user):
        target = await sdb.employees.find_one({"id": resolved}, {"_id": 0, "id": 1})
        if not target:
            raise HTTPException(404, "Employee not found")
    return resolved


def _today() -> str:
    return engine.now_ist().date().isoformat()


def _attendance_employee_name(employee: dict, fallback: str) -> str:
    name = str(employee.get("name") or "").strip()
    if not name:
        name = " ".join(filter(None, [
            str(employee.get("first_name") or "").strip(),
            str(employee.get("last_name") or "").strip(),
        ])).strip()
    return name or str(employee.get("employee_id") or fallback)


async def _store_check_in(existing: Optional[dict], doc: dict,
                          retry_rejected: bool = False):
    """Persist exactly one punch for an employee/business-date key."""
    try:
        if existing and retry_rejected:
            prior = {key: existing.get(key) for key in (
                "check_in", "check_out", "attendance_type", "project_id",
                "site_location", "geo_inside", "geo_location_matched",
                "geo_distance_m", "approval_status", "approval_remarks",
                "approved_by", "approved_at",
            ) if existing.get(key) is not None}
            prior["archived_at"] = iso_now()
            result = await sdb.attendance.update_one(
                {"id": existing["id"], "approval_status": "rejected", "status": "absent"},
                {
                    "$set": doc,
                    "$push": {"rejected_attempts": prior},
                    "$unset": {
                        "check_out": "", "check_out_ip": "", "check_out_notes": "",
                        "worked_hours": "", "working_minutes": "", "approved_by": "",
                        "approved_by_name": "", "approved_at": "", "approval_remarks": "",
                    },
                },
            )
            if result.matched_count == 0:
                raise HTTPException(400, "Attendance has already been updated; refresh and retry")
        elif existing:
            result = await sdb.attendance.update_one(
                {"id": existing["id"], "check_in": None}, {"$set": doc})
            if result.matched_count == 0:
                raise HTTPException(400, "Already checked in today")
        else:
            await sdb.attendance.insert_one(dict(doc))
    except DuplicateKeyError:
        raise HTTPException(400, "Already checked in today")


async def _employee_name_map(ids: list) -> dict:
    """id -> display name for a set of employee ids (users fallback)."""
    out = {}
    if not ids:
        return out
    async for e in sdb.employees.find({"id": {"$in": ids}}, {"_id": 0}):
        out[e["id"]] = engine.emp_name(e)
    remaining = [i for i in ids if i not in out]
    if remaining:
        async for u in sdb.users.find({"user_id": {"$in": remaining}},
                                      {"_id": 0, "user_id": 1, "name": 1, "email": 1}):
            out[u["user_id"]] = u.get("name") or u.get("email") or u["user_id"]
    return out


def _month_bounds(year: int, month: int):
    start = _date(year, month, 1).isoformat()
    if month == 12:
        end = _date(year + 1, 1, 1).isoformat()
    else:
        end = _date(year, month + 1, 1).isoformat()
    return start, end


async def _get_leave_rule() -> dict:
    doc = await sdb.leave_rules.find_one({"id": "default"}, {"_id": 0})
    if doc:
        return doc
    return {
        "id": "default",
        "allowances": DEFAULT_LEAVE_ALLOWANCE,
        "working_days_per_week": 6,
        "week_off_days": [6],   # Sunday
    }


# ==================================================
# Check-in / Check-out
# ==================================================
@router.post("/attendance/check-in")
async def check_in(payload: CheckInIn, request: Request,
                   session_token: Optional[str] = Cookie(default=None),
                   authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    _require_punch_permission(user)
    emp_id = await _resolve_employee_id(user, payload.employee_id)
    emp_doc = await sdb.employees.find_one(
        {"id": emp_id}, {"_id": 0, "shift_start": 1, "grace_minutes": 1,
                         "weekly_offs": 1, "first_name": 1, "last_name": 1,
                         "name": 1, "employee_id": 1, "employment_status": 1})
    if not emp_doc:
        raise HTTPException(status_code=404, detail="Employee not found")
    if emp_doc.get("employment_status") == "terminated":
        raise HTTPException(status_code=403, detail="Terminated employees cannot check in")
    employee_name = _attendance_employee_name(emp_doc, emp_id)
    today = _today()

    existing = await sdb.attendance.find_one({"employee_id": emp_id, "date": today}, {"_id": 0})
    retry_rejected = _retryable_rejected_punch(existing)
    if existing and existing.get("check_in") and not retry_rejected:
        raise HTTPException(status_code=400, detail="Already checked in today")

    att_type = payload.attendance_type or "office"
    await _validate_attendance_project(user, payload.project_id)
    policy = await _get_attendance_policy()

    # ---- Auto-holiday / weekly-off short-circuit ----
    # If today is a company holiday or weekly-off, mark the day accordingly
    # and skip the geo-fence + late-mark logic entirely.
    is_holiday_today, holiday_row = await _is_holiday(today)
    is_weekly_off = datetime.strptime(today, "%Y-%m-%d").weekday() in _weekly_off_days(emp_doc, policy)
    if (is_holiday_today or is_weekly_off) and att_type == "office":
        holiday_doc = {
            "id": existing["id"] if existing else new_id("att_"),
            "employee_id": emp_id, "employee_name": employee_name,
            "date": today, "check_in": iso_now(),
            "attendance_type": att_type,
            "status": "holiday", "approval_status": "auto",
            "holiday_name": (holiday_row or {}).get("name") if is_holiday_today
                              else "Weekly Off",
            "holiday_kind": (holiday_row or {}).get("kind") if is_holiday_today
                              else "weekly_off",
        }
        if not existing:
            holiday_doc["created_at"] = iso_now()
        await _store_check_in(existing, holiday_doc, retry_rejected)
        await audit(user, "attendance.check_in", target=holiday_doc["id"],
                    target_type="attendance",
                    meta={"employee_id": emp_id, "attendance_type": att_type,
                          "status": "holiday"})
        return await sdb.attendance.find_one({"id": holiday_doc["id"]}, {"_id": 0})

    # ---- Geo-fence enforcement ----
    geo_result = {"inside": True, "matched_location": None, "distance_m": None}
    is_office = att_type == "office"
    geo_enabled = policy.get("geo_fencing_enabled")
    if is_office:
        # Enforce office geofencing whenever the admin opted in OR an office
        # fence is actually configured (a marked office/default location). This
        # closes the trap where `require_geo_for_office` was left off/blank yet a
        # fence existed — which previously let staff check in from home.
        office_fence_exists = (
            policy.get("default_office_lat") is not None
            or await sdb.office_locations.count_documents({"kind": "office", "is_active": True}) > 0
        )
        geo_needed = bool(geo_enabled) and (
            bool(policy.get("require_geo_for_office", True)) or office_fence_exists
        )
    else:
        geo_needed = bool(geo_enabled)
    if geo_needed:
        if payload.lat is None or payload.lng is None:
            raise HTTPException(
                status_code=400,
                detail="GPS location required. Please allow location access and retry.",
            )
        # GPS accuracy validation — reject fixes worse than the policy threshold.
        max_acc = policy.get("max_gps_accuracy_m")
        if max_acc and payload.accuracy_m and payload.accuracy_m > max_acc:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "gps_accuracy_low",
                    "message": (f"GPS accuracy is {int(payload.accuracy_m)}m, needs to be "
                                f"under {int(max_acc)}m. Please step outdoors and try again."),
                    "accuracy_m": payload.accuracy_m,
                    "max_accuracy_m": max_acc,
                },
            )
        # map attendance_type -> location kind
        kind = {
            "office": "office", "site_visit": "site",
            "warehouse": "warehouse", "client_meeting": "client",
            "vendor_visit": "vendor",
        }.get(att_type, "office")
        geo_result = await _resolve_geo_fence(kind, payload.lat, payload.lng,
                                              payload.project_id, payload.accuracy_m)
        # For office: fall back to policy default fence if no explicit location
        if not geo_result.get("matched_location") and is_office \
                and policy.get("default_office_lat") is not None:
            d = _haversine_m(payload.lat, payload.lng,
                             policy["default_office_lat"], policy["default_office_lng"])
            radius = policy.get("default_office_radius_m") or 150
            tolerance = min(float(payload.accuracy_m or 0), GPS_TOLERANCE_CAP_M)
            geo_result = {
                "inside": d <= (radius + tolerance),
                "matched_location": {"id": "policy_default", "name": "Head Office",
                                     "kind": "office", "radius_m": radius},
                "distance_m": round(d, 1),
                "reason": None if d <= (radius + tolerance) else
                          f"You are {round(d)}m from Head Office (allowed: {int(radius)}m)",
            }

        if not geo_result["inside"]:
            # Outside authorised location
            if not payload.force_outside:
                # Block check-in and tell UI to show options
                raise HTTPException(
                    status_code=422,
                    detail={
                        "code": "outside_geofence",
                        "message": (geo_result.get("reason") or
                                    "You are outside the authorized location."),
                        "distance_m": geo_result.get("distance_m"),
                        "matched_location": geo_result.get("matched_location"),
                        "options": ["Request Approval", "Retry", "Contact Admin"],
                    },
                )
            # user explicitly clicked "Request Approval" → mark pending
            if not policy.get("approval_required_when_outside", True):
                raise HTTPException(400, "Outside-location approval is disabled by policy")

    # An active configured fence is itself the authorization for a site punch.
    # Unmatched or explicitly out-of-fence non-office punches still need review.
    status, approval_status = _initial_attendance_state(
        att_type, geo_needed, geo_result, payload.force_outside,
    )

    # Late arrival reason enforcement (uses the employee's own shift + grace)
    late_min = _late_minutes(_emp_shift_start(emp_doc, policy), _emp_grace(emp_doc, policy)) if is_office else None
    if (is_office and policy.get("require_late_reason") and late_min and late_min > 0
            and not (payload.late_reason and payload.late_reason.strip())
            and not (payload.late_category and payload.late_category.strip())):
        raise HTTPException(
            status_code=422,
            detail={
                "code": "late_reason_required",
                "message": (f"You are {late_min} minutes late. Please provide a reason to check in."),
                "late_minutes": late_min,
                "categories": policy.get("late_reason_categories") or [],
            },
        )

    # --- Jewellers ERP late logic ---
    # Late becomes a first-class status (never auto half-day) with a
    # configurable Rs. fine; admin approval of the late arrival waives it.
    late_approval_status = "not_required"
    late_fine = 0.0
    if is_office and late_min and late_min > 0:
        if status == "present":
            status = "late"
        late_approval_status = "pending"
        if policy.get("late_fine_enabled"):
            late_fine = float(policy.get("late_fine_amount") or 0)
            cap = float(policy.get("late_fine_daily_cap") or 0)
            if cap > 0:
                late_fine = min(late_fine, cap)

    doc = {
        "id": existing["id"] if existing else new_id("att_"),
        "employee_id": emp_id,
        "employee_name": employee_name,
        "date": today,
        "check_in": iso_now(),
        "check_in_ip": _client_ip(request),
        "check_in_location": payload.location or "",
        "check_in_notes": payload.notes or "",
        "attendance_type": att_type,
        "project_id": payload.project_id,
        "site_location": payload.site_location,
        "expected_time": payload.expected_time,
        "site_reason": payload.reason,
        "late_reason": payload.late_reason,
        "late_category": payload.late_category,
        "late_approval_status": late_approval_status,
        "late_fine_amount": late_fine,
        "late_fine_waived": False,
        # Geo
        "check_in_lat": payload.lat,
        "check_in_lng": payload.lng,
        "check_in_accuracy_m": payload.accuracy_m,
        "geo_inside": geo_result["inside"],
        "geo_location_matched": (geo_result.get("matched_location") or {}).get("name"),
        "geo_distance_m": geo_result.get("distance_m"),
        # Device fingerprint
        "device_id": payload.device_id,
        "device_label": payload.device_label,
        "user_agent": payload.user_agent or (request.headers.get("user-agent") if request else None),
        # Lateness marker vs policy office_start (best-effort, timezone-naive HH:MM)
        "late_minutes": late_min,
        "status": status,
        "approval_status": approval_status,
    }
    if not existing:
        doc["created_at"] = iso_now()
    await _store_check_in(existing, doc, retry_rejected)
    await audit(user, "attendance.check_in", target=doc["id"], target_type="attendance",
                meta={"employee_id": emp_id, "attendance_type": att_type,
                      "project_id": payload.project_id, "status": status})
    # Notify HR/Admins when an approval is needed (out-of-zone or non-office)
    if approval_status == "pending":
        where = doc.get("site_location") or doc.get("geo_location_matched") or ""
        dist = doc.get("geo_distance_m")
        detail = f"{att_type.replace('_', ' ').title()}"
        if where:
            detail += f" · {where}"
        if dist and not geo_result.get("inside", True):
            detail += f" · {round(dist)}m outside fence"
        await emit_admins(
            "attendance_pending",
            f"Attendance approval: {employee_name}",
            body=detail,
            link="/attendance",
            priority="high",
            org_id=user_org_id(user),
            meta={"attendance_id": doc["id"], "employee_id": emp_id},
            dedup_key=f"att_pending_{doc['id']}",
        )
    return await sdb.attendance.find_one({"id": doc["id"]}, {"_id": 0})


@router.post("/attendance/check-out")
async def check_out(payload: CheckOutIn, request: Request,
                    session_token: Optional[str] = Cookie(default=None),
                    authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    _require_punch_permission(user)
    emp_id = await _resolve_employee_id(user, payload.employee_id)
    today = _today()

    existing = await sdb.attendance.find_one({"employee_id": emp_id, "date": today}, {"_id": 0})
    if not existing or not existing.get("check_in"):
        raise HTTPException(status_code=400, detail="Not checked in today")
    if existing.get("check_out"):
        raise HTTPException(status_code=400, detail="Already checked out today")

    ci = datetime.fromisoformat(existing["check_in"])
    now = now_utc()
    if ci.tzinfo is None:
        ci = ci.replace(tzinfo=timezone.utc)
    working_minutes = max(int((now - ci).total_seconds() // 60), 0)
    hours = round(working_minutes / 60.0, 2)

    # Day classification (Jewellers logic): late is NEVER auto-converted
    # to half-day — it is penalised via the Rs. fine instead.
    policy = await _get_attendance_policy()
    emp = await sdb.employees.find_one({"id": emp_id}, {"_id": 0}) or {}
    half_day_min = int(emp.get("half_day_min_minutes")
                       or (policy.get("half_day_min_hours") or 4) * 60)
    status = existing["status"]
    if status == "late":
        pass
    elif status == "present" and working_minutes < half_day_min:
        status = "half_day"

    result = await sdb.attendance.update_one(
        {"id": existing["id"], "check_out": None},
        {"$set": {
            "check_out": now.isoformat(),
            "check_out_ip": _client_ip(request),
            "check_out_notes": payload.notes or "",
            "worked_hours": hours,
            "working_minutes": working_minutes,
            "status": status,
            "updated_at": iso_now(),
        }},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=400, detail="Already checked out today")
    await audit(user, "attendance.check_out", target=existing["id"], target_type="attendance",
                meta={"employee_id": emp_id, "working_minutes": working_minutes,
                      "status": status})
    return await sdb.attendance.find_one({"id": existing["id"]}, {"_id": 0})


# ==================================================
# My attendance summary
# ==================================================
@router.get("/attendance/me/today")
async def my_today(request: Request,
                   session_token: Optional[str] = Cookie(default=None),
                   authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    emp_id = await _resolve_employee_id(user, None)
    row = await sdb.attendance.find_one({"employee_id": emp_id, "date": _today()}, {"_id": 0})
    return {"employee_id": emp_id, "date": _today(), "record": row}


@router.get("/attendance/me/summary")
async def my_summary(request: Request, year: Optional[int] = None, month: Optional[int] = None,
                     session_token: Optional[str] = Cookie(default=None),
                     authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    emp_id = await _resolve_employee_id(user, None)
    local_now = engine.now_ist()
    y = year or local_now.year
    m = month or local_now.month
    start, end = _month_bounds(y, m)
    rows = await sdb.attendance.find(
        {"employee_id": emp_id, "date": {"$gte": start, "$lt": end}},
        {"_id": 0},
    ).sort("date", 1).to_list(500)
    counts = {s: 0 for s in ATTENDANCE_STATUSES}
    for r in rows:
        counts[r.get("status", "absent")] = counts.get(r.get("status", "absent"), 0) + 1
    return {"employee_id": emp_id, "year": y, "month": m, "records": rows, "counts": counts}


# ==================================================
# Monthly sheet (Admin/HR — payroll-ready)
# ==================================================
@router.get("/attendance/monthly")
async def monthly_sheet(request: Request, year: Optional[int] = None, month: Optional[int] = None,
                        session_token: Optional[str] = Cookie(default=None),
                        authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    if not has_any_permission(user, "employees.read", "attendance.update", "attendance.approve"):
        raise HTTPException(status_code=403, detail="Missing permission: employees.read")

    local_now = engine.now_ist()
    y = year or local_now.year
    m = month or local_now.month
    start, end = _month_bounds(y, m)

    employees = await sdb.employees.find(
        {}, {"_id": 0, "id": 1, "name": 1, "first_name": 1, "last_name": 1,
             "employee_id": 1, "designation": 1, "department": 1,
             "shift_start": 1, "shift_end": 1, "grace_minutes": 1}).to_list(500)
    rows = []
    for e in employees:
        e["name"] = engine.emp_name(e)
        recs = await sdb.attendance.find(
            {"employee_id": e["id"], "date": {"$gte": start, "$lt": end}},
            {"_id": 0},
        ).sort("date", 1).to_list(500)
        counts = {s: 0 for s in ATTENDANCE_STATUSES}
        total_hours = 0.0
        for r in recs:
            s = r.get("status", "absent")
            counts[s] = counts.get(s, 0) + 1
            total_hours += float(r.get("worked_hours") or 0)
        rows.append({
            "employee": e,
            "counts": counts,
            "worked_hours": round(total_hours, 2),
            "records": recs,
        })
    return {"year": y, "month": m, "rows": rows}


# ==================================================
# Admin override (mark leave / holiday / etc.)
# ==================================================
@router.post("/attendance/override")
async def override_attendance(payload: AttendanceOverrideIn, request: Request,
                              session_token: Optional[str] = Cookie(default=None),
                              authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    if not has_any_permission(user, "employees.update", "attendance.update", "attendance.approve"):
        raise HTTPException(status_code=403, detail="Missing permission: employees.update")
    if payload.status not in ATTENDANCE_STATUSES:
        raise HTTPException(status_code=400, detail="Invalid status")
    _validate_manual_attendance(payload.date, None, None)
    if not await sdb.employees.find_one({"id": payload.employee_id}, {"_id": 0, "id": 1}):
        raise HTTPException(404, "Employee not found")

    existing = await sdb.attendance.find_one(
        {"employee_id": payload.employee_id, "date": payload.date},
        {"_id": 0},
    )
    updates = {
        "employee_id": payload.employee_id,
        "date": payload.date,
        "status": payload.status,
        "leave_type": payload.leave_type,
        "override_notes": payload.notes or "",
        "override_by": user["user_id"],
        "override_at": iso_now(),
    }
    if existing:
        await sdb.attendance.update_one({"id": existing["id"]}, {"$set": updates})
        return await sdb.attendance.find_one({"id": existing["id"]}, {"_id": 0})
    updates["id"] = new_id("att_")
    updates["created_at"] = iso_now()
    await sdb.attendance.insert_one(dict(updates))
    return await sdb.attendance.find_one({"id": updates["id"]}, {"_id": 0})


# ==================================================
# Leave rules
# ==================================================
@router.get("/attendance/leave-rules")
async def get_leave_rule(request: Request,
                         session_token: Optional[str] = Cookie(default=None),
                         authorization: Optional[str] = Header(default=None)):
    await require_user(request, session_token, authorization)
    return await _get_leave_rule()


@router.put("/attendance/leave-rules")
async def put_leave_rule(payload: LeaveRuleIn, request: Request,
                         session_token: Optional[str] = Cookie(default=None),
                         authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    if not has_any_permission(user, "employees.update", "attendance.update", "attendance.approve"):
        raise HTTPException(status_code=403, detail="Missing permission: employees.update")
    doc = payload.model_dump()
    doc["id"] = "default"
    doc["updated_at"] = iso_now()
    await sdb.leave_rules.replace_one({"id": "default"}, doc, upsert=True)
    return await _get_leave_rule()


# ==================================================
# Leave requests
# ==================================================
@router.post("/leaves")
async def create_leave(payload: LeaveRequestIn, request: Request,
                       session_token: Optional[str] = Cookie(default=None),
                       authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    if payload.leave_type not in LEAVE_TYPES:
        raise HTTPException(status_code=400, detail="Invalid leave_type")
    emp_id = await _resolve_employee_id(user, payload.employee_id)

    # Compute days between (inclusive)
    try:
        d1 = _date.fromisoformat(payload.from_date)
        d2 = _date.fromisoformat(payload.to_date)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Leave dates must be YYYY-MM-DD")
    if d2 < d1:
        raise HTTPException(status_code=400, detail="to_date before from_date")
    days = (d2 - d1).days + 1
    if days > 366:
        raise HTTPException(status_code=400, detail="A leave request cannot exceed 366 days")
    overlap = await sdb.leaves.find_one({
        "employee_id": emp_id,
        "status": {"$in": ["pending", "approved"]},
        "from_date": {"$lte": payload.to_date},
        "to_date": {"$gte": payload.from_date},
    }, {"_id": 0, "id": 1})
    if overlap:
        raise HTTPException(status_code=409, detail="An active leave request already overlaps these dates")

    # Resolve the employee's display name explicitly (leave permissions
    # must always show WHO the leave is for).
    emp_doc = await sdb.employees.find_one({"id": emp_id}, {"_id": 0})
    employee_name = (engine.emp_name(emp_doc) if emp_doc else None) or user.get("name") or emp_id

    doc = {
        "id": new_id("lv_"),
        "employee_id": emp_id,
        "employee_name": employee_name,
        "leave_type": payload.leave_type,
        "from_date": payload.from_date,
        "to_date": payload.to_date,
        "days": days,
        "reason": payload.reason or "",
        "status": "pending",
        "created_at": iso_now(),
        "created_by": user["user_id"],
    }
    await sdb.leaves.insert_one(dict(doc))

    # Notify HR + Admins that a leave request needs review
    try:
        from core.notifications import emit_hr
        await emit_hr(
            "leave_request",
            f"Leave request · {doc['employee_name']}",
            body=f"{doc['leave_type']} · {doc['from_date']} → {doc['to_date']} ({doc['days']} day{'s' if doc['days'] != 1 else ''})",
            link="/attendance",
            priority="normal",
            org_id=user_org_id(user),
            meta={"leave_id": doc["id"], "employee_id": emp_id, "days": doc["days"]},
        )
    except Exception:
        pass

    return await sdb.leaves.find_one({"id": doc["id"]}, {"_id": 0})


@router.get("/leaves")
async def list_leaves(request: Request, employee_id: Optional[str] = None,
                      status: Optional[str] = None, mine: Optional[bool] = None,
                      session_token: Optional[str] = Cookie(default=None),
                      authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    q: dict = {}
    if not _can_manage_attendance(user):
        q["employee_id"] = await _resolve_employee_id(user, employee_id)
    elif mine:
        q["employee_id"] = await _resolve_employee_id(user, None)
    elif employee_id:
        q["employee_id"] = employee_id
    if status:
        q["status"] = status
    rows = await sdb.leaves.find(q, {"_id": 0}).sort("created_at", -1).to_list(500)
    # Always surface the employee's name on every leave permission row.
    missing = [r["employee_id"] for r in rows if not r.get("employee_name")]
    if missing:
        name_map = await _employee_name_map(list(set(missing)))
        for r in rows:
            if not r.get("employee_name"):
                r["employee_name"] = name_map.get(r["employee_id"], r["employee_id"])
    return rows


@router.post("/leaves/{leave_id}/action")
async def act_on_leave(leave_id: str, payload: LeaveActionIn, request: Request,
                       session_token: Optional[str] = Cookie(default=None),
                       authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    if not has_any_permission(user, "employees.update", "attendance.update", "attendance.approve"):
        raise HTTPException(status_code=403, detail="Missing permission: employees.update")
    if payload.action not in ("approve", "reject"):
        raise HTTPException(status_code=400, detail="Invalid action")
    lv, review_token = await _claim_pending_review(sdb.leaves, leave_id)
    new_status = "approved" if payload.action == "approve" else "rejected"
    try:
        # Approved leave fills only empty/absent days. A real punch, holiday, or
        # other worked state is business evidence and must never be overwritten.
        if new_status == "approved":
            d1 = _date.fromisoformat(lv["from_date"])
            d2 = _date.fromisoformat(lv["to_date"])
            cur = d1
            while cur <= d2:
                ds = cur.isoformat()
                existing = await sdb.attendance.find_one(
                    {"employee_id": lv["employee_id"], "date": ds}, {"_id": 0})
                if _attendance_allows_leave(existing):
                    update = {"$set": {
                        "employee_id": lv["employee_id"], "date": ds,
                        "status": "leave", "leave_type": lv["leave_type"],
                        "leave_id": lv["id"], "updated_at": iso_now(),
                    }, "$setOnInsert": {"id": new_id("att_"), "created_at": iso_now()}}
                    try:
                        await sdb.attendance.update_one(
                            {"employee_id": lv["employee_id"], "date": ds},
                            update, upsert=True)
                    except DuplicateKeyError:
                        # A punch won the race with leave approval; preserve it.
                        pass
                cur += timedelta(days=1)

        decided_at = iso_now()
        result = await sdb.leaves.update_one(
            {"id": leave_id, "status": "pending", "review_token": review_token},
            {"$set": {
                "status": new_status, "action_by": user["user_id"],
                "action_by_name": user.get("name"), "action_at": decided_at,
                "action_remarks": payload.remarks or "",
            }, "$unset": {"review_token": "", "review_started_at": ""}},
        )
        if result.modified_count != 1:
            raise RuntimeError("Leave review claim was lost")
    except Exception:
        await _release_review_claim(sdb.leaves, leave_id, review_token)
        raise

    await audit(user, f"leave.{payload.action}", target=leave_id,
                target_type="leave", meta={"employee_id": lv.get("employee_id"),
                                           "from_date": lv.get("from_date"),
                                           "to_date": lv.get("to_date")})

    # Notify the requester of the decision
    try:
        from core.notifications import emit as _notify
        requester_uid = lv.get("created_by")
        if requester_uid:
            await _notify(
                [requester_uid], "leave_decided",
                f"Leave {new_status} · {lv['from_date']} → {lv['to_date']}",
                body=(payload.remarks or f"Your leave request was {new_status} by {user.get('name')}."),
                link="/attendance",
                priority="normal",
                meta={"leave_id": lv["id"], "status": new_status},
            )
    except Exception:
        pass

    return await sdb.leaves.find_one({"id": leave_id}, {"_id": 0})


@router.get("/leaves/balance/{employee_id}")
async def leave_balance(employee_id: str, year: Optional[int] = None,
                        request: Request = None,
                        session_token: Optional[str] = Cookie(default=None),
                        authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    employee_id = await _resolve_employee_id(user, employee_id)
    y = year or engine.now_ist().year
    year_start = f"{y}-01-01"
    year_end = f"{y+1}-01-01"
    rule = await _get_leave_rule()
    allowances = rule.get("allowances") or DEFAULT_LEAVE_ALLOWANCE

    used = {t: 0 for t in LEAVE_TYPES}
    cur = sdb.leaves.find({
        "employee_id": employee_id,
        "status": "approved",
        "from_date": {"$gte": year_start, "$lt": year_end},
    }, {"_id": 0, "leave_type": 1, "days": 1})
    async for lv in cur:
        used[lv["leave_type"]] = used.get(lv["leave_type"], 0) + lv["days"]

    balance = {t: {"allowance": allowances.get(t, 0),
                   "used": used.get(t, 0),
                   "remaining": max(0, allowances.get(t, 0) - used.get(t, 0))}
               for t in LEAVE_TYPES}
    return {"employee_id": employee_id, "year": y, "balance": balance}


# ==================================================
# Meta
# ==================================================
@router.get("/attendance/meta")
async def attendance_meta(request: Request,
                          session_token: Optional[str] = Cookie(default=None),
                          authorization: Optional[str] = Header(default=None)):
    await require_user(request, session_token, authorization)
    return {
        "statuses": ATTENDANCE_STATUSES,
        "leave_types": LEAVE_TYPES,
        "leave_statuses": LEAVE_STATUSES,
        "default_allowance": DEFAULT_LEAVE_ALLOWANCE,
        "attendance_types": ["office", "site_visit"],
    }


# ==================================================
# Site-visit approvals (HR / Director / Admin)
# ==================================================
@router.get("/attendance/pending-approvals")
async def pending_approvals(request: Request,
                            session_token: Optional[str] = Cookie(default=None),
                            authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    if not has_any_permission(user, "employees.update", "attendance.update", "attendance.approve"):
        raise HTTPException(status_code=403, detail="Missing permission")
    rows = await sdb.attendance.find(
        {"approval_status": "pending"}, {"_id": 0},
    ).sort("check_in", -1).to_list(500)
    return rows


@router.post("/attendance/{att_id}/approve")
async def approve_attendance(att_id: str, payload: ApproveAttendanceIn, request: Request,
                             session_token: Optional[str] = Cookie(default=None),
                             authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    if not has_any_permission(user, "employees.update", "attendance.update", "attendance.approve"):
        raise HTTPException(status_code=403, detail="Missing permission")
    if payload.action == "approve":
        new_status = "present"
        approval_status = "approved"
    elif payload.action == "reject":
        new_status = "absent"
        approval_status = "rejected"
    else:
        raise HTTPException(status_code=400, detail="Invalid action")
    row = await sdb.attendance.find_one_and_update(
        {"id": att_id, "approval_status": "pending"},
        {"$set": {
            "status": new_status, "approval_status": approval_status,
            "approved_by": user["user_id"], "approved_by_name": user.get("name"),
            "approved_at": iso_now(), "approval_remarks": payload.remarks or "",
        }},
        return_document=ReturnDocument.AFTER,
    )
    if not row:
        current = await sdb.attendance.find_one({"id": att_id}, {"_id": 0})
        if not current:
            raise HTTPException(status_code=404, detail="Attendance record not found")
        raise HTTPException(status_code=400, detail=f"Already {current.get('approval_status')}")
    row.pop("_id", None)
    await audit(user, f"attendance.{payload.action}", target=att_id, target_type="attendance",
                meta={"employee_id": row.get("employee_id"), "date": row.get("date"),
                      "remarks": payload.remarks or ""})
    # Notify the employee about the decision
    emp = await sdb.employees.find_one(
        {"id": row.get("employee_id")}, {"_id": 0, "user_id": 1, "email": 1})
    target_user_id = None
    if emp and emp.get("user_id"):
        target_user_id = emp["user_id"]
    elif emp and emp.get("email"):
        u = await sdb.users.find_one({"email": emp["email"].lower()}, {"_id": 0, "user_id": 1})
        target_user_id = (u or {}).get("user_id")
    else:
        # solo-admin fallback: employee_id may be the user_id itself
        u = await sdb.users.find_one({"user_id": row.get("employee_id")}, {"_id": 0, "user_id": 1})
        target_user_id = (u or {}).get("user_id")
    if target_user_id:
        verdict = "approved" if payload.action == "approve" else "rejected"
        await emit([target_user_id], "attendance_decided",
                   f"Attendance {verdict} for {row.get('date')}",
                   body=(payload.remarks or "").strip(),
                   link="/attendance",
                   priority="normal",
                   meta={"attendance_id": att_id, "decision": verdict},
                   dedup_key=f"att_decided_{att_id}")
    return row


# ==================================================================
# JEWELLERS ERP PORTED FEATURES
# Monthly summary engine · salary impact · team dashboard · live board
# manual attendance · short/hourly leave · corrections · late approvals
# ==================================================================

# ---------- Monthly summary (daily grid + payable/LOP days) ----------
@router.get("/attendance/summary")
async def attendance_summary(request: Request, employee_id: str,
                             year: Optional[int] = None, month: Optional[int] = None,
                             session_token: Optional[str] = Cookie(default=None),
                             authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    can_view_team = has_any_permission(
        user, "employees.read", "attendance.update", "attendance.approve")
    if not can_view_team:
        # Employees may only view their own summary
        own = await _resolve_employee_id(user, None)
        if own != employee_id:
            raise HTTPException(403, "You can only view your own attendance summary")
    emp = await sdb.employees.find_one({"id": employee_id}, {"_id": 0})
    if not emp:
        # Solo-admin fallback: user without an employee record
        emp = {"id": employee_id, "first_name": user.get("name") or "", "last_name": ""}
    local_now = engine.now_ist()
    y = year or local_now.year
    m = month or local_now.month
    policy = await _get_attendance_policy()
    data = await engine.monthly_summary(emp, y, m, policy)
    is_self = (emp.get("user_id") == user.get("user_id")) or \
              ((emp.get("email") or "").lower() == (user.get("email") or "").lower())
    if not is_self and not has_permission(user, "payroll.read"):
        data = _without_compensation(data)
    return data


# ---------- Salary impact view (self-service) ----------
@router.get("/attendance/my-salary")
async def my_salary(request: Request, year: Optional[int] = None, month: Optional[int] = None,
                    session_token: Optional[str] = Cookie(default=None),
                    authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    emp = await sdb.employees.find_one(
        {"$or": [{"user_id": user["user_id"]}, {"email": user.get("email")}]}, {"_id": 0})
    if not emp:
        return {"has_employee": False}
    local_now = engine.now_ist()
    y = year or local_now.year
    m = month or local_now.month
    policy = await _get_attendance_policy()
    data = await engine.monthly_summary(emp, y, m, policy)
    data["has_employee"] = True
    import calendar as _cal
    data["month_label"] = f"{_cal.month_name[m]} {y}"
    return data


# ---------- Team dashboard (HR) ----------
@router.get("/attendance/dashboard")
async def team_dashboard(request: Request,
                         session_token: Optional[str] = Cookie(default=None),
                         authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    if not has_any_permission(user, "employees.read", "attendance.update", "attendance.approve"):
        raise HTTPException(403, "Missing permission: employees.read")
    today = _today()
    total_emp = await sdb.employees.count_documents(
        {"employment_status": {"$nin": ["terminated"]}})
    recs = await sdb.attendance.find({"date": today}, {"_id": 0}).to_list(1000)
    present = sum(1 for r in recs if r.get("status") in ("present", "late", "half_day", "pending_approval"))
    late = sum(1 for r in recs if r.get("status") == "late")
    checked_in = sum(1 for r in recs if r.get("check_in") and not r.get("check_out"))
    checked_out = sum(1 for r in recs if r.get("check_out"))
    on_leave = sum(1 for r in recs if r.get("status") == "leave")
    pending_corr = await sdb.attendance_corrections.count_documents({"status": "pending"})
    pending_late = await sdb.attendance.count_documents({"late_approval_status": "pending"})
    pending_leaves = await sdb.leaves.count_documents({"status": "pending"})
    return {
        "date": today,
        "total_employees": total_emp,
        "present_today": present,
        "late_today": late,
        "absent_today": max(total_emp - present - on_leave, 0),
        "on_leave": on_leave,
        "currently_checked_in": checked_in,
        "checked_out": checked_out,
        "not_checked_in": max(total_emp - len(recs), 0),
        "pending_corrections": pending_corr,
        "pending_late_approvals": pending_late,
        "pending_leaves": pending_leaves,
    }


# ---------- Today's records (with employee names) ----------
@router.get("/attendance/records")
async def attendance_records(request: Request, employee_id: Optional[str] = None,
                             start: Optional[str] = None, end: Optional[str] = None,
                             session_token: Optional[str] = Cookie(default=None),
                             authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    if not has_any_permission(user, "employees.read", "attendance.update", "attendance.approve"):
        employee_id = await _resolve_employee_id(user, None)
    q: dict = {}
    if employee_id:
        q["employee_id"] = employee_id
    if start or end:
        q["date"] = {}
        if start:
            q["date"]["$gte"] = start
        if end:
            q["date"]["$lte"] = end
    rows = await sdb.attendance.find(q, {"_id": 0}).sort("date", -1).to_list(1000)
    name_map = await _employee_name_map(list({r["employee_id"] for r in rows}))
    for r in rows:
        r["employee_name"] = name_map.get(r["employee_id"]) or r.get("employee_name") or r["employee_id"]
    return rows


# ---------- Live attendance board ----------
@router.get("/attendance/live")
async def live_board(request: Request,
                     session_token: Optional[str] = Cookie(default=None),
                     authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    if not has_any_permission(user, "employees.read", "attendance.update", "attendance.approve"):
        raise HTTPException(403, "Missing permission: employees.read")
    today = _today()
    policy = await _get_attendance_policy()
    emps = await sdb.employees.find(
        {"employment_status": {"$nin": ["terminated"]}}, {"_id": 0}).to_list(1000)
    recs = {r["employee_id"]: r async for r in sdb.attendance.find({"date": today}, {"_id": 0})}
    is_holiday_today, _hrow = await _is_holiday(today)
    weekday = _date.fromisoformat(today).weekday()

    people = []
    counts = {"checked_in": 0, "checked_out": 0, "late": 0, "absent": 0, "on_leave": 0, "off": 0}
    for e in emps:
        rec = recs.get(e["id"])
        weekly_offs = e.get("weekly_offs") if e.get("weekly_offs") is not None else (policy.get("weekly_off_days") or [6])
        weekly_off = weekday in (weekly_offs or [])
        if rec and rec.get("status") == "leave":
            status = "on_leave"; counts["on_leave"] += 1
        elif rec and rec.get("check_in") and not rec.get("check_out"):
            status = "late" if rec.get("status") == "late" else "checked_in"
            counts["checked_in"] += 1
            if rec.get("status") == "late":
                counts["late"] += 1
        elif rec and rec.get("check_out"):
            status = "checked_out"; counts["checked_out"] += 1
        elif is_holiday_today:
            status = "holiday"; counts["off"] += 1
        elif weekly_off:
            status = "weekly_off"; counts["off"] += 1
        else:
            status = "absent"; counts["absent"] += 1
        people.append({
            "employee_id": e["id"],
            "name": engine.emp_name(e),
            "department": e.get("department"),
            "designation": e.get("designation"),
            "shift_start": e.get("shift_start"), "shift_end": e.get("shift_end"),
            "status": status,
            "check_in": engine._hhmm_ist((rec or {}).get("check_in")),
            "check_out": engine._hhmm_ist((rec or {}).get("check_out")),
            "late_minutes": (rec or {}).get("late_minutes") or 0,
            "geo_inside": (rec or {}).get("geo_inside"),
            "working_minutes": (rec or {}).get("working_minutes") or 0,
        })
    order = {"late": 0, "checked_in": 1, "on_leave": 2, "absent": 3,
             "checked_out": 4, "weekly_off": 5, "holiday": 6}
    people.sort(key=lambda p: (order.get(p["status"], 9), p["name"] or ""))
    return {"date": today, "generated_at": engine.now_ist().strftime("%H:%M"),
            "total": len(emps), "counts": counts, "people": people}


# ---------- Manual attendance (admin) ----------
@router.post("/attendance/manual")
async def manual_attendance(payload: ManualAttendanceIn, request: Request,
                            session_token: Optional[str] = Cookie(default=None),
                            authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    if not has_any_permission(user, "employees.update", "attendance.update", "attendance.approve"):
        raise HTTPException(403, "Missing permission: employees.update")
    if payload.status not in ATTENDANCE_STATUSES:
        raise HTTPException(400, "Invalid status")
    _validate_manual_attendance(payload.date, payload.check_in, payload.check_out)
    if not await sdb.employees.find_one({"id": payload.employee_id}, {"_id": 0, "id": 1}):
        raise HTTPException(404, "Employee not found")
    existing = await sdb.attendance.find_one(
        {"employee_id": payload.employee_id, "date": payload.date}, {"_id": 0})
    updates = {
        "employee_id": payload.employee_id,
        "date": payload.date,
        "status": payload.status,
        "check_in": payload.check_in,
        "check_out": payload.check_out,
        "late_reason": payload.late_reason,
        "short_leave_hours": payload.short_leave_hours or 0,
        "manual_notes": payload.notes,
        "is_manual": True,
        "updated_by": user["user_id"],
        "updated_at": iso_now(),
    }
    if payload.check_in and payload.check_out:
        ci = _parse_correction_datetime(payload.check_in, "check-in")
        co = _parse_correction_datetime(payload.check_out, "check-out")
        wm = int((co - ci).total_seconds() // 60)
        updates["working_minutes"] = wm
        updates["worked_hours"] = round(wm / 60.0, 2)
    if existing:
        await sdb.attendance.update_one({"id": existing["id"]}, {"$set": updates})
        row_id = existing["id"]
    else:
        updates["id"] = new_id("att_")
        updates["created_at"] = iso_now()
        await sdb.attendance.insert_one(dict(updates))
        row_id = updates["id"]
    await audit(user, "attendance.manual", target=row_id, target_type="attendance",
                meta={"employee_id": payload.employee_id, "date": payload.date,
                      "status": payload.status})
    return await sdb.attendance.find_one({"id": row_id}, {"_id": 0})


# ---------- Short / hourly leave (admin) ----------
@router.post("/attendance/short-leave")
async def short_leave(payload: ShortLeaveIn, request: Request,
                      session_token: Optional[str] = Cookie(default=None),
                      authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    if not has_any_permission(user, "employees.update", "attendance.update", "attendance.approve"):
        raise HTTPException(403, "Missing permission: employees.update")
    if not payload.hours or payload.hours <= 0 or payload.hours > 12:
        raise HTTPException(400, "Hours must be between 0 and 12")
    _validate_manual_attendance(payload.date, None, None)
    if not await sdb.employees.find_one({"id": payload.employee_id}, {"_id": 0, "id": 1}):
        raise HTTPException(404, "Employee not found")
    existing = await sdb.attendance.find_one(
        {"employee_id": payload.employee_id, "date": payload.date}, {"_id": 0})
    note = f"Short/hourly leave: {payload.hours}h" + (f" — {payload.reason}" if payload.reason else "")
    updates = {
        "employee_id": payload.employee_id,
        "date": payload.date,
        "short_leave_hours": payload.hours,
        "short_leave_reason": payload.reason,
        "short_leave_note": note,
        "updated_at": iso_now(),
        "updated_by": user["user_id"],
    }
    if not existing or existing.get("status") in (None, "absent"):
        updates["status"] = existing.get("status", "present") if existing and existing.get("status") not in (None, "absent") else "present"
        updates.setdefault("is_manual", True)
    if existing:
        await sdb.attendance.update_one({"id": existing["id"]}, {"$set": updates})
        row_id = existing["id"]
    else:
        updates["id"] = new_id("att_")
        updates["created_at"] = iso_now()
        await sdb.attendance.insert_one(dict(updates))
        row_id = updates["id"]
    row = await sdb.attendance.find_one({"id": row_id}, {"_id": 0})
    nm = await _employee_name_map([payload.employee_id])
    row["employee_name"] = nm.get(payload.employee_id, payload.employee_id)
    return row


# ---------- Late approvals (Jewellers workflow) ----------
@router.get("/attendance/late-approvals")
async def list_late_approvals(request: Request, status: Optional[str] = "pending",
                              session_token: Optional[str] = Cookie(default=None),
                              authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    if not has_any_permission(user, "employees.read", "attendance.update", "attendance.approve"):
        raise HTTPException(403, "Missing permission: employees.read")
    q = {"late_approval_status": status} if status else {"late_approval_status": {"$in": ["pending", "approved", "rejected"]}}
    rows = await sdb.attendance.find(q, {"_id": 0}).sort("date", -1).to_list(500)
    name_map = await _employee_name_map(list({r["employee_id"] for r in rows}))
    for r in rows:
        r["employee_name"] = name_map.get(r["employee_id"]) or r.get("employee_name") or r["employee_id"]
    return rows


@router.put("/attendance/{record_id}/late-review")
async def review_late(record_id: str, payload: LateReviewIn, request: Request,
                      session_token: Optional[str] = Cookie(default=None),
                      authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    if not has_any_permission(user, "employees.update", "attendance.update", "attendance.approve"):
        raise HTTPException(403, "Missing permission: employees.update")
    if payload.status not in ("approved", "rejected"):
        raise HTTPException(400, "status must be approved or rejected")
    # Approving/excusing a late arrival waives its fine; rejecting keeps it.
    row = await sdb.attendance.find_one_and_update(
        {"id": record_id, "late_approval_status": "pending"},
        {"$set": {
            "late_approval_status": payload.status,
            "late_fine_waived": payload.status == "approved",
            "late_reviewed_by": user["user_id"],
            "late_reviewed_by_name": user.get("name"),
            "late_reviewed_at": iso_now(),
            "late_review_notes": payload.review_notes or "",
        }},
        return_document=ReturnDocument.AFTER,
    )
    if not row:
        current = await sdb.attendance.find_one({"id": record_id}, {"_id": 0})
        if not current:
            raise HTTPException(404, "Attendance record not found")
        raise HTTPException(
            409,
            f"Late arrival already {current.get('late_approval_status') or 'not reviewable'}",
        )
    row.pop("_id", None)
    await audit(user, f"attendance.late_{payload.status}", target=record_id,
                target_type="attendance",
                meta={"employee_id": row.get("employee_id"), "date": row.get("date")})
    # Notify the employee
    emp = await sdb.employees.find_one({"id": row.get("employee_id")},
                                       {"_id": 0, "user_id": 1, "email": 1})
    target_uid = (emp or {}).get("user_id")
    if not target_uid:
        u = await sdb.users.find_one({"user_id": row.get("employee_id")}, {"_id": 0, "user_id": 1})
        target_uid = (u or {}).get("user_id")
    if target_uid:
        verdict = "approved (fine waived)" if payload.status == "approved" else "rejected (fine applies)"
        await emit([target_uid], "late_decided",
                   f"Late arrival {verdict} · {row.get('date')}",
                   body=(payload.review_notes or "").strip(),
                   link="/attendance", priority="normal",
                   meta={"attendance_id": record_id, "decision": payload.status},
                   dedup_key=f"late_decided_{record_id}")
    return await sdb.attendance.find_one({"id": record_id}, {"_id": 0})


# ---------- Attendance corrections ----------
@router.post("/attendance/corrections")
async def create_correction(payload: CorrectionIn, request: Request,
                            session_token: Optional[str] = Cookie(default=None),
                            authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    _validate_correction_request(
        payload.date, payload.requested_check_in, payload.requested_check_out,
    )
    emp_id = payload.employee_id if (payload.employee_id and has_any_permission(user, "employees.update", "attendance.update", "attendance.approve")) \
        else await _resolve_employee_id(user, None)
    nm = await _employee_name_map([emp_id])
    doc = {
        "id": new_id("corr_"),
        "employee_id": emp_id,
        "employee_name": nm.get(emp_id, user.get("name") or emp_id),
        "date": payload.date,
        "requested_check_in": payload.requested_check_in,
        "requested_check_out": payload.requested_check_out,
        "reason": payload.reason,
        "status": "pending",
        "created_at": iso_now(),
        "created_by": user["user_id"],
    }
    await sdb.attendance_corrections.insert_one(dict(doc))
    await emit_admins("attendance_correction",
                      f"Attendance correction: {doc['employee_name']}",
                      body=f"{payload.date} · {payload.reason}",
                      link="/attendance", priority="normal",
                      meta={"correction_id": doc["id"], "employee_id": emp_id},
                      dedup_key=f"corr_{doc['id']}",
                      org_id=user_org_id(user))
    return await sdb.attendance_corrections.find_one({"id": doc["id"]}, {"_id": 0})


@router.get("/attendance/corrections")
async def list_corrections(request: Request, status: Optional[str] = None,
                           mine: Optional[bool] = None,
                           session_token: Optional[str] = Cookie(default=None),
                           authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    q: dict = {}
    if mine or not has_any_permission(user, "employees.read", "attendance.update", "attendance.approve"):
        q["employee_id"] = await _resolve_employee_id(user, None)
    if status:
        q["status"] = status
    rows = await sdb.attendance_corrections.find(q, {"_id": 0}).sort("created_at", -1).to_list(500)
    missing = [r["employee_id"] for r in rows if not r.get("employee_name")]
    if missing:
        nm = await _employee_name_map(list(set(missing)))
        for r in rows:
            if not r.get("employee_name"):
                r["employee_name"] = nm.get(r["employee_id"], r["employee_id"])
    return rows


@router.put("/attendance/corrections/{corr_id}/review")
async def review_correction(corr_id: str, payload: CorrectionReviewIn, request: Request,
                            session_token: Optional[str] = Cookie(default=None),
                            authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    if not has_any_permission(user, "employees.update", "attendance.update", "attendance.approve"):
        raise HTTPException(403, "Missing permission: employees.update")
    if payload.status not in ("approved", "rejected"):
        raise HTTPException(400, "status must be approved or rejected")
    c, review_token = await _claim_pending_review(sdb.attendance_corrections, corr_id)
    try:
        if payload.status == "approved":
            # Apply the requested times before finalizing the review. The claim
            # makes concurrent approve/reject requests mutually exclusive.
            existing = await sdb.attendance.find_one(
                {"employee_id": c["employee_id"], "date": c["date"]}, {"_id": 0})
            updates = {"employee_id": c["employee_id"], "date": c["date"],
                       "is_manual": True, "updated_at": iso_now(),
                       "correction_id": corr_id}
            if c.get("requested_check_in"):
                updates["check_in"] = c["requested_check_in"]
            if c.get("requested_check_out"):
                updates["check_out"] = c["requested_check_out"]
            ci = updates.get("check_in") or (existing or {}).get("check_in")
            co = updates.get("check_out") or (existing or {}).get("check_out")
            if ci and co:
                d1 = _parse_correction_datetime(ci, "check-in")
                d2 = _parse_correction_datetime(co, "check-out")
                if d2 <= d1:
                    raise HTTPException(400, "Corrected check-out must be after check-in")
                wm = int((d2 - d1).total_seconds() // 60)
                updates["working_minutes"] = wm
                updates["worked_hours"] = round(wm / 60.0, 2)
                updates["status"] = "present" if wm >= 240 else "half_day"
            elif ci:
                updates["status"] = "present"
            if existing:
                await sdb.attendance.update_one({"id": existing["id"]}, {"$set": updates})
            else:
                updates["id"] = new_id("att_")
                updates["created_at"] = iso_now()
                await sdb.attendance.insert_one(dict(updates))

        result = await sdb.attendance_corrections.update_one(
            {"id": corr_id, "status": "pending", "review_token": review_token},
            {"$set": {
                "status": payload.status, "review_notes": payload.review_notes or "",
                "reviewed_by": user["user_id"], "reviewed_by_name": user.get("name"),
                "reviewed_at": iso_now(),
            }, "$unset": {"review_token": "", "review_started_at": ""}},
        )
        if result.modified_count != 1:
            raise RuntimeError("Correction review claim was lost")
    except Exception:
        await _release_review_claim(sdb.attendance_corrections, corr_id, review_token)
        raise
    await audit(user, f"attendance.correction_{payload.status}", target=corr_id,
                target_type="attendance_correction",
                meta={"employee_id": c["employee_id"], "date": c["date"]})
    return await sdb.attendance_corrections.find_one({"id": corr_id}, {"_id": 0})


# ---------- Per-employee attendance & payroll config ----------
@router.get("/attendance/employees/{employee_id}/config")
async def get_employee_config(employee_id: str, request: Request,
                              session_token: Optional[str] = Cookie(default=None),
                              authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    if not has_any_permission(user, "employees.read", "attendance.update", "attendance.approve"):
        raise HTTPException(403, "Missing permission: employees.read")
    emp = await sdb.employees.find_one({"id": employee_id}, {"_id": 0})
    if not emp:
        raise HTTPException(404, "Employee not found")
    data = {
        "id": emp["id"],
        "name": engine.emp_name(emp),
        "department": emp.get("department"),
        "shift_start": emp.get("shift_start"),
        "shift_end": emp.get("shift_end"),
        "grace_minutes": emp.get("grace_minutes"),
        "weekly_offs": emp.get("weekly_offs"),
        "half_day_min_minutes": emp.get("half_day_min_minutes"),
        "full_day_min_minutes": emp.get("full_day_min_minutes"),
    }
    if has_any_permission(user, "payroll.read", "payroll.create"):
        data.update({
            "monthly_salary": float(emp.get("monthly_salary") or 0),
            "net_monthly_structure": float((emp.get("salary") or {}).get("net_monthly") or 0),
            "effective_monthly_salary": engine.effective_monthly_salary(emp),
            "payroll_basis_days": emp.get("payroll_basis_days") or 26,
        })
    return data


@router.put("/attendance/employees/{employee_id}/config")
async def set_employee_config(employee_id: str, payload: EmployeeAttendanceConfigIn,
                              request: Request,
                              session_token: Optional[str] = Cookie(default=None),
                              authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    if not has_any_permission(user, "employees.update", "attendance.update", "attendance.approve"):
        raise HTTPException(403, "Missing permission: employees.update")
    emp = await sdb.employees.find_one({"id": employee_id}, {"_id": 0})
    if not emp:
        raise HTTPException(404, "Employee not found")
    patch = {k: v for k, v in payload.model_dump(exclude_unset=True).items()}
    if not patch:
        raise HTTPException(400, "No fields to update")
    compensation_fields = {"monthly_salary", "payroll_basis_days"}
    if compensation_fields.intersection(patch) and not has_permission(user, "payroll.create"):
        raise HTTPException(403, "Missing permission: payroll.create")
    patch["updated_at"] = iso_now()
    await sdb.employees.update_one({"id": employee_id}, {"$set": patch})
    await audit(user, "employee.attendance_config", target=employee_id, target_type="employee",
                meta={k: v for k, v in patch.items() if k != "updated_at"})
    return await get_employee_config(employee_id, request, session_token, authorization)
