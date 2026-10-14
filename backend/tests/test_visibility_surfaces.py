"""Regression coverage for secondary visibility surfaces."""
import asyncio

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from routes.calendar import _date_window
from routes.comments import CommentIn, _require_entity_access


def test_calendar_window_is_validated_and_bounded():
    assert _date_window("2026-01-01", "2026-12-31") == ("2026-01-01", "2026-12-31")

    with pytest.raises(HTTPException) as reversed_range:
        _date_window("2026-02-01", "2026-01-01")
    assert reversed_range.value.status_code == 400

    with pytest.raises(HTTPException) as oversized_range:
        _date_window("2025-01-01", "2026-12-31")
    assert oversized_range.value.status_code == 400


def test_comment_payload_limits_are_enforced():
    with pytest.raises(ValidationError):
        CommentIn(entity_type="project", entity_id="", body="valid")
    with pytest.raises(ValidationError):
        CommentIn(entity_type="project", entity_id="project_1", body="x" * 5001)


def test_comment_entity_permission_is_required_before_lookup():
    user = {"user_id": "user_1", "role": "Client", "permissions": []}
    with pytest.raises(HTTPException) as exc:
        asyncio.run(_require_entity_access(user, "vendor", "vendor_1"))
    assert exc.value.status_code == 403
