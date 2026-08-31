"""Holiday Calendar routes.

A single per-org holiday calendar that feeds Attendance, Payroll, Dashboard.
Each holiday is a row keyed by ISO date:
    {id, date:"2026-01-26", name:"Republic Day", kind:"national|optional|festival|company",
     recurring:false, description?, active:true}

Endpoints
---------
- GET    /api/holidays?year=2026&include_weekly_off=true
- POST   /api/holidays               (Admin only)   – single row
- POST   /api/holidays/bulk          (Admin only)   – seed a year in one call
- PATCH  /api/holidays/{id}          (Admin only)
- DELETE /api/holidays/{id}          (Admin only)
- GET    /api/holidays/is-holiday/{date}   – helper for pickers/UI

Sync with attendance:
- `/attendance/monthly` (existing sheet endpoint) will now mark 'holiday' rows.
- We compute weekly-off + holiday overlap on read; no periodic job needed.
"""
from fastapi import APIRouter, HTTPException, Request, Cookie, Header
from typing import Optional, List
from datetime import date as _date, datetime, timedelta
from pydantic import BaseModel

from core.scoped_db import sdb
from core.helpers import iso_now, new_id
from core.deps import require_user
from core.rbac import has_permission
from core.audit import audit


router = APIRouter()

HOLIDAY_KINDS = ["national", "optional", "festival", "company", "regional"]


class HolidayIn(BaseModel):
    date: str                       # YYYY-MM-DD
    name: str
    kind: Optional[str] = "company"
    recurring: Optional[bool] = False   # if True, every year on same MM-DD
    description: Optional[str] = None
    active: Optional[bool] = True


class HolidayBulkIn(BaseModel):
    year: int
    holidays: List[HolidayIn]


class HolidayUpdate(BaseModel):
    name: Optional[str] = None
    kind: Optional[str] = None
    description: Optional[str] = None
    active: Optional[bool] = None
    recurring: Optional[bool] = None


def _validate_date(d: str) -> str:
    try:
        _date.fromisoformat(d)
        return d
    except Exception:
        raise HTTPException(400, f"Invalid date: {d}")


def _expand_recurring(rows: List[dict], year: int) -> List[dict]:
    """Materialise recurring holidays for the requested year."""
    out = []
    for r in rows:
        if not r.get("active", True):
            continue
        try:
            d = _date.fromisoformat(r["date"])
        except Exception:
            continue
        if r.get("recurring"):
            d = d.replace(year=year)
            row = {**r, "date": d.isoformat(), "materialized_from_recurring": True}
            out.append(row)
        elif d.year == year:
            out.append(r)
    return out


@router.get("/holidays")
async def list_holidays(request: Request,
                        year: Optional[int] = None,
                        include_weekly_off: bool = False,
                        session_token: Optional[str] = Cookie(default=None),
                        authorization: Optional[str] = Header(default=None)):
    """List holidays. Pass `year` to auto-expand recurring rows for that year."""
    await require_user(request, session_token, authorization)
    rows = await sdb.holidays.find({}, {"_id": 0}).sort("date", 1).to_list(2000)
    if year:
        rows = _expand_recurring(rows, year)
        rows.sort(key=lambda r: r["date"])
    resp = {"holidays": rows}
    if include_weekly_off and year:
        # Compute weekly-off dates from attendance policy
        pol = await sdb.attendance_policies.find_one({}, {"_id": 0}) or {}
        weekly_off_days = pol.get("weekly_off_days", [6])
        offs = []
        d = _date(year, 1, 1)
        end = _date(year, 12, 31)
        while d <= end:
            if d.weekday() in weekly_off_days:
                offs.append(d.isoformat())
            d += timedelta(days=1)
        resp["weekly_off_dates"] = offs
    return resp


