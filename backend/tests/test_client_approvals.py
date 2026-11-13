"""P2.6 client approvals: personal portal links, approval requests, and the
client's decision landing on the drawing revision and in the audit log."""
import asyncio
import copy
import inspect
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import core.notifications as notifications
import core.portal as portal
import routes.approvals as ap
import routes.drawings as drawings


# ---------------------------------------------------------------- fake db
def _get(doc, path):
    cur = doc
    for part in path.split("."):
        if isinstance(cur, list):
            try:
                cur = cur[int(part)]
            except (ValueError, IndexError):
                return None
        elif isinstance(cur, dict):
            cur = cur.get(part)
        else:
            return None
    return cur


def _set(doc, path, value):
    parts = path.split(".")
    cur = doc
    for part in parts[:-1]:
        cur = cur[int(part)] if isinstance(cur, list) else cur.setdefault(part, {})
    if isinstance(cur, list):
        cur[int(parts[-1])] = value
    else:
        cur[parts[-1]] = value


def _match(doc, q):
    for k, v in (q or {}).items():
        have = _get(doc, k)
        if isinstance(v, dict) and any(x.startswith("$") for x in v):
            if "$in" in v and have not in v["$in"]:
                return False
            if "$ne" in v and have == v["$ne"]:
                return False
            if "$nin" in v and have in v["$nin"]:
                return False
        elif have != v:
            return False
    return True


class _Cursor:
    def __init__(self, rows):
        self.rows = rows

    def sort(self, *_a, **_k):
        return self

    async def to_list(self, _n=None):
        return [copy.deepcopy(r) for r in self.rows]


class _Coll:
    def __init__(self, rows=None):
        self.rows = [copy.deepcopy(r) for r in rows or []]

    def find(self, q=None, _p=None):
        return _Cursor([r for r in self.rows if _match(r, q)])

    async def find_one(self, q=None, _p=None):
        return next((copy.deepcopy(r) for r in self.rows if _match(r, q)), None)

    async def insert_one(self, doc):
        self.rows.append(copy.deepcopy(doc))

    async def count_documents(self, q=None):
        return sum(1 for r in self.rows if _match(r, q))

    def _apply(self, r, u):
        for k, v in (u.get("$set") or {}).items():
            _set(r, k, copy.deepcopy(v))
        for k, v in (u.get("$push") or {}).items():
            r.setdefault(k, []).append(copy.deepcopy(v))

    async def update_one(self, q, u):
        for r in self.rows:
            if _match(r, q):
                self._apply(r, u)
                return SimpleNamespace(modified_count=1, matched_count=1)
        return SimpleNamespace(modified_count=0, matched_count=0)

    async def update_many(self, q, u):
        n = 0
        for r in self.rows:
            if _match(r, q):
                self._apply(r, u)
                n += 1
        return SimpleNamespace(modified_count=n)


class _Scoped:
    """Mimics core.scoped_db.sdb for one tenant: reads and writes stay in org_a."""
    def __init__(self, raw, org_id):
        self._raw, self._org = raw, org_id

    def __getattr__(self, name):
        coll = getattr(self._raw, name)
        org = self._org

        class _View:
            def find(self, q=None, p=None):
                return coll.find({**(q or {}), "org_id": org}, p)

            async def find_one(self, q=None, p=None):
                return await coll.find_one({**(q or {}), "org_id": org}, p)

            async def insert_one(self, doc):
                await coll.insert_one({**doc, "org_id": org})

            async def count_documents(self, q=None):
                return await coll.count_documents({**(q or {}), "org_id": org})

            async def update_one(self, q, u):
                return await coll.update_one({**q, "org_id": org}, u)

            async def update_many(self, q, u):
                return await coll.update_many({**q, "org_id": org}, u)
        return _View()


PM = {"user_id": "u_pm", "org_id": "org_a", "role": "ProjectManager", "name": "Ravi",
      "permissions": ["projects.read", "projects.update", "files.read", "files.create"]}

DRAWING = {"id": "drw_1", "org_id": "org_a", "project_id": "p1", "number": "A-101", "title": "Living room plan",
           "archived": False, "rev_count": 1,
           "revisions": [{"rev": "A", "file_id": "f1", "file_name": "A-101-A.pdf", "status": "issued",
                          "purpose": "approval", "note": "Please check the sofa wall"}]}


