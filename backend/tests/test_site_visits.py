"""Site visits + live map (Phase 3): geofence, attendance link, photos, visibility.

Runs the real route functions (including the real attendance check-in) against a
small in-memory collection fake, so no database server is needed.
"""
import asyncio
import copy
import re
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException, UploadFile
from pymongo.errors import DuplicateKeyError

import core.access_control as access_control
import routes.attendance as att
import routes.site_visits as sv
import services.local_files as local_files

_MISSING = object()

SITE = (23.0225, 72.5714)          # Cloud-9 site fence centre (radius 100 m)
OFFICE = (23.0300, 72.5800)        # office fence centre (radius 150 m)
FAR = (23.0600, 72.6200)           # several km from both
JPEG = b"\xff\xd8\xff\xe0" + b"0" * 2048


# ---------------------------------------------------------------- fake Mongo
def _value(doc, key):
    cur = doc
    for part in key.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return _MISSING
        cur = cur[part]
    return cur


def _match(doc, query):
    for key, cond in (query or {}).items():
        if key == "$or":
            if not any(_match(doc, sub) for sub in cond):
                return False
            continue
        if key == "$and":
            if not all(_match(doc, sub) for sub in cond):
                return False
            continue
        val = _value(doc, key)
        if isinstance(cond, dict) and cond and all(k.startswith("$") for k in cond):
            for op, arg in cond.items():
                present = None if val is _MISSING else val
                if op == "$in":
                    ok = (any(x in arg for x in present) if isinstance(present, list)
                          else present in arg)
                elif op == "$nin":
                    ok = (not any(x in arg for x in present) if isinstance(present, list)
                          else present not in arg)
                elif op == "$ne":
                    ok = present != arg
                elif op == "$lt":
                    ok = val is not _MISSING and val < arg
                elif op == "$exists":
                    ok = (val is not _MISSING) == bool(arg)
                else:
                    raise AssertionError(f"unsupported operator {op}")
                if not ok:
                    return False
        else:
            present = None if val is _MISSING else val
            if isinstance(present, list) and not isinstance(cond, list):
                if cond not in present:
                    return False
            elif present != cond:
                return False
    return True


class _Cursor:
    def __init__(self, rows):
        self.rows = rows

    def sort(self, key, direction=1):
        self.rows.sort(key=lambda r: (r.get(key) is None, r.get(key) or ""), reverse=direction == -1)
        return self

    def limit(self, n):
        self.rows = self.rows[:n]
        return self

    async def to_list(self, n=None):
        return [copy.deepcopy(r) for r in (self.rows if n is None else self.rows[:n])]

    def __aiter__(self):
        self._it = iter([copy.deepcopy(r) for r in self.rows])
        return self

    async def __anext__(self):
        try:
            return next(self._it)
        except StopIteration:
            raise StopAsyncIteration


class _Coll:
    def __init__(self, name, unique=()):
        self.name = name
        self.docs = []
        self.unique = unique

    def find(self, query=None, _projection=None):
        return _Cursor([d for d in self.docs if _match(d, query)])

    async def find_one(self, query=None, _projection=None):
        for d in self.docs:
            if _match(d, query):
                return copy.deepcopy(d)
        return None

    async def insert_one(self, doc):
        for field in self.unique:
            if doc.get(field) is not None and any(d.get(field) == doc[field] for d in self.docs):
                raise DuplicateKeyError(f"duplicate {field}")
        self.docs.append(copy.deepcopy(doc))
        return SimpleNamespace(inserted_id=doc.get("id"))

    async def update_one(self, query, update):
        for d in self.docs:
            if _match(d, query):
                for k, v in (update.get("$set") or {}).items():
                    d[k] = copy.deepcopy(v)
                for k in (update.get("$unset") or {}):
                    d.pop(k, None)
                for k, v in (update.get("$push") or {}).items():
                    d.setdefault(k, []).append(copy.deepcopy(v))
                for k, v in (update.get("$inc") or {}).items():
                    d[k] = (d.get(k) or 0) + v
                return SimpleNamespace(matched_count=1, modified_count=1)
        return SimpleNamespace(matched_count=0, modified_count=0)

    async def delete_one(self, query):
        for i, d in enumerate(self.docs):
            if _match(d, query):
                del self.docs[i]
                return SimpleNamespace(deleted_count=1)
        return SimpleNamespace(deleted_count=0)

    async def count_documents(self, query=None):
        return sum(1 for d in self.docs if _match(d, query))

    async def distinct(self, field, query=None):
        out = []
        for d in self.docs:
            if _match(d, query) and d.get(field) not in out:
                out.append(d.get(field))
        return out


