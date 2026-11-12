"""Tenant registry completeness and the workspace export (P0.3)."""
import asyncio
import io
import json
import pathlib
import re
import zipfile
from types import SimpleNamespace

from starlette.requests import Request

import routes.platform as platform
from core.tenant_registry import EXPORT_SKIPPED, TENANT_COLLECTIONS

BACKEND = pathlib.Path(__file__).resolve().parents[1]


def test_every_scoped_collection_is_registered_for_export_and_purge():
    used = set()
    for path in BACKEND.rglob("*.py"):
        if "tests" in path.parts or "scripts" in path.parts:
            continue
        used |= set(re.findall(r"\bsdb\.([a-z_]+)", path.read_text(encoding="utf-8", errors="ignore")))
    missing = sorted(used - set(TENANT_COLLECTIONS))
    assert not missing, f"register these tenant collections in core/tenant_registry.py: {missing}"


class _Cursor:
    def __init__(self, rows, projection):
        self.rows, self.projection = rows, projection

    def __aiter__(self):
        async def it():
            for row in self.rows:
                yield {k: v for k, v in row.items() if self.projection.get(k, 1) != 0}
        return it()


class _Coll:
    def __init__(self, rows=()):
        self.rows = [dict(r) for r in rows]
        self.updates = []

    def find(self, query, projection=None):
        return _Cursor([r for r in self.rows if r.get("org_id") == query.get("org_id")], projection or {})

    async def update_one(self, query, update):
        self.updates.append((query, update))


class _Db:
    def __init__(self):
        self.colls = {name: _Coll() for name in TENANT_COLLECTIONS}
        self.colls["users"] = _Coll([
            {"org_id": "org_a", "user_id": "u1", "email": "a@x.test", "password_hash": "secret"},
            {"org_id": "org_b", "user_id": "u2", "email": "b@x.test", "password_hash": "other"},
        ])
        self.colls["projects"] = _Coll([{"org_id": "org_a", "id": "p1", "name": "Villa"}])
        self.colls["google_calendar_connections"] = _Coll([{"org_id": "org_a", "refresh_token": "tok"}])
        self.colls["organizations"] = _Coll()

    def __getattr__(self, name):
        return self.colls[name]

    def __getitem__(self, name):
        return self.colls[name]


def test_export_contains_only_the_tenant_without_secrets(monkeypatch, tmp_path):
    fake = _Db()
    (tmp_path / "org_a").mkdir()
    (tmp_path / "org_a" / "plan.pdf").write_bytes(b"%PDF-1.7 a")
    (tmp_path / "org_b").mkdir()
    (tmp_path / "org_b" / "other.pdf").write_bytes(b"%PDF-1.7 b")
    audits = []

    async def allow(*_a, **_k):
        return {"user_id": "sa"}

    async def get_org(org_id):
        return {"org_id": org_id, "name": "Tenant A", "slug": "tenant-a"}

    async def audit(*args, **kwargs):
        audits.append(args[1])

    from services import local_files
    monkeypatch.setattr(local_files, "STORAGE_ROOT", tmp_path)
    monkeypatch.setattr(platform, "db", fake)
    monkeypatch.setattr(platform, "require_super_admin", allow)
    monkeypatch.setattr(platform, "get_org", get_org)
    monkeypatch.setattr(platform, "audit", audit)

    request = Request({"type": "http", "method": "GET", "path": "/", "headers": [],
                       "client": ("203.0.113.1", 1), "scheme": "https", "server": ("gamaa.in", 443)})

    async def collect():
        response = await platform.export_org("org_a", request)
        return b"".join([chunk async for chunk in response.body_iterator])

    archive = zipfile.ZipFile(io.BytesIO(asyncio.run(collect())))
    names = set(archive.namelist())
    users = [json.loads(line) for line in archive.read("data/users.jsonl").splitlines()]
    assert users == [{"org_id": "org_a", "user_id": "u1", "email": "a@x.test"}]   # no hash, no org_b
    assert "files/org_a/plan.pdf" in names and not any("org_b" in n for n in names)
    assert not any(f"data/{c}.jsonl" in names for c in EXPORT_SKIPPED)
    manifest = json.loads(archive.read("manifest.json"))
    assert manifest["collections"]["projects"] == 1 and manifest["files"] == 1
    assert fake.organizations.updates and "exported_at" in fake.organizations.updates[0][1]["$set"]
    assert audits == ["org.export"]
