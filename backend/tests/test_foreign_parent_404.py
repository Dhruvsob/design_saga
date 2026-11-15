"""Reads keyed by a parent record answer 404 when that record is not in the
caller's workspace (the cross-tenant probe saw empty 200s: no data leaked,
but a 404 is the honest answer and matches every other ID route)."""
import asyncio

import pytest
from fastapi import HTTPException

import routes.accounting as accounting
import routes.finance_extras as fx
import routes.vendors as vendors


class _Cursor:
    def __init__(self, rows):
        self.rows = rows

    def sort(self, *_a, **_k):
        return self

    async def to_list(self, _n=None):
        return list(self.rows)

    def __aiter__(self):
        self._it = iter(self.rows)
        return self

    async def __anext__(self):
        try:
            return next(self._it)
        except StopIteration:
            raise StopAsyncIteration


class _Coll:
    def __init__(self, rows=()):
        self.rows = list(rows)

    async def find_one(self, q, _p=None):
        return next((r for r in self.rows if all(r.get(k) == v for k, v in q.items())), None)

    def find(self, *_a, **_k):
        return _Cursor([])


class _Scoped:
    def __init__(self, **colls):
        self.colls = colls

    def __getattr__(self, name):
        return self.colls.setdefault(name, _Coll())

    def __getitem__(self, name):
        return getattr(self, name)


FIN = {"user_id": "u", "org_id": "org_a", "permissions": ["finance.read"]}


@pytest.fixture
def own(monkeypatch):
    fake = _Scoped(accounts=_Coll([{"id": "acc_bank"}]), vendors_acc=_Coll([{"id": "ven_own"}]),
                   invoices=_Coll([{"id": "inv_own"}]))

    async def user(*_a, **_k):
        return FIN

    for mod in (accounting, fx, vendors):
        monkeypatch.setattr(mod, "sdb", fake)
        monkeypatch.setattr(mod, "require_user", user)
        monkeypatch.setattr(mod, "has_permission", lambda u, p: p in u["permissions"])

    async def no_stats(_bid):
        return {}
    monkeypatch.setattr(fx, "_batch_live_stats", no_stats)
    return fake


def run(coro):
    return asyncio.run(coro)


@pytest.mark.parametrize("call", [
    lambda: fx.list_bank_batches("acc_other_workspace", request=None),
    lambda: fx.list_bank_rows("acc_other_workspace", request=None),
    lambda: vendors.list_vendor_commissions("ven_other_workspace", request=None),
    lambda: accounting.collection_entries("invoice", "inv_other_workspace", request=None),
])
def test_foreign_parent_is_404(own, call):
    with pytest.raises(HTTPException) as exc:
        run(call())
    assert exc.value.status_code == 404


def test_own_parent_still_answers(own):
    assert run(fx.list_bank_batches("acc_bank", request=None)) == {"batches": []}
    assert run(vendors.list_vendor_commissions("ven_own", request=None)) == []
    out = run(accounting.collection_entries("invoice", "inv_own", request=None))
    assert out["source_id"] == "inv_own" and out["receipts"] == []
