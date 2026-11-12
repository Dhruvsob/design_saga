"""Site visits and the live check-in map (Phase 3).

Site visit (from a project):
- GPS is required. The project's site geo-fence decides whether the pin is
  inside; outside the fence, or with no fence for the project, the visit is
  only recorded when the person explicitly sends it for approval (the same
  rule attendance applies to a site-visit punch).
- The first visit of the day is also the day's attendance check-in (type
  ``site_visit``, through the attendance check-in itself, so late/geo/approval
  rules stay in one place). Later visits are linked to that attendance record.
- Photos (phone camera) are stored privately through ``services.local_files``
  (type/size checks, tenant quota) with the server time and the device GPS,
  and are only served to people who may see the visit. Never a public URL.
- Every visit is written to the project's activity timeline (no coordinates).

Live map: today's check-in and site-visit pins plus office/site fences.

Who sees what:
- staff: their own visits;
- managers (attendance approval, e.g. Project Manager): visits on projects
  they manage and of employees on those projects' teams;
- HR / Admin / Director (employees.update or attendance.update): everyone.
Every query runs through ``sdb`` (tenant scope).
"""
from datetime import date as _date, datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Cookie, File, Form, Header, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from pymongo.errors import DuplicateKeyError

from core import attendance_engine as engine
from core.access_control import get_visible_project, merge_query, user_identity_ids
from core.audit import audit
from core.deps import require_user
from core.helpers import iso_now, new_id, now_utc
from core.limits import MAX_LIST_ROWS
from core.rbac import has_any_permission, has_permission
from core.scoped_db import sdb
from core.tenancy import user_org_id
from models.attendance import CheckInIn
from routes import attendance as att
from services.local_files import remove_upload, resolve_storage_key, save_upload
from core.limits import tenant_storage_quota_bytes

router = APIRouter()

MAX_PHOTOS_PER_VISIT = 20
PHOTO_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
# Photos and notes can be added until the end of the visit's own day.
_PUBLIC_PHOTO_FIELDS = ("id", "content_type", "size", "captured_at", "client_taken_at",
                        "lat", "lng", "accuracy_m", "distance_m", "distance_from",
                        "caption", "uploaded_by", "uploaded_by_name")


# ---------------------------------------------------------------- models
class SiteVisitIn(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)
    accuracy_m: Optional[float] = Field(default=None, ge=0, le=100000)
    notes: Optional[str] = Field(default="", max_length=2000)
    force_outside: bool = False
    device_id: Optional[str] = Field(default=None, max_length=200)
    device_label: Optional[str] = Field(default=None, max_length=200)


class SiteVisitCheckOutIn(BaseModel):
    lat: Optional[float] = Field(default=None, ge=-90, le=90)
    lng: Optional[float] = Field(default=None, ge=-180, le=180)
    accuracy_m: Optional[float] = Field(default=None, ge=0, le=100000)
    notes: Optional[str] = Field(default=None, max_length=2000)


class SiteVisitNotesIn(BaseModel):
    notes: str = Field(default="", max_length=2000)


# ---------------------------------------------------------------- access
def sees_everyone(user: dict) -> bool:
    return has_any_permission(user, "employees.update", "attendance.update")


def is_team_manager(user: dict) -> bool:
    return has_permission(user, "attendance.approve")


async def managed_team(user: dict) -> tuple[list, list]:
    """(projects the user manages, employee ids on those projects' teams)."""
    ids = list(await user_identity_ids(user))
    projects = await sdb.projects.find(
        {"project_manager_id": {"$in": ids}}, {"_id": 0, "id": 1, "team_ids": 1},
    ).to_list(MAX_LIST_ROWS)
    project_ids = [p["id"] for p in projects if p.get("id")]
    refs = sorted({str(m) for p in projects for m in (p.get("team_ids") or []) if m})
    employee_ids: list = []
    if refs:
        rows = await sdb.employees.find(
            {"$or": [{"id": {"$in": refs}}, {"user_id": {"$in": refs}}]}, {"_id": 0, "id": 1},
        ).to_list(MAX_LIST_ROWS)
        employee_ids = [r["id"] for r in rows if r.get("id")]
    return project_ids, employee_ids


