"""Attendance + Leave routes.

- Employees: `POST /attendance/check-in`, `/check-out`, `GET /attendance/me/summary`
- HR/Admin: monthly sheet, override, leave approval, leave rule config
- Data shape kept payroll-friendly: `attendance` docs keyed by (employee_id, date).
"""
from fastapi import APIRouter, HTTPException, Request, Cookie, Header
from typing import Optional
from datetime import date as _date, datetime, timezone, timedelta

from core.db import db
from core.helpers import now_utc, iso_now, new_id
from core.deps import require_user
from core.rbac import has_permission
from models.attendance import (
    CheckInIn, CheckOutIn, AttendanceOverrideIn,
    LeaveRequestIn, LeaveActionIn, LeaveRuleIn, ApproveAttendanceIn,
    ATTENDANCE_STATUSES, LEAVE_TYPES, LEAVE_STATUSES, DEFAULT_LEAVE_ALLOWANCE,
)

router = APIRouter()


# ==================================================
# Helpers
# ==================================================
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
    emp = await db.employees.find_one(
        {"$or": [{"user_id": user["user_id"]}, {"email": user.get("email")}]},
        {"_id": 0, "id": 1},
    )
    if emp:
        return emp["id"]
    # Otherwise use the user_id itself (still usable for solo admin dev)
    return user["user_id"]


def _today() -> str:
    return now_utc().date().isoformat()


def _month_bounds(year: int, month: int):
    start = _date(year, month, 1).isoformat()
    if month == 12:
        end = _date(year + 1, 1, 1).isoformat()
    else:
        end = _date(year, month + 1, 1).isoformat()
    return start, end


async def _get_leave_rule() -> dict:
    doc = await db.leave_rules.find_one({"id": "default"}, {"_id": 0})
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

    existing = await db.attendance.find_one({"employee_id": emp_id, "date": today}, {"_id": 0})
    if existing and existing.get("check_in"):
        raise HTTPException(status_code=400, detail="Already checked in today")

    doc = {
        "id": existing["id"] if existing else new_id("att_"),
        "employee_id": emp_id,
        "employee_name": user.get("name"),
        "date": today,
        "check_in": iso_now(),
        "check_in_ip": _client_ip(request),
        "check_in_location": payload.location or "",
        "check_in_notes": payload.notes or "",
        "attendance_type": payload.attendance_type or "office",
        "project_id": payload.project_id,
        "site_location": payload.site_location,
        "expected_time": payload.expected_time,
        "site_reason": payload.reason,
        # Site visits require approval; office check-in is auto-approved
        "status": "present" if (payload.attendance_type or "office") == "office" else "pending_approval",
        "approval_status": "auto" if (payload.attendance_type or "office") == "office" else "pending",
    }
    if existing:
        await db.attendance.update_one({"id": existing["id"]}, {"$set": doc})
    else:
        doc["created_at"] = iso_now()
        await db.attendance.insert_one(dict(doc))
    return await db.attendance.find_one({"id": doc["id"]}, {"_id": 0})


@router.post("/attendance/check-out")
async def check_out(payload: CheckOutIn, request: Request,
                    session_token: Optional[str] = Cookie(default=None),
                    authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    emp_id = await _resolve_employee_id(user, payload.employee_id)
    today = _today()

    existing = await db.attendance.find_one({"employee_id": emp_id, "date": today}, {"_id": 0})
    if not existing or not existing.get("check_in"):
        raise HTTPException(status_code=400, detail="Not checked in today")
    if existing.get("check_out"):
        raise HTTPException(status_code=400, detail="Already checked out today")

    ci = datetime.fromisoformat(existing["check_in"])
    now = now_utc()
    hours = round((now - ci).total_seconds() / 3600.0, 2)
    status = existing["status"]
    if hours < 4:
        status = "half_day"

    await db.attendance.update_one(
        {"id": existing["id"]},
        {"$set": {
            "check_out": iso_now(),
            "check_out_ip": _client_ip(request),
            "check_out_notes": payload.notes or "",
            "worked_hours": hours,
            "status": status,
            "updated_at": iso_now(),
        }},
    )
    return await db.attendance.find_one({"id": existing["id"]}, {"_id": 0})


# ==================================================
# My attendance summary
# ==================================================
@router.get("/attendance/me/today")
async def my_today(request: Request,
                   session_token: Optional[str] = Cookie(default=None),
                   authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    emp_id = await _resolve_employee_id(user, None)
    row = await db.attendance.find_one({"employee_id": emp_id, "date": _today()}, {"_id": 0})
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
    rows = await db.attendance.find(
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

    employees = await db.employees.find({}, {"_id": 0, "id": 1, "name": 1, "employee_id": 1, "designation": 1}).to_list(500)
    rows = []
    for e in employees:
        recs = await db.attendance.find(
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

    existing = await db.attendance.find_one(
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
        await db.attendance.update_one({"id": existing["id"]}, {"$set": updates})
        return await db.attendance.find_one({"id": existing["id"]}, {"_id": 0})
    updates["id"] = new_id("att_")
    updates["created_at"] = iso_now()
    await db.attendance.insert_one(dict(updates))
    return await db.attendance.find_one({"id": updates["id"]}, {"_id": 0})


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
    await db.leave_rules.replace_one({"id": "default"}, doc, upsert=True)
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

    doc = {
        "id": new_id("lv_"),
        "employee_id": emp_id,
        "employee_name": user.get("name"),
        "leave_type": payload.leave_type,
        "from_date": payload.from_date,
        "to_date": payload.to_date,
        "days": days,
        "reason": payload.reason or "",
        "status": "pending",
        "created_at": iso_now(),
        "created_by": user["user_id"],
    }
    await db.leaves.insert_one(dict(doc))
    return await db.leaves.find_one({"id": doc["id"]}, {"_id": 0})


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
    rows = await db.leaves.find(q, {"_id": 0}).sort("created_at", -1).to_list(500)
    return rows


@router.post("/leaves/{leave_id}/action")
async def act_on_leave(leave_id: str, payload: LeaveActionIn, request: Request,
                       session_token: Optional[str] = Cookie(default=None),
                       authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    if not has_permission(user, "employees.update"):
        raise HTTPException(status_code=403, detail="Missing permission: employees.update")
    lv = await db.leaves.find_one({"id": leave_id}, {"_id": 0})
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

    await db.leaves.update_one({"id": leave_id}, {"$set": {
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
            await db.attendance.update_one(
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

    return await db.leaves.find_one({"id": leave_id}, {"_id": 0})


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
    cur = db.leaves.find({
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
    rows = await db.attendance.find(
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
    row = await db.attendance.find_one({"id": att_id}, {"_id": 0})
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

    await db.attendance.update_one({"id": att_id}, {"$set": {
        "status": new_status,
        "approval_status": approval_status,
        "approved_by": user["user_id"],
        "approved_by_name": user.get("name"),
        "approved_at": iso_now(),
        "approval_remarks": payload.remarks or "",
    }})
    return await db.attendance.find_one({"id": att_id}, {"_id": 0})
