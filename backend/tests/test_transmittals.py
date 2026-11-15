"""P2.7 drawing transmittals: issue sets, superseded marks, acknowledgement
from the portal or recorded by the studio, void, and the transmittal PDF."""
import asyncio
import re
import zlib
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import core.notifications as notifications
import core.portal as portal
import routes.transmittals as tr
from test_client_approvals import _Coll, _Scoped, _match


class _Counters(_Coll):
    async def find_one_and_update(self, q, u, return_document=None):
        for r in self.rows:
            if _match(r, q):
                r["seq"] = r.get("seq", 0) + u["$inc"]["seq"]
                return dict(r)
        return None


def _drawing(did, number, revs, project="p1", org="org_a"):
    return {"id": did, "org_id": org, "project_id": project, "number": number, "title": f"Sheet {number}",
            "archived": False, "revisions": [{"rev": r, "file_id": f"f_{did}_{r}", "file_name": f"{number}-{r}.pdf",
                                              "status": "issued" if n == len(revs) - 1 else "superseded"}
                                             for n, r in enumerate(revs)]}


PM = {"user_id": "u_pm", "org_id": "org_a", "name": "Ravi",
      "permissions": ["files.read", "files.create", "projects.read"]}
TOKEN = "k" * 43
SHARED = "s" * 43


@pytest.fixture
def env(monkeypatch):
    raw = SimpleNamespace(
        projects=_Coll([{"id": "p1", "org_id": "org_a", "name": "Villa Serena", "client_name": "Mehta",
                         "share_token": SHARED},
                        {"id": "p2", "org_id": "org_b", "name": "Other", "share_token": "t" * 43}]),
        organizations=_Coll([{"org_id": "org_a", "name": "Arc Studio"}, {"org_id": "org_b", "name": "B"}]),
        drawings=_Coll([_drawing("d1", "A-101", ["A"]), _drawing("d2", "A-102", ["A", "B"]),
                        {**_drawing("d3", "A-103", []), "revisions": []},
                        _drawing("dx", "X-1", ["A"], project="p2", org="org_b")]),
        portal_access=_Coll([{"id": "pax_1", "org_id": "org_a", "project_id": "p1", "name": "Anita Mehta",
                              "email": "anita@client.test", "token_hash": portal.token_hash(TOKEN), "revoked_at": None},
                             {"id": "pax_2", "org_id": "org_a", "project_id": "p1", "name": "Raj Mehta",
                              "token_hash": portal.token_hash("r" * 43), "revoked_at": None}]),
        transmittals=_Coll(), counters=_Counters(),
        files=_Coll([{"id": "f_d1_A", "org_id": "org_a", "project_id": "p1", "storage_key": "x/f.pdf"}]),
    )
    audits, bells = [], []

    async def user(*_a, **_k):
        return PM

    async def visible_project(_u, project_id, *_a, **_k):
        p = await raw.projects.find_one({"id": project_id, "org_id": "org_a"})
        if not p:
            raise HTTPException(404, "Project not found")
        return p

    async def record_audit(actor, action, target="", target_type="", meta=None, org_id=None):
        audits.append({"actor": (actor or {}).get("user_id"), "action": action, "meta": meta or {},
                       "org_id": org_id or (actor or {}).get("org_id")})

    async def bell(user_ids, kind, title, **kw):
        bells.append({"to": user_ids, "title": title})
        return 1

    monkeypatch.setattr(tr, "sdb", _Scoped(raw, "org_a"))
    monkeypatch.setattr(tr, "db", raw)
    monkeypatch.setattr(tr, "require_user", user)
    monkeypatch.setattr(tr, "get_visible_project", visible_project)
    monkeypatch.setattr(tr, "audit", record_audit)
    monkeypatch.setattr(tr, "has_permission", lambda u, p: p in u.get("permissions", []))
    monkeypatch.setattr(tr, "user_org_id", lambda u: u.get("org_id"))
    monkeypatch.setattr(notifications, "emit", bell)
    return SimpleNamespace(raw=raw, audits=audits, bells=bells)


