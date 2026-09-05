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
from core.rbac import has_permission
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
    if not has_permission(user, "*.*"):
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
@router.get("/attendance/locations")
async def list_locations(request: Request,
                         session_token: Optional[str] = Cookie(default=None),
                         authorization: Optional[str] = Header(default=None)):
    await require_user(request, session_token, authorization)
    rows = await sdb.office_locations.find({}, {"_id": 0}).sort("kind", 1).to_list(200)
    return rows


@router.post("/attendance/locations")
async def create_location(payload: GeoLocationIn, request: Request,
                          session_token: Optional[str] = Cookie(default=None),
                          authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    if not has_permission(user, "*.*"):
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
    if not has_permission(user, "*.*"):
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
                             project_id: Optional[str] = None) -> dict:
    """Find the nearest matching location and check if within radius.

    Returns dict {inside, matched_location, distance_m, nearest}.
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
    inside = best_dist <= float(best.get("radius_m", 150))
    return {
        "inside": inside,
        "matched_location": {"id": best["id"], "name": best["name"],
                             "kind": best["kind"], "radius_m": best.get("radius_m")},
        "distance_m": round(best_dist, 1),
        "reason": None if inside else
                  f"You are {round(best_dist)}m from '{best['name']}' (allowed: {best.get('radius_m', 150)}m)",
    }


@router.get("/attendance/geo-check")
async def geo_check(lat: float, lng: float, kind: str = "office",
                    project_id: Optional[str] = None, request: Request = None,
                    session_token: Optional[str] = Cookie(default=None),
                    authorization: Optional[str] = Header(default=None)):
    """Quick check before check-in — tells UI whether user is inside a fence."""
    await require_user(request, session_token, authorization)
    return await _resolve_geo_fence(kind, lat, lng, project_id)


# ==================================================
# Helpers
# ==================================================
def _late_minutes(office_start_hhmm: str, grace: int) -> int:
    """Best-effort lateness marker relative to office_start.
    Returns 0 if within grace, else minutes late."""
    try:
        h, m = office_start_hhmm.split(":")
        expected = int(h) * 60 + int(m) + int(grace or 0)
        n = now_utc()
        # Approximate local IST (UTC+5:30); adjust if needed via policy in future.
        local = n + timedelta(hours=5, minutes=30)
        actual = local.hour * 60 + local.minute
        return max(actual - expected, 0)
    except Exception:
        return 0


def _client_ip(request: Request) -> str:
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else ""


async def _resolve_employee_id(user: dict, provided: Optional[str]) -> str:
    """Fall back to employee mapping (by user_id or email) if not provided."""
    if provided:
        return provided
    # Try to find employee doc linked to this user
    emp = await sdb.employees.find_one(
        {"$or": [{"user_id": user["user_id"]}, {"email": user.get("email")}]},
        {"_id": 0, "id": 1},
    )
    if emp:
        return emp["id"]
    # Otherwise use the user_id itself (still usable for solo admin dev)
    return user["user_id"]


def _today() -> str:
    return now_utc().date().isoformat()


async def _employee_name_map(ids: list) -> dict:
    """id -> display name for a set of employee ids (users fallback)."""
    out = {}
    if not ids:
        return out
    async for e in sdb.employees.find({"id": {"$in": ids}}, {"_id": 0}):
        out[e["id"]] = engine.emp_name(e)
    remaining = [i for i in ids if i not in out]
    if remaining:
        async for u in db.users.find({"user_id": {"$in": remaining}},
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
    emp_id = await _resolve_employee_id(user, payload.employee_id)
    today = _today()

    existing = await sdb.attendance.find_one({"employee_id": emp_id, "date": today}, {"_id": 0})
    if existing and existing.get("check_in"):
        raise HTTPException(status_code=400, detail="Already checked in today")

    att_type = payload.attendance_type or "office"
    policy = await _get_attendance_policy()

    # ---- Auto-holiday / weekly-off short-circuit ----
    # If today is a company holiday or weekly-off, mark the day accordingly
    # and skip the geo-fence + late-mark logic entirely.
    is_holiday_today, holiday_row = await _is_holiday(today)
    is_weekly_off = datetime.strptime(today, "%Y-%m-%d").weekday() in (policy.get("weekly_off_days") or [])
    if (is_holiday_today or is_weekly_off) and att_type == "office":
        holiday_doc = {
            "id": existing["id"] if existing else new_id("att_"),
            "employee_id": emp_id, "employee_name": user.get("name"),
            "date": today, "check_in": iso_now(),
            "attendance_type": att_type,
            "status": "holiday", "approval_status": "auto",
            "holiday_name": (holiday_row or {}).get("name") if is_holiday_today
                              else "Weekly Off",
            "holiday_kind": (holiday_row or {}).get("kind") if is_holiday_today
                              else "weekly_off",
        }
        if existing:
            await sdb.attendance.update_one({"id": existing["id"]}, {"$set": holiday_doc})
        else:
            holiday_doc["created_at"] = iso_now()
            await sdb.attendance.insert_one(dict(holiday_doc))
        return await sdb.attendance.find_one({"id": holiday_doc["id"]}, {"_id": 0})

    # ---- Geo-fence enforcement ----
    geo_result = {"inside": True, "matched_location": None, "distance_m": None}
    is_office = att_type == "office"
    geo_needed = policy.get("geo_fencing_enabled") and (
        not is_office or policy.get("require_geo_for_office")
    )
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
                                              payload.project_id)
        # For office: fall back to policy default fence if no explicit location
        if not geo_result.get("matched_location") and is_office \
                and policy.get("default_office_lat") is not None:
            d = _haversine_m(payload.lat, payload.lng,
                             policy["default_office_lat"], policy["default_office_lng"])
            radius = policy.get("default_office_radius_m") or 150
            geo_result = {
                "inside": d <= radius,
                "matched_location": {"id": "policy_default", "name": "Head Office",
                                     "kind": "office", "radius_m": radius},
                "distance_m": round(d, 1),
                "reason": None if d <= radius else
                          f"You are {round(d)}m from Head Office (allowed: {radius}m)",
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

    # Determine final status
    if geo_needed and not geo_result["inside"] and payload.force_outside:
        status = "pending_approval"
        approval_status = "pending"
    elif is_office:
        status = "present"
        approval_status = "auto"
    else:
        # non-office types need HR approval per existing behaviour
        status = "pending_approval"
        approval_status = "pending"

    # Late arrival reason enforcement
    late_min = _late_minutes(policy["office_start"], policy.get("grace_minutes", 0)) if is_office else None
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
        "employee_name": user.get("name"),
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
    if existing:
        await sdb.attendance.update_one({"id": existing["id"]}, {"$set": doc})
    else:
        doc["created_at"] = iso_now()
        await sdb.attendance.insert_one(dict(doc))
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
            f"Attendance approval: {user.get('name') or emp_id}",
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

    await sdb.attendance.update_one(
        {"id": existing["id"]},
        {"$set": {
            "check_out": iso_now(),
            "check_out_ip": _client_ip(request),
            "check_out_notes": payload.notes or "",
            "worked_hours": hours,
            "working_minutes": working_minutes,
            "status": status,
            "updated_at": iso_now(),
        }},
    )
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
    y = year or now_utc().year
    m = month or now_utc().month
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
    if not has_permission(user, "employees.read"):
        raise HTTPException(status_code=403, detail="Missing permission: employees.read")

    y = year or now_utc().year
    m = month or now_utc().month
    start, end = _month_bounds(y, m)

    employees = await sdb.employees.find({}, {"_id": 0, "id": 1, "name": 1, "employee_id": 1, "designation": 1}).to_list(500)
    rows = []
    for e in employees:
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
    if not has_permission(user, "employees.update"):
        raise HTTPException(status_code=403, detail="Missing permission: employees.update")
    if payload.status not in ATTENDANCE_STATUSES:
        raise HTTPException(status_code=400, detail="Invalid status")

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
    if not has_permission(user, "employees.update"):
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
    d1 = _date.fromisoformat(payload.from_date)
    d2 = _date.fromisoformat(payload.to_date)
    if d2 < d1:
        raise HTTPException(status_code=400, detail="to_date before from_date")
    days = (d2 - d1).days + 1

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
    if mine:
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
    if not has_permission(user, "employees.update"):
        raise HTTPException(status_code=403, detail="Missing permission: employees.update")
    lv = await sdb.leaves.find_one({"id": leave_id}, {"_id": 0})
    if not lv:
        raise HTTPException(status_code=404, detail="Leave not found")
    if lv["status"] != "pending":
        raise HTTPException(status_code=400, detail=f"Leave already {lv['status']}")

    if payload.action == "approve":
        new_status = "approved"
    elif payload.action == "reject":
        new_status = "rejected"
    else:
        raise HTTPException(status_code=400, detail="Invalid action")

    await sdb.leaves.update_one({"id": leave_id}, {"$set": {
        "status": new_status,
        "action_by": user["user_id"],
        "action_by_name": user.get("name"),
        "action_at": iso_now(),
        "action_remarks": payload.remarks or "",
    }})

    # If approved, back-fill attendance as leave for each date in range
    if new_status == "approved":
        d1 = _date.fromisoformat(lv["from_date"])
        d2 = _date.fromisoformat(lv["to_date"])
        cur = d1
        while cur <= d2:
            ds = cur.isoformat()
            await sdb.attendance.update_one(
                {"employee_id": lv["employee_id"], "date": ds},
                {"$set": {
                    "employee_id": lv["employee_id"],
                    "date": ds,
                    "status": "leave",
                    "leave_type": lv["leave_type"],
                    "leave_id": lv["id"],
                    "updated_at": iso_now(),
                }, "$setOnInsert": {"id": new_id("att_"), "created_at": iso_now()}},
                upsert=True,
            )
            cur += timedelta(days=1)

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
    await require_user(request, session_token, authorization)
    y = year or now_utc().year
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
    if not has_permission(user, "employees.update"):
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
    if not has_permission(user, "employees.update"):
        raise HTTPException(status_code=403, detail="Missing permission")
    row = await sdb.attendance.find_one({"id": att_id}, {"_id": 0})
    if not row:
        raise HTTPException(status_code=404, detail="Attendance record not found")
    if row.get("approval_status") != "pending":
        raise HTTPException(status_code=400, detail=f"Already {row.get('approval_status')}")

    if payload.action == "approve":
        new_status = "present"
        approval_status = "approved"
    elif payload.action == "reject":
        new_status = "absent"
        approval_status = "rejected"
    else:
        raise HTTPException(status_code=400, detail="Invalid action")

    await sdb.attendance.update_one({"id": att_id}, {"$set": {
        "status": new_status,
        "approval_status": approval_status,
        "approved_by": user["user_id"],
        "approved_by_name": user.get("name"),
        "approved_at": iso_now(),
        "approval_remarks": payload.remarks or "",
    }})
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
        u = await db.users.find_one({"email": emp["email"].lower()}, {"_id": 0, "user_id": 1})
        target_user_id = (u or {}).get("user_id")
    else:
        # solo-admin fallback: employee_id may be the user_id itself
        u = await db.users.find_one({"user_id": row.get("employee_id")}, {"_id": 0, "user_id": 1})
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
    return await sdb.attendance.find_one({"id": att_id}, {"_id": 0})


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
    if not has_permission(user, "employees.read"):
        # Employees may only view their own summary
        own = await _resolve_employee_id(user, None)
        if own != employee_id:
            raise HTTPException(403, "You can only view your own attendance summary")
    emp = await sdb.employees.find_one({"id": employee_id}, {"_id": 0})
    if not emp:
        # Solo-admin fallback: user without an employee record
        emp = {"id": employee_id, "first_name": user.get("name") or "", "last_name": ""}
    y = year or now_utc().year
    m = month or now_utc().month
    policy = await _get_attendance_policy()
    return await engine.monthly_summary(emp, y, m, policy)


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
    y = year or now_utc().year
    m = month or now_utc().month
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
    if not has_permission(user, "employees.read"):
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
    if not has_permission(user, "employees.read"):
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
    if not has_permission(user, "employees.read"):
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
    if not has_permission(user, "employees.update"):
        raise HTTPException(403, "Missing permission: employees.update")
    if payload.status not in ATTENDANCE_STATUSES:
        raise HTTPException(400, "Invalid status")
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
        try:
            ci = datetime.fromisoformat(payload.check_in.replace("Z", "+00:00"))
            co = datetime.fromisoformat(payload.check_out.replace("Z", "+00:00"))
            wm = max(int((co - ci).total_seconds() // 60), 0)
            updates["working_minutes"] = wm
            updates["worked_hours"] = round(wm / 60.0, 2)
        except Exception:
            pass
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
    if not has_permission(user, "employees.update"):
        raise HTTPException(403, "Missing permission: employees.update")
    if not payload.hours or payload.hours <= 0 or payload.hours > 12:
        raise HTTPException(400, "Hours must be between 0 and 12")
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
    if not has_permission(user, "employees.read"):
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
    if not has_permission(user, "employees.update"):
        raise HTTPException(403, "Missing permission: employees.update")
    if payload.status not in ("approved", "rejected"):
        raise HTTPException(400, "status must be approved or rejected")
    row = await sdb.attendance.find_one({"id": record_id}, {"_id": 0})
    if not row:
        raise HTTPException(404, "Attendance record not found")
    if not row.get("late_approval_status") or row.get("late_approval_status") == "not_required":
        raise HTTPException(400, "This record is not a late arrival awaiting review")
    # Approving/excusing a late arrival waives its fine; rejecting keeps it.
    await sdb.attendance.update_one({"id": record_id}, {"$set": {
        "late_approval_status": payload.status,
        "late_fine_waived": payload.status == "approved",
        "late_reviewed_by": user["user_id"],
        "late_reviewed_by_name": user.get("name"),
        "late_reviewed_at": iso_now(),
        "late_review_notes": payload.review_notes or "",
    }})
    await audit(user, f"attendance.late_{payload.status}", target=record_id,
                target_type="attendance",
                meta={"employee_id": row.get("employee_id"), "date": row.get("date")})
    # Notify the employee
    emp = await sdb.employees.find_one({"id": row.get("employee_id")},
                                       {"_id": 0, "user_id": 1, "email": 1})
    target_uid = (emp or {}).get("user_id")
    if not target_uid:
        u = await db.users.find_one({"user_id": row.get("employee_id")}, {"_id": 0, "user_id": 1})
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
    emp_id = payload.employee_id if (payload.employee_id and has_permission(user, "employees.update")) \
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
    if mine or not has_permission(user, "employees.read"):
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
    if not has_permission(user, "employees.update"):
        raise HTTPException(403, "Missing permission: employees.update")
    if payload.status not in ("approved", "rejected"):
        raise HTTPException(400, "status must be approved or rejected")
    c = await sdb.attendance_corrections.find_one({"id": corr_id}, {"_id": 0})
    if not c:
        raise HTTPException(404, "Correction not found")
    if c.get("status") != "pending":
        raise HTTPException(400, f"Correction already {c.get('status')}")
    await sdb.attendance_corrections.update_one({"id": corr_id}, {"$set": {
        "status": payload.status,
        "review_notes": payload.review_notes or "",
        "reviewed_by": user["user_id"],
        "reviewed_by_name": user.get("name"),
        "reviewed_at": iso_now(),
    }})
    if payload.status == "approved":
        # Apply the requested times to the attendance row (upsert)
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
            try:
                d1 = datetime.fromisoformat(str(ci).replace("Z", "+00:00"))
                d2 = datetime.fromisoformat(str(co).replace("Z", "+00:00"))
                wm = max(int((d2 - d1).total_seconds() // 60), 0)
                updates["working_minutes"] = wm
                updates["worked_hours"] = round(wm / 60.0, 2)
                updates["status"] = "present" if wm >= 240 else "half_day"
            except Exception:
                pass
        if existing:
            await sdb.attendance.update_one({"id": existing["id"]}, {"$set": updates})
        else:
            updates["id"] = new_id("att_")
            updates["created_at"] = iso_now()
            await sdb.attendance.insert_one(dict(updates))
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
    if not has_permission(user, "employees.read"):
        raise HTTPException(403, "Missing permission: employees.read")
    emp = await sdb.employees.find_one({"id": employee_id}, {"_id": 0})
    if not emp:
        raise HTTPException(404, "Employee not found")
    return {
        "id": emp["id"],
        "name": engine.emp_name(emp),
        "department": emp.get("department"),
        "shift_start": emp.get("shift_start"),
        "shift_end": emp.get("shift_end"),
        "grace_minutes": emp.get("grace_minutes"),
        "weekly_offs": emp.get("weekly_offs"),
        "half_day_min_minutes": emp.get("half_day_min_minutes"),
        "full_day_min_minutes": emp.get("full_day_min_minutes"),
        "monthly_salary": float(emp.get("monthly_salary") or 0),
        "net_monthly_structure": float((emp.get("salary") or {}).get("net_monthly") or 0),
        "effective_monthly_salary": engine.effective_monthly_salary(emp),
        "payroll_basis_days": emp.get("payroll_basis_days") or 26,
    }


@router.put("/attendance/employees/{employee_id}/config")
async def set_employee_config(employee_id: str, payload: EmployeeAttendanceConfigIn,
                              request: Request,
                              session_token: Optional[str] = Cookie(default=None),
                              authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    if not has_permission(user, "employees.update"):
        raise HTTPException(403, "Missing permission: employees.update")
    emp = await sdb.employees.find_one({"id": employee_id}, {"_id": 0})
    if not emp:
        raise HTTPException(404, "Employee not found")
    patch = {k: v for k, v in payload.model_dump(exclude_unset=True).items()}
    if not patch:
        raise HTTPException(400, "No fields to update")
    patch["updated_at"] = iso_now()
    await sdb.employees.update_one({"id": employee_id}, {"$set": patch})
    await audit(user, "employee.attendance_config", target=employee_id, target_type="employee",
                meta={k: v for k, v in patch.items() if k != "updated_at"})
    return await get_employee_config(employee_id, request, session_token, authorization)
