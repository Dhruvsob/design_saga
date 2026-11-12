"""P1.6 usage per workspace and P1.4 workspace-scoped sign-in."""
import asyncio
from types import SimpleNamespace

from starlette.requests import Request

import routes.auth as auth
import routes.platform as platform
from services import local_files


class _Cursor:
    def __init__(self, rows):
        self.rows = rows

    def sort(self, *_a, **_k):
        return self

    def __aiter__(self):
        async def it():
            for r in self.rows:
                yield dict(r)
        return it()


def _matches(row, query):
    for k, v in query.items():
        if k == "$or":
            if not any(_matches(row, q) for q in v):
                return False
        elif isinstance(v, dict):
            if "$ne" in v and row.get(k) == v["$ne"]:
                return False
            if "$exists" in v and (k in row) != v["$exists"]:
                return False
        elif row.get(k) != v:
            return False
    return True


class _Coll:
    def __init__(self, rows):
        self.rows = rows

    def find(self, query=None, _p=None):
        return _Cursor([r for r in self.rows if _matches(r, query or {})])

    async def count_documents(self, query):
        return sum(1 for r in self.rows if _matches(r, query))

    async def find_one(self, query, _p=None, sort=None):
        rows = [r for r in self.rows if _matches(r, query)]
        if sort:
            key, direction = sort[0]
            rows.sort(key=lambda r: r.get(key) or "", reverse=direction < 0)
        return dict(rows[0]) if rows else None


def _request():
    return Request({"type": "http", "method": "GET", "path": "/api/platform/usage", "headers": [],
                    "client": ("203.0.113.10", 1), "scheme": "https", "server": ("gamaa.in", 443)})


def test_usage_reports_seats_projects_and_files_per_workspace(monkeypatch, tmp_path):
    monkeypatch.setattr(local_files, "STORAGE_ROOT", tmp_path)
    monkeypatch.setattr(local_files, "MAX_TENANT_STORAGE_BYTES", 512 * 1024 * 1024)
    (tmp_path / "org_a").mkdir()
    (tmp_path / "org_a" / "a.pdf").write_bytes(b"x" * 2048)
    (tmp_path / "org_a" / "b.tmp").write_bytes(b"x" * 999)          # unfinished upload: ignored
    db = SimpleNamespace(
        organizations=_Coll([
            {"org_id": "org_a", "name": "Studio A", "slug": "studio-a", "plan": "pro",
             "features": {"limits": {"max_users": 5, "max_projects": 10, "storage_mb": 100}}},
            {"org_id": "org_b", "name": "Studio B", "slug": "studio-b", "is_active": False},
        ]),
        users=_Coll([
            {"org_id": "org_a", "is_active": True, "last_login": "2026-11-10T09:00:00"},
            {"org_id": "org_a", "is_active": True, "last_login": "2026-11-12T09:00:00"},
            {"org_id": "org_a", "is_active": False},
            {"org_id": "org_b", "is_active": True},
        ]),
        projects=_Coll([{"org_id": "org_a"}, {"org_id": "org_a"}, {"org_id": "org_b"}]),
    )

    async def super_admin(*_a, **_k):
        return {"user_id": "sa"}

    async def ai_calls(org_id):
        return {"org_a": 7}.get(org_id, 0)

    import core.entitlements as entitlements
    monkeypatch.setattr(platform, "db", db)
    monkeypatch.setattr(platform, "require_super_admin", super_admin)
    monkeypatch.setattr(entitlements, "ai_calls_this_month", ai_calls)
    out = asyncio.run(platform.platform_usage(_request()))
    a, b = out["workspaces"]
    assert a["seats"] == {"used": 2, "limit": 5}
    assert a["projects"] == {"used": 2, "limit": 10}
    assert a["storage"] == {"bytes": 2048, "files": 1, "quota_bytes": 100 * 1024 * 1024}
    assert a["last_login"] == "2026-11-12T09:00:00"
    assert a["ai"] == {"calls": 7, "allowance": None}
    assert b["status"] == "inactive" and b["storage"]["files"] == 0
    assert b["seats"]["limit"] == 10 and b["plan"] == "starter"   # no own limits: the plan applies
    assert b["storage"]["quota_bytes"] == 512 * 1024 * 1024        # platform cap when no plan quota


def _candidates():
    return [{"user_id": "ds", "org_id": "org_default", "employee_id": "DS0001"},
            {"user_id": "other", "org_id": "org_b", "employee_id": "DS0001"}]


def _orgs(monkeypatch):
    monkeypatch.setattr(auth, "db", SimpleNamespace(organizations=_Coll([
        {"org_id": "org_default", "slug": "design-saga"}, {"org_id": "org_b", "slug": "studio-b"}])))


def test_workspace_narrows_a_shared_login_id(monkeypatch):
    _orgs(monkeypatch)
    out = asyncio.run(auth._narrow_to_workspace(_candidates(), "studio-b"))
    assert [c["user_id"] for c in out] == ["other"]
    out = asyncio.run(auth._narrow_to_workspace(_candidates(), "design-saga"))
    assert [c["user_id"] for c in out] == ["ds"]


def test_unknown_or_unrelated_workspace_never_blocks_sign_in(monkeypatch):
    _orgs(monkeypatch)
    assert len(asyncio.run(auth._narrow_to_workspace(_candidates(), "gone-studio"))) == 2
    assert len(asyncio.run(auth._narrow_to_workspace(_candidates(), None))) == 2
    one = _candidates()[:1]
    assert asyncio.run(auth._narrow_to_workspace(one, "studio-b")) == one   # single match untouched
