"""Attendance enhancements + Holiday Calendar tests."""
import os
import pytest
import requests
from datetime import datetime, timezone

BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE}/api"
ADMIN_TOK = "stable_testtok_do_not_delete"


def _h(tok=ADMIN_TOK):
    return {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def admin():
    return _h()


# ============================================================
# Holiday Calendar
# ============================================================
def test_holiday_crud_and_recurring(admin):
    # Cleanup
    for h in requests.get(f"{API}/holidays", headers=admin).json().get("holidays", []):
        requests.delete(f"{API}/holidays/{h['id']}", headers=admin)

    # Create a national recurring holiday
    r = requests.post(f"{API}/holidays", headers=admin, json={
        "date": "2026-01-26", "name": "Republic Day",
        "kind": "national", "recurring": True,
    })
    assert r.status_code == 200, r.text
    hid = r.json()["id"]

    # Duplicate is rejected
    r2 = requests.post(f"{API}/holidays", headers=admin, json={
        "date": "2026-01-26", "name": "Republic Day", "kind": "national",
    })
    assert r2.status_code == 409

    # List for 2028 → recurring rolls forward
    r3 = requests.get(f"{API}/holidays?year=2028&include_weekly_off=true", headers=admin)
    assert r3.status_code == 200
    d3 = r3.json()
    matches = [x for x in d3["holidays"] if x["date"] == "2028-01-26"]
    assert matches and matches[0]["name"] == "Republic Day"
    assert matches[0].get("materialized_from_recurring")
    # Weekly-off dates included
    assert isinstance(d3["weekly_off_dates"], list) and len(d3["weekly_off_dates"]) >= 52

    # is-holiday probe (recurring match on a future year)
    probe = requests.get(f"{API}/holidays/is-holiday/2030-01-26", headers=admin).json()
    assert probe["is_holiday"] is True and probe["holiday"] is not None

    # Non-holiday date returns false
    probe2 = requests.get(f"{API}/holidays/is-holiday/2030-08-14", headers=admin).json()
    assert probe2["is_holiday"] is False or probe2["is_weekly_off"] is False

    # Delete
    d = requests.delete(f"{API}/holidays/{hid}", headers=admin)
    assert d.status_code == 200


def test_holiday_bulk_seed(admin):
    payload = {
        "year": 2027,
        "holidays": [
            {"date": "2027-08-15", "name": "Independence Day", "kind": "national", "recurring": True},
            {"date": "2027-10-02", "name": "Gandhi Jayanti", "kind": "national", "recurring": True},
            {"date": "2027-12-25", "name": "Christmas", "kind": "festival", "recurring": True},
        ],
    }
    r = requests.post(f"{API}/holidays/bulk", headers=admin, json=payload)
    assert r.status_code == 200
    d = r.json()
    assert d["inserted"] == 3
    # Second run should insert 0 (idempotent)
    r2 = requests.post(f"{API}/holidays/bulk", headers=admin, json=payload)
    assert r2.json()["inserted"] == 0


def test_holiday_kind_validation(admin):
    r = requests.post(f"{API}/holidays", headers=admin, json={
        "date": "2029-06-01", "name": "X", "kind": "invalid_kind",
    })
    assert r.status_code == 400


def test_holiday_admin_only():
    r = requests.post(f"{API}/holidays", headers=_h("newbie_tok"), json={
        "date": "2029-06-01", "name": "X", "kind": "company",
    })
    assert r.status_code in (401, 403)


# ============================================================
# Attendance enhancements
# ============================================================
def test_attendance_policy_carries_new_fields(admin):
    r = requests.put(f"{API}/attendance/policy", headers=admin, json={
        "office_start": "10:00", "office_end": "19:00",
        "grace_minutes": 15, "half_day_min_hours": 4, "full_day_min_hours": 8,
        "weekly_off_days": [6], "holidays": [],
        "geo_fencing_enabled": True, "require_geo_for_office": False,
        "approval_required_when_outside": True,
        "max_gps_accuracy_m": 75, "require_late_reason": True,
    })
    assert r.status_code == 200
    p = r.json()
    assert p["max_gps_accuracy_m"] == 75
    assert p["require_late_reason"] is True