class _DB(SimpleNamespace):
    def __getattr__(self, name):  # any other collection starts empty
        coll = _Coll(name)
        setattr(self, name, coll)
        return coll


USERS = {
    "a": {"user_id": "u_a", "email": "a@studio.test", "name": "Asha", "role": "Employee", "org_id": "org_a"},
    "b": {"user_id": "u_b", "email": "b@studio.test", "name": "Bhavin", "role": "Employee", "org_id": "org_a"},
    "pm": {"user_id": "u_pm", "email": "pm@studio.test", "name": "Priya", "role": "ProjectManager", "org_id": "org_a"},
    "designer": {"user_id": "u_d", "email": "d@studio.test", "name": "Dev", "role": "Designer", "org_id": "org_a"},
    "hr": {"user_id": "u_hr", "email": "hr@studio.test", "name": "Hema", "role": "HR", "org_id": "org_a"},
    "client": {"user_id": "u_c", "email": "c@client.test", "name": "Client", "role": "Client", "org_id": "org_a"},
}


@pytest.fixture
def world(monkeypatch, tmp_path):
    db = _DB(site_visits=_Coll("site_visits", unique=("open_key",)))
    db.employees.docs = [
        {"id": "emp_a", "user_id": "u_a", "email": "a@studio.test", "first_name": "Asha", "last_name": "Rao"},
        {"id": "emp_b", "user_id": "u_b", "email": "b@studio.test", "first_name": "Bhavin", "last_name": "Shah"},
        {"id": "emp_pm", "user_id": "u_pm", "email": "pm@studio.test", "first_name": "Priya", "last_name": "N"},
        {"id": "emp_d", "user_id": "u_d", "email": "d@studio.test", "first_name": "Dev", "last_name": "K"},
    ]
    db.projects.docs = [
        {"id": "p1", "name": "Cloud-9", "team_ids": ["emp_a", "emp_d"], "project_manager_id": "emp_pm"},
        {"id": "p2", "name": "Lake House", "team_ids": ["emp_b"], "project_manager_id": "emp_x"},
    ]
    db.office_locations.docs = [
        {"id": "loc_site", "name": "Cloud-9 site", "kind": "site", "project_id": "p1",
         "lat": SITE[0], "lng": SITE[1], "radius_m": 100, "is_active": True},
        {"id": "loc_office", "name": "Studio", "kind": "office", "project_id": None,
         "lat": OFFICE[0], "lng": OFFICE[1], "radius_m": 150, "is_active": True},
    ]
    state = {"user": USERS["a"], "audits": [], "alerts": []}

    async def current_user(*_a, **_k):
        return state["user"]

    async def record_audit(user, action, target=None, target_type=None, meta=None, **_k):
        state["audits"].append({"actor": user["user_id"], "action": action, "target": target,
                                "target_type": target_type, "meta": meta or {}})

    async def record_alert(*args, **kwargs):
        state["alerts"].append((args, kwargs))
        return 1

    for module in (sv, att, access_control):
        monkeypatch.setattr(module, "sdb", db)
    monkeypatch.setattr(sv, "require_user", current_user)
    monkeypatch.setattr(att, "require_user", current_user)
    monkeypatch.setattr(sv, "audit", record_audit)
    monkeypatch.setattr(att, "audit", record_audit)
    monkeypatch.setattr(att, "emit_admins", record_alert)
    monkeypatch.setattr(local_files, "STORAGE_ROOT", tmp_path)
    return SimpleNamespace(db=db, state=state, root=tmp_path)


