"""Backend tests for the upgraded Task module + BC regression checks.

Covers:
- /api/tasks/meta shape
- Filters on GET /api/tasks
- Task creation (employee + vendor) + timeline/lane-sync
- GET/PUT/PATCH/DELETE task lifecycle
- Bulk update
- Follow-ups add/update/delete
- Reminders endpoint
- Project custom areas/categories
- Backward compat: /auth/me, /dashboard/stats, /projects, /employees,
  /quotations-adv, /leads
"""
import os
import pytest
import requests

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
TOKEN = "test_session_admin_001"
H = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def s():
    sess = requests.Session()
    sess.headers.update(H)
    return sess


@pytest.fixture(scope="module")
def project_id(s):
    r = s.get(f"{BASE_URL}/api/projects")
    if r.status_code == 200 and r.json():
        return r.json()[0].get("id")
    # Seed if empty
    s.post(f"{BASE_URL}/api/seed")
    r = s.get(f"{BASE_URL}/api/projects")
    return r.json()[0].get("id") if r.status_code == 200 and r.json() else None


# --- meta ---
def test_tasks_meta(s):
    r = s.get(f"{BASE_URL}/api/tasks/meta")
    assert r.status_code == 200
    d = r.json()
    assert d["task_types"] == ["employee", "vendor"]
    assert set(d["lanes"]) == {"todo", "in_progress", "review", "done"}
    assert len(d["status_detail"]) == 13
    assert set(d["priorities"]) >= {"low", "medium", "high", "urgent", "critical"}
    assert isinstance(d["areas"], list) and len(d["areas"]) > 5
    assert isinstance(d["categories"], list)
    assert isinstance(d["categories_employee"], list)
    assert isinstance(d["categories_vendor"], list)


# --- create employee task ---
@pytest.fixture(scope="module")
def emp_task(s, project_id):
    payload = {
        "title": "TEST_EMP_TASK",
        "project_id": project_id,
        "task_type": "employee",
        "area": "Kitchen",
        "category": "Material Selection",
        "item_description": "Marble slab shortlist",
        "priority": "high",
        "status_detail": "Selection Required",
    }
    r = s.post(f"{BASE_URL}/api/tasks", json=payload)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["id"].startswith("tsk_")
    assert d["status"] == "todo"  # lane synced
    assert d["status_detail"] == "Selection Required"
    assert d["priority"] == "high"
    assert d["created_by"]
    assert len(d.get("timeline", [])) >= 1
    return d


def test_create_vendor_task(s, project_id):
    payload = {
        "title": "TEST_VENDOR_TASK",
        "project_id": project_id,
        "task_type": "vendor",
        "area": "Living Room",
        "category": "Carpenter",
        "priority": "medium",
        "status_detail": "Quotation Requested",
        "vendor_contact": {
            "vendor_name": "ACME Wood",
            "phone": "999",
            "email": "a@b.com",
            "whatsapp": "999",
        },
    }
    r = s.post(f"{BASE_URL}/api/tasks", json=payload)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["vendor_contact"]["vendor_name"] == "ACME Wood"
    assert d["status"] == "todo"
    # cleanup
    s.delete(f"{BASE_URL}/api/tasks/{d['id']}")


def test_get_task(s, emp_task):
    r = s.get(f"{BASE_URL}/api/tasks/{emp_task['id']}")
    assert r.status_code == 200
    d = r.json()
    assert isinstance(d["follow_ups"], list)
    assert isinstance(d["timeline"], list)
    assert isinstance(d["attachments"], list)
    assert isinstance(d["reference_links"], list)


def test_filters(s, emp_task):
    r = s.get(f"{BASE_URL}/api/tasks", params={
        "task_type": "employee",
        "status_detail": "Selection Required",
        "priority": "high",
        "area": "Kitchen",
        "category": "Material Selection",
        "search": "Marble",
    })
    assert r.status_code == 200
    ids = [t["id"] for t in r.json()]
    assert emp_task["id"] in ids


def test_update_task_timeline(s, emp_task):
    tid = emp_task["id"]
    r = s.put(f"{BASE_URL}/api/tasks/{tid}", json={
        "title": "TEST_EMP_TASK_UPDATED",
        "priority": "critical",
    })
    assert r.status_code == 200
    d = r.json()
    assert d["priority"] == "critical"
    # timeline preserved and extended
    events = d.get("timeline", [])
    assert len(events) >= 2  # created + updates


def test_patch_status_lane(s, emp_task):
    r = s.patch(f"{BASE_URL}/api/tasks/{emp_task['id']}/status",
                json={"status": "in_progress"})
    assert r.status_code == 200
    d = r.json()
    assert d["status"] == "in_progress"
    assert d.get("status_detail")  # sync


