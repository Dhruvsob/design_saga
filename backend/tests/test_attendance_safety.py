"""Focused regression coverage for attendance identity and business dates."""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException

from routes import attendance


def test_attendance_manager_permission_is_explicit():
    assert attendance._can_manage_attendance({"permissions": ["attendance.update"]}) is True
    assert attendance._can_manage_attendance({"permissions": ["attendance.approve"]}) is True
    assert attendance._can_manage_attendance({"permissions": ["attendance.create"]}) is False


def test_regular_employee_cannot_supply_a_coworker_id():
    user = {"user_id": "user_a", "permissions": ["attendance.create"]}
    assert attendance._select_employee_id(user, None, "emp_a") == "emp_a"
    assert attendance._select_employee_id(user, "emp_a", "emp_a") == "emp_a"
    with pytest.raises(HTTPException) as exc:
        attendance._select_employee_id(user, "emp_b", "emp_a")
    assert exc.value.status_code == 403


def test_attendance_manager_can_target_an_employee():
    user = {"user_id": "manager", "permissions": ["attendance.update"]}
    assert attendance._select_employee_id(user, "emp_b", "emp_a") == "emp_b"


def test_today_uses_india_business_date(monkeypatch):
    ist = timezone(timedelta(hours=5, minutes=30))
    monkeypatch.setattr(
        attendance.engine,
        "now_ist",
        lambda: datetime(2026, 10, 13, 0, 15, tzinfo=ist),
    )
    assert attendance._today() == "2026-10-13"


def test_authorized_site_check_in_is_present_immediately():
    state = attendance._initial_attendance_state(
        "site_visit",
        True,
        {"inside": True, "matched_location": {"id": "site_a"}},
        False,
    )
    assert state == ("present", "auto")


def test_outside_site_check_in_still_requires_approval():
    geo = {"inside": False, "matched_location": {"id": "site_a"}}
    assert attendance._initial_attendance_state("site_visit", True, geo, True) == (
        "pending_approval", "pending",
    )


def test_unmatched_site_check_in_still_requires_approval():
    state = attendance._initial_attendance_state(
        "site_visit", True, {"inside": False, "matched_location": None}, True,
    )
    assert state == ("pending_approval", "pending")


def test_office_check_in_behavior_is_unchanged():
    assert attendance._initial_attendance_state(
        "office", True, {"inside": True, "matched_location": {"id": "hq"}}, False,
    ) == ("present", "auto")