REQ = SimpleNamespace(headers={}, client=None)


def run(coro):
    return asyncio.run(coro)


def as_user(world, key):
    world.state["user"] = USERS[key]


def start(world, project="p1", at=SITE, **extra):
    payload = sv.SiteVisitIn(lat=at[0], lng=at[1], accuracy_m=12, **extra)
    return run(sv.start_site_visit(project, payload, REQ))


def photo(world, visit_id, data=JPEG, name="photo.jpg", at=SITE):
    upload = UploadFile(file=BytesIO(data), filename=name)
    return run(sv.add_site_visit_photo(visit_id, REQ, upload=upload, lat=at[0], lng=at[1],
                                       accuracy_m=8, caption="Slab shuttering", taken_at=None))


def status_of(call):
    with pytest.raises(HTTPException) as exc:
        call()
    return exc.value.status_code, exc.value.detail


# ---------------------------------------------------------------- check in
def test_first_visit_inside_the_fence_is_the_days_attendance(world):
    visit = start(world, notes="Checked slab levels")
    assert visit["geo_status"] == "inside" and visit["status"] == "open"
    assert visit["fence"]["id"] == "loc_site" and visit["project_name"] == "Cloud-9"
    assert "open_key" not in visit and visit["can_edit"] is True

    [record] = world.db.attendance.docs
    assert record["attendance_type"] == "site_visit" and record["project_id"] == "p1"
    assert record["status"] == "present" and record["approval_status"] == "auto"
    assert record["site_visits"][0]["id"] == visit["id"]
    assert visit["attendance_id"] == record["id"] and visit["attendance_created"] is True

    timeline = [a for a in world.state["audits"] if a["action"] == "project.site_visit"]
    assert timeline and timeline[0]["target"] == "p1" and timeline[0]["target_type"] == "project"
    meta_text = repr(timeline[0]["meta"])
    assert str(SITE[0]) not in meta_text and "lat" not in timeline[0]["meta"]  # no coordinates on the timeline


def test_outside_the_fence_needs_an_explicit_request_and_then_waits_for_approval(world):
    code, detail = status_of(lambda: start(world, at=FAR))
    assert code == 422 and detail["code"] == "outside_geofence" and detail["distance_m"] > 1000
    assert world.db.attendance.docs == [] and world.db.site_visits.docs == []

    visit = start(world, at=FAR, force_outside=True)
    assert visit["geo_status"] == "outside"
    [record] = world.db.attendance.docs
    assert record["approval_status"] == "pending" and record["status"] == "pending_approval"
    assert world.state["alerts"], "HR/admins are told an approval is waiting"


def test_project_without_a_site_fence_is_never_auto_verified(world):
    as_user(world, "b")
    code, detail = status_of(lambda: start(world, project="p2", at=FAR))
    assert code == 422 and detail["code"] == "no_site_fence"
    visit = start(world, project="p2", at=FAR, force_outside=True)
    assert visit["geo_status"] == "no_fence"
    assert world.db.attendance.docs[0]["approval_status"] == "pending"


def test_poor_gps_is_refused_before_anything_is_stored(world):
    payload = sv.SiteVisitIn(lat=SITE[0], lng=SITE[1], accuracy_m=900)
    code, detail = status_of(lambda: run(sv.start_site_visit("p1", payload, REQ)))
    assert code == 422 and detail["code"] == "gps_accuracy_low"
    assert world.db.site_visits.docs == [] and world.db.attendance.docs == []


