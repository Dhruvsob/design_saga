"""Room-wise selections (P2.3) and quotation acceptance through the client portal.

Reuses the in-memory tenant/portal fakes of test_client_approvals so the
same personal-link rules apply: only a named client contact can decide, a
decision names them, and anything the studio changes after sending makes the
pending request stale instead of letting the client approve an old version.
"""
import asyncio
import importlib.util
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest
from fastapi import HTTPException

import core.notifications as notifications
import routes.approvals as ap
import routes.selections as sel

_spec = importlib.util.spec_from_file_location(
    "_approval_fakes", Path(__file__).with_name("test_client_approvals.py"))
fakes = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fakes)


class _Coll(fakes._Coll):
    async def delete_one(self, q):
        before = len(self.rows)
        self.rows = [r for r in self.rows if not fakes._match(r, q)]
        return SimpleNamespace(deleted_count=before - len(self.rows))


class _Scoped(fakes._Scoped):
    def __getattr__(self, name):
        view = super().__getattr__(name)
        coll, org = getattr(self._raw, name), self._org

        async def delete_one(q):
            return await coll.delete_one({**q, "org_id": org})
        view.delete_one = delete_one
        return view


PM = {"user_id": "u_pm", "org_id": "org_a", "role": "ProjectManager", "name": "Ravi",
      "permissions": ["projects.read", "projects.update", "quotations.update"]}


def run(coro):
    return asyncio.run(coro)


@pytest.fixture
def env(monkeypatch):
    raw = SimpleNamespace(
        projects=_Coll([{"id": "p1", "org_id": "org_a", "name": "Villa", "share_token": "s" * 43}]),
        organizations=_Coll([{"org_id": "org_a", "name": "Arc Studio", "display_name": "Arc Studio"}]),
        portal_access=_Coll(), approvals=_Coll(), drawings=_Coll(), files=_Coll(),
        project_selections=_Coll(),
        products=_Coll([{"id": "prd_1", "org_id": "org_a", "name": "Calacatta quartz", "brand": "Stonex",
                         "finish": "Honed", "dimensions": "3200 x 1600 x 20 mm", "unit": "sqft",
                         "specs": [{"label": "Edge", "value": "Mitred 40 mm"}], "default_vendor_id": "ven_1"}]),
        vendors=_Coll([{"id": "ven_1", "org_id": "org_a", "name": "Stone World"},
                       {"id": "ven_b", "org_id": "org_b", "name": "Other tenant supplier"}]),
        quotations_adv=_Coll([{"id": "q1", "org_id": "org_a", "number": "QT-0007", "project_id": "p1",
                               "project_title": "Villa interiors", "type": "turnkey", "status": "draft",
                               "version": 2, "updated_at": "2026-11-20T09:00:00", "converted_project_id": None,
                               "cost": {"grand_total": 1234567.5}, "approval": {}},
                              {"id": "q_nolink", "org_id": "org_a", "number": "QT-0008", "project_id": None,
                               "status": "draft", "updated_at": "x", "converted_project_id": None,
                               "cost": {"grand_total": 1000}}]),
    )
    audits, bells = [], []

    async def user(*_a, **_k):
        return PM

    async def visible(_u, project_id, *_a, **_k):
        p = await raw.projects.find_one({"id": project_id, "org_id": "org_a"})
        if not p:
            raise HTTPException(404, "Project not found")
        return p

    async def record(actor, action, target="", target_type="", meta=None, org_id=None):
        audits.append({"action": action, "target": target, "meta": meta or {}})

    async def bell(user_ids, kind, title, **kw):
        bells.append({"to": user_ids, "kind": kind, "title": title})
        return 1

    scoped = _Scoped(raw, "org_a")
    for mod in (ap, sel):
        monkeypatch.setattr(mod, "sdb", scoped)
        monkeypatch.setattr(mod, "require_user", user)
        monkeypatch.setattr(mod, "get_visible_project", visible)
        monkeypatch.setattr(mod, "audit", record)
        monkeypatch.setattr(mod, "has_permission", lambda u, p: p in u.get("permissions", []))
    monkeypatch.setattr(ap, "db", raw)
    monkeypatch.setattr(notifications, "emit", bell)
    return SimpleNamespace(raw=raw, audits=audits, bells=bells)


