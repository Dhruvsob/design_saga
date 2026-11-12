"""What a workspace may use: plan catalogue + per-workspace overrides (P1.2).

effective entitlements = the workspace's plan (``platform_plans``, editable by
Super Admin; ``DEFAULT_PLANS`` below until edited) adjusted by the workspace's
own settings, which act as overrides:

* ``features.limits``            per-workspace limits. Every workspace created
                                 before plans were enforced has them, so it keeps
                                 exactly what it had until "Use plan values".
* ``features.modules``           business-mode preset + per-workspace switches.
* ``features.module_grants``     modules switched on for this workspace even
                                 though its plan excludes them.
* ``features.ai_credits_monthly``per-workspace AI allowance.

Every gate (module access, user/project/storage limits, AI) reads
:func:`for_org_id` so plans and overrides behave the same everywhere.
"""
import copy
import time
from typing import Optional

PLAN_KEYS = ("starter", "pro", "enterprise")
LIMIT_KEYS = ("max_users", "max_projects", "storage_mb")

# Starting values only; Super Admin edits them in the console. Every plan
# includes every module until a plan is narrowed, so existing customers keep
# what they use. ``ai_credits_monthly``: None = no monthly cap, 0 = AI off.
DEFAULT_PLANS = {
    "starter": {"name": "Starter", "limits": {"max_users": 10, "max_projects": 100, "storage_mb": 2048},
                "excluded_modules": [], "ai_credits_monthly": None, "support": "Email, business hours"},
    "pro": {"name": "Professional", "limits": {"max_users": 30, "max_projects": 1000, "storage_mb": 10240},
            "excluded_modules": [], "ai_credits_monthly": None, "support": "Priority"},
    "enterprise": {"name": "Enterprise", "limits": {"max_users": 500, "max_projects": 10000, "storage_mb": 51200},
                   "excluded_modules": [], "ai_credits_monthly": None, "support": "Named contact"},
}

_CACHE_SECONDS = 30
_cache: dict = {"at": 0.0, "plans": None}


def invalidate_plans() -> None:
    _cache["plans"] = None


def merge_plan(base: dict, row: dict) -> dict:
    plan = copy.deepcopy(base)
    for field in ("name", "support"):
        if isinstance(row.get(field), str) and row[field].strip():
            plan[field] = row[field].strip()
    if isinstance(row.get("limits"), dict):
        for k in LIMIT_KEYS:
            v = row["limits"].get(k)
            if isinstance(v, int) and v > 0:
                plan["limits"][k] = v
    if isinstance(row.get("excluded_modules"), list):
        plan["excluded_modules"] = sorted({str(m) for m in row["excluded_modules"]})
    if "ai_credits_monthly" in row:
        v = row["ai_credits_monthly"]
        plan["ai_credits_monthly"] = v if v is None or (isinstance(v, int) and v >= 0) else None
    return plan


async def load_plans() -> dict:
    """The plan catalogue (defaults merged with Super Admin edits), cached briefly."""
    now = time.monotonic()
    if _cache["plans"] is not None and now - _cache["at"] < _CACHE_SECONDS:
        return _cache["plans"]
    from .db import db
    plans = {k: copy.deepcopy(v) for k, v in DEFAULT_PLANS.items()}
    async for row in db.platform_plans.find({}, {"_id": 0}):
        if row.get("key") in plans:
            plans[row["key"]] = merge_plan(plans[row["key"]], row)
    _cache.update(at=now, plans=plans)
    return plans


def effective(org: Optional[dict], plans: dict) -> dict:
    """Pure: combine a workspace document with the plan catalogue."""
    from models.organization import features_for_mode
    org = org or {}
    key = org.get("plan") if org.get("plan") in plans else "starter"
    plan = plans[key]
    features = org.get("features") or {}
    own_limits = {k: int(v) for k, v in (features.get("limits") or {}).items()
                  if k in LIMIT_KEYS and isinstance(v, (int, float)) and v > 0}
    switches = {**features_for_mode(org.get("business_mode") or "hybrid"),
                **(features.get("modules") or {})}
    grants = set(features.get("module_grants") or [])
    excluded = set(plan.get("excluded_modules") or [])
    modules = {k: (v is not False) and (k not in excluded or k in grants) for k, v in switches.items()}
    has_ai_override = "ai_credits_monthly" in features
    return {
        "plan": key,
        "plan_name": plan["name"],
        "support": plan.get("support"),
        "limits": {**plan["limits"], **own_limits},
        "modules": modules,
        "ai_credits_monthly": features["ai_credits_monthly"] if has_ai_override else plan.get("ai_credits_monthly"),
        "plan_excluded": sorted(excluded - grants),
        "overrides": {"limits": sorted(own_limits), "module_grants": sorted(grants),
                      "ai_credits_monthly": has_ai_override},
    }


async def for_org(org: Optional[dict]) -> Optional[dict]:
    if not org:
        return None
    return effective(org, await load_plans())


async def for_org_id(org_id: Optional[str]) -> Optional[dict]:
    """Effective entitlements, or None when the workspace does not exist (the
    default workspace during first start-up): callers then allow."""
    if not org_id:
        return None
    from .db import db
    org = await db.organizations.find_one(
        {"org_id": org_id}, {"_id": 0, "plan": 1, "features": 1, "business_mode": 1})
    return await for_org(org)


# ---------------------------------------------------------------------------
# AI allowance
# ---------------------------------------------------------------------------
def _month() -> str:
    from .helpers import business_today
    return business_today().strftime("%Y-%m")


async def ai_calls_this_month(org_id: str) -> int:
    from .db import db
    row = await db.ai_usage.find_one({"org_id": org_id, "month": _month()}, {"_id": 0, "calls": 1})
    return int((row or {}).get("calls") or 0)


async def consume_ai_credit(org_id: Optional[str]) -> None:
    """Count one AI request against the workspace's monthly allowance, or refuse it."""
    from fastapi import HTTPException
    if not org_id:
        return
    ent = await for_org_id(org_id)
    allowance = (ent or {}).get("ai_credits_monthly")
    if allowance == 0:
        raise HTTPException(status_code=403, detail="AI is not included in your workspace's plan.")
    from .db import db
    month = _month()
    if allowance is not None and await ai_calls_this_month(org_id) >= allowance:
        raise HTTPException(status_code=429,
                            detail=f"Your workspace has used its {allowance} AI requests for this month.")
    # The upsert copies org_id and month from the filter into a new row.
    await db.ai_usage.update_one({"org_id": org_id, "month": month}, {"$inc": {"calls": 1}}, upsert=True)
