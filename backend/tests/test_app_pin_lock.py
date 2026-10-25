"""Regression tests for the personal inactivity PIN lock."""
import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import routes.auth as auth
from core.session_lock import (
    enforce_session_pin,
    session_is_recent,
    session_pin_locked,
)
from routes.auth import _validate_app_pin


NOW = datetime(2026, 10, 25, 12, 0, tzinfo=timezone.utc)


def test_pin_lock_is_fail_closed_when_unlock_lease_is_missing_or_expired():
    assert session_pin_locked({"pin_required": True}, at=NOW) is True
    assert session_pin_locked({
        "pin_required": True,
        "pin_unlocked_until": NOW - timedelta(seconds=1),
    }, at=NOW) is True


def test_pin_lock_allows_only_a_live_unlock_lease():
    assert session_pin_locked({
        "pin_required": True,
        "pin_unlocked_until": NOW + timedelta(seconds=1),
    }, at=NOW) is False
    assert session_pin_locked({"pin_required": False}, at=NOW) is False
    assert session_pin_locked({}, at=NOW) is False


def test_pin_lock_accepts_iso_dates_and_rejects_invalid_dates():
    assert session_pin_locked({
        "pin_required": True,
        "pin_unlocked_until": (NOW + timedelta(seconds=1)).isoformat(),
    }, at=NOW) is False
    assert session_pin_locked({
        "pin_required": True,
        "pin_unlocked_until": "not-a-date",
    }, at=NOW) is True


def test_pin_must_be_exactly_six_numeric_digits():
    assert _validate_app_pin("012345") == "012345"
    for invalid in ("1234", "1234567", "12a456", "", None):
        with pytest.raises(HTTPException) as exc:
            _validate_app_pin(invalid)
        assert exc.value.status_code == 400


def test_recent_login_window_is_bounded_and_rejects_future_timestamps():
    assert session_is_recent({"created_at": NOW - timedelta(minutes=9)}, at=NOW)
    assert session_is_recent({"created_at": NOW - timedelta(minutes=11)}, at=NOW) is False
    assert session_is_recent({"created_at": NOW + timedelta(seconds=1)}, at=NOW) is False
    assert session_is_recent({}, at=NOW) is False


def test_server_guard_blocks_expired_pin_session():
    request = SimpleNamespace(state=SimpleNamespace(auth_session={
        "pin_required": True,
        "pin_unlocked_until": datetime.now(timezone.utc) - timedelta(seconds=1),
    }))
    with pytest.raises(HTTPException) as exc:
        asyncio.run(enforce_session_pin(request))
    assert exc.value.status_code == 423


def test_server_guard_allows_unlocked_or_non_pin_session():
    unlocked = SimpleNamespace(state=SimpleNamespace(auth_session={
        "pin_required": True,
        "pin_unlocked_until": datetime.now(timezone.utc) + timedelta(seconds=30),
    }))
    ordinary = SimpleNamespace(state=SimpleNamespace(auth_session={}))
    asyncio.run(enforce_session_pin(unlocked))
    asyncio.run(enforce_session_pin(ordinary))


def test_incorrect_pin_attempts_are_counted_and_lock_after_five(monkeypatch):
    class Locks:
        def __init__(self):
            self.doc = {
                "user_id": "user_a", "enabled": True,
                "pin_hash": auth.hash_password("654321"), "failed_attempts": 0,
            }

        async def find_one(self, query, _projection=None):
            if query.get("user_id") != self.doc["user_id"]:
                return None
            return dict(self.doc)

        async def update_one(self, _query, update):
            for key, amount in update.get("$inc", {}).items():
                self.doc[key] = int(self.doc.get(key) or 0) + amount
            self.doc.update(update.get("$set", {}))
            for key in update.get("$unset", {}):
                self.doc.pop(key, None)

    locks = Locks()
    monkeypatch.setattr(auth, "db", SimpleNamespace(user_app_locks=locks))
    user = {"user_id": "user_a"}

    for remaining in (4, 3, 2, 1):
        with pytest.raises(HTTPException) as exc:
            asyncio.run(auth._verify_app_pin(user, "000000"))
        assert exc.value.status_code == 401
        assert f"{remaining} attempt(s) remaining" in exc.value.detail

    with pytest.raises(HTTPException) as exc:
        asyncio.run(auth._verify_app_pin(user, "000000"))
    assert exc.value.status_code == 429
    assert locks.doc["failed_attempts"] == 5
    assert locks.doc.get("locked_until") is not None