def person():
    return run(ap.add_portal_person("p1", ap.PersonIn(name="Mrs Mehta", email="mehta@example.com"), request=None))


def decide(token, approval_id, decision="approve", comment=None):
    return run(ap.portal_decide(token, approval_id, ap.ClientDecisionIn(decision=decision, comment=comment)))


def new_selection(**kw):
    body = {"room": "Kitchen", "item": "Counter top", **kw}
    return run(sel.create_selection("p1", sel.SelectionIn(**body), request=None))


# ------------------------------------------------------------------ selections
def test_library_product_fills_item_specification_and_supplier(env):
    s = new_selection(item=None, product_id="prd_1")
    assert s["item"] == "Stonex Calacatta quartz"
    assert "Honed" in s["specification"] and "Edge: Mitred 40 mm" in s["specification"]
    assert s["supplier"] == "Stone World" and s["vendor_id"] == "ven_1"
    assert s["unit"] == "sqft" and s["status"] == "proposed"


def test_foreign_or_missing_references_are_refused(env):
    with pytest.raises(HTTPException) as exc:
        new_selection(vendor_id="ven_b")
    assert exc.value.status_code == 400
    with pytest.raises(HTTPException) as exc:
        new_selection(product_id="prd_other")
    assert exc.value.status_code == 400


def test_client_approves_a_selection_in_the_portal(env):
    s = new_selection(specification="Quartz, 20 mm, honed", supplier="Stone World")
    with pytest.raises(HTTPException) as exc:
        run(sel.send_selection(s["id"], request=None))
    assert exc.value.status_code == 409          # nobody can decide yet
    token = person()["token"]
    sent = run(sel.send_selection(s["id"], request=None))
    assert sent["status"] == "sent"
    approval = env.raw.approvals.rows[-1]
    assert approval["kind"] == "selection" and approval["title"] == "Kitchen: Counter top"
    assert "Supplier: Stone World" in approval["description"]

    assert decide(token, approval["id"])["status"] == "approved"
    row = env.raw.project_selections.rows[0]
    assert row["status"] == "approved" and row["decided_by_name"] == "Mrs Mehta (client)"
    assert row["decided_via"] == "client_portal" and row["decided_at"]
    assert env.bells[-1]["to"] == ["u_pm"]
    listing = run(sel.list_selections("p1", request=None))
    assert listing["summary"] == {"total": 1, "proposed": 0, "sent": 0, "approved": 1,
                                  "changes_requested": 0, "not_approved": 0}


def test_changing_an_approved_selection_asks_the_client_again(env):
    token = person()["token"]
    s = new_selection()
    run(sel.send_selection(s["id"], request=None))
    decide(token, env.raw.approvals.rows[-1]["id"])
    notes_only = run(sel.update_selection(s["id"], sel.SelectionUpdate(notes="Order early"), request=None))
    assert notes_only["status"] == "approved"            # a note is not a new choice
    changed = run(sel.update_selection(s["id"], sel.SelectionUpdate(specification="Granite instead"), request=None))
    assert changed["status"] == "proposed" and changed["decided_by_name"] is None
    assert "Changed specification after it was approved" in changed["history"][-1]["comment"]
    with pytest.raises(HTTPException):
        run(sel.delete_selection("nope", request=None))


def test_editing_while_waiting_makes_the_pending_request_stale(env):
    token = person()["token"]
    s = new_selection()
    run(sel.send_selection(s["id"], request=None))
    approval_id = env.raw.approvals.rows[-1]["id"]
    run(sel.update_selection(s["id"], sel.SelectionUpdate(item="Counter top, quartz"), request=None))
    assert env.raw.approvals.rows[-1]["status"] == "superseded"
    with pytest.raises(HTTPException) as exc:
        decide(token, approval_id)
    assert exc.value.status_code == 409
    assert env.raw.project_selections.rows[0]["status"] == "proposed"


