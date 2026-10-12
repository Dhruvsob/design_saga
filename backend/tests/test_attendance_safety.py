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


def test_leave_never_overwrites_a_real_punch_or_worked_status():
    assert attendance._attendance_allows_leave(None) is True
    assert attendance._attendance_allows_leave({"status": "absent"}) is True
    assert attendance._attendance_allows_leave({"status": "leave"}) is True
    assert attendance._attendance_allows_leave({"status": "present"}) is False
    assert attendance._attendance_allows_leave({
        "status": "absent", "check_in": "2026-10-12T09:00:00+05:30",
    }) is False


def test_correction_requires_valid_same_day_ordered_times():
    attendance._validate_correction_request(
        "2026-10-12",
        "2026-10-12T09:00:00+05:30",
        "2026-10-12T18:00:00+05:30",
    )
    with pytest.raises(HTTPException):
        attendance._validate_correction_request("2026-10-12", None, None)
    with pytest.raises(HTTPException):
        attendance._validate_correction_request(
            "2026-10-12", "2026-10-13T09:00:00+05:30", None,
        )
    with pytest.raises(HTTPException):
        attendance._validate_correction_request(
            "2026-10-12",
            "2026-10-12T18:00:00+05:30",
            "2026-10-12T09:00:00+05:30",
        )


def test_team_attendance_can_be_returned_without_compensation():
    safe = attendance._without_compensation({
        "employee": {"id": "emp_a", "monthly_salary": 50000},
        "summary": {"present": 20},
        "payable_days": 20,
        "net_payable": 45000,
        "deduction": 5000,
        "late_fine": 100,
        "daily": [],
    })
    assert safe["employee"] == {"id": "emp_a"}
    assert safe["summary"] == {"present": 20}
    assert "net_payable" not in safe
    assert "deduction" not in safe
    assert "late_fine" not in safe
