"""Public demo/contact request intake for the Gamaa landing page.

The endpoint deliberately accepts only a small, validated text payload. It
does not authenticate because prospective customers are not ERP users yet;
abuse is bounded by the shared HTTP rate limiter and a hidden honeypot field.
Only the platform-owner API can read the stored requests.
"""
import re
import uuid
from typing import Literal, Optional

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from core.db import db
from core.helpers import iso_now


router = APIRouter()


def _plain_text(value):
    if not isinstance(value, str):
        return value
    # Preserve normal newlines/tabs but remove non-printing control bytes.
    return re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", value).strip()


class ContactRequestIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=2, max_length=120)
    company: str = Field(min_length=2, max_length=160)
    email: EmailStr
    phone: Optional[str] = Field(default=None, max_length=40)
    type: Optional[Literal[
        "architecture", "interior", "consultancy", "turnkey", "hybrid",
    ]] = None
    message: Optional[str] = Field(default=None, max_length=2000)
    # Humans never see/fill this field. Bots that do receive the same generic
    # success response without creating database noise.
    website: str = Field(default="", max_length=200)

    _clean_text = field_validator(
        "name", "company", "phone", "message", "website", mode="before",
    )(_plain_text)


@router.post("/contact", status_code=202)
async def submit_contact(payload: ContactRequestIn):
    if payload.website:
        return {"ok": True}

    doc = payload.model_dump(exclude={"website"})
    doc.update({
        "request_id": "contact_" + uuid.uuid4().hex[:16],
        "email": str(payload.email).lower(),
        "status": "new",
        "source": "gamaa_public_landing",
        "created_at": iso_now(),
    })
    await db.contact_requests.insert_one(doc)
    return {"ok": True}
