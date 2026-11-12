"""One-time set-password links replace passwords chosen by platform staff (P0.6)."""
import asyncio
from datetime import timedelta
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import core.invites as invites
import routes.auth as auth
from core.helpers import now_utc


class _Invites:
    def __init__(self):
        self.rows = []

    async def delete_many(self, query):
        self.rows = [r for r in self.rows if not (r["user_id"] == query["user_id"] and r["used_at"] is None)]

    async def insert_one(self, doc):
        self.rows.append(dict(doc))

    async def find_one(self, query, _projection=None):
        for r in self.rows:
            if (r["token_hash"] == query["token_hash"] and r["used_at"] is None
                    and r["expires_at"] > query["expires_at"]["$gt"]):
                return dict(r)
        return None

    async def update_one(self, query, update):
        for r in self.rows:
            if r["token_hash"] == query["token_hash"] and r["used_at"] is None:
                r.update(update["$set"])
                return SimpleNamespace(modified_count=1)
        return SimpleNamespace(modified_count=0)


class _Users:
    def __init__(self):
        self.doc = {"user_id": "u1", "org_id": "org_a", "email": "owner@studio.test", "name": "Owner"}

    async def find_one(self, query, _projection=None):
        return dict(self.doc) if query.get("user_id") == "u1" else None

    async def update_one(self, _query, update):
        self.doc.update(update["$set"])


@pytest.fixture
def fake(monkeypatch):
    db = SimpleNamespace(user_invites=_Invites(), users=_Users(),
                         organizations=SimpleNamespace(find_one=_org))
    monkeypatch.setattr(invites, "db", db)
    monkeypatch.setattr(auth, "db", db)
    reset = []

    async def reset_security(user):
        reset.append(user["user_id"])

    async def audit(*_a, **_k):
        return None

    monkeypatch.setattr(auth, "reset_user_security_after_admin_password_change", reset_security)
    monkeypatch.setattr(auth, "audit", audit)
    return SimpleNamespace(db=db, reset=reset)


async def _org(*_a, **_k):
    return {"name": "Studio A"}


def _token(path):
    assert path.startswith("/invite/")
    return path.removeprefix("/invite/")


def test_link_sets_the_password_once_and_ends_sessions(fake):
    token = _token(asyncio.run(invites.issue_set_password_link(fake.db.users.doc, "invite", "sa")))
    assert all(token not in str(r) for r in fake.db.user_invites.rows)   # only the hash is stored

    details = asyncio.run(auth.invite_details(token))
    assert details["workspace"] == "Studio A" and details["email"] == "owner@studio.test"

    asyncio.run(auth.accept_invite(auth.InviteAcceptIn(token=token, password="NewSecure123")))
    assert auth.verify_password("NewSecure123", fake.db.users.doc["password_hash"])
    assert fake.reset == ["u1"]
    with pytest.raises(HTTPException) as exc:                          # single use
        asyncio.run(auth.accept_invite(auth.InviteAcceptIn(token=token, password="Another123")))
    assert exc.value.status_code == 404


def test_new_link_replaces_an_unused_one_and_expired_links_fail(fake):
    first = _token(asyncio.run(invites.issue_set_password_link(fake.db.users.doc, "reset", "sa")))
    second = _token(asyncio.run(invites.issue_set_password_link(fake.db.users.doc, "reset", "sa")))
    assert asyncio.run(invites.find_valid_invite(first)) is None
    assert asyncio.run(invites.find_valid_invite(second)) is not None
    fake.db.user_invites.rows[-1]["expires_at"] = now_utc() - timedelta(seconds=1)
    with pytest.raises(HTTPException):
        asyncio.run(auth.invite_details(second))