@pytest.fixture
def env(monkeypatch):
    raw = SimpleNamespace(
        projects=_Coll([{"id": "p1", "org_id": "org_a", "name": "Villa", "share_token": "s" * 43},
                        {"id": "p2", "org_id": "org_b", "name": "Other", "share_token": "t" * 43}]),
        organizations=_Coll([{"org_id": "org_a", "name": "Arc Studio", "display_name": "Arc Studio"},
                             {"org_id": "org_b", "name": "Other Co"}]),
        portal_access=_Coll(), approvals=_Coll(), drawings=_Coll([DRAWING]),
        files=_Coll([{"id": "f1", "org_id": "org_a", "project_id": "p1", "name": "A-101-A.pdf",
                      "storage_key": "org_a/p1/f1.pdf"},
                     {"id": "f9", "org_id": "org_a", "project_id": "p9", "name": "elsewhere.pdf"}]),
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
        audits.append({"actor": (actor or {}).get("user_id"), "action": action, "target": target,
                       "org_id": org_id or (actor or {}).get("org_id"), "meta": meta or {}})

    async def bell(user_ids, kind, title, **kw):
        bells.append({"to": user_ids, "kind": kind, "title": title, **kw})
        return 1

    scoped = _Scoped(raw, "org_a")
    monkeypatch.setattr(ap, "sdb", scoped)
    monkeypatch.setattr(ap, "db", raw)
    monkeypatch.setattr(ap, "require_user", user)
    monkeypatch.setattr(ap, "get_visible_project", visible_project)
    monkeypatch.setattr(ap, "audit", record_audit)
    monkeypatch.setattr(ap, "has_permission", lambda u, p: p in u.get("permissions", []))
    monkeypatch.setattr(notifications, "emit", bell)
    return SimpleNamespace(raw=raw, audits=audits, bells=bells)


def run(coro):
    return asyncio.run(coro)


def add_person(name="Mrs Mehta", email="Mehta@Example.com"):
    return run(ap.add_portal_person("p1", ap.PersonIn(name=name, email=email), request=None))


def ask_drawing():
    return run(ap.request_approval("p1", ap.ApprovalIn(kind="drawing", drawing_id="drw_1"), request=None))


def decide(token, approval_id, decision="approve", comment=None):
    return run(ap.portal_decide(token, approval_id, ap.ClientDecisionIn(decision=decision, comment=comment)))


# ---------------------------------------------------------------- personal links
def test_personal_link_is_hashed_resolves_and_can_be_renewed_or_revoked(env):
    person = add_person()
    token = person["token"]
    stored = env.raw.portal_access.rows[0]
    assert token not in str(stored) and stored["token_hash"] == portal.token_hash(token)
    assert stored["email"] == "mehta@example.com" and stored["org_id"] == "org_a"
    assert "token_hash" not in person

    ctx = run(portal.resolve(env.raw, token))
    assert ctx["project"]["id"] == "p1" and ctx["contact"]["name"] == "Mrs Mehta"
    assert portal.viewer(ctx["contact"])["can_decide"] is True

    renewed = run(ap.renew_portal_link(person["id"], request=None))
    with pytest.raises(HTTPException) as old:
        run(portal.resolve(env.raw, token))
    assert old.value.status_code == 404
    assert run(portal.resolve(env.raw, renewed["token"]))["contact"]["id"] == person["id"]

    run(ap.revoke_portal_person(person["id"], request=None))
    with pytest.raises(HTTPException):
        run(portal.resolve(env.raw, renewed["token"]))
    assert [a["action"] for a in env.audits] == ["portal.person.add", "portal.person.new_link",
                                                  "portal.person.revoke"]


def test_personal_link_stops_with_a_suspended_workspace(env):
    token = add_person()["token"]
    env.raw.organizations.rows[0]["is_suspended"] = True
    with pytest.raises(HTTPException) as exc:
        run(portal.resolve(env.raw, token))
    assert exc.value.status_code == 404


def test_bad_email_is_refused(env):
    with pytest.raises(HTTPException) as exc:
        add_person(email="not-an-email")
    assert exc.value.status_code == 400


# ---------------------------------------------------------------- requests
def test_drawing_request_uses_current_revision_and_refuses_duplicates(env):
    a = ask_drawing()
    assert (a["title"], a["rev"], a["file_id"], a["status"]) == ("A-101 rev A · Living room plan", "A", "f1", "pending")
    assert a["description"] == "Please check the sofa wall"
    with pytest.raises(HTTPException) as dup:
        ask_drawing()
    assert dup.value.status_code == 409


def test_variation_needs_title_and_amount_and_file_must_belong_to_project(env):
    with pytest.raises(HTTPException):
        run(ap.request_approval("p1", ap.ApprovalIn(kind="variation", title="False ceiling"), request=None))
    with pytest.raises(HTTPException):
        run(ap.request_approval("p1", ap.ApprovalIn(kind="variation", amount=5), request=None))
    with pytest.raises(HTTPException) as foreign:
        run(ap.request_approval("p1", ap.ApprovalIn(kind="document", title="Mood board", file_id="f9"), request=None))
    assert foreign.value.status_code == 400
    v = run(ap.request_approval("p1", ap.ApprovalIn(kind="variation", title="False ceiling, bedroom 2",
                                                    amount=45000, days=7), request=None))
    assert (v["amount"], v["days"]) == (45000, 7)


# ---------------------------------------------------------------- client decisions
def test_client_approval_lands_on_the_drawing_and_in_audit(env):
    token = add_person()["token"]
    a = ask_drawing()
    out = decide(token, a["id"], comment="Looks good")
    assert out == {"ok": True, "status": "approved"}

    rev = env.raw.drawings.rows[0]["revisions"][0]
    assert rev["status"] == "approved" and rev["decided_by_name"] == "Mrs Mehta (client)"
    assert rev["decided_via"] == "client_portal" and rev["comment"] == "Looks good"
    assert rev["client_approval_id"] == a["id"]
    row = env.raw.approvals.rows[0]
    assert (row["status"], row["decided_by_name"], row["decided_by_email"]) == ("approved", "Mrs Mehta", "mehta@example.com")
    actions = {x["action"]: x for x in env.audits}
    assert actions["drawing.revision.approved"]["target"] == "drw_1"
    assert actions["drawing.revision.approved"]["org_id"] == "org_a"
    assert actions["approval.client.approved"]["actor"].startswith("portal:pax_")
    assert env.bells[0]["to"] == ["u_pm"] and env.bells[0]["kind"] == "client_decision"

    with pytest.raises(HTTPException) as again:
        decide(token, a["id"])
    assert again.value.status_code == 409


def test_shared_link_cannot_decide_and_changes_need_a_comment(env):
    a = ask_drawing()
    with pytest.raises(HTTPException) as shared:
        decide("s" * 43, a["id"])
    assert shared.value.status_code == 403
    token = add_person()["token"]
    with pytest.raises(HTTPException) as bare:
        decide(token, a["id"], decision="changes")
    assert bare.value.status_code == 400
    assert decide(token, a["id"], decision="changes", comment="Move the TV unit")["status"] == "changes_requested"
    assert env.raw.drawings.rows[0]["revisions"][0]["status"] == "rejected"


def test_a_revised_drawing_closes_the_old_request(env):
    token = add_person()["token"]
    a = ask_drawing()
    revs = env.raw.drawings.rows[0]["revisions"]
    revs[0]["status"] = "superseded"
    revs.append({"rev": "B", "file_id": "f1", "status": "issued"})
    with pytest.raises(HTTPException) as exc:
        decide(token, a["id"])
    assert exc.value.status_code == 409
    assert env.raw.approvals.rows[0]["status"] == "superseded"
    # issuing or deciding in the studio closes pending client requests too
    assert "close_for_drawing" in inspect.getsource(drawings.issue_revision)
    assert "close_for_drawing" in inspect.getsource(drawings.decide_revision)


def test_links_cannot_reach_another_projects_requests(env):
    a = ask_drawing()
    env.raw.portal_access.rows.append({"id": "pax_x", "org_id": "org_b", "project_id": "p2", "name": "Other",
                                       "token_hash": portal.token_hash("o" * 43), "revoked_at": None})
    with pytest.raises(HTTPException) as exc:
        decide("o" * 43, a["id"])
    assert exc.value.status_code == 404
    with pytest.raises(HTTPException):
        run(ap.portal_approval_file("o" * 43, a["id"]))


def test_portal_list_hides_closed_requests_and_links_the_file(env):
    a = ask_drawing()
    v = run(ap.request_approval("p1", ap.ApprovalIn(kind="variation", title="Extra wardrobe", amount=30000),
                                request=None))
    run(ap.withdraw_approval(v["id"], request=None))
    with pytest.raises(HTTPException):
        run(ap.withdraw_approval(v["id"], request=None))
    ctx = run(portal.resolve(env.raw, "s" * 43))
    rows = run(ap.for_portal(env.raw, ctx, "s" * 43))
    assert [r["id"] for r in rows] == [a["id"]]
    assert rows[0]["file_url"] == f"/api/portal/{'s' * 43}/approvals/{a['id']}/file"
    assert "requested_by" not in rows[0] and "history" not in rows[0]


def test_summary_counts_approved_variations(env):
    token = add_person()["token"]
    v1 = run(ap.request_approval("p1", ap.ApprovalIn(kind="variation", title="Ceiling", amount=45000, days=7),
                                 request=None))
    run(ap.request_approval("p1", ap.ApprovalIn(kind="variation", title="Wardrobe", amount=-5000), request=None))
    decide(token, v1["id"])
    out = run(ap.list_approvals("p1", request=None))
    assert out["summary"]["approved"] == 1 and out["summary"]["pending"] == 1
    assert out["summary"]["variations_approved_amount"] == 45000
    assert out["summary"]["variations_approved_days"] == 7
    assert out["people"][0]["name"] == "Mrs Mehta" and "token_hash" not in out["people"][0]