def test_one_open_visit_at_a_time_and_later_visits_reuse_the_attendance(world):
    first = start(world)
    code, detail = status_of(lambda: start(world))
    assert code == 409 and detail["code"] == "visit_open"

    closed = run(sv.finish_site_visit(first["id"], sv.SiteVisitCheckOutIn(notes="Done"), REQ))
    assert closed["status"] == "closed" and closed["duration_minutes"] == 0 and closed["notes"] == "Done"
    assert "open_key" not in world.db.site_visits.docs[0]
    code, _ = status_of(lambda: run(sv.finish_site_visit(first["id"], sv.SiteVisitCheckOutIn(), REQ)))
    assert code == 409

    second = start(world)
    assert len(world.db.attendance.docs) == 1, "no second attendance record for the same day"
    assert second["attendance_created"] is False
    assert [v["id"] for v in world.db.attendance.docs[0]["site_visits"]] == [first["id"], second["id"]]


def test_a_visit_left_open_yesterday_closes_itself(world):
    world.db.site_visits.docs.append({
        "id": "sv_old", "project_id": "p1", "project_name": "Cloud-9", "employee_id": "emp_a",
        "user_id": "u_a", "date": "2000-01-01", "check_in_at": "2000-01-01T05:00:00+00:00",
        "status": "open", "open_key": "org_a:emp_a", "photos": [], "photo_count": 0,
    })
    start(world)
    old = next(v for v in world.db.site_visits.docs if v["id"] == "sv_old")
    assert old["status"] == "closed" and old["auto_closed"] is True and old["check_out_at"] is None


def test_unique_open_key_stops_a_double_submit(world):
    start(world)
    world.db.site_visits.docs[0]["status"] = "weird"  # hide it from the open-visit lookup
    code, _ = status_of(lambda: start(world))
    assert code in (400, 409)


def test_people_without_punch_permission_cannot_check_in(world):
    as_user(world, "client")
    code, _ = status_of(lambda: start(world))
    assert code == 403
    assert world.db.site_visits.docs == []


def test_staff_cannot_check_in_on_a_project_they_are_not_on(world):
    as_user(world, "b")  # Bhavin is on p2 only; p1 has a site fence (so it is open for site punches)
    world.db.office_locations.docs[0]["project_id"] = "p1"
    world.db.projects.docs.append({"id": "p3", "name": "Private", "team_ids": [], "project_manager_id": "emp_x"})
    code, _ = status_of(lambda: start(world, project="p3"))
    assert code == 403


# ---------------------------------------------------------------- photos
def test_photo_is_stored_privately_with_time_gps_and_distance(world):
    visit = start(world)
    meta = photo(world, visit["id"], at=(SITE[0] + 0.0003, SITE[1]))
    assert "storage_key" not in meta and meta["content_type"] == "image/jpeg"
    assert meta["captured_at"] and meta["distance_from"] == "site" and 20 < meta["distance_m"] < 50
    stored = world.db.site_visits.docs[0]["photos"][0]
    assert re.fullmatch(r"org_a/[a-f0-9]{32}\.jpg", stored["storage_key"])
    assert (Path(world.root) / stored["storage_key"]).read_bytes() == JPEG
    assert world.db.site_visits.docs[0]["photo_count"] == 1

    response = run(sv.site_visit_photo(visit["id"], meta["id"], REQ))
    assert response.headers["cache-control"] == "private, no-store"
    assert response.media_type == "image/jpeg"


def test_photo_type_and_content_are_checked(world):
    visit = start(world)
    code, _ = status_of(lambda: photo(world, visit["id"], data=b"%PDF-1.7 fake", name="plan.pdf"))
    assert code == 422
    code, _ = status_of(lambda: photo(world, visit["id"], data=b"%PDF-1.7 fake", name="plan.jpg"))
    assert code == 422  # content does not match the extension
    code, _ = status_of(lambda: photo(world, visit["id"], data=b"<svg onload=alert(1)>", name="x.svg"))
    assert code == 422
    assert world.db.site_visits.docs[0]["photo_count"] == 0
    assert not [p for p in Path(world.root).rglob("*") if p.is_file()]


