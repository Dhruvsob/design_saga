"""Employee non-financial correction workflow regressions."""

import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

import server


class _Employees:
    def __init__(self, matched=1):
        self.matched = matched
        self.calls = []

    async def update_one(self, query, update):
        self.calls.append((query, update))
        return SimpleNamespace(matched_count=self.matched)


def _install(monkeypatch, user):
    employees = _Employees()
    audits = []

    async def require_user(*_args, **_kwargs):
        return user

    async def audit_log(*args, **kwargs):
        audits.append((args, kwargs))

    monkeypatch.setattr(server, "require_user", require_user)
    monkeypatch.setattr(server, "audit_log", audit_log)
    monkeypatch.setattr(server, "sdb", SimpleNamespace(employees=employees))
    return employees, audits


def test_warning_and_reward_models_reject_blank_or_oversized_content():
    with pytest.raises(ValidationError):
        server.WarningIn(reason="   ")
    with pytest.raises(ValidationError):
        server.RewardIn(title="x" * 301)


def test_authorized_warning_edit_targets_only_nested_record_and_audits(monkeypatch):
    employees, audits = _install(
        monkeypatch,
        {"user_id": "usr_admin", "permissions": ["employees.update"]},
    )

    result = asyncio.run(server.update_warning(
        "emp_1", "warn_1", server.WarningIn(reason=" Corrected ", note="Safe note"),
        object(), None, None,
    ))

    query, update = employees.calls[0]
    assert query == {"id": "emp_1", "performance.warnings.id": "warn_1"}
    assert update["$set"]["performance.warnings.$.reason"] == "Corrected"
    assert result["id"] == "warn_1"
    assert audits[0][0][1] == "employee.warning.update"
    assert audits[0][1]["meta"] == {"warning_id": "warn_1"}


def test_authorized_reward_delete_is_scoped_and_audited(monkeypatch):
    employees, audits = _install(
        monkeypatch,
        {"user_id": "usr_admin", "permissions": ["employees.update"]},
    )

    result = asyncio.run(server.remove_reward(
        "emp_1", "rwd_1", object(), None, None,
    ))

    query, update = employees.calls[0]
    assert query == {"id": "emp_1", "performance.rewards.id": "rwd_1"}
    assert update["$pull"] == {"performance.rewards": {"id": "rwd_1"}}
    assert result == {"ok": True}
    assert audits[0][0][1] == "employee.reward.remove"


def test_employee_correction_requires_update_permission(monkeypatch):
    employees, audits = _install(
        monkeypatch,
        {"user_id": "usr_employee", "permissions": ["employees.read"]},
    )

    with pytest.raises(HTTPException) as exc:
        asyncio.run(server.remove_warning(
            "emp_1", "warn_1", object(), None, None,
        ))

    assert exc.value.status_code == 403
    assert employees.calls == []
    assert audits == []


def test_employee_document_edit_is_nested_scoped_and_audited(monkeypatch):
    employees, audits = _install(
        monkeypatch,
        {"user_id": "usr_admin", "permissions": ["employees.update"]},
    )

    result = asyncio.run(server.update_employee_doc(
        "emp_1", "edoc_1",
        server.DocumentIn(label=" Offer letter ", url="https://files.example/offer.pdf"),
        object(), None, None,
    ))

    query, update = employees.calls[0]
    assert query == {"id": "emp_1", "documents.id": "edoc_1"}
    assert update["$set"]["documents.$.label"] == "Offer letter"
    assert update["$set"]["documents.$.url"] == "https://files.example/offer.pdf"
    assert result["id"] == "edoc_1"
    assert audits[0][0][1] == "employee.document.update"
    assert audits[0][1]["meta"] == {"document_id": "edoc_1"}
