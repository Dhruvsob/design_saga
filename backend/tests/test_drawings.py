"""Drawing register: numbering, revision letters, supersession, decisions, archive-not-delete."""

import asyncio
import os
import uuid

import pytest
from fastapi import HTTPException
from motor.motor_asyncio import AsyncIOMotorClient

from routes import drawings as dr


def test_revision_letters_continue_like_spreadsheet_columns():
    assert [dr.next_revision(x) for x in (None, "A", "B", "Y", "Z", "AA", "AZ")] == ["A", "B", "C", "Z", "AA", "AB", "BA"]


def test_drawing_number_is_normalised_and_validated():
    assert dr._clean_number("  a-101 ") == "A-101"
    assert dr._clean_number("ID/02.3") == "ID/02.3"
    with pytest.raises(HTTPException):
        dr._clean_number("<script>")


def test_register_lifecycle(monkeypatch):
    import core.audit as audit_module
    import core.db as db_module
    import core.scoped_db as scoped_db_module
    from core.scoped_db import set_scope_from_user, clear_scope, sdb
    org = f"org_test_{uuid.uuid4().hex[:8]}"
    user = {"org_id": org, "role": "Admin", "user_id": f"u_{org}", "name": "Architect", "permissions": ["*.*"]}

    async def visible(_user, project_id, permission="projects.read", projection=None):
        return {"id": project_id, "name": "Villa"}

    async def require(*_a, **_k):
        return user

    def run(coro):
        return coro

    async def main():
        client = AsyncIOMotorClient(os.environ["MONGO_URL"])
        db = client[os.environ["DB_NAME"]]
        for module in (db_module, scoped_db_module, audit_module):
            monkeypatch.setattr(module, "db", db)
        monkeypatch.setattr(dr, "get_visible_project", visible)
        monkeypatch.setattr(dr, "require_user", require)
        set_scope_from_user(user)
        try:
            await sdb.files.insert_many([
                {"id": f"f1_{org}", "project_id": "prj_1", "name": "plan-a.pdf", "url": "/api/files/f1/content"},
                {"id": f"f2_{org}", "project_id": "prj_1", "name": "plan-b.pdf", "url": "/api/files/f2/content"},
                {"id": f"fx_{org}", "project_id": "prj_other", "name": "x.pdf", "url": "/api/files/fx/content"},
            ])
            d = await dr.create_drawing("prj_1", dr.DrawingIn(number="a-101", title="Ground floor plan"), None)
            assert d["number"] == "A-101" and d["current"] is None
            with pytest.raises(HTTPException) as exc:
                await dr.create_drawing("prj_1", dr.DrawingIn(number="A-101", title="Dup"), None)
            assert exc.value.status_code == 409
            with pytest.raises(HTTPException):     # file from another project
                await dr.issue_revision(d["id"], dr.RevisionIn(file_id=f"fx_{org}"), None)

            a = await dr.issue_revision(d["id"], dr.RevisionIn(file_id=f"f1_{org}", purpose="approval", issued_to="Client"), None)
            assert a["current"]["rev"] == "A" and a["current"]["status"] == "issued"
            with pytest.raises(HTTPException):     # rejection needs a reason
                await dr.decide_revision(d["id"], "A", dr.DecisionIn(decision="rejected"), None)
            r = await dr.decide_revision(d["id"], "A", dr.DecisionIn(decision="rejected", comment="Move the kitchen"), None)
            assert r["current"]["status"] == "rejected"
            with pytest.raises(HTTPException):     # already decided
                await dr.decide_revision(d["id"], "A", dr.DecisionIn(decision="approved"), None)

            b = await dr.issue_revision(d["id"], dr.RevisionIn(file_id=f"f2_{org}", purpose="construction"), None)
            assert [x["rev"] for x in b["revisions"]] == ["A", "B"]
            assert b["revisions"][0]["status"] == "rejected" and b["revisions"][0]["superseded_by"] == "B"
            with pytest.raises(HTTPException):     # only the current revision can be decided
                await dr.decide_revision(d["id"], "A", dr.DecisionIn(decision="approved"), None)
            ok = await dr.decide_revision(d["id"], "b", dr.DecisionIn(decision="approved"), None)
            assert ok["current"]["status"] == "approved" and ok["current"]["decided_by_name"] == "Architect"
            c = await dr.issue_revision(d["id"], dr.RevisionIn(file_id=f"f2_{org}"), None)
            assert c["revisions"][1]["status"] == "superseded" and c["current"]["rev"] == "C"

            with pytest.raises(HTTPException):     # number fixed once issued
                await dr.update_drawing(d["id"], dr.DrawingUpdate(number="A-102"), None)
            with pytest.raises(HTTPException):     # issued drawings are archived, not deleted
                await dr.delete_drawing(d["id"], None)
            await dr.update_drawing(d["id"], dr.DrawingUpdate(archived=True), None)
            listed = await dr.list_drawings("prj_1", None)
            assert listed["drawings"] == []
            listed = await dr.list_drawings("prj_1", None, include_archived=True)
            assert listed["drawings"][0]["revision_count"] == 3

            draft = await dr.create_drawing("prj_1", dr.DrawingIn(number="ID-01", title="Ceiling", discipline="Interior"), None)
            await dr.delete_drawing(draft["id"], None)
            assert await sdb.drawings.find_one({"id": draft["id"]}) is None

            resp = await dr.drawing_register_export("prj_1", None)
            assert resp.body[:2] == b"PK"
        finally:
            clear_scope()
            for name in ("drawings", "files", "audit_log"):
                await db[name].delete_many({"org_id": org})
            client.close()

    asyncio.run(main())