def test_photo_limit_per_visit(world, monkeypatch):
    monkeypatch.setattr(sv, "MAX_PHOTOS_PER_VISIT", 2)
    visit = start(world)
    photo(world, visit["id"])
    photo(world, visit["id"])
    code, _ = status_of(lambda: photo(world, visit["id"]))
    assert code == 409
    assert len([p for p in Path(world.root).rglob("*") if p.is_file()]) == 2


def test_only_the_visitor_adds_photos_and_others_cannot_read_them(world):
    visit = start(world)
    meta = photo(world, visit["id"])
    as_user(world, "b")
    assert status_of(lambda: photo(world, visit["id"]))[0] == 404
    assert status_of(lambda: run(sv.site_visit_photo(visit["id"], meta["id"], REQ)))[0] == 404
    assert status_of(lambda: run(sv.get_site_visit(visit["id"], REQ)))[0] == 404
    assert status_of(lambda: run(sv.delete_site_visit_photo(visit["id"], meta["id"], REQ)))[0] == 404
    as_user(world, "hr")
    assert run(sv.site_visit_photo(visit["id"], meta["id"], REQ)).media_type == "image/jpeg"
    assert status_of(lambda: photo(world, visit["id"]))[0] == 403  # HR can see, not add


def test_removing_a_photo_deletes_the_file(world):
    visit = start(world)
    meta = photo(world, visit["id"])
    key = world.db.site_visits.docs[0]["photos"][0]["storage_key"]
    assert run(sv.delete_site_visit_photo(visit["id"], meta["id"], REQ)) == {"ok": True}
    assert world.db.site_visits.docs[0]["photos"] == [] and world.db.site_visits.docs[0]["photo_count"] == 0
    assert not (Path(world.root) / key).exists()
    assert any(a["action"] == "site_visit.photo_delete" for a in world.state["audits"])


def test_photos_and_notes_lock_after_the_visit_day(world):
    visit = start(world)
    world.db.site_visits.docs[0].update(status="closed", date="2000-01-01")
    assert status_of(lambda: photo(world, visit["id"]))[0] == 409
    assert status_of(lambda: run(sv.update_site_visit_notes(
        visit["id"], sv.SiteVisitNotesIn(notes="late edit"), REQ)))[0] == 409


# ---------------------------------------------------------------- visibility
def _seed_two_visits(world):
    a = start(world)
    as_user(world, "b")
    b = start(world, project="p2", at=FAR, force_outside=True)
    return a, b


def test_staff_see_only_their_own_visits(world):
    a, b = _seed_two_visits(world)
    as_user(world, "a")
    mine = run(sv.list_site_visits(REQ, date=None, employee_id=None, project_id=None))
    assert mine["scope"] == "own" and [v["id"] for v in mine["visits"]] == [a["id"]]
    as_user(world, "designer")  # on the p1 team, but not the visitor
    listed = run(sv.project_site_visits("p1", REQ))
    assert listed["scope"] == "own" and listed["visits"] == []
    assert status_of(lambda: run(sv.get_site_visit(a["id"], REQ)))[0] == 404


def test_hr_sees_everyone_and_managers_see_their_team(world):
    a, b = _seed_two_visits(world)
    as_user(world, "hr")
    assert {v["id"] for v in run(sv.list_site_visits(REQ, date=None, employee_id=None, project_id=None))["visits"]} == {a["id"], b["id"]}
    as_user(world, "pm")  # manages p1 only
    team = run(sv.list_site_visits(REQ, date=None, employee_id=None, project_id=None))
    assert team["scope"] == "team" and [v["id"] for v in team["visits"]] == [a["id"]]
    assert run(sv.project_site_visits("p1", REQ))["visits"][0]["id"] == a["id"]
    assert status_of(lambda: run(sv.get_site_visit(b["id"], REQ)))[0] == 404


