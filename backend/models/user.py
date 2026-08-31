"""User & auth request/response models."""
from pydantic import BaseModel, EmailStr, Field, field_validator
from typing import Optional
import re


_STRONG_PW = re.compile(r"^(?=.*[A-Za-z])(?=.*\d).{8,128}$")


def _validate_password(v: str) -> str:
    if not _STRONG_PW.match(v or ""):
        raise ValueError(
            "Password must be at least 8 characters and contain both letters and digits."
        )
    return v


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    name: str = Field(min_length=1, max_length=120)
    role: Optional[str] = "Employee"
    phone: Optional[str] = None
    approve_immediately: Optional[bool] = True   # admin can create a pre-approved user

    @field_validator("password")
    @classmethod
    def _pw(cls, v):
        return _validate_password(v)


class LoginPasswordIn(BaseModel):
    identifier: str        # email OR employee_id (e.g. DS0001)
    password: str


class ChangePasswordIn(BaseModel):
    old_password: str
    new_password: str = Field(min_length=8, max_length=128)

    @field_validator("new_password")
    @classmethod
    def _pw(cls, v):
        return _validate_password(v)


class ResetPasswordIn(BaseModel):
    new_password: str = Field(min_length=8, max_length=128)

    @field_validator("new_password")
    @classmethod
    def _pw(cls, v):
        return _validate_password(v)


class ApprovalDecisionIn(BaseModel):
    decision: str          # approve | reject
    role: Optional[str] = None
    reason: Optional[str] = None
