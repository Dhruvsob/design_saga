"""Tenant-scoped Mongo proxy.

Set the current user's tenant scope at the start of every authenticated
request (see `core/deps.require_user`), then use `sdb` in place of `db`
for every business collection. All reads / writes are transparently
filtered by `tenant_filter(user)` and inserts are stamped with `org_id`.

Platform-level collections (organizations, users, user_sessions,
login_attempts) MUST continue to use plain `db` because SuperAdmins
need cross-org access.
"""
from contextvars import ContextVar
from typing import Optional
import os

from .db import db


# --- inline versions of tenant_filter / is_super_admin to avoid circular import ---
DEFAULT_ORG_ID = "org_default"
_SA_EMAILS = {
    e.strip().lower()
    for e in os.environ.get("SUPER_ADMIN_EMAILS", "designsaga10@gmail.com").split(",")
    if e.strip()
}


def _is_super_admin_local(user: Optional[dict]) -> bool:
    if not user:
        return False
    if user.get("is_super_admin") is True:
        return True
    if (user.get("role") or "").lower() in ("superadmin", "super_admin"):
        return True
    email = (user.get("email") or "").strip().lower()
    return email in _SA_EMAILS


def _tenant_filter_local(user: dict) -> dict:
    if _is_super_admin_local(user):
        return {}
    oid = user.get("org_id") or DEFAULT_ORG_ID
    if oid == DEFAULT_ORG_ID:
        return {"$or": [{"org_id": DEFAULT_ORG_ID},
                        {"org_id": {"$exists": False}},
                        {"org_id": None}]}
    return {"org_id": oid}


# Current request scope. `None` = SuperAdmin / no scope (see everything).
_scope: ContextVar[Optional[dict]] = ContextVar("_scope", default=None)


def set_scope_from_user(user: Optional[dict]):
    """Called at the top of every authenticated request."""
    if not user:
        _scope.set(None)
        return
    # SuperAdmin with no impersonation → cross-org.
    if _is_super_admin_local(user) and not user.get("org_id"):
        _scope.set(None)
        return
    _scope.set(_tenant_filter_local(user))


def clear_scope():
    _scope.set(None)


def current_org_id() -> Optional[str]:
    """Extract a single org_id from the current scope (for inserts)."""
    s = _scope.get()
    if not s:
        return None
    if isinstance(s.get("org_id"), str):
        return s["org_id"]
    if "$or" in s:
        for cond in s["$or"]:
            oid = cond.get("org_id")
            if isinstance(oid, str):
                return oid
    return None


def _merge(scope: Optional[dict], q: Optional[dict]) -> dict:
    if scope is None or scope == {}:
        return q or {}
    if not q:
        return dict(scope)
    # If both use $or on the same field, wrap in $and to preserve semantics
    if "$or" in q and "$or" in scope:
        return {"$and": [scope, q]}
    if "$and" in q:
        return {**q, "$and": q["$and"] + [scope]}
    # Field-level merge; scope takes precedence for org_id
    out = dict(q)
    for k, v in scope.items():
        out.setdefault(k, v)
    return out


class _ScopedColl:
    def __init__(self, coll):
        self._c = coll

    def _s(self):
        return _scope.get()

    def find(self, q=None, *a, **kw):
        return self._c.find(_merge(self._s(), q), *a, **kw)

    def find_one(self, q=None, *a, **kw):
        return self._c.find_one(_merge(self._s(), q), *a, **kw)

    def find_one_and_update(self, q, u, *a, **kw):
        return self._c.find_one_and_update(_merge(self._s(), q), u, *a, **kw)

    def count_documents(self, q=None, *a, **kw):
        return self._c.count_documents(_merge(self._s(), q or {}), *a, **kw)

    def update_one(self, q, u, *a, **kw):
        return self._c.update_one(_merge(self._s(), q), u, *a, **kw)

    def update_many(self, q, u, *a, **kw):
        return self._c.update_many(_merge(self._s(), q), u, *a, **kw)

    def delete_one(self, q, *a, **kw):
        return self._c.delete_one(_merge(self._s(), q), *a, **kw)

    def delete_many(self, q, *a, **kw):
        return self._c.delete_many(_merge(self._s(), q), *a, **kw)

    def insert_one(self, doc, *a, **kw):
        oid = current_org_id()
        if oid and isinstance(doc, dict) and not doc.get("org_id"):
            doc = {**doc, "org_id": oid}
        return self._c.insert_one(doc, *a, **kw)

    def insert_many(self, docs, *a, **kw):
        oid = current_org_id()
        if oid:
            docs = [({**d, "org_id": oid} if isinstance(d, dict) and not d.get("org_id") else d) for d in docs]
        return self._c.insert_many(docs, *a, **kw)

    def aggregate(self, pipeline, *a, **kw):
        s = self._s()
        if s:
            pipeline = [{"$match": s}] + list(pipeline)
        return self._c.aggregate(pipeline, *a, **kw)

    def distinct(self, key, filter=None, *a, **kw):
        return self._c.distinct(key, _merge(self._s(), filter or {}), *a, **kw)

    def __getattr__(self, name):
        # Passthrough for anything we haven't wrapped
        return getattr(self._c, name)


class _ScopedDB:
    """Proxy that returns scoped collections. Access `sdb.leads` etc."""
    def __getattr__(self, name):
        return _ScopedColl(getattr(db, name))

    def __getitem__(self, name):
        return _ScopedColl(db[name])


sdb = _ScopedDB()
