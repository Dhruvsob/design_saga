"""A blank optional time is "not set", not a failed request.

Production 2026-11-16: a site-visit check-in with "Expected time" left blank
sent expected_time="" and the whole check-in failed with 422."""
import pytest
from pydantic import ValidationError

from models.attendance import AttendancePolicyIn, CheckInIn, EmployeeAttendanceConfigIn


@pytest.mark.parametrize("blank", ["", "   ", None])
def test_blank_expected_time_on_a_site_visit_check_in_is_accepted(blank):
    body = CheckInIn(attendance_type="site_visit", project_id="prj_1", site_location="Bopal", expected_time=blank)
    assert body.expected_time is None


def test_a_real_expected_time_is_kept_and_a_wrong_one_is_refused():
    assert CheckInIn(attendance_type="site_visit", expected_time=" 14:30 ").expected_time == "14:30"
    with pytest.raises(ValidationError, match="HH:MM"):
        CheckInIn(attendance_type="site_visit", expected_time="2pm")


def test_blank_employee_shift_means_use_the_workspace_hours():
    cfg = EmployeeAttendanceConfigIn(shift_start="", shift_end="")
    assert cfg.shift_start is None and cfg.shift_end is None
    with pytest.raises(ValidationError):
        EmployeeAttendanceConfigIn(shift_start="25:00")


def test_policy_office_hours_stay_required():
    with pytest.raises(ValidationError):
        AttendancePolicyIn(office_start="")
