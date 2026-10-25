import pytest
from pydantic import ValidationError

from models.organization import OrgCreateIn
from models.user import ChangePasswordIn, RegisterIn, ResetPasswordIn
from server import EmployeeAccountIn, EmployeePasswordResetIn


@pytest.mark.parametrize("password", [
    "abcdefgh",
    "12345678",
    "short1",
])
def test_every_account_creation_path_rejects_weak_passwords(password):
    with pytest.raises(ValidationError):
        RegisterIn(email="user@example.com", name="User", password=password)
    with pytest.raises(ValidationError):
        OrgCreateIn(
            name="Example Studio",
            admin_email="admin@example.com",
            admin_name="Admin",
            admin_password=password,
        )
    with pytest.raises(ValidationError):
        EmployeeAccountIn(password=password)


@pytest.mark.parametrize("password", ["abcdefgh", "12345678", "short1"])
def test_every_password_reset_path_rejects_weak_passwords(password):
    with pytest.raises(ValidationError):
        ChangePasswordIn(old_password="OldPassword1", new_password=password)
    with pytest.raises(ValidationError):
        ResetPasswordIn(new_password=password)
    with pytest.raises(ValidationError):
        EmployeePasswordResetIn(password=password)


def test_strong_password_is_accepted_everywhere():
    password = "SecurePass123"
    assert RegisterIn(email="user@example.com", name="User", password=password).password == password
    assert OrgCreateIn(
        name="Example Studio",
        admin_email="admin@example.com",
        admin_name="Admin",
        admin_password=password,
    ).admin_password == password
    assert EmployeeAccountIn(password=password).password == password
    assert EmployeePasswordResetIn(password=password).password == password


def test_employee_password_reset_cannot_keep_existing_sessions():
    with pytest.raises(ValidationError):
        EmployeePasswordResetIn(password="SecurePass123", sign_out_everywhere=False)
