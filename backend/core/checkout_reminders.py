"""Evening "you haven't checked out" reminders.

Production on 2026-11-19: 51 of 100 attendance rows were past days with a
check-in and no check-out (one employee alone 24), so working hours were
unknown. Nothing reminded people to check out.

Every run (the server calls it every 15 minutes) looks at today's open
check-ins in each active workspace and notifies the person once their shift
end (employee shift_end, else the workspace's office_end, else 19:00) plus a
grace hour has passed. One reminder per person per day (dedup key), through
the normal notification bell, so per-user notification settings apply.
Nothing is changed in the attendance record itself: an unfinished punch is
never auto-completed.
"""
from datetime import datetime, timedelta
from typing import Optional

from core.attendance_engine import _hhmm_ist, now_ist
from core.db import db

GRACE = timedelta(minutes=60)
DEFAULT_END = "19:00"


def _minutes(hhmm: Optional[str]) -> Optional[int]:
    try:
        h, m = str(hhmm).split(":")
        return int(h) * 60 + int(m)
    except (TypeError, ValueError):
        return None


def due(shift_end: Optional[str], now: datetime) -> bool:
    end = _minutes(shift_end) or _minutes(DEFAULT_END)
    return now.hour * 60 + now.minute >= end + int(GRACE.total_seconds() // 60)


async def send_checkout_reminders(now: Optional[datetime] = None) -> dict:
    from core.notifications import emit
    now = now or now_ist()
    today = now.date().isoformat()
    sent, checked = 0, 0
    async for org in db.organizations.find({"is_active": {"$ne": False}, "is_suspended": {"$ne": True}},
                                           {"_id": 0, "org_id": 1}):
        org_id = org.get("org_id")
        if not org_id:
            continue
        policy = await db.attendance_policies.find_one({"org_id": org_id}, {"_id": 0, "office_end": 1}) or {}
        async for row in db.attendance.find(
                {"org_id": org_id, "date": today, "check_in": {"$nin": [None, ""]},
                 "check_out": {"$in": [None, ""]}},
                {"_id": 0, "employee_id": 1, "check_in": 1}):
            checked += 1
            emp = await db.employees.find_one({"org_id": org_id, "id": row.get("employee_id")},
                                              {"_id": 0, "user_id": 1, "email": 1, "shift_end": 1})
            if not emp or not due(emp.get("shift_end") or policy.get("office_end"), now):
                continue
            uid = emp.get("user_id")
            if not uid and emp.get("email"):
                u = await db.users.find_one({"org_id": org_id, "email": emp["email"]}, {"_id": 0, "user_id": 1})
                uid = (u or {}).get("user_id")
            if not uid:
                continue
            at = _hhmm_ist(row.get("check_in")) or ""          # stored as UTC; show IST
            sent += await emit(
                [uid], "attendance_pending", "You haven't checked out today",
                body=(f"You checked in at {at}. " if at else "")
                + "Check out on the Attendance page, or ask for a correction if you have already left.",
                link="/attendance", priority="normal", dedup_key=f"checkout-reminder:{today}",
                meta={"date": today})
    return {"open_check_ins": checked, "reminders": sent}
