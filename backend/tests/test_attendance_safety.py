"""Focused regression coverage for attendance identity and business dates."""

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from routes import attendance
from models.attendance import (
    AttendancePolicyIn, CheckInIn, EmployeeAttendanceConfigIn, GeoLocationIn,
)


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


def test_attendance_project_options_include_authorized_site_projects(monkeypatch):
    class Locations:
        async def distinct(self, field, query):
            assert field == "project_id"
            assert query["kind"] == "site"
            return ["project_site"]

    async def assigned_only(_user):
        return {"$or": [{"team_ids": {"$in": ["emp_a"]}}]}

    monkeypatch.setattr(
        attendance, "sdb", SimpleNamespace(office_locations=Locations()),
    )
    monkeypatch.setattr(attendance, "project_visibility_query", assigned_only)
    query = asyncio.run(attendance._attendance_project_query({
        "user_id": "user_a", "permissions": ["attendance.create"],
    }))
    assert query == {
        "$and": [
            {"archived": {"$ne": True}},
            {"$or": [
                {"$or": [{"team_ids": {"$in": ["emp_a"]}}]},
                {"id": {"$in": ["project_site"]}},
            ]},
        ],
    }


def test_attendance_managers_can_choose_any_active_project():
    query = asyncio.run(attendance._attendance_project_query({
        "user_id": "manager", "permissions": ["attendance.update"],
    }))
    assert query == {"archived": {"$ne": True}}


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


def test_rejected_attendance_can_be_retried_but_other_punches_cannot():
    rejected = {"status": "absent", "approval_status": "rejected", "check_in": "old"}
    assert attendance._retryable_rejected_punch(rejected) is True
    assert attendance._retryable_rejected_punch({**rejected, "approval_status": "pending"}) is False
    assert attendance._retryable_rejected_punch({**rejected, "status": "present"}) is False


def test_rejected_retry_archives_prior_attempt(monkeypatch):
    class Result:
        matched_count = 1

    class Collection:
        args = None

        async def update_one(self, query, update):
            self.args = (query, update)
            return Result()

    collection = Collection()
    monkeypatch.setattr(attendance, "sdb", SimpleNamespace(attendance=collection))
    existing = {
        "id": "att_1", "status": "absent", "approval_status": "rejected",
        "check_in": "2026-10-13T09:00:00+05:30", "check_out": "2026-10-13T10:00:00+05:30",
        "approval_remarks": "Outside authorized site",
    }
    replacement = {
        "id": "att_1", "status": "present", "approval_status": "auto",
        "check_in": "2026-10-13T11:00:00+05:30",
    }
    asyncio.run(attendance._store_check_in(existing, replacement, retry_rejected=True))
    query, update = collection.args
    assert query == {"id": "att_1", "approval_status": "rejected", "status": "absent"}
    assert update["$set"] == replacement
    assert update["$push"]["rejected_attempts"]["check_in"] == existing["check_in"]
    assert update["$push"]["rejected_attempts"]["approval_remarks"] == "Outside authorized site"
    assert "check_out" in update["$unset"]


def test_employee_weekly_off_overrides_org_policy():
    policy = {"weekly_off_days": [6]}
    assert attendance._weekly_off_days({"weekly_offs": [2]}, policy) == [2]
    assert attendance._weekly_off_days({"weekly_offs": []}, policy) == []
    assert attendance._weekly_off_days({}, policy) == [6]


def test_manual_attendance_rejects_invalid_cross_day_and_reversed_times():
    attendance._validate_manual_attendance(
        "2026-10-13", "2026-10-13T09:00:00+05:30", "2026-10-13T18:00:00+05:30",
    )
    with pytest.raises(HTTPException):
        attendance._validate_manual_attendance("bad-date", None, None)
    with pytest.raises(HTTPException):
        attendance._validate_manual_attendance("2026-10-13", None, "2026-10-13T18:00:00+05:30")
    with pytest.raises(HTTPException):
        attendance._validate_manual_attendance(
            "2026-10-13", "2026-10-14T09:00:00+05:30", None,
        )
    with pytest.raises(HTTPException):
        attendance._validate_manual_attendance(
            "2026-10-13", "2026-10-13T18:00:00+05:30", "2026-10-13T09:00:00+05:30",
        )


def test_attendance_models_reject_invalid_types_geo_and_schedules():
    with pytest.raises(ValidationError):
        CheckInIn(attendance_type="somewhere")
    with pytest.raises(ValidationError):
        CheckInIn(lat=91, lng=72)
    with pytest.raises(ValidationError):
        GeoLocationIn(name="HQ", kind="office", lat=23, lng=72, radius_m=-1)
    with pytest.raises(ValidationError):
        AttendancePolicyIn(office_start="25:00")
    with pytest.raises(ValidationError):
        AttendancePolicyIn(weekly_off_days=[7])
    with pytest.raises(ValidationError):
        EmployeeAttendanceConfigIn(shift_start="9am")