def run(coro):
    return asyncio.run(coro)


def issue(**kw):
    body = {"items": [{"drawing_id": "d2"}, {"drawing_id": "d1"}],
            "recipients": [{"portal_person_id": "pax_1"}, {"name": "BuildRight Contractors", "company": "BuildRight",
                                                           "email": "Site@BuildRight.test"}],
            "purpose": "construction", "note": "Issued for site", **kw}
    return run(tr.issue_transmittal("p1", tr.TransmittalIn(**body), request=None))


def pdf_text(data: bytes) -> str:
    out = []
    for m in re.finditer(rb"stream\r?\n(.*?)\r?\nendstream", data, re.S):
        try:
            out.append(zlib.decompress(m.group(1)).decode("latin-1"))
        except zlib.error:
            out.append(m.group(1).decode("latin-1", "ignore"))
    return "".join(out)


def test_issue_snapshots_current_revisions_and_numbers_per_project(env):
    t = issue()
    assert t["number"] == "TR-001" and t["status"] == "issued" and t["ack_status"] == "awaiting"
    assert [(i["number"], i["rev"]) for i in t["items"]] == [("A-101", "A"), ("A-102", "B")]
    client, contractor = t["recipients"]
    assert (client["name"], client["email"], client["portal_person_id"]) == ("Anita Mehta", "anita@client.test", "pax_1")
    assert contractor["email"] == "site@buildright.test" and contractor["portal_person_id"] is None
    assert issue()["number"] == "TR-002"
    assert env.audits[0]["action"] == "transmittal.issue"
    assert env.audits[0]["meta"]["items"] == ["A-101 rev A", "A-102 rev B"]


@pytest.mark.parametrize("items,recipients", [
    ([{"drawing_id": "d3"}], [{"name": "X"}]),             # never issued
    ([{"drawing_id": "dx"}], [{"name": "X"}]),             # another tenant's project
    ([{"drawing_id": "d1"}], [{"portal_person_id": "pax_gone"}]),
    ([{"drawing_id": "d1"}], [{"name": "  "}]),
    ([{"drawing_id": "d1"}], [{"name": "X", "email": "nope"}]),
])
def test_bad_items_or_recipients_are_refused(env, items, recipients):
    with pytest.raises(HTTPException) as exc:
        issue(items=items, recipients=recipients)
    assert exc.value.status_code == 400


def test_a_newer_revision_marks_the_line_superseded_everywhere(env):
    t = issue()
    env.raw.drawings.rows[0]["revisions"][0]["status"] = "superseded"
    env.raw.drawings.rows[0]["revisions"].append({"rev": "B", "file_id": "f_d1_B", "status": "issued"})
    listed = run(tr.list_transmittals("p1", request=None))
    row = listed["transmittals"][0]
    assert [i["superseded_by"] for i in row["items"]] == ["B", None]
    assert row["superseded_count"] == 1 and listed["summary"]["with_superseded"] == 1

    ctx = run(portal.resolve(env.raw, TOKEN))
    shown = run(tr.for_portal(env.raw, ctx, TOKEN))[0]
    assert shown["items"][0]["superseded_by"] == "B"
    assert shown["items"][0]["file_url"] == f"/api/portal/{TOKEN}/transmittals/{t['id']}/items/0/file"

    current = {"d1": {"rev": "B"}, "d2": {"rev": "B"}}
    text = pdf_text(tr.transmittal_pdf(tr.decorate(env.raw.transmittals.rows[0], current),
                                       {"name": "Arc Studio"}, {"name": "Villa Serena"}))
    assert "SUPERSEDED by rev B" in text and "TR-001" in text and "Received by" in text


