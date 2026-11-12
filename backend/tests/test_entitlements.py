"""P1.2 entitlements: plan catalogue + per-workspace overrides drive every gate."""
import asyncio
import copy
import inspect
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from starlette.requests import Request

import core.entitlements as ent
import core.features as features
import routes.platform as platform

PLANS = copy.deepcopy(ent.DEFAULT_PLANS)
PLANS["starter"]["excluded_modules"] = ["accounting", "payroll"]
PLANS["starter"]["ai_credits_monthly"] = 0


def test_plan_applies_when_the_workspace_has_no_own_limits():
    e = ent.effective({"plan": "pro", "business_mode": "consultancy"}, PLANS)
    assert e["limits"] == PLANS["pro"]["limits"] and e["plan_name"] == "Professional"
    assert e["modules"]["accounting"] is True and e["modules"]["purchase_orders"] is False  # mode preset


def test_older_workspaces_keep_their_own_limits_and_switches():
    org = {"plan": "starter", "features": {"limits": {"max_users": 500, "storage_mb": 5000},
                                           "modules": {"loans": False}}}
    e = ent.effective(org, PLANS)
    assert e["limits"] == {"max_users": 500, "max_projects": 100, "storage_mb": 5000}
    assert e["overrides"]["limits"] == ["max_users", "storage_mb"]
    assert e["modules"]["loans"] is False


def test_plan_exclusions_and_per_workspace_grants():
    e = ent.effective({"plan": "starter"}, PLANS)
    assert e["modules"]["accounting"] is False and e["plan_excluded"] == ["accounting", "payroll"]
    granted = ent.effective({"plan": "starter", "features": {"module_grants": ["accounting"]}}, PLANS)
    assert granted["modules"]["accounting"] is True and granted["plan_excluded"] == ["payroll"]
    off = ent.effective({"plan": "starter", "features": {"module_grants": ["accounting"],
                                                         "modules": {"accounting": False}}}, PLANS)
    assert off["modules"]["accounting"] is False          # a switch turned off always wins


def test_ai_allowance_from_plan_or_override():
    assert ent.effective({"plan": "starter"}, PLANS)["ai_credits_monthly"] == 0
    assert ent.effective({"plan": "starter", "features": {"ai_credits_monthly": 50}}, PLANS)["ai_credits_monthly"] == 50
    assert ent.effective({"plan": "starter", "features": {"ai_credits_monthly": None}}, PLANS)["ai_credits_monthly"] is None
    assert ent.effective({"plan": "unknown"}, PLANS)["plan"] == "starter"


def test_merge_plan_ignores_bad_values():
    merged = ent.merge_plan(PLANS["pro"], {"name": " Studio+ ", "limits": {"max_users": -5, "max_projects": 70},
                                           "excluded_modules": ["inventory", "inventory"],
                                           "ai_credits_monthly": -1})
    assert merged["name"] == "Studio+" and merged["limits"]["max_users"] == 30
    assert merged["limits"]["max_projects"] == 70 and merged["excluded_modules"] == ["inventory"]
    assert merged["ai_credits_monthly"] is None


def _with_plans(monkeypatch, org):
    async def load_plans():
        return copy.deepcopy(PLANS)

    async def for_org_id(_org_id):
        return ent.effective(org, PLANS)

    monkeypatch.setattr(ent, "load_plans", load_plans)
    monkeypatch.setattr(ent, "for_org_id", for_org_id)


def test_module_gate_names_the_plan(monkeypatch):
    _with_plans(monkeypatch, {"plan": "starter"})
    with pytest.raises(HTTPException) as exc:
        asyncio.run(features.require_module({"user_id": "u", "org_id": "org_a"}, "accounting"))
    assert exc.value.status_code == 403 and "Starter plan" in exc.value.detail
    asyncio.run(features.require_module({"user_id": "u", "org_id": "org_a"}, "clients"))


class _Usage:
    def __init__(self, calls):
        self.calls = calls

    async def find_one(self, *_a, **_k):
        return {"calls": self.calls}

    async def update_one(self, _q, update, upsert=False):
        assert upsert
        self.calls += update["$inc"]["calls"]


def test_ai_allowance_is_enforced_per_month(monkeypatch):
    import core.db
    usage = _Usage(calls=1)
    monkeypatch.setattr(core.db, "db", SimpleNamespace(ai_usage=usage))
    _with_plans(monkeypatch, {"plan": "pro", "features": {"ai_credits_monthly": 2}})
    asyncio.run(ent.consume_ai_credit("org_a"))
    assert usage.calls == 2
    with pytest.raises(HTTPException) as exc:
        asyncio.run(ent.consume_ai_credit("org_a"))
    assert exc.value.status_code == 429
    _with_plans(monkeypatch, {"plan": "starter"})             # plan allowance 0 = AI off
    with pytest.raises(HTTPException) as exc:
        asyncio.run(ent.consume_ai_credit("org_a"))
    assert exc.value.status_code == 403


def test_ai_endpoints_consume_credits():
    import server
    assert "consume_ai_credit" in inspect.getsource(server.ai_chat)
    assert "consume_ai_credit" in inspect.getsource(server.adv_ai_suggest)


