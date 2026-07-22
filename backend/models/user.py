"""User & auth request/response models."""
from pydantic import BaseModel, EmailStr, Field
from typing import Optional


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6, max_length=128)
    name: str = Field(min_length=1, max_length=120)
    role: Optional[str] = "Employee"
    phone: Optional[str] = None
    approve_immediately: Optional[bool] = True   # admin can create a pre-approved user


class LoginPasswordIn(BaseModel):
    identifier: str        # email OR employee_id (e.g. DS0001)
    password: str


class ChangePasswordIn(BaseModel):
    old_password: str
    new_password: str = Field(min_length=6, max_length=128)


class ResetPasswordIn(BaseModel):
    new_password: str = Field(min_length=6, max_length=128)


class ApprovalDecisionIn(BaseModel):
    decision: str          # approve | reject
    role: Optional[str] = None
    reason: Optional[str] = None