def test_patch_status_detail(s, emp_task):
    r = s.patch(f"{BASE_URL}/api/tasks/{emp_task['id']}/status",
                json={"status_detail": "Ordered"})
    assert r.status_code == 200
    d = r.json()
    assert d["status_detail"] == "Ordered"
    assert d["status"] == "in_progress"


def test_patch_status_invalid(s, emp_task):
    r = s.patch(f"{BASE_URL}/api/tasks/{emp_task['id']}/status",
                json={"status_detail": "NotARealStatus"})
    assert r.status_code == 400


def test_bulk_update(s, emp_task):
    r = s.post(f"{BASE_URL}/api/tasks/bulk-update", json={
        "task_ids": [emp_task["id"]],
        "priority": "urgent",
        "status_detail": "On Hold",
    })
    assert r.status_code == 200
    d = r.json()
    assert d["ok"] is True and d["updated"] == 1
    got = s.get(f"{BASE_URL}/api/tasks/{emp_task['id']}").json()
    assert got["priority"] == "urgent"
    assert got["status_detail"] == "On Hold"
    assert got["status"] == "review"


# --- follow-ups ---
@pytest.fixture(scope="module")
def follow_up(s, emp_task):
    r = s.post(f"{BASE_URL}/api/tasks/{emp_task['id']}/follow-ups", json={
        "follow_up_date": "2026-02-15",
        "reminder_date": "2026-02-14",
        "reminder_time": "10:00",
        "notes": "Call vendor",
        "next_follow_up_date": "2026-02-20",
    })
    assert r.status_code == 200, r.text
    d = r.json()
    fus = d["follow_ups"]
    assert len(fus) >= 1
    # a follow_up_added timeline event exists
    assert any(e.get("event") == "follow_up_added" for e in d["timeline"])
    return fus[-1]


def test_update_follow_up(s, emp_task, follow_up):
    r = s.patch(f"{BASE_URL}/api/tasks/{emp_task['id']}/follow-ups/{follow_up['id']}",
                json={"status": "done"})
    assert r.status_code == 200
    d = r.json()
    fu = next(f for f in d["follow_ups"] if f["id"] == follow_up["id"])
    assert fu["status"] == "done"


def test_delete_follow_up(s, emp_task, follow_up):
    r = s.delete(f"{BASE_URL}/api/tasks/{emp_task['id']}/follow-ups/{follow_up['id']}")
    assert r.status_code == 200
    got = s.get(f"{BASE_URL}/api/tasks/{emp_task['id']}").json()
    assert not any(f["id"] == follow_up["id"] for f in got["follow_ups"])


def test_reminders_upcoming(s):
    r = s.get(f"{BASE_URL}/api/tasks/reminders/upcoming", params={"days": 30})
    assert r.status_code == 200
    assert isinstance(r.json(), list)


# --- project areas/categories ---
def test_project_areas_and_categories(s, project_id):
    if not project_id:
        pytest.skip("no project seeded")
    r = s.post(f"{BASE_URL}/api/projects/{project_id}/areas",
               json={"name": "TEST_Zen_Room"})
    assert r.status_code == 200
    r = s.get(f"{BASE_URL}/api/projects/{project_id}/areas")
    assert r.status_code == 200
    assert "TEST_Zen_Room" in r.json()["custom"]

    r = s.post(f"{BASE_URL}/api/projects/{project_id}/categories",
               json={"name": "TEST_SmartLight", "task_type": "vendor"})
    assert r.status_code == 200

    # cleanup
    s.delete(f"{BASE_URL}/api/projects/{project_id}/areas/TEST_Zen_Room")
    s.delete(f"{BASE_URL}/api/projects/{project_id}/categories/TEST_SmartLight")


# --- delete task (last) ---
def test_delete_task(s, emp_task):
    r = s.delete(f"{BASE_URL}/api/tasks/{emp_task['id']}")
    assert r.status_code == 200
    r2 = s.get(f"{BASE_URL}/api/tasks/{emp_task['id']}")
    assert r2.status_code == 404


# --- backward compat ---
@pytest.mark.parametrize("path", [
    "/api/auth/me",
    "/api/dashboard/stats",
    "/api/projects",
    "/api/employees",
    "/api/leads",
    "/api/quotations-adv",
])
def test_backward_compat(s, path):
    r = s.get(f"{BASE_URL}{path}")
    assert r.status_code == 200, f"{path} -> {r.status_code} {r.text[:200]}"
