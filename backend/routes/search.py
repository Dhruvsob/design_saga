"""Global search — one endpoint powering the header search + ⌘K palette.

Tenant-scoped via the scoped-db proxy. Returns normalized results with a
deeplink route so the frontend can navigate straight to the record.
"""
import re
from typing import Optional
from fastapi import APIRouter, Request, Cookie, Header

from core.deps import require_user
from core.scoped_db import sdb
from core.rbac import has_permission

router = APIRouter()


def _rx(q: str):
    return {"$regex": re.escape(q), "$options": "i"}


@router.get("/search")
async def global_search(request: Request, q: str = "", limit: int = 5,
                        session_token: Optional[str] = Cookie(default=None),
                        authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    q = (q or "").strip()
    if len(q) < 2:
        return {"query": q, "results": []}
    limit = max(1, min(limit, 10))
    rx = _rx(q)
    results = []

    async def push(coll, mongo_q, type_, title_key, route_fn, subtitle_fn, perm):
        if not has_permission(user, perm):
            return
        mongo_q = {"$and": [mongo_q, {"archived": {"$ne": True}}]}
        rows = await coll.find(mongo_q, {"_id": 0}).sort("created_at", -1).to_list(limit)
        for r in rows:
            results.append({
                "type": type_,
                "id": r.get("id"),
                "title": r.get(title_key) or "(untitled)",
                "subtitle": subtitle_fn(r),
                "route": route_fn(r),
            })

    await push(sdb.projects, {"$or": [{"name": rx}, {"client_name": rx}]},
               "project", "name",
               lambda r: f"/projects/{r.get('id')}",
               lambda r: " \u00b7 ".join(x for x in [r.get("client_name"), r.get("stage")] if x),
               "projects.read")

    await push(sdb.clients, {"$or": [{"name": rx}, {"company": rx}, {"email": rx}, {"phone": rx}]},
               "client", "name",
               lambda r: f"/clients/{r.get('id')}",
               lambda r: r.get("company") or r.get("email") or "",
               "clients.read")

    await push(sdb.leads, {"$or": [{"name": rx}, {"email": rx}, {"phone": rx}, {"location": rx}]},
               "lead", "name",
               lambda r: "/crm",
               lambda r: " \u00b7 ".join(x for x in [r.get("stage"), r.get("source")] if x),
               "leads.read")

    await push(sdb.tasks, {"$or": [{"title": rx}, {"area": rx}, {"category": rx}]},
               "task", "title",
               lambda r: f"/tasks/{r.get('id')}",
               lambda r: " \u00b7 ".join(x for x in [r.get("status_detail") or r.get("status"), r.get("assignee_name")] if x),
               "tasks.read")

    await push(sdb.vendors_acc, {"$or": [{"name": rx}, {"company_name": rx}, {"contact_person": rx}]},
               "vendor", "name",
               lambda r: f"/vendors/{r.get('id')}",
               lambda r: r.get("agency_type") or "",
               "vendors.read")

    await push(sdb.invoices, {"$or": [{"number": rx}, {"client_name": rx}, {"project_name": rx}]},
               "invoice", "number",
               lambda r: "/invoices",
               lambda r: " \u00b7 ".join(x for x in [r.get("client_name"), r.get("status")] if x),
               "invoices.read")

    await push(sdb.employees, {"$or": [{"name": rx}, {"employee_id": rx}, {"designation": rx}]},
               "employee", "name",
               lambda r: f"/employees/{r.get('id')}",
               lambda r: " \u00b7 ".join(x for x in [r.get("employee_id"), r.get("designation")] if x),
               "employees.read")

    await push(sdb.purchase_orders, {"$or": [{"po_number": rx}, {"vendor_name": rx}]},
               "purchase_order", "po_number",
               lambda r: "/purchase-orders",
               lambda r: " \u00b7 ".join(x for x in [r.get("vendor_name"), r.get("status")] if x),
               "vendors.read")

    return {"query": q, "results": results[:40]}