def test_portal_acknowledgement_only_by_the_named_recipient(env):
    t = issue()
    ctx = run(portal.resolve(env.raw, TOKEN))
    assert run(tr.for_portal(env.raw, ctx, TOKEN))[0]["can_acknowledge"] is True
    other = run(portal.resolve(env.raw, "r" * 43))
    assert run(tr.for_portal(env.raw, other, "r" * 43))[0]["can_acknowledge"] is False

    for token, code in ((SHARED, 403), ("r" * 43, 403)):
        with pytest.raises(HTTPException) as exc:
            run(tr.portal_acknowledge(token, t["id"]))
        assert exc.value.status_code == code
    assert run(tr.portal_acknowledge(TOKEN, t["id"], tr.PortalAckIn(note="Got the set"))) == {"ok": True}
    rec = env.raw.transmittals.rows[0]["recipients"][0]
    assert rec["acknowledged_via"] == "portal" and rec["ack_note"] == "Got the set"
    with pytest.raises(HTTPException) as again:
        run(tr.portal_acknowledge(TOKEN, t["id"]))
    assert again.value.status_code == 409
    assert env.audits[-1]["action"] == "transmittal.acknowledge" and env.audits[-1]["actor"] == "portal:pax_1"
    assert env.audits[-1]["org_id"] == "org_a" and env.bells[0]["to"] == ["u_pm"]


def test_studio_records_the_rest_and_status_becomes_acknowledged(env):
    t = issue()
    contractor = t["recipients"][1]["id"]
    out = run(tr.record_acknowledgement(t["id"], contractor, tr.AckIn(note="Signed copy received",
                                                                      received_date="2026-11-14"), request=None))
    assert out["ack_status"] == "partly_acknowledged"
    assert out["recipients"][1]["recorded_by_name"] == "Ravi" and out["recipients"][1]["received_date"] == "2026-11-14"
    with pytest.raises(HTTPException):
        run(tr.record_acknowledgement(t["id"], contractor, tr.AckIn(), request=None))
    run(tr.portal_acknowledge(TOKEN, t["id"]))
    assert run(tr.list_transmittals("p1", request=None))["transmittals"][0]["ack_status"] == "acknowledged"


def test_void_keeps_the_record_hides_it_from_the_portal_and_blocks_changes(env):
    t = issue()
    out = run(tr.void_transmittal(t["id"], tr.VoidIn(reason="Wrong revision attached"), request=None))
    assert out["status"] == "void" and out["ack_status"] == "void"
    assert len(env.raw.transmittals.rows) == 1
    with pytest.raises(HTTPException):
        run(tr.void_transmittal(t["id"], tr.VoidIn(reason="again"), request=None))
    with pytest.raises(HTTPException):
        run(tr.record_acknowledgement(t["id"], t["recipients"][1]["id"], tr.AckIn(), request=None))
    ctx = run(portal.resolve(env.raw, TOKEN))
    assert run(tr.for_portal(env.raw, ctx, TOKEN)) == []
    with pytest.raises(HTTPException) as exc:
        run(tr.portal_acknowledge(TOKEN, t["id"]))
    assert exc.value.status_code == 404
    text = pdf_text(tr.transmittal_pdf(tr.decorate(env.raw.transmittals.rows[0], {}), {"name": "Arc"}, {"name": "V"}))
    assert "VOID - Wrong revision attached" in text


def test_portal_file_and_pdf_stay_inside_the_link_project(env):
    t = issue(share_in_portal=False)
    with pytest.raises(HTTPException) as hidden:
        run(tr.portal_transmittal_pdf(TOKEN, t["id"]))
    assert hidden.value.status_code == 404
    t2 = issue()
    with pytest.raises(HTTPException) as out_of_range:
        run(tr.portal_transmittal_file(TOKEN, t2["id"], 7))
    assert out_of_range.value.status_code == 404
    with pytest.raises(HTTPException) as foreign:
        run(tr.portal_transmittal_file("t" * 43, t2["id"], 0))
    assert foreign.value.status_code == 404
    pdf = run(tr.portal_transmittal_pdf(TOKEN, t2["id"]))
    assert pdf.media_type == "application/pdf"
