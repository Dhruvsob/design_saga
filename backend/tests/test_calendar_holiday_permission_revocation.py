import asyncio

import pytest
from fastapi import HTTPException

from routes import calendar, holidays


async def _revoked_user(*_args, **_kwargs):
    return {
        "user_id": "usr_revoked",
        "org_id": "org_test",
        "role": "Custom",
        "permissions": [],
    }


def test_calendar_update_fails_after_permission_revocation(monkeypatch):
    monkeypatch.setattr(calendar, "require_user", _revoked_user)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(calendar.update_event("evt_owned", calendar.EventUpdate(title="Changed"), None))

    assert exc.value.status_code == 403
    assert exc.value.detail == "Missing permission: calendar.read"


def test_calendar_delete_fails_after_permission_revocation(monkeypatch):
    monkeypatch.setattr(calendar, "require_user", _revoked_user)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(calendar.delete_event("evt_owned", None))

    assert exc.value.status_code == 403
    assert exc.value.detail == "Missing permission: calendar.read"


def test_holiday_probe_requires_read_permission(monkeypatch):
    monkeypatch.setattr(holidays, "require_user", _revoked_user)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(holidays.is_holiday("2026-10-29", None))

    assert exc.value.status_code == 403
    assert exc.value.detail == "Missing permission: holidays.read"
