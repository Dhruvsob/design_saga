"""Site snags: raise -> fixed with photo -> verified close / reopen; permissions and history."""

import asyncio
import os
import uuid

import pytest
from fastapi import HTTPException
from motor.motor_asyncio import AsyncIOMotorClient

from routes import snags as sn


class _Upload:
    def __init__(self, name):
        self.filename = name


def test_snag_lifecycle(monkeypatch):
    import core.audit as audit_module
    import core.db as db_module
    import core.scoped_db as scoped_db_module
    from core.scoped_db import set_scope_from_user, clear_scope, sdb
    org = f"org_test_{uuid.uuid4().hex[:8]}"
    pm = {"org_id": org, "role": "ProjectManager", "user_id": f"pm_{org}", "name": "PM",
          "permissions": ["projects.update", "tasks.create", "projects.read"]}
    site = {"org_id": org, "role": "Employee", "user_id": f"emp_{org}", "name": "Ravi",
            "permissions": ["tasks.update", "projects.read"]}
    other = {"org_id": org, "role": "Employee", "user_id": f"oth_{org}", "name": "Other",
             "permissions": ["tasks.update", "projects.read"]}
    current = {"user": pm}
    removed = []

    async def visible(_user, project_id, permission="projects.read", projection=None):
        return {"id": project_id}

    async def require(*_a, **_k):
        return current["user"]

    async def store(user, upload):
        return {"storage_key": f"k/{upload.filename}", "content_type": "image/jpeg", "size": 10, "sha256": "x",
                "original_name": upload.filename}

    def perms(user, *names):
        return any(n in user["permissions"] for n in names)

    async def main():
        client = AsyncIOMotorClient(os.environ["MONGO_URL"])
        db = client[os.environ["DB_NAME"]]
        for module in (db_module, scoped_db_module, audit_module):
            monkeypatch.setattr(module, "db", db)
        monkeypatch.setattr(sn, "get_visible_project", visible)
        monkeypatch.setattr(sn, "require_user", require)
        monkeypatch.setattr(sn, "_store_photo", store)
        monkeypatch.setattr(sn, "remove_upload", lambda key: removed.append(key))
        monkeypatch.setattr(sn, "has_permission", lambda u, p: p in u["permissions"])
        monkeypatch.setattr(sn, "has_any_permission", perms)
        set_scope_from_user(pm)
        try:
            await db.users.insert_one({"user_id": site["user_id"], "org_id": org, "name": "Ravi"})
            current["user"] = site
            s = await sn.raise_snag("prj_1", None, title="Cracked tile near entrance", area="Lobby",
                                    priority="high", assignee_user_id=site["user_id"], photo=_Upload("crack.jpg"),
                                    description=None, due_date="2026-11-20", vendor_id=None)
            assert s["number"] == "SN-001" and s["status"] == "open" and s["assignee_name"] == "Ravi"
            assert s["photos"][0]["kind"] == "issue" and "storage_key" not in s["photos"][0]
            with pytest.raises(HTTPException):          # assignee cannot be from another company
                await sn.raise_snag("prj_1", None, title="x y", assignee_user_id="ghost", priority="normal",
                                    area=None, description=None, due_date=None, vendor_id=None, photo=None)
            with pytest.raises(HTTPException) as exc:   # staff cannot verify
                await sn.change_status(s["id"], sn.SnagStatusIn(action="close"), None)
            assert exc.value.status_code == 403
            current["user"] = other
            with pytest.raises(HTTPException) as exc:   # not the assignee
                await sn.mark_fixed(s["id"], None, photo=_Upload("fix.jpg"), note=None)
            assert exc.value.status_code == 403
            current["user"] = site
            fixed = await sn.mark_fixed(s["id"], None, photo=_Upload("fix.jpg"), note="Replaced tile")
            assert fixed["status"] == "fixed" and [p["kind"] for p in fixed["photos"]] == ["issue", "fix"]
            with pytest.raises(HTTPException):          # history exists: cannot delete
                await sn.delete_snag(s["id"], None)

            current["user"] = pm
            with pytest.raises(HTTPException):          # reopen needs a reason
                await sn.change_status(s["id"], sn.SnagStatusIn(action="reopen"), None)
            again = await sn.change_status(s["id"], sn.SnagStatusIn(action="reopen", note="Grout missing"), None)
            assert again["status"] == "open" and again["reopen_count"] == 1
            with pytest.raises(HTTPException):          # close only after a fix
                await sn.change_status(s["id"], sn.SnagStatusIn(action="close"), None)
            await sn.mark_fixed(s["id"], None, photo=_Upload("fix2.jpg"), note=None)   # manager may report the fix
            closed = await sn.change_status(s["id"], sn.SnagStatusIn(action="close"), None)
            assert closed["status"] == "closed" and closed["closed_by_name"] == "PM"
            assert [h["action"] for h in closed["history"]] == ["raised", "fixed", "reopened", "fixed", "verified & closed"]

            second = await sn.raise_snag("prj_1", None, title="Paint patch", priority="normal", area=None,
                                         description=None, due_date=None, assignee_user_id=None, vendor_id=None,
                                         photo=_Upload("p.jpg"))
            assert second["number"] == "SN-002"
            await sn.delete_snag(second["id"], None)        # raised by mistake, no history: removed with its photo
            assert "k/p.jpg" in removed
            listed = await sn.list_snags("prj_1", None)
            assert listed["counts"]["closed"] == 1 and len(listed["snags"]) == 1
        finally:
            clear_scope()
            for name in ("snags", "users", "audit_log", "counters", "sequences"):
                await db[name].delete_many({"org_id": org})
            client.close()

    asyncio.run(main())