async def visit_scope(user: dict) -> tuple[dict, str]:
    """Mongo filter for the visits this user may see, and its name."""
    if sees_everyone(user):
        return {}, "all"
    own = sorted(await user_identity_ids(user))
    terms = [{"employee_id": {"$in": own}}, {"user_id": user["user_id"]}]
    label = "own"
    if is_team_manager(user):
        project_ids, employee_ids = await managed_team(user)
        if project_ids:
            terms.append({"project_id": {"$in": project_ids}})
        if employee_ids:
            terms.append({"employee_id": {"$in": employee_ids}})
        label = "team"
    return {"$or": terms}, label


def _require_attendance_access(user: dict) -> None:
    if not has_any_permission(user, "attendance.read", "attendance.create",
                              "attendance.update", "attendance.approve"):
        raise HTTPException(403, "Missing attendance permission")


async def _visible_visit(user: dict, visit_id: str) -> dict:
    scope, _ = await visit_scope(user)
    visit = await sdb.site_visits.find_one(merge_query({"id": visit_id}, scope), {"_id": 0})
    if not visit:
        raise HTTPException(404, "Site visit not found")
    return visit


async def _is_owner(user: dict, visit: dict) -> bool:
    if visit.get("user_id") == user.get("user_id"):
        return True
    return visit.get("employee_id") in await user_identity_ids(user)


async def _own_visit(user: dict, visit_id: str) -> dict:
    visit = await _visible_visit(user, visit_id)
    if not await _is_owner(user, visit):
        raise HTTPException(403, "Only the person who made this visit can change it")
    return visit


def _still_editable(visit: dict) -> bool:
    return visit.get("status") == "open" or visit.get("date") == att._today()


# ---------------------------------------------------------------- shaping
def public_photo(photo: dict) -> dict:
    return {k: photo.get(k) for k in _PUBLIC_PHOTO_FIELDS if k in photo}


def public_visit(visit: dict, *, editable: bool = False) -> dict:
    out = {k: v for k, v in visit.items() if k not in ("open_key", "photos", "device_id")}
    out["photos"] = [public_photo(p) for p in (visit.get("photos") or [])]
    out["photo_count"] = len(out["photos"])
    out["can_edit"] = editable
    return out


async def _shape_rows(user: dict, rows: list) -> list:
    ids = await user_identity_ids(user)
    today = att._today()
    out = []
    for v in rows:
        mine = v.get("user_id") == user.get("user_id") or v.get("employee_id") in ids
        editable = mine and (v.get("status") == "open" or v.get("date") == today)
        out.append(public_visit(v, editable=editable))
    return out


