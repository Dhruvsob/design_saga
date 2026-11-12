"""Plan limits apply on every create path and to uploads (P0.7)."""
import asyncio
import inspect
from io import BytesIO
from types import SimpleNamespace

import pytest
from fastapi import HTTPException, UploadFile

import core.limits as limits
import server
from services import local_files


class _Orgs:
    def __init__(self, limits_doc):
        self.limits_doc = limits_doc

    async def find_one(self, *_a, **_k):
        return {"features": {"limits": self.limits_doc}}


class _Projects:
    def __init__(self, n):
        self.n = n

    async def count_documents(self, _q):
        return self.n


def _patch(monkeypatch, limits_doc, projects):
    import core.db
    import core.scoped_db
    monkeypatch.setattr(core.db, "db", SimpleNamespace(organizations=_Orgs(limits_doc)))
    monkeypatch.setattr(core.scoped_db, "sdb", SimpleNamespace(projects=_Projects(projects)))


def test_project_limit_refuses_at_the_cap(monkeypatch):
    _patch(monkeypatch, {"max_projects": 3}, projects=3)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(limits.enforce_project_limit("org_a"))
    assert exc.value.status_code == 402 and "3/3" in exc.value.detail
    _patch(monkeypatch, {"max_projects": 3}, projects=2)
    asyncio.run(limits.enforce_project_limit("org_a"))


@pytest.mark.parametrize("handler", ["create_project", "convert_lead_to_project", "adv_convert"])
def test_every_project_create_path_checks_the_limit(handler):
    assert "enforce_project_limit" in inspect.getsource(getattr(server, handler))


def test_plan_storage_quota_is_capped_by_the_platform_limit(tmp_path, monkeypatch):
    monkeypatch.setattr(local_files, "STORAGE_ROOT", tmp_path)
    monkeypatch.setattr(local_files, "MAX_STORAGE_BYTES", 10_000)
    monkeypatch.setattr(local_files, "MAX_TENANT_STORAGE_BYTES", 1_000)
    big = b"%PDF-1.7\n" + b"x" * 60
    # A plan quota below the platform cap is enforced.
    with pytest.raises(ValueError, match="company file-storage quota"):
        asyncio.run(local_files.save_upload(UploadFile(filename="a.pdf", file=BytesIO(big)), "org_a", 50))
    # A plan quota above the platform cap cannot exceed it.
    monkeypatch.setattr(local_files, "MAX_TENANT_STORAGE_BYTES", 50)
    with pytest.raises(ValueError, match="company file-storage quota"):
        asyncio.run(local_files.save_upload(UploadFile(filename="b.pdf", file=BytesIO(big)), "org_b", 10**9))


def test_storage_quota_reads_the_tenant_plan(monkeypatch):
    _patch(monkeypatch, {"storage_mb": 2}, projects=0)
    assert asyncio.run(limits.tenant_storage_quota_bytes("org_a")) == 2 * 1024 * 1024
    _patch(monkeypatch, {}, projects=0)               # no own quota: the plan's applies (P1.2)
    assert asyncio.run(limits.tenant_storage_quota_bytes("org_a")) == 2048 * 1024 * 1024
