"""Deactivating a chart-of-accounts entry is audited and refuses unknown IDs
(the cross-tenant probe saw {"ok": true} for another workspace's account ID)."""
import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import routes.accounting as acc


class _Accounts:
    def __init__(self):
        self.rows = [{"id": "acc_rent", "name": "Rent", "code": "4100", "active": True}]

    async def find_one(self, q, _p=None):
        return next((dict(r) for r in self.rows if r["id"] == q.get("id")), None)

    async def update_one(self, q, u):
        for r in self.rows:
            if r["id"] == q.get("id"):
                r.update(u["$set"])


@pytest.fixture
def env(monkeypatch):
    accounts, audits = _Accounts(), []

    async def user(*_a, **_k):
        return {"user_id": "u_acct", "org_id": "org_a", "permissions": ["finance.delete"]}

    async def record(actor, action, **kw):
        audits.append((action, kw.get("target")))

    monkeypatch.setattr(acc, "sdb", SimpleNamespace(accounts=accounts))
    monkeypatch.setattr(acc, "require_user", user)
    monkeypatch.setattr(acc, "has_permission", lambda u, p: p in u["permissions"])
    monkeypatch.setattr(acc, "audit", record)
    return accounts, audits


def test_unknown_account_is_404(env):
    with pytest.raises(HTTPException) as exc:
        asyncio.run(acc.deactivate_account("acc_other_workspace", request=None))
    assert exc.value.status_code == 404


def test_deactivation_is_soft_and_audited_once(env):
    accounts, audits = env
    assert asyncio.run(acc.deactivate_account("acc_rent", request=None)) == {"ok": True}
    assert accounts.rows[0]["active"] is False and accounts.rows[0]["deactivated_by"] == "u_acct"
    asyncio.run(acc.deactivate_account("acc_rent", request=None))      # repeat: no second audit row
    assert audits == [("account.deactivate", "acc_rent")]