def test_withdrawn_request_reopens_and_studio_can_record_an_in_person_decision(env):
    person()
    s = new_selection()
    run(sel.send_selection(s["id"], request=None))
    run(ap.withdraw_approval(env.raw.approvals.rows[-1]["id"], request=None))
    assert env.raw.project_selections.rows[0]["status"] == "proposed"
    done = run(sel.record_decision(s["id"], sel.StudioDecisionIn(
        decision="approve", note="Approved on site visit, 20 Nov"), request=None))
    assert done["status"] == "approved" and done["decided_via"] == "studio"
    assert done["decided_by_name"] == "Ravi (recorded)"
    with pytest.raises(HTTPException) as exc:
        run(sel.delete_selection(s["id"], request=None))
    assert exc.value.status_code == 409                  # approved stays on record


def test_proposed_selection_can_be_deleted(env):
    s = new_selection()
    assert run(sel.delete_selection(s["id"], request=None)) == {"ok": True}
    assert env.raw.project_selections.rows == []


# ------------------------------------------------------------------ quotations
def send_quote(qid="q1", note=None):
    return run(ap.send_quotation_for_acceptance(qid, request=None, payload=ap.QuoteSendIn(note=note)))


def test_quotation_needs_a_project_and_a_client_contact(env):
    with pytest.raises(HTTPException) as exc:
        send_quote("q_nolink")
    assert exc.value.status_code == 409 and "project" in exc.value.detail
    with pytest.raises(HTTPException) as exc:
        send_quote()
    assert exc.value.status_code == 409 and "client contact" in exc.value.detail


def test_client_accepts_the_exact_version_sent(env):
    token = person()["token"]
    out = send_quote(note="Revised after the site meeting")
    a = out["approval"]
    assert a["kind"] == "quotation" and a["amount"] == 1234567.5 and a["quotation_version"] == 2
    q = env.raw.quotations_adv.rows[0]
    assert q["status"] == "sent" and q["approval"]["client_status"] == "pending"
    assert q["approval"]["internal_status"] == "approved"
    with pytest.raises(HTTPException) as again:
        send_quote()
    assert again.value.status_code == 409             # same version already waiting

    ctx = run(ap.portal.resolve(env.raw, token))
    rows = run(ap.for_portal(env.raw, ctx, token))
    assert rows[0]["file_url"] == f"/api/portal/{token}/approvals/{a['id']}/file"

    assert decide(token, a["id"], comment="Go ahead")["status"] == "approved"
    q = env.raw.quotations_adv.rows[0]
    assert q["status"] == "approved"
    assert q["approval"]["client_status"] == "approved" and q["approval"]["client_by"] == "Mrs Mehta"
    assert q["approval"]["client_version"] == 2 and q["approval"]["client_total"] == 1234567.5
    assert "quotation.client.accepted" in [x["action"] for x in env.audits]


def test_quotation_changed_after_sending_cannot_be_accepted(env):
    token = person()["token"]
    a = send_quote()["approval"]
    env.raw.quotations_adv.rows[0]["updated_at"] = "2026-11-20T10:00:00"   # studio edited it
    with pytest.raises(HTTPException) as exc:
        decide(token, a["id"])
    assert exc.value.status_code == 409
    assert env.raw.approvals.rows[-1]["status"] == "superseded"
    assert env.raw.quotations_adv.rows[0]["status"] == "sent"


def test_client_asks_for_changes_puts_the_quotation_under_review(env):
    token = person()["token"]
    a = send_quote()["approval"]
    decide(token, a["id"], decision="changes", comment="Drop the false ceiling")
    q = env.raw.quotations_adv.rows[0]
    assert q["status"] == "under_review" and q["approval"]["client_status"] == "changes_requested"
    assert q["approval"]["client_response"] == "Drop the false ceiling"


def test_portal_serves_the_quotation_pdf_and_refuses_a_stale_one(env, monkeypatch):
    token = person()["token"]
    a = send_quote()["approval"]
    fake = ModuleType("server")
    fake.generate_quotation_pdf_adv = lambda q, org: b"%PDF-1.4 fixture " + q["number"].encode()
    monkeypatch.setitem(sys.modules, "server", fake)
    res = run(ap.portal_approval_file(token, a["id"]))
    assert res.media_type == "application/pdf"
    assert "QT-0007-v2.pdf" in res.headers["content-disposition"]
    env.raw.quotations_adv.rows[0]["updated_at"] = "later"
    with pytest.raises(HTTPException) as exc:
        run(ap.portal_approval_file(token, a["id"]))
    assert exc.value.status_code == 409