@router.post("/holidays")
async def create_holiday(payload: HolidayIn, request: Request,
                         session_token: Optional[str] = Cookie(default=None),
                         authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    if not has_permission(user, "*.*"):
        raise HTTPException(403, "Admin only")
    if payload.kind and payload.kind not in HOLIDAY_KINDS:
        raise HTTPException(400, f"kind must be one of {HOLIDAY_KINDS}")
    _validate_date(payload.date)
    dup = await sdb.holidays.find_one({"date": payload.date, "name": payload.name}, {"_id": 0})
    if dup:
        raise HTTPException(409, "Holiday already exists on that date with the same name")
    doc = payload.model_dump()
    doc["id"] = new_id("hol_")
    doc["created_at"] = iso_now()
    doc["created_by"] = user["user_id"]
    await sdb.holidays.insert_one(dict(doc))
    await audit(user, "holiday.create", target=doc["id"], target_type="holiday",
                meta={"date": doc["date"], "name": doc["name"], "kind": doc["kind"]})
    return doc


@router.post("/holidays/bulk")
async def bulk_create(payload: HolidayBulkIn, request: Request,
                      session_token: Optional[str] = Cookie(default=None),
                      authorization: Optional[str] = Header(default=None)):
    """Idempotently seed a whole year of holidays. Skips duplicates."""
    user = await require_user(request, session_token, authorization)
    if not has_permission(user, "*.*"):
        raise HTTPException(403, "Admin only")
    inserted = 0
    for h in payload.holidays:
        _validate_date(h.date)
        if await sdb.holidays.find_one({"date": h.date, "name": h.name}, {"_id": 0}):
            continue
        doc = h.model_dump()
        doc["id"] = new_id("hol_")
        doc["created_at"] = iso_now()
        doc["created_by"] = user["user_id"]
        await sdb.holidays.insert_one(dict(doc))
        inserted += 1
    await audit(user, "holiday.bulk_create", target=str(payload.year), target_type="holiday",
                meta={"year": payload.year, "inserted": inserted, "requested": len(payload.holidays)})
    return {"ok": True, "inserted": inserted, "requested": len(payload.holidays)}


@router.patch("/holidays/{holiday_id}")
async def update_holiday(holiday_id: str, payload: HolidayUpdate, request: Request,
                         session_token: Optional[str] = Cookie(default=None),
                         authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    if not has_permission(user, "*.*"):
        raise HTTPException(403, "Admin only")
    patch = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not patch:
        raise HTTPException(400, "No fields to update")
    if patch.get("kind") and patch["kind"] not in HOLIDAY_KINDS:
        raise HTTPException(400, f"kind must be one of {HOLIDAY_KINDS}")
    patch["updated_at"] = iso_now()
    r = await sdb.holidays.update_one({"id": holiday_id}, {"$set": patch})
    if not r.matched_count:
        raise HTTPException(404, "Holiday not found")
    return await sdb.holidays.find_one({"id": holiday_id}, {"_id": 0})


@router.delete("/holidays/{holiday_id}")
async def delete_holiday(holiday_id: str, request: Request,
                         session_token: Optional[str] = Cookie(default=None),
                         authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    if not has_permission(user, "*.*"):
        raise HTTPException(403, "Admin only")
    r = await sdb.holidays.delete_one({"id": holiday_id})
    if not r.deleted_count:
        raise HTTPException(404, "Holiday not found")
    await audit(user, "holiday.delete", target=holiday_id, target_type="holiday")
    return {"ok": True}


@router.get("/holidays/is-holiday/{date_str}")
async def is_holiday(date_str: str, request: Request,
                     session_token: Optional[str] = Cookie(default=None),
                     authorization: Optional[str] = Header(default=None)):
    """Check if a specific date is a holiday (also considers weekly-off + recurring)."""
    await require_user(request, session_token, authorization)
    _validate_date(date_str)
    d = _date.fromisoformat(date_str)

    # Recurring match: same month+day
    rows = await sdb.holidays.find({"active": True}, {"_id": 0}).to_list(2000)
    match = None
    for r in rows:
        try:
            hd = _date.fromisoformat(r["date"])
        except Exception:
            continue
        if r.get("recurring") and hd.month == d.month and hd.day == d.day:
            match = r; break
        if r["date"] == date_str:
            match = r; break

    # Weekly off
    pol = await sdb.attendance_policies.find_one({}, {"_id": 0}) or {}
    weekly_off = d.weekday() in (pol.get("weekly_off_days") or [6])

    return {
        "date": date_str,
        "is_holiday": bool(match) or weekly_off,
        "holiday": match,
        "is_weekly_off": weekly_off,
    }