def _minutes_between(start_iso: Optional[str], end: datetime) -> Optional[int]:
    try:
        start = datetime.fromisoformat(str(start_iso).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    return max(int((end - start).total_seconds() // 60), 0)


def _valid_day(value: Optional[str]) -> str:
    if not value:
        return att._today()
    try:
        return _date.fromisoformat(value).isoformat()
    except ValueError as exc:
        raise HTTPException(422, "Date must be YYYY-MM-DD") from exc


def _client_time(value: Optional[str]) -> Optional[str]:
    """Device capture time, kept only when it is a sane timestamp near now."""
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    now = now_utc()
    if dt > now + timedelta(minutes=10) or dt < now - timedelta(days=2):
        return None
    return dt.astimezone(timezone.utc).isoformat()


async def _fence_details(location_id: Optional[str]) -> Optional[dict]:
    if not location_id:
        return None
    loc = await sdb.office_locations.find_one(
        {"id": location_id}, {"_id": 0, "id": 1, "name": 1, "lat": 1, "lng": 1, "radius_m": 1})
    if not loc or loc.get("lat") is None or loc.get("lng") is None:
        return None
    return {"id": loc["id"], "name": loc.get("name"), "lat": float(loc["lat"]),
            "lng": float(loc["lng"]), "radius_m": loc.get("radius_m") or 150}


async def _close_visit(user: dict, visit: dict, *, auto: bool = False,
                       payload: Optional[SiteVisitCheckOutIn] = None) -> dict:
    now = now_utc()
    update = {
        "status": "closed",
        "check_out_at": now.isoformat(),
        "duration_minutes": _minutes_between(visit.get("check_in_at"), now),
        "updated_at": iso_now(),
    }
    if auto:
        # A visit left open on an earlier day: the real end time is unknown.
        update["auto_closed"] = True
        update["check_out_at"] = None
        update["duration_minutes"] = None
    if payload is not None:
        if payload.lat is not None and payload.lng is not None:
            update["check_out_lat"] = payload.lat
            update["check_out_lng"] = payload.lng
            update["check_out_accuracy_m"] = payload.accuracy_m
        if payload.notes is not None:
            update["notes"] = payload.notes.strip()
    result = await sdb.site_visits.update_one(
        {"id": visit["id"], "status": "open"}, {"$set": update, "$unset": {"open_key": ""}})
    if result.matched_count == 0:
        raise HTTPException(409, "This visit has already been finished")
    await audit(user, "project.site_visit_end", target=visit["project_id"], target_type="project",
                meta={"visit_id": visit["id"], "employee_name": visit.get("employee_name"),
                      "duration_minutes": update["duration_minutes"],
                      "photos": int(visit.get("photo_count") or 0), "auto_closed": auto})
    return {**visit, **update}


# ---------------------------------------------------------------- check in
@router.post("/projects/{project_id}/site-visits")
async def start_site_visit(project_id: str, payload: SiteVisitIn, request: Request,
                           session_token: Optional[str] = Cookie(default=None),
                           authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    att._require_punch_permission(user)
    project = await att._validate_attendance_project(user, project_id)
    if not project:
        raise HTTPException(400, "Select a project for the site visit")
    emp_id = await att._resolve_employee_id(user, None)
    emp = await sdb.employees.find_one(
        {"id": emp_id}, {"_id": 0, "id": 1, "name": 1, "first_name": 1, "last_name": 1,
                         "employee_id": 1, "employment_status": 1})
    if not emp:
        raise HTTPException(404, "Employee not found")
    if emp.get("employment_status") == "terminated":
        raise HTTPException(403, "Former staff cannot check in")

    policy = await att._get_attendance_policy()
    max_acc = policy.get("max_gps_accuracy_m")
    if max_acc and payload.accuracy_m and payload.accuracy_m > max_acc:
        raise HTTPException(422, detail={
            "code": "gps_accuracy_low",
            "message": (f"GPS accuracy is {int(payload.accuracy_m)}m, needs to be under "
                        f"{int(max_acc)}m. Step outdoors and try again."),
            "accuracy_m": payload.accuracy_m, "max_accuracy_m": max_acc,
        })

    today = att._today()
    open_visit = await sdb.site_visits.find_one(
        {"employee_id": emp_id, "status": "open"}, {"_id": 0})
    if open_visit:
        if (open_visit.get("date") or "") < today:
            await _close_visit(user, open_visit, auto=True)
        else:
            raise HTTPException(409, detail={
                "code": "visit_open",
                "message": f"Finish your visit at {open_visit.get('project_name') or 'the other site'} first.",
                "visit_id": open_visit["id"], "project_id": open_visit.get("project_id"),
            })

    geo = await att._resolve_geo_fence("site", payload.lat, payload.lng, project_id, payload.accuracy_m)
    matched = geo.get("matched_location") or None
    geo_status = "inside" if geo.get("inside") else ("outside" if matched else "no_fence")
    if geo_status != "inside":
        if not payload.force_outside:
            raise HTTPException(422, detail={
                "code": "outside_geofence" if geo_status == "outside" else "no_site_fence",
                "message": (geo.get("reason") if geo_status == "outside" else
                            "This project has no site location yet, so the visit cannot be verified "
                            "automatically."),
                "distance_m": geo.get("distance_m"), "matched_location": matched,
            })
        if not policy.get("approval_required_when_outside", True):
            raise HTTPException(400, "Outside-location approval is disabled by policy")

    # The first check-in of the day is made through attendance itself.
    existing = await sdb.attendance.find_one({"employee_id": emp_id, "date": today}, {"_id": 0})
    attendance_created = False
    if not existing or not existing.get("check_in") or att._retryable_rejected_punch(existing):
        record = await att.check_in(CheckInIn(
            attendance_type="site_visit", project_id=project_id,
            site_location=project.get("name"), location=project.get("name") or "",
            notes=payload.notes or "", lat=payload.lat, lng=payload.lng,
            accuracy_m=payload.accuracy_m,
            force_outside=bool(payload.force_outside and geo_status != "inside"),
            device_id=payload.device_id, device_label=payload.device_label,
        ), request, session_token, authorization)
        attendance_id = record.get("id")
        attendance_created = True
    else:
        attendance_id = existing["id"]

    fence = await _fence_details((matched or {}).get("id"))
    org_id = user_org_id(user) or "org_default"
    visit = {
        "id": new_id("sv_"),
        "project_id": project_id,
        "project_name": project.get("name"),
        "employee_id": emp_id,
        "employee_name": att._attendance_employee_name(emp, emp_id),
        "user_id": user["user_id"],
        "date": today,
        "check_in_at": iso_now(),
        "status": "open",
        "open_key": f"{org_id}:{emp_id}",
        "lat": payload.lat,
        "lng": payload.lng,
        "accuracy_m": payload.accuracy_m,
        "geo_status": geo_status,
        "geo_distance_m": geo.get("distance_m"),
        "fence": fence,
        "notes": (payload.notes or "").strip(),
        "photos": [],
        "photo_count": 0,
        "attendance_id": attendance_id,
        "attendance_created": attendance_created,
        "device_id": payload.device_id,
        "device_label": payload.device_label,
        "created_at": iso_now(),
    }
    try:
        await sdb.site_visits.insert_one(dict(visit))
    except DuplicateKeyError as exc:
        raise HTTPException(409, detail={"code": "visit_open",
                                         "message": "You already have a visit in progress."}) from exc
    if attendance_id:
        await sdb.attendance.update_one({"id": attendance_id}, {"$push": {"site_visits": {
            "id": visit["id"], "project_id": project_id, "project_name": project.get("name"),
            "at": visit["check_in_at"], "geo_status": geo_status,
        }}})
    await audit(user, "project.site_visit", target=project_id, target_type="project",
                meta={"visit_id": visit["id"], "employee_name": visit["employee_name"],
                      "geo_status": geo_status, "attendance_created": attendance_created})
    return public_visit(visit, editable=True)


@router.post("/site-visits/{visit_id}/check-out")
async def finish_site_visit(visit_id: str, payload: SiteVisitCheckOutIn, request: Request,
                            session_token: Optional[str] = Cookie(default=None),
                            authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    att._require_punch_permission(user)
    visit = await _own_visit(user, visit_id)
    if visit.get("status") != "open":
        raise HTTPException(409, "This visit has already been finished")
    closed = await _close_visit(user, visit, payload=payload)
    return public_visit(closed, editable=_still_editable(closed))


@router.patch("/site-visits/{visit_id}")
async def update_site_visit_notes(visit_id: str, payload: SiteVisitNotesIn, request: Request,
                                  session_token: Optional[str] = Cookie(default=None),
                                  authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    att._require_punch_permission(user)
    visit = await _own_visit(user, visit_id)
    if not _still_editable(visit):
        raise HTTPException(409, "Notes can be changed until the end of the visit day")
    notes = payload.notes.strip()
    await sdb.site_visits.update_one({"id": visit_id}, {"$set": {"notes": notes, "updated_at": iso_now()}})
    return public_visit({**visit, "notes": notes}, editable=True)


# ---------------------------------------------------------------- photos
@router.post("/site-visits/{visit_id}/photos")
async def add_site_visit_photo(
        visit_id: str, request: Request, upload: UploadFile = File(...),
        lat: Optional[float] = Form(None), lng: Optional[float] = Form(None),
        accuracy_m: Optional[float] = Form(None), caption: Optional[str] = Form(None),
        taken_at: Optional[str] = Form(None),
        session_token: Optional[str] = Cookie(default=None),
        authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    att._require_punch_permission(user)
    visit = await _own_visit(user, visit_id)
    if not _still_editable(visit):
        raise HTTPException(409, "Photos can be added until the end of the visit day")
    if int(visit.get("photo_count") or 0) >= MAX_PHOTOS_PER_VISIT:
        raise HTTPException(409, f"A visit can hold up to {MAX_PHOTOS_PER_VISIT} photos")
    if (lat is None) != (lng is None):
        raise HTTPException(422, "Send both latitude and longitude, or neither")
    if lat is not None and not (-90 <= lat <= 90 and -180 <= lng <= 180):
        raise HTTPException(422, "Invalid photo location")
    if accuracy_m is not None and not (0 <= accuracy_m <= 100000):
        raise HTTPException(422, "Invalid GPS accuracy")
    if Path(upload.filename or "").suffix.lower() not in PHOTO_EXTENSIONS:
        raise HTTPException(422, "Photos must be JPG, PNG or WebP")
    try:
        stored = await save_upload(upload, user_org_id(user) or "org_default", await tenant_storage_quota_bytes(user_org_id(user)))
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except OSError as exc:
        raise HTTPException(503, "File storage is unavailable") from exc
    if not str(stored.get("content_type") or "").startswith("image/"):
        remove_upload(stored["storage_key"])
        raise HTTPException(422, "Photos must be JPG, PNG or WebP")

    distance = None
    distance_from = None
    if lat is not None:
        fence = visit.get("fence")
        if fence and fence.get("lat") is not None:
            distance = round(att._haversine_m(lat, lng, fence["lat"], fence["lng"]), 1)
            distance_from = "site"
        elif visit.get("lat") is not None:
            distance = round(att._haversine_m(lat, lng, visit["lat"], visit["lng"]), 1)
            distance_from = "check_in"
    photo = {
        "id": new_id("svp_"),
        **stored,
        "captured_at": iso_now(),
        "client_taken_at": _client_time(taken_at),
        "lat": lat, "lng": lng, "accuracy_m": accuracy_m,
        "distance_m": distance, "distance_from": distance_from,
        "caption": (caption or "").strip()[:300] or None,
        "uploaded_by": user["user_id"],
        "uploaded_by_name": user.get("name"),
    }
    try:
        result = await sdb.site_visits.update_one(
            {"id": visit_id, "photo_count": {"$lt": MAX_PHOTOS_PER_VISIT}},
            {"$push": {"photos": photo}, "$inc": {"photo_count": 1}, "$set": {"updated_at": iso_now()}})
    except Exception:
        remove_upload(stored["storage_key"])
        raise
    if result.matched_count == 0:
        remove_upload(stored["storage_key"])
        raise HTTPException(409, f"A visit can hold up to {MAX_PHOTOS_PER_VISIT} photos")
    await audit(user, "site_visit.photo_add", target=visit_id, target_type="site_visit",
                meta={"project_id": visit.get("project_id"), "photo_id": photo["id"],
                      "size": stored["size"], "sha256": stored["sha256"]})
    return public_photo(photo)


@router.get("/site-visits/{visit_id}/photos/{photo_id}")
async def site_visit_photo(visit_id: str, photo_id: str, request: Request,
                           session_token: Optional[str] = Cookie(default=None),
                           authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    _require_attendance_access(user)
    visit = await _visible_visit(user, visit_id)
    photo = next((p for p in visit.get("photos") or [] if p.get("id") == photo_id), None)
    if not photo or not photo.get("storage_key"):
        raise HTTPException(404, "Photo not found")
    try:
        path = resolve_storage_key(photo["storage_key"])
    except ValueError as exc:
        raise HTTPException(404, "Photo not found") from exc
    if not path.is_file():
        raise HTTPException(404, "Stored photo is unavailable")
    return FileResponse(
        path, media_type=photo.get("content_type") or "application/octet-stream",
        filename=photo.get("original_name") or "site-photo.jpg",
        content_disposition_type="inline",
        headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"},
    )


@router.delete("/site-visits/{visit_id}/photos/{photo_id}")
async def delete_site_visit_photo(visit_id: str, photo_id: str, request: Request,
                                  session_token: Optional[str] = Cookie(default=None),
                                  authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    _require_attendance_access(user)
    visit = await _visible_visit(user, visit_id)
    owner = await _is_owner(user, visit)
    if not ((owner and _still_editable(visit)) or sees_everyone(user)):
        raise HTTPException(403, "Only the person who took the photo can remove it on the same day")
    photos = list(visit.get("photos") or [])
    photo = next((p for p in photos if p.get("id") == photo_id), None)
    if not photo:
        raise HTTPException(404, "Photo not found")
    remaining = [p for p in photos if p.get("id") != photo_id]
    # Optimistic write: refuse if another upload/removal changed the list meanwhile.
    result = await sdb.site_visits.update_one(
        {"id": visit_id, "photo_count": int(visit.get("photo_count") or len(photos))},
        {"$set": {"photos": remaining, "photo_count": len(remaining), "updated_at": iso_now()}})
    if result.matched_count == 0:
        raise HTTPException(409, "The visit changed meanwhile; refresh and try again")
    remove_upload(photo.get("storage_key"))
    await audit(user, "site_visit.photo_delete", target=visit_id, target_type="site_visit",
                meta={"project_id": visit.get("project_id"), "photo_id": photo_id,
                      "sha256": photo.get("sha256")})
    return {"ok": True}


# ---------------------------------------------------------------- lists
@router.get("/projects/{project_id}/site-visits")
async def project_site_visits(project_id: str, request: Request,
                              session_token: Optional[str] = Cookie(default=None),
                              authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    project = await get_visible_project(user, project_id,
                                        projection={"_id": 0, "id": 1, "name": 1,
                                                    "project_manager_id": 1})
    ids = await user_identity_ids(user)
    if sees_everyone(user) or (is_team_manager(user) and project.get("project_manager_id") in ids):
        scope, label = {}, ("all" if sees_everyone(user) else "team")
    else:
        scope, label = await visit_scope(user)
    rows = await sdb.site_visits.find(
        merge_query({"project_id": project_id}, scope), {"_id": 0},
    ).sort("check_in_at", -1).to_list(MAX_LIST_ROWS)

    can_check_in = False
    if has_permission(user, "attendance.create") or att._can_edit_punches(user):
        try:
            await att._validate_attendance_project(user, project_id)
            can_check_in = True
        except HTTPException:
            can_check_in = False
    my_open = None
    own_emp = await sdb.employees.find_one(
        {"$or": [{"user_id": user["user_id"]}] + ([{"email": user["email"]}] if user.get("email") else [])},
        {"_id": 0, "id": 1})
    if own_emp:
        row = await sdb.site_visits.find_one({"employee_id": own_emp["id"], "status": "open"}, {"_id": 0})
        if row:
            my_open = public_visit(row, editable=True)
    fences = []
    if has_any_permission(user, "attendance.read", "attendance.create", "attendance.update", "attendance.approve"):
        fences = await sdb.office_locations.find(
            {"kind": "site", "is_active": True, "project_id": project_id},
            {"_id": 0, "id": 1, "name": 1, "lat": 1, "lng": 1, "radius_m": 1, "address": 1},
        ).to_list(20)
    return {
        "project_id": project_id,
        "scope": label,
        "visits": await _shape_rows(user, rows),
        "can_check_in": can_check_in and bool(own_emp),
        "has_employee_profile": bool(own_emp),
        "can_manage_fence": has_any_permission(user, "attendance.update"),
        "my_open_visit": my_open,
        "site_fences": fences,
        "max_photos": MAX_PHOTOS_PER_VISIT,
    }


@router.get("/site-visits")
async def list_site_visits(request: Request,
                           date: Optional[str] = Query(None, max_length=10),
                           employee_id: Optional[str] = Query(None, max_length=120),
                           project_id: Optional[str] = Query(None, max_length=120),
                           session_token: Optional[str] = Cookie(default=None),
                           authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    _require_attendance_access(user)
    scope, label = await visit_scope(user)
    q: dict = {}
    if date:
        q["date"] = _valid_day(date)
    if employee_id:
        q["employee_id"] = employee_id
    if project_id:
        q["project_id"] = project_id
    rows = await sdb.site_visits.find(merge_query(q, scope), {"_id": 0}) \
        .sort("check_in_at", -1).to_list(MAX_LIST_ROWS)
    return {"scope": label, "visits": await _shape_rows(user, rows)}


@router.get("/site-visits/live-map")
async def live_map(request: Request, date: Optional[str] = Query(None, max_length=10),
                   session_token: Optional[str] = Cookie(default=None),
                   authorization: Optional[str] = Header(default=None)):
    """Today's check-ins and site visits as map pins, with office/site fences."""
    user = await require_user(request, session_token, authorization)
    if not (sees_everyone(user) or is_team_manager(user)):
        raise HTTPException(403, "The live map is for HR, admins and managers")
    day = _valid_day(date)
    if sees_everyone(user):
        label, employee_filter, visit_filter = "all", {}, {}
    else:
        project_ids, team_ids = await managed_team(user)
        own = sorted(await user_identity_ids(user))
        people = sorted(set(team_ids) | set(own))
        label = "team"
        employee_filter = {"employee_id": {"$in": people}}
        visit_filter = {"$or": [{"employee_id": {"$in": people}}]
                        + ([{"project_id": {"$in": project_ids}}] if project_ids else [])}

    visits = await sdb.site_visits.find(
        merge_query({"date": day}, visit_filter), {"_id": 0, "photos": 0, "open_key": 0, "device_id": 0},
    ).sort("check_in_at", 1).to_list(MAX_LIST_ROWS)
    records = await sdb.attendance.find(
        merge_query({"date": day}, employee_filter), {"_id": 0},
    ).to_list(MAX_LIST_ROWS)
    names = await att._employee_name_map(sorted({r["employee_id"] for r in records if r.get("employee_id")}))
    from_visit = {v.get("attendance_id") for v in visits if v.get("attendance_created")}

    pins, no_location = [], []
    for r in records:
        if not r.get("check_in") or r.get("status") == "leave":
            continue
        name = names.get(r.get("employee_id")) or r.get("employee_name") or r.get("employee_id")
        if r.get("check_in_lat") is None or r.get("check_in_lng") is None:
            no_location.append({"employee_id": r.get("employee_id"), "employee_name": name,
                                "at": r.get("check_in"), "attendance_type": r.get("attendance_type")})
            continue
        if r.get("id") in from_visit:
            continue  # the site-visit pin below already shows this check-in
        pins.append({
            "type": "check_in", "id": r.get("id"), "employee_id": r.get("employee_id"),
            "employee_name": name, "at": r.get("check_in"), "checked_out_at": r.get("check_out"),
            "lat": r.get("check_in_lat"), "lng": r.get("check_in_lng"),
            "accuracy_m": r.get("check_in_accuracy_m"),
            "attendance_type": r.get("attendance_type"),
            "place": r.get("geo_location_matched") or r.get("site_location") or r.get("check_in_location"),
            "geo_inside": r.get("geo_inside"), "status": r.get("status"),
            "approval_status": r.get("approval_status"),
        })
    for v in visits:
        pins.append({
            "type": "site_visit", "id": v["id"], "employee_id": v.get("employee_id"),
            "employee_name": v.get("employee_name"), "at": v.get("check_in_at"),
            "checked_out_at": v.get("check_out_at"), "lat": v.get("lat"), "lng": v.get("lng"),
            "accuracy_m": v.get("accuracy_m"), "project_id": v.get("project_id"),
            "place": v.get("project_name"), "geo_status": v.get("geo_status"),
            "geo_inside": v.get("geo_status") == "inside", "open": v.get("status") == "open",
            "photo_count": int(v.get("photo_count") or 0),
        })

    fences = await sdb.office_locations.find(
        {"is_active": True}, {"_id": 0, "id": 1, "name": 1, "kind": 1, "lat": 1, "lng": 1,
                              "radius_m": 1, "project_id": 1},
    ).to_list(200)
    policy = await att._get_attendance_policy()
    if policy.get("default_office_lat") is not None and policy.get("default_office_lng") is not None:
        fences.append({"id": "policy_default", "name": "Head Office", "kind": "office",
                       "lat": policy["default_office_lat"], "lng": policy["default_office_lng"],
                       "radius_m": policy.get("default_office_radius_m") or 150})
    summary = {
        "checked_in": sum(1 for r in records if r.get("check_in") and r.get("status") != "leave"),
        "on_site_now": sum(1 for v in visits if v.get("status") == "open"),
        "site_visits": len(visits),
        "outside_fence": sum(1 for p in pins if p.get("geo_inside") is False),
        "no_location": len(no_location),
    }
    return {"date": day, "generated_at": engine.now_ist().strftime("%H:%M"), "scope": label,
            "pins": pins, "fences": fences, "no_location": no_location, "summary": summary}


@router.get("/site-visits/{visit_id}")
async def get_site_visit(visit_id: str, request: Request,
                         session_token: Optional[str] = Cookie(default=None),
                         authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    _require_attendance_access(user)
    visit = await _visible_visit(user, visit_id)
    editable = await _is_owner(user, visit) and _still_editable(visit)
    return public_visit(visit, editable=editable)