def test_project_list_needs_project_visibility(world):
    start(world)
    as_user(world, "b")
    assert status_of(lambda: run(sv.project_site_visits("p1", REQ)))[0] == 404


def test_project_list_tells_the_page_what_the_user_can_do(world):
    first = start(world)
    data = run(sv.project_site_visits("p1", REQ))
    assert data["can_check_in"] is True and data["my_open_visit"]["id"] == first["id"]
    assert data["site_fences"][0]["id"] == "loc_site" and data["can_manage_fence"] is False
    assert "storage_key" not in repr(data)


# ---------------------------------------------------------------- live map
def test_live_map_is_for_hr_admins_and_managers_only(world):
    _seed_two_visits(world)
    for who in ("a", "designer", "client"):
        as_user(world, who)
        assert status_of(lambda: run(sv.live_map(REQ, date=None)))[0] == 403


def test_live_map_shows_pins_and_fences_without_duplicates(world):
    a, b = _seed_two_visits(world)
    world.db.attendance.docs.append({
        "id": "att_pm", "employee_id": "emp_pm", "date": att._today(), "check_in": "2026-11-08T04:30:00+00:00",
        "check_in_lat": OFFICE[0], "check_in_lng": OFFICE[1], "attendance_type": "office",
        "geo_inside": True, "status": "present",
    })
    world.db.attendance.docs.append({
        "id": "att_d", "employee_id": "emp_d", "date": att._today(), "check_in": "2026-11-08T04:40:00+00:00",
        "attendance_type": "office", "status": "present",
    })
    world.db.attendance_policies.docs.append({"default_office_lat": 23.1, "default_office_lng": 72.5})
    as_user(world, "hr")
    data = run(sv.live_map(REQ, date=None))
    kinds = sorted((p["type"], p["id"]) for p in data["pins"])
    assert kinds == sorted([("site_visit", a["id"]), ("site_visit", b["id"]), ("check_in", "att_pm")])
    assert data["summary"]["on_site_now"] == 2 and data["summary"]["outside_fence"] == 1
    assert [n["employee_id"] for n in data["no_location"]] == ["emp_d"]
    assert {f["id"] for f in data["fences"]} == {"loc_site", "loc_office", "policy_default"}
    assert "photos" not in repr(data["pins"]) and "storage_key" not in repr(data)


def test_live_map_for_a_manager_is_limited_to_the_team(world):
    a, b = _seed_two_visits(world)
    as_user(world, "pm")
    data = run(sv.live_map(REQ, date=None))
    assert data["scope"] == "team"
    assert [p["id"] for p in data["pins"]] == [a["id"]]
    assert all(p["employee_id"] != "emp_b" for p in data["pins"] + data["no_location"])


def test_live_map_rejects_bad_dates(world):
    as_user(world, "hr")
    assert status_of(lambda: run(sv.live_map(REQ, date="08/11/2026")))[0] == 422


# ---------------------------------------------------------------- wiring
def test_module_only_uses_the_tenant_scoped_database():
    source = Path(sv.__file__).read_text(encoding="utf-8")
    assert "from core.db import" not in source and " db." not in source
    assert "sdb.site_visits" in source


def test_site_visits_are_purged_with_their_tenant_and_photo_uploads_are_rate_limited():
    import routes.platform as platform
    from core.http_security import RATE_RULES

    assert "site_visits" in platform.TENANT_PURGE_COLLECTIONS
    assert any(bucket == "site_photo" and rx.search("/api/site-visits/sv_1/photos")
               for _m, rx, bucket, *_ in RATE_RULES)


def test_routes_are_registered():
    import server

    paths = set(server.app.openapi()["paths"])
    for path in ("/api/projects/{project_id}/site-visits", "/api/site-visits/live-map",
                 "/api/site-visits/{visit_id}/photos", "/api/site-visits/{visit_id}/photos/{photo_id}",
                 "/api/site-visits/{visit_id}/check-out"):
        assert path in paths
