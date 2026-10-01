"""Regression tests for production password-login identifier lookup."""

from routes.auth import _identifier_query


def test_email_lookup_is_normalized():
    assert {"email": "owner@example.com"} in _identifier_query(
        "Owner@Example.com"
    )["$or"]


def test_tenant_employee_id_format_is_not_hard_coded():
    query = _identifier_query("emp-2026-0001")
    employee_clause = next(part for part in query["$or"] if "employee_id" in part)
    assert "EMP-2026-0001" in employee_clause["employee_id"]["$in"]


def test_internal_user_id_is_supported():
    assert {"user_id": "user_abc123"} in _identifier_query("user_abc123")["$or"]