def test_new_workspaces_follow_their_plan():
    assert 'DEFAULT_FEATURES["limits"]' not in inspect.getsource(platform.create_org)


def _request(path):
    return Request({"type": "http", "method": "PUT", "path": path, "headers": [],
                    "client": ("203.0.113.10", 1), "scheme": "https", "server": ("gamaa.in", 443)})


class _Orgs:
    def __init__(self, org):
        self.org = org
        self.updates = []

    async def find_one(self, *_a, **_k):
        return copy.deepcopy(self.org)

    async def update_one(self, _q, update, upsert=False):
        self.updates.append(update)


def _sa(monkeypatch, db):
    async def super_admin(*_a, **_k):
        return {"user_id": "sa"}

    async def audit(*_a, **_k):
        return None

    async def get_org(_oid):
        return await db.organizations.find_one()

    monkeypatch.setattr(platform, "db", db)
    monkeypatch.setattr(platform, "require_super_admin", super_admin)
    monkeypatch.setattr(platform, "audit", audit)
    monkeypatch.setattr(platform, "get_org", get_org)


def test_switching_on_an_excluded_module_grants_it(monkeypatch):
    _with_plans(monkeypatch, {"plan": "starter"})
    orgs = _Orgs({"org_id": "org_a", "plan": "starter", "features": {"modules": {}}})
    _sa(monkeypatch, SimpleNamespace(organizations=orgs))
    asyncio.run(platform.set_org_modules("org_a", platform.OrgModulesIn(modules={"accounting": True, "loans": False}),
                                         _request("/api/platform/orgs/org_a/modules")))
    assert orgs.updates[-1]["$set"]["features.module_grants"] == ["accounting"]


def test_reset_to_plan_clears_own_limits_and_ai(monkeypatch):
    _with_plans(monkeypatch, {"plan": "pro"})
    orgs = _Orgs({"org_id": "org_a", "plan": "pro", "features": {"limits": {"max_users": 500}}})
    _sa(monkeypatch, SimpleNamespace(organizations=orgs))
    asyncio.run(platform.update_org_limits("org_a", {"reset_to_plan": True}, _request("/x")))
    assert set(orgs.updates[-1]["$unset"]) == {"features.limits", "features.ai_credits_monthly"}
    asyncio.run(platform.update_org_limits("org_a", {"max_projects": None, "ai_credits_monthly": 25},
                                           _request("/x")))
    assert orgs.updates[-1]["$unset"] == {"features.limits.max_projects": ""}
    assert orgs.updates[-1]["$set"]["features.ai_credits_monthly"] == 25


def test_editing_a_plan_saves_and_refreshes_the_catalogue(monkeypatch):
    plans_coll = _Orgs({})
    _sa(monkeypatch, SimpleNamespace(platform_plans=plans_coll, organizations=_Orgs({})))
    invalidated = []
    monkeypatch.setattr(ent, "invalidate_plans", lambda: invalidated.append(True))
    payload = platform.PlanIn(name="Starter", support="Email", limits={"max_users": 5, "max_projects": 20,
                                                                         "storage_mb": 1024},
                              excluded_modules=["inventory"], ai_credits_monthly=0)
    asyncio.run(platform.update_plan("starter", payload, _request("/api/platform/plans/starter")))
    saved = plans_coll.updates[-1]["$set"]
    assert saved["key"] == "starter" and saved["limits"]["max_users"] == 5 and invalidated
    with pytest.raises(HTTPException):
        asyncio.run(platform.update_plan("gold", payload, _request("/api/platform/plans/gold")))


def test_studio_admin_sees_own_plan_and_usage(monkeypatch, tmp_path):
    import routes.organization as organization
    from services import local_files

    class _Count:
        def __init__(self, n):
            self.n = n

        async def count_documents(self, _q):
            return self.n

    async def admin(*_a, **_k):
        return {"user_id": "a", "org_id": "org_a", "role": "Admin"}

    async def get_org(_oid):
        return {"org_id": "org_a", "plan": "starter", "features": {"limits": {"max_users": 12}}}

    async def calls(_oid):
        return 0

    monkeypatch.setattr(local_files, "STORAGE_ROOT", tmp_path)
    monkeypatch.setattr(organization, "require_user", admin)
    monkeypatch.setattr(organization, "has_permission", lambda _u, p: p == "*.*")
    monkeypatch.setattr(organization, "get_org", get_org)
    monkeypatch.setattr(organization, "db", SimpleNamespace(users=_Count(4), projects=_Count(9)))
    monkeypatch.setattr(ent, "ai_calls_this_month", calls)
    _with_plans(monkeypatch, {"plan": "starter"})
    out = asyncio.run(organization.current_org_usage(_request("/api/org/current/usage")))
    assert out["plan_name"] == "Starter"
    assert out["users"] == {"used": 4, "limit": 12} and out["projects"] == {"used": 9, "limit": 100}
    assert out["ai"] == {"calls": 0, "allowance": 0} and out["plan_excluded"] == ["accounting", "payroll"]
    monkeypatch.setattr(organization, "has_permission", lambda _u, _p: False)
    with pytest.raises(HTTPException):
        asyncio.run(organization.current_org_usage(_request("/api/org/current/usage")))
