"""Vendor / Agency management + Vendor Ledger (Phase-2).

Enterprise-grade vendor master with dedicated bills and payments, deep
integration with the accounting journal (single source of truth) and read-time
derivation of ledger, outstanding balance and performance metrics.

Design decisions
----------------
* **Reuse** the existing `db.vendors_acc` collection so historical
  journal_entries and the vendor_ledger endpoint in `routes/accounting.py`
  keep working unchanged.
* **New collections**:
    - `vendor_bills`     – bills received from vendors (before/without payment)
    - `vendor_ratings`   – per-project rating snapshots (drives performance %)
* **Vendor payments** are recorded as balanced journal_entries with
  `source="vendor_payment"` (DR Accounts Payable · CR Cash/Bank), plus a
  `bill_ids` link so we can compute paid-vs-outstanding on any bill.
* Every business query is tenant-scoped by `sdb`; new records are stamped with
  the active organization context.

RBAC
----
* `vendors.read`   – operational directory/assignment data
* `vendors.create` – Admin, Director, ProjectManager, Accountant
* `vendors.update` – Admin, Director, ProjectManager, Accountant
* `vendors.delete` – Admin, Director
* `finance.read`   – required for bills, payments, ledgers and commissions
* `finance.create` – required for posting bills & payments (Admin, Director, Accountant)
"""
from fastapi import APIRouter, HTTPException, Request, Cookie, Header, File, Form, UploadFile
from fastapi.responses import FileResponse
from pymongo.errors import DuplicateKeyError
from typing import Optional, List
from datetime import datetime, timezone
import hashlib

from core.db import db
from core.scoped_db import sdb
from core.helpers import business_today, iso_now, new_id
from core.deps import require_user
from core.tenancy import user_org_id
from core.rbac import has_permission
from core.locks import doc_lock
from core.finance import require_asset_account
from core.audit import audit
from core.url_security import external_http_url
from services.local_files import remove_upload, resolve_storage_key, save_upload
from core.access_control import (
    get_visible_project, merge_query, project_visibility_query, task_visibility_query,
    visible_project_ids,
)
import re as _re_mod
from models.accounting import VendorIn
from models.vendor import (
    VendorUpdate, VendorBillIn, VendorBillUpdate, VendorPaymentIn,
    VendorRatingIn, VendorDocumentIn,
    CommissionConfig, CommissionReceiveIn, CommissionExpectedIn, CommissionExpectedUpdate,
    AGENCY_TYPES, VENDOR_BILL_STATUSES, COMMISSION_TYPES, COMMISSION_STATUSES,
)


router = APIRouter()


# ==================================================
# helpers
# ==================================================
def _require(user: dict, perm: str):
    if not has_permission(user, perm):
        raise HTTPException(status_code=403, detail=f"Missing permission: {perm}")


_VENDOR_FINANCIAL_FIELDS = {
    "pan", "bank_name", "bank_account_number", "bank_ifsc", "bank_branch",
    "upi_id", "tds_applicable", "tds_rate", "commission",
}


def _can_read_vendor_financials(user: dict) -> bool:
    return has_permission(user, "finance.read")


def _vendor_for_user(vendor: dict, user: dict) -> dict:
    out = dict(vendor)
    if not _can_read_vendor_financials(user):
        for field in _VENDOR_FINANCIAL_FIELDS:
            out.pop(field, None)
        if not has_permission(user, "vendors.update"):
            out.pop("documents", None)
    return out


async def _vendor_task_query(vendor: dict) -> dict:
    """Use a legacy vendor-name link only when it identifies one active vendor."""
    terms = [{"vendor_id": vendor["id"]}]
    name = (vendor.get("name") or "").strip()
    if name:
        matches = await sdb.vendors_acc.count_documents({
            "name": {"$regex": f"^{_re_mod.escape(name)}$", "$options": "i"},
            "active": {"$ne": False},
        })
        if matches == 1:
            terms.append({"vendor_contact.vendor_name": name})
    return {"$or": terms}


def _bill_total(bill: dict) -> float:
    """Compute a bill's grand total from items + tax + tds."""
    items = bill.get("items") or []
    subtotal = 0.0
    for it in items:
        amt = float(it.get("quantity") or 0) * float(it.get("rate") or 0)
        it["amount"] = round(amt, 2)
        subtotal += amt
    tax = round(subtotal * float(bill.get("tax_rate") or 0) / 100.0, 2)
    tds = round(subtotal * float(bill.get("tds_rate") or 0) / 100.0, 2)
    grand = round(subtotal + tax - tds, 2)
    bill["subtotal"] = round(subtotal, 2)
    bill["tax_amount"] = tax
    bill["tds_amount"] = tds
    bill["total"] = grand
    return grand


async def _post_vendor_bill(user: dict, bill: dict) -> dict:
    """Post one received vendor bill to GRN clearing/expense and A/P."""
    if bill.get("journal_entry_id"):
        existing = await sdb.journal_entries.find_one(
            {"id": bill["journal_entry_id"]}, {"_id": 0})
        if existing:
            return existing
    if bill.get("status") == "draft":
        raise HTTPException(status_code=409, detail="Draft bills are not posted to accounting")
    if float(bill.get("subtotal") or 0) <= 0 or float(bill.get("total") or 0) <= 0:
        raise HTTPException(status_code=400, detail="A received bill must have a positive total")

    from routes.accounting import _post_journal, _seed_coa_if_empty
    await _seed_coa_if_empty()
    ap = await sdb.accounts.find_one(
        {"name": "Accounts Payable", "type": "liability", "active": {"$ne": False}},
        {"_id": 0},
    )
    if not ap:
        raise HTTPException(status_code=500, detail="Accounts Payable account missing")

    project_id = bill.get("project_id")
    if bill.get("po_id"):
        po = await sdb.purchase_orders.find_one({"id": bill["po_id"]}, {"_id": 0})
        if not po or po.get("vendor_id") != bill.get("vendor_id"):
            raise HTTPException(status_code=400, detail="Purchase order does not belong to this vendor")
        if po.get("status") in {"draft", "cancelled"}:
            raise HTTPException(status_code=409, detail="Purchase order must be sent before billing")
        project_id = po.get("project_id") or project_id
        po_lines = {line["id"]: line for line in po.get("lines") or []}
        received_by_line = {}
        async for grn in sdb.goods_receipts.find(
            {"po_id": po["id"]}, {"_id": 0, "lines": 1}
        ):
            for line in grn.get("lines") or []:
                line_id = line.get("po_line_id")
                received_by_line[line_id] = received_by_line.get(line_id, 0.0) + float(
                    line.get("received_qty") or 0)
        billed_by_line = {}
        async for prior in sdb.vendor_bills.find(
            {"po_id": po["id"], "id": {"$ne": bill["id"]},
             "journal_entry_id": {"$ne": None},
             "status": {"$in": ["received", "partially_paid", "overdue", "paid"]}},
            {"_id": 0, "items": 1},
        ):
            for item in prior.get("items") or []:
                line_id = item.get("po_line_id")
                billed_by_line[line_id] = billed_by_line.get(line_id, 0.0) + float(
                    item.get("quantity") or 0)
        for item in bill.get("items") or []:
            line_id = item.get("po_line_id")
            if not line_id or line_id not in po_lines:
                raise HTTPException(status_code=400, detail="Every PO bill item must link to a PO line")
            new_total = billed_by_line.get(line_id, 0.0) + float(item.get("quantity") or 0)
            if new_total > received_by_line.get(line_id, 0.0) + 0.001:
                raise HTTPException(
                    status_code=409,
                    detail=f"Billed quantity exceeds received quantity for {po_lines[line_id].get('item_name')}",
                )
        base = await sdb.accounts.find_one(
            {"name": "GRN Clearing", "type": "liability", "active": {"$ne": False}},
            {"_id": 0},
        )
        if not base:
            raise HTTPException(status_code=409, detail="No GRN clearing account exists; record the goods receipt first")
    else:
        if bill.get("expense_account_id"):
            base = await sdb.accounts.find_one(
                {"id": bill["expense_account_id"], "type": "expense",
                 "active": {"$ne": False}},
                {"_id": 0},
            )
        else:
            base = await sdb.accounts.find_one(
                {"name": "Miscellaneous Expenses", "type": "expense",
                 "active": {"$ne": False}},
                {"_id": 0},
            )
            await sdb.vendor_bills.update_one(
                {"id": bill["id"]},
                {"$set": {"expense_account_id": (base or {}).get("id"),
                          "accounting_warning": "default_expense_account"}},
            )
        if not base:
            raise HTTPException(status_code=400, detail="A valid expense account is required for a non-PO bill")

    subtotal = round(float(bill.get("subtotal") or 0), 2)
    tax = round(float(bill.get("tax_amount") or 0), 2)
    tds = round(float(bill.get("tds_amount") or 0), 2)
    payable = round(float(bill.get("total") or 0), 2)
    lines = [{
        "account_id": base["id"], "debit": subtotal, "credit": 0,
        "description": "GRN clearing" if bill.get("po_id") else "Vendor expense",
    }]
    if tax > 0:
        input_gst = await sdb.accounts.find_one(
            {"name": "Input GST Credit", "type": "asset", "active": {"$ne": False}},
            {"_id": 0},
        )
        if not input_gst:
            raise HTTPException(status_code=500, detail="Input GST Credit account missing")
        lines.append({"account_id": input_gst["id"], "debit": tax, "credit": 0,
                      "description": "Input GST credit"})
    lines.append({"account_id": ap["id"], "debit": 0, "credit": payable,
                  "description": f"Payable to {bill.get('vendor_name') or 'vendor'}"})
    if tds > 0:
        tds_account = await sdb.accounts.find_one(
            {"name": "TDS Payable", "type": "liability", "active": {"$ne": False}},
            {"_id": 0},
        )
        if not tds_account:
            raise HTTPException(status_code=500, detail="TDS Payable account missing")
        lines.append({"account_id": tds_account["id"], "debit": 0, "credit": tds,
                      "description": "TDS withheld"})

    journal = await _post_journal(
        user, bill["bill_date"],
        f"Vendor bill {bill.get('bill_number')} · {bill.get('vendor_name')}",
        lines, reference=bill.get("bill_number"), project_id=project_id,
        vendor_id=bill.get("vendor_id"), source="vendor_bill", source_id=bill["id"],
    )
    await sdb.vendor_bills.update_one(
        {"id": bill["id"]},
        {"$set": {"journal_entry_id": journal["id"], "accounting_status": "posted",
                  "project_id": project_id, "posted_at": iso_now(),
                  "posted_by": user["user_id"]}},
    )
    return journal


async def _paid_against_bill(bill_id: str) -> float:
    """Sum of all vendor payments settled against this bill."""
    total = 0.0
    async for pmt in sdb.vendor_payments.find(
        {"bill_ids": bill_id, "status": {"$ne": "reversed"}}, {"_id": 0}
    ):
        # For payments that settle multiple bills we stored a per-bill split.
        splits = pmt.get("bill_splits") or {}
        if bill_id in splits:
            total += float(splits[bill_id])
        else:
            # legacy single-bill payment
            total += float(pmt.get("amount") or 0)
    return round(total, 2)


async def _refresh_bill_status(bill_id: str):
    """Re-derive a bill's status based on paid vs total."""
    bill = await sdb.vendor_bills.find_one({"id": bill_id}, {"_id": 0})
    if not bill or bill.get("status") == "cancelled":
        return
    paid = await _paid_against_bill(bill_id)
    total = float(bill.get("total") or 0)
    if paid <= 0.001:
        new_status = "received"
    elif paid + 0.001 >= total:
        new_status = "paid"
    else:
        new_status = "partially_paid"
    # overdue check
    if new_status in ("received", "partially_paid"):
        due = bill.get("due_date")
        if due:
            try:
                if datetime.fromisoformat(due).date() < business_today():
                    new_status = "overdue" if new_status == "received" else new_status
            except Exception:
                pass
    await sdb.vendor_bills.update_one(
        {"id": bill_id}, {"$set": {"status": new_status, "paid_amount": paid,
                                   "outstanding": round(total - paid, 2)}}
    )


# ==================================================
# Vendor master — CRUD
# ==================================================
@router.get("/vendors")
async def list_vendors(
    request: Request,
    q: Optional[str] = None,
    agency_type: Optional[str] = None,
    category: Optional[str] = None,
    active: Optional[bool] = None,
    project_id: Optional[str] = None,
    session_token: Optional[str] = Cookie(default=None),
    authorization: Optional[str] = Header(default=None),
):
    user = await require_user(request, session_token, authorization)
    _require(user, "vendors.read")

    query: dict = {}
    if agency_type: query["agency_type"] = agency_type
    if category:    query["category"] = category
    if active is not None:
        query["active"] = active
    else:
        query["active"] = {"$ne": False}
    if q:
        rx = {"$regex": q, "$options": "i"}
        query["$or"] = [{"name": rx}, {"company": rx}, {"phone": rx},
                        {"email": rx}, {"gstin": rx}, {"contact_person": rx}]

    rows = await sdb.vendors_acc.find(query, {"_id": 0}).sort("name", 1).to_list(1000)

    # Filter by project: only vendors that have journal_entries or bills against this project
    if project_id:
        await get_visible_project(user, project_id)
        involved = set()
        async for e in sdb.journal_entries.find({"project_id": project_id,
                                                "vendor_id": {"$ne": None}},
                                               {"_id": 0, "vendor_id": 1}):
            if e.get("vendor_id"): involved.add(e["vendor_id"])
        async for b in sdb.vendor_bills.find({"project_id": project_id},
                                            {"_id": 0, "vendor_id": 1}):
            involved.add(b["vendor_id"])
        rows = [r for r in rows if r["id"] in involved]

    # Outstanding balances are accounting data, not general vendor-directory data.
    if _can_read_vendor_financials(user):
        for v in rows:
            outstanding = 0.0
            async for b in sdb.vendor_bills.find(
                {"vendor_id": v["id"], "status": {"$in": ["received", "partially_paid", "overdue"]}},
                {"_id": 0, "outstanding": 1, "total": 1, "paid_amount": 1},
            ):
                outstanding += float(b.get("outstanding") or (b.get("total", 0) - b.get("paid_amount", 0)))
            v["outstanding"] = round(outstanding, 2)
    return [_vendor_for_user(v, user) for v in rows]



async def _ensure_unique_gstin(gstin, exclude_id: Optional[str] = None):
    """GSTIN identifies one registration; it must be unique (case-insensitive)
    among active vendors of the tenant. PAN may legitimately repeat across a
    company's state-wise GSTINs, so it is not forced unique."""
    g = (gstin or "").strip().upper()
    if not g:
        return None
    if not _re_mod.fullmatch(r"[0-9]{2}[A-Z0-9]{13}", g):
        raise HTTPException(status_code=400, detail="GSTIN must be 15 characters (e.g. 27ABCDE1234F1Z5)")
    q = {"gstin": {"$regex": f"^{_re_mod.escape(g)}$", "$options": "i"}, "active": {"$ne": False}}
    if exclude_id:
        q["id"] = {"$ne": exclude_id}
    if await sdb.vendors_acc.find_one(q, {"_id": 1}):
        raise HTTPException(status_code=409, detail="Another active vendor already uses this GSTIN")
    return g


@router.post("/vendors")
async def create_vendor(
    payload: VendorIn, request: Request,
    session_token: Optional[str] = Cookie(default=None),
    authorization: Optional[str] = Header(default=None),
):
    user = await require_user(request, session_token, authorization)
    _require(user, "vendors.create")
    doc = payload.model_dump()
    if doc.get("agency_type") and doc["agency_type"] not in AGENCY_TYPES:
        raise HTTPException(status_code=400,
                            detail=f"agency_type must be one of {AGENCY_TYPES}")
    if doc.get("gstin"):
        doc["gstin"] = await _ensure_unique_gstin(doc["gstin"])
        doc["gstin_key"] = f"{user_org_id(user)}:{doc['gstin']}"
    if doc.get("pan"):
        doc["pan"] = doc["pan"].strip().upper()
    doc["id"] = new_id("vnd_")
    doc["created_at"] = iso_now()
    doc["created_by"] = user["user_id"]
    doc["documents"] = []
    doc["rating"] = float(doc.get("rating") or 0)
    doc.setdefault("active", True)
    try:
        await sdb.vendors_acc.insert_one(dict(doc))
    except DuplicateKeyError:
        raise HTTPException(status_code=409, detail="A vendor with this GSTIN already exists")
    await audit(user, "vendor.create", target=doc["id"], target_type="vendor",
                meta={"name": doc.get("name"), "agency_type": doc.get("agency_type")})
    return await sdb.vendors_acc.find_one({"id": doc["id"]}, {"_id": 0})


@router.get("/vendors/meta")
async def vendors_meta(request: Request,
                       session_token: Optional[str] = Cookie(default=None),
                       authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    _require(user, "vendors.read")
    return {"agency_types": AGENCY_TYPES, "bill_statuses": VENDOR_BILL_STATUSES}


@router.get("/vendors/{vendor_id}")
async def get_vendor(vendor_id: str, request: Request,
                     session_token: Optional[str] = Cookie(default=None),
                     authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    _require(user, "vendors.read")
    v = await sdb.vendors_acc.find_one({"id": vendor_id}, {"_id": 0})
    if not v:
        raise HTTPException(status_code=404, detail="Vendor not found")

    can_finance = _can_read_vendor_financials(user)
    # Aggregate finance only for users allowed to read accounting data.
    bills = (await sdb.vendor_bills.find({"vendor_id": vendor_id}, {"_id": 0})
             .sort("bill_date", -1).to_list(500)) if can_finance else []
    payments = (await sdb.vendor_payments.find({"vendor_id": vendor_id}, {"_id": 0})
                .sort("payment_date", -1).to_list(500)) if can_finance else []

    outstanding = sum(float(b.get("outstanding") or 0)
                      for b in bills if b.get("status") in ("received", "partially_paid", "overdue"))
    total_billed = sum(float(b.get("total") or 0) for b in bills
                       if b.get("status") not in ("draft", "cancelled"))
    total_paid = sum(float(p.get("amount") or 0) for p in payments
                     if p.get("status") != "reversed")

    # Assigned tasks / projects (backward compat: some tasks store vendor_id, others vendor_contact.vendor_name)
    task_query = await _vendor_task_query(v)
    tasks = await sdb.tasks.find(
        merge_query(task_query, await task_visibility_query(user)), {"_id": 0}
    ).sort("created_at", -1).to_list(500)

    project_ids = list({t.get("project_id") for t in tasks if t.get("project_id")})
    # Finance readers may also discover projects through bills/journals.
    if can_finance:
        async for b in sdb.vendor_bills.find({"vendor_id": vendor_id, "project_id": {"$ne": None}},
                                            {"_id": 0, "project_id": 1}):
            if b.get("project_id"): project_ids.append(b["project_id"])
        async for e in sdb.journal_entries.find({"vendor_id": vendor_id, "project_id": {"$ne": None}},
                                               {"_id": 0, "project_id": 1}):
            if e.get("project_id"): project_ids.append(e["project_id"])
    project_ids = list(set(project_ids))
    projects = await sdb.projects.find(merge_query(
                                      {"id": {"$in": project_ids}},
                                      await project_visibility_query(user)),
                                      {"_id": 0, "id": 1, "name": 1, "stage": 1,
                                       "client_name": 1}).to_list(200)

    v["summary"] = {
        "task_count": len(tasks),
        "project_count": len(projects),
    }
    if can_finance:
        v["summary"].update({
            "total_billed": round(total_billed, 2),
            "total_paid": round(total_paid, 2),
            "outstanding": round(outstanding, 2),
            "open_bills": sum(1 for b in bills if b.get("status") in ("received", "partially_paid", "overdue")),
        })
        v["bills"] = bills
        v["payments"] = payments
    v["tasks"] = tasks
    v["projects"] = projects
    return _vendor_for_user(v, user)


@router.patch("/vendors/{vendor_id}")
async def update_vendor(vendor_id: str, payload: VendorUpdate, request: Request,
                        session_token: Optional[str] = Cookie(default=None),
                        authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    _require(user, "vendors.update")
    patch = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not patch:
        raise HTTPException(status_code=400, detail="No fields to update")
    if patch.get("agency_type") and patch["agency_type"] not in AGENCY_TYPES:
        raise HTTPException(status_code=400, detail=f"agency_type must be one of {AGENCY_TYPES}")
    if patch.get("gstin"):
        patch["gstin"] = await _ensure_unique_gstin(patch["gstin"], exclude_id=vendor_id)
        patch["gstin_key"] = f"{user_org_id(user)}:{patch['gstin']}"
    if patch.get("pan"):
        patch["pan"] = patch["pan"].strip().upper()
    patch["updated_at"] = iso_now()
    patch["updated_by"] = user["user_id"]
    res = await sdb.vendors_acc.update_one({"id": vendor_id}, {"$set": patch})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Vendor not found")
    await audit(user, "vendor.update", target=vendor_id, target_type="vendor",
                meta={"fields": [key for key in patch if key not in ("updated_at", "updated_by")]})
    return await sdb.vendors_acc.find_one({"id": vendor_id}, {"_id": 0})


@router.delete("/vendors/{vendor_id}")
async def delete_vendor(vendor_id: str, request: Request,
                        session_token: Optional[str] = Cookie(default=None),
                        authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    _require(user, "vendors.delete")
    # Soft delete – preserve accounting audit trail.
    res = await sdb.vendors_acc.update_one(
        {"id": vendor_id},
        {"$set": {"active": False, "deleted_at": iso_now(), "deleted_by": user["user_id"]}}
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Vendor not found")
    await audit(user, "vendor.archive", target=vendor_id, target_type="vendor")
    return {"ok": True, "soft_deleted": True}


# ==================================================
# Vendor documents (attachments on the master card)
# ==================================================
@router.post("/vendors/{vendor_id}/documents")
async def add_vendor_document(vendor_id: str, payload: VendorDocumentIn, request: Request,
                              session_token: Optional[str] = Cookie(default=None),
                              authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    _require(user, "vendors.update")
    v = await sdb.vendors_acc.find_one({"id": vendor_id}, {"_id": 0})
    if not v:
        raise HTTPException(status_code=404, detail="Vendor not found")
    doc = payload.model_dump()
    try:
        doc["url"] = external_http_url(doc["url"])
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    doc["id"] = new_id("vdoc_")
    doc["uploaded_at"] = iso_now()
    doc["uploaded_by"] = user["user_id"]
    await sdb.vendors_acc.update_one({"id": vendor_id}, {"$push": {"documents": doc}})
    return doc


@router.post("/vendors/{vendor_id}/documents/upload")
async def upload_vendor_document(
        vendor_id: str, request: Request, label: Optional[str] = Form(None),
        kind: Optional[str] = Form(None), expires_on: Optional[str] = Form(None),
        upload: UploadFile = File(...),
        session_token: Optional[str] = Cookie(default=None),
        authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    _require(user, "vendors.update")
    vendor = await sdb.vendors_acc.find_one({"id": vendor_id}, {"_id": 0})
    if not vendor:
        raise HTTPException(status_code=404, detail="Vendor not found")
    try:
        stored = await save_upload(upload, user_org_id(user))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(status_code=503, detail="File storage is unavailable") from exc

    doc_id = new_id("vdoc_")
    doc = {
        "id": doc_id, "label": (label or stored["original_name"]).strip()[:180],
        "url": f"/api/vendors/{vendor_id}/documents/{doc_id}/content",
        "kind": (kind or "other").strip()[:60],
        "expires_on": (expires_on or "").strip()[:10] or None,
        "uploaded_at": iso_now(), "uploaded_by": user["user_id"], **stored,
    }
    try:
        await sdb.vendors_acc.update_one({"id": vendor_id}, {"$push": {"documents": doc}})
    except Exception:
        remove_upload(stored["storage_key"])
        raise
    await audit(user, "vendor.document_upload", target=doc_id, target_type="vendor_document",
                meta={"vendor_id": vendor_id, "size": stored["size"],
                      "sha256": stored["sha256"]})
    return doc


@router.get("/vendors/{vendor_id}/documents/{doc_id}/content")
async def vendor_document_content(
        vendor_id: str, doc_id: str, request: Request,
        session_token: Optional[str] = Cookie(default=None),
        authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    if not (_can_read_vendor_financials(user) or has_permission(user, "vendors.update")):
        raise HTTPException(status_code=403, detail="Missing permission: finance.read")
    vendor = await sdb.vendors_acc.find_one({"id": vendor_id}, {"_id": 0, "documents": 1})
    document = next((row for row in (vendor or {}).get("documents", []) if row.get("id") == doc_id), None)
    if not document or not document.get("storage_key"):
        raise HTTPException(status_code=404, detail="Document not found")
    try:
        path = resolve_storage_key(document["storage_key"])
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Document not found") from exc
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Stored file is unavailable")
    media_type = document.get("content_type") or "application/octet-stream"
    disposition = "inline" if media_type == "application/pdf" or media_type.startswith("image/") else "attachment"
    return FileResponse(
        path, media_type=media_type,
        filename=document.get("original_name") or document.get("label") or "document",
        content_disposition_type=disposition,
        headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"},
    )


@router.delete("/vendors/{vendor_id}/documents/{doc_id}")
async def remove_vendor_document(vendor_id: str, doc_id: str, request: Request,
                                 session_token: Optional[str] = Cookie(default=None),
                                 authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    _require(user, "vendors.update")
    vendor = await sdb.vendors_acc.find_one({"id": vendor_id}, {"_id": 0, "documents": 1})
    if not vendor:
        raise HTTPException(status_code=404, detail="Vendor not found")
    document = next((row for row in vendor.get("documents", []) if row.get("id") == doc_id), None)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    await sdb.vendors_acc.update_one({"id": vendor_id},
                                    {"$pull": {"documents": {"id": doc_id}}})
    remove_upload(document.get("storage_key"))
    await audit(user, "vendor.document_delete", target=doc_id, target_type="vendor_document",
                meta={"vendor_id": vendor_id, "name": document.get("label")})
    return {"ok": True}


# ==================================================
# Vendor ratings (per-project) → aggregate score
# ==================================================
@router.post("/vendors/{vendor_id}/rate")
async def rate_vendor(vendor_id: str, payload: VendorRatingIn, request: Request,
                      session_token: Optional[str] = Cookie(default=None),
                      authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    _require(user, "vendors.update")
    v = await sdb.vendors_acc.find_one({"id": vendor_id}, {"_id": 0})
    if not v:
        raise HTTPException(status_code=404, detail="Vendor not found")

    doc = payload.model_dump()
    if doc.get("project_id"):
        await get_visible_project(user, doc["project_id"])
    doc["id"] = new_id("vrat_")
    doc["vendor_id"] = vendor_id
    doc["rated_by"] = user["user_id"]
    doc["rated_by_name"] = user.get("name")
    doc["created_at"] = iso_now()
    doc["org_id"] = user_org_id(user)
    # composite = mean of provided dimensions
    dims = [doc.get(k) for k in ("quality", "timeliness", "cost", "communication")
            if doc.get(k) is not None]
    doc["overall"] = round(sum(dims) / len(dims), 2) if dims else None
    await sdb.vendor_ratings.insert_one(dict(doc))

    # Refresh aggregate rating on vendor master.
    agg = []
    async for r in sdb.vendor_ratings.find({"vendor_id": vendor_id}, {"_id": 0, "overall": 1}):
        if r.get("overall") is not None:
            agg.append(float(r["overall"]))
    new_avg = round(sum(agg) / len(agg), 2) if agg else 0.0
    await sdb.vendors_acc.update_one({"id": vendor_id},
                                    {"$set": {"rating": new_avg,
                                              "rating_count": len(agg)}})
    return doc


@router.get("/vendors/{vendor_id}/ratings")
async def list_vendor_ratings(vendor_id: str, request: Request,
                              session_token: Optional[str] = Cookie(default=None),
                              authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    _require(user, "vendors.read")
    # Verify the vendor belongs to the caller's org before exposing ratings.
    if not await sdb.vendors_acc.find_one({"id": vendor_id}, {"_id": 0, "id": 1}):
        raise HTTPException(status_code=404, detail="Vendor not found")
    visible_ids = await visible_project_ids(user)
    return await sdb.vendor_ratings.find({
        "vendor_id": vendor_id,
        "$or": [{"project_id": {"$in": visible_ids}}, {"project_id": None},
                {"project_id": {"$exists": False}}],
    }, {"_id": 0}) \
                                  .sort("created_at", -1).to_list(500)


# ==================================================
# Vendor Bills
# ==================================================
@router.post("/vendor-bills")
async def create_vendor_bill(payload: VendorBillIn, request: Request,
                             session_token: Optional[str] = Cookie(default=None),
                             authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    _require(user, "finance.create")

    idem = (request.headers.get("idempotency-key") or "").strip()[:100] or None
    request_key = f"{user_org_id(user)}:{payload.vendor_id}:{idem}" if idem else None
    if request_key:
        prior = await sdb.vendor_bills.find_one({"request_key": request_key}, {"_id": 0})
        if prior:
            return prior

    vendor = await sdb.vendors_acc.find_one({"id": payload.vendor_id}, {"_id": 0})
    if not vendor:
        raise HTTPException(status_code=404, detail="Vendor not found")

    doc = payload.model_dump()
    if doc.get("bill_number"):
        doc["bill_number"] = doc["bill_number"].strip()
        dup = await sdb.vendor_bills.find_one({
            "vendor_id": payload.vendor_id,
            "bill_number": {"$regex": f"^{_re_mod.escape(doc['bill_number'])}$", "$options": "i"},
            "status": {"$ne": "cancelled"},
        }, {"_id": 0, "id": 1})
        if dup:
            raise HTTPException(status_code=409,
                                detail="A bill with this number already exists for this vendor")
    if doc.get("project_id") and not await sdb.projects.find_one({"id": doc["project_id"]}, {"_id": 1}):
        raise HTTPException(status_code=400, detail="Project not found")
    if doc.get("status") not in (None, "draft", "received"):
        doc["status"] = "received"   # paid/partial states are derived from payments
    doc["id"] = new_id("vbill_")
    # Auto-generate a sequential bill number if the vendor didn't provide one.
    if not doc.get("bill_number"):
        from core.helpers import next_sequence, max_trailing_number
        _seed = await max_trailing_number(
            sdb.vendor_bills.find({"bill_number": {"$regex": "^VB-"}}, {"_id": 0, "bill_number": 1}),
            field="bill_number")
        doc["bill_number"] = f"VB-{await next_sequence(user.get('org_id'), 'vendor_bill', _seed)}"
    doc["bill_key"] = (
        f"{user_org_id(user)}:{payload.vendor_id}:{doc['bill_number'].casefold()}"
    )
    doc["items"] = [i if isinstance(i, dict) else i.model_dump()
                    for i in (doc.get("items") or [])]
    _bill_total(doc)
    doc["paid_amount"] = 0.0
    doc["outstanding"] = doc["total"]
    doc.setdefault("status", "received")
    doc["vendor_name"] = vendor.get("name")
    doc["created_at"] = iso_now()
    doc["created_by"] = user["user_id"]
    if request_key:
        doc["request_key"] = request_key
        doc["client_request_id"] = idem
    try:
        await sdb.vendor_bills.insert_one(dict(doc))
    except DuplicateKeyError:
        if request_key:
            prior = await sdb.vendor_bills.find_one({"request_key": request_key}, {"_id": 0})
            if prior:
                return prior
        raise HTTPException(status_code=409,
                            detail="A bill with this number already exists for this vendor")
    if doc.get("status") != "draft":
        try:
            await _post_vendor_bill(user, doc)
        except Exception:
            # The bill is not yet visible to any payment workflow; compensate
            # the failed create instead of leaving an unposted A/P document.
            await sdb.vendor_bills.delete_one({"id": doc["id"]})
            raise
    if doc.get("status") != "draft":
        await _refresh_bill_status(doc["id"])
    await audit(
        user, "vendor_bill.create", target=doc["id"], target_type="vendor_bill",
        meta={"status": doc.get("status"), "total": doc.get("total"),
              "journal_entry_id": (await sdb.vendor_bills.find_one(
                  {"id": doc["id"]}, {"_id": 0, "journal_entry_id": 1}) or {}).get("journal_entry_id")},
    )
    # Auto-compute commission for this bill (if vendor has commission enabled).
    await _compute_commission_for_bill(doc["id"])
    return await sdb.vendor_bills.find_one({"id": doc["id"]}, {"_id": 0})


@router.get("/vendor-bills")
async def list_vendor_bills(request: Request,
                            vendor_id: Optional[str] = None,
                            project_id: Optional[str] = None,
                            status: Optional[str] = None,
                            session_token: Optional[str] = Cookie(default=None),
                            authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    _require(user, "finance.read")
    query: dict = {}
    if vendor_id:  query["vendor_id"] = vendor_id
    if project_id: query["project_id"] = project_id
    if status:     query["status"] = status
    rows = await sdb.vendor_bills.find(query, {"_id": 0}).sort("bill_date", -1).to_list(1000)
    return rows


@router.get("/vendor-bills/{bill_id}")
async def get_vendor_bill(bill_id: str, request: Request,
                          session_token: Optional[str] = Cookie(default=None),
                          authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    _require(user, "finance.read")
    bill = await sdb.vendor_bills.find_one({"id": bill_id}, {"_id": 0})
    if not bill:
        raise HTTPException(status_code=404, detail="Bill not found")
    # Attach payments that touch this bill
    bill["payments"] = await sdb.vendor_payments.find(
        {"bill_ids": bill_id}, {"_id": 0}
    ).sort("payment_date", -1).to_list(200)
    return bill


@router.patch("/vendor-bills/{bill_id}")
async def update_vendor_bill(bill_id: str, payload: VendorBillUpdate, request: Request,
                             session_token: Optional[str] = Cookie(default=None),
                             authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    _require(user, "finance.update")
    bill = await sdb.vendor_bills.find_one({"id": bill_id}, {"_id": 0})
    if not bill:
        raise HTTPException(status_code=404, detail="Bill not found")
    patch = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not patch:
        raise HTTPException(status_code=400, detail="No fields to update")
    if patch.get("status") and patch["status"] not in VENDOR_BILL_STATUSES:
        raise HTTPException(status_code=400,
                            detail=f"status must be one of {VENDOR_BILL_STATUSES}")
    if patch.get("status") in ("paid", "partially_paid"):
        raise HTTPException(status_code=400, detail="Paid status is derived from recorded payments")
    if bill.get("status") == "cancelled" and patch.get("status") not in (None, "cancelled"):
        raise HTTPException(status_code=400, detail="Cancelled bills cannot be reopened")
    financial_fields = {
        "bill_number", "bill_date", "project_id", "po_id", "expense_account_id",
        "items", "tax_rate", "tds_rate",
    }
    if bill.get("journal_entry_id") and financial_fields.intersection(patch):
        raise HTTPException(
            status_code=409,
            detail="Posted bill financials cannot be edited. Cancel with a reversal and record a corrected bill.",
        )
    if bill.get("journal_entry_id") and patch.get("status") == "cancelled":
        raise HTTPException(status_code=409, detail="Use the cancel action so accounting is reversed")
    if ("items" in patch or "tax_rate" in patch or "tds_rate" in patch) and float(bill.get("paid_amount") or 0) > 0:
        raise HTTPException(status_code=400, detail="Bill amounts cannot change after payments are recorded; reverse the payments first")
    if patch.get("bill_number"):
        patch["bill_number"] = patch["bill_number"].strip()
        dup = await sdb.vendor_bills.find_one({
            "vendor_id": bill.get("vendor_id"), "id": {"$ne": bill_id},
            "bill_number": {"$regex": f"^{_re_mod.escape(patch['bill_number'])}$", "$options": "i"},
            "status": {"$ne": "cancelled"},
        }, {"_id": 1})
        if dup:
            raise HTTPException(status_code=409, detail="A bill with this number already exists for this vendor")
        patch["bill_key"] = (
            f"{user_org_id(user)}:{bill['vendor_id']}:{patch['bill_number'].casefold()}"
        )
    if "items" in patch or "tax_rate" in patch or "tds_rate" in patch:
        merged = {**bill, **patch}
        merged["items"] = [i if isinstance(i, dict) else i.model_dump()
                           for i in (merged.get("items") or [])]
        _bill_total(merged)
        patch["items"] = merged["items"]
        patch["subtotal"] = merged["subtotal"]
        patch["tax_amount"] = merged["tax_amount"]
        patch["tds_amount"] = merged["tds_amount"]
        patch["total"] = merged["total"]
    merged_for_post = {**bill, **patch}
    if bill.get("status") == "draft" and patch.get("status") == "received":
        merged_for_post["items"] = [
            item if isinstance(item, dict) else item.model_dump()
            for item in (merged_for_post.get("items") or [])
        ]
        _bill_total(merged_for_post)
        await _post_vendor_bill(user, merged_for_post)
    patch["updated_at"] = iso_now()
    patch["updated_by"] = user["user_id"]
    await sdb.vendor_bills.update_one({"id": bill_id}, {"$set": patch})
    updated_bill = await sdb.vendor_bills.find_one({"id": bill_id}, {"_id": 0})
    if updated_bill and updated_bill.get("status") != "draft":
        await _refresh_bill_status(bill_id)
    # If financials changed, re-compute commission for this bill.
    if "items" in patch or "tax_rate" in patch or "tds_rate" in patch or "status" in patch:
        await _compute_commission_for_bill(bill_id)
    return await sdb.vendor_bills.find_one({"id": bill_id}, {"_id": 0})


@router.delete("/vendor-bills/{bill_id}")
async def delete_vendor_bill(bill_id: str, request: Request,
                             session_token: Optional[str] = Cookie(default=None),
                             authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    _require(user, "finance.delete")
    bill = await sdb.vendor_bills.find_one({"id": bill_id}, {"_id": 0})
    if not bill:
        raise HTTPException(status_code=404, detail="Bill not found")
    if bill.get("status") == "cancelled":
        return {"ok": True, "already_cancelled": True,
                "reversal_je_id": bill.get("reversal_je_id")}
    paid = await _paid_against_bill(bill_id)
    if paid > 0:
        raise HTTPException(
            status_code=409,
            detail="Reverse all payments against this bill before cancelling it",
        )
    if bill.get("status") == "draft" and not bill.get("journal_entry_id"):
        await sdb.vendor_bills.delete_one({"id": bill_id})
        await sdb.vendor_commissions.delete_many({
            "bill_id": bill_id, "status": {"$in": ["pending", "invoiced"]},
        })
        return {"ok": True, "deleted": True}

    original = await sdb.journal_entries.find_one(
        {"id": bill.get("journal_entry_id")}, {"_id": 0})
    if not original:
        raise HTTPException(
            status_code=409,
            detail="Bill has no linked accounting entry; reconcile it before cancellation",
        )
    from routes.accounting import _post_journal
    reversal_key = f"{user_org_id(user) or 'org_default'}:vendor_bill_reversal:{bill_id}"
    reversal = await sdb.journal_entries.find_one(
        {"idempotency_key": reversal_key}, {"_id": 0})
    if not reversal:
        reversal = await _post_journal(
            user, business_today().isoformat(),
            f"Reversal of vendor bill {bill.get('bill_number')}",
            [{"account_id": line["account_id"], "debit": line.get("credit") or 0,
              "credit": line.get("debit") or 0,
              "description": f"Reversal · {line.get('description') or ''}"}
             for line in original.get("lines") or []],
            reference=bill.get("bill_number"), project_id=bill.get("project_id"),
            vendor_id=bill.get("vendor_id"), source="vendor_bill_reversal",
            source_id=bill_id,
        )
    await sdb.journal_entries.update_one(
        {"id": original["id"]},
        {"$set": {"reversed": True, "reversal_je_id": reversal["id"],
                  "reversed_at": iso_now(), "reversed_by": user["user_id"]}},
    )
    await sdb.vendor_bills.update_one(
        {"id": bill_id},
        {"$set": {"status": "cancelled", "cancelled_at": iso_now(),
                  "cancelled_by": user["user_id"], "reversal_je_id": reversal["id"]}},
    )
    # Preserve the commission audit row; pending commissions are cancelled and
    # received commissions get their own accounting reversal.
    await _compute_commission_for_bill(bill_id)
    await audit(user, "vendor_bill.cancel", target=bill_id, target_type="vendor_bill",
                meta={"journal_entry_id": original["id"], "reversal_je_id": reversal["id"]})
    return {"ok": True, "cancelled": True, "reversal_je_id": reversal["id"]}


# ==================================================
# Vendor Payments  (creates the journal entry)
# ==================================================
@router.post("/vendor-payments")
async def create_vendor_payment(payload: VendorPaymentIn, request: Request,
                                session_token: Optional[str] = Cookie(default=None),
                                authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    _require(user, "finance.create")

    if payload.amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be positive")
    bank_acc = await require_asset_account(payload.paid_from_account_id, "Bank/cash account")
    idem = (request.headers.get("idempotency-key") or "").strip()[:100] or None
    request_key = f"{user_org_id(user)}:{payload.vendor_id}:{idem}" if idem else None
    async with doc_lock(sdb.vendors_acc, payload.vendor_id):
        if idem:
            prior = await sdb.vendor_payments.find_one(
                {"$or": [{"request_key": request_key},
                         {"vendor_id": payload.vendor_id, "client_request_id": idem}]},
                {"_id": 0})
            if prior:
                return prior
        return await _create_vendor_payment_locked(user, payload, bank_acc, idem, request_key)


async def _create_vendor_payment_locked(user: dict, payload: VendorPaymentIn, bank_acc: dict,
                                        idem: Optional[str], request_key: Optional[str]):
    vendor = await sdb.vendors_acc.find_one({"id": payload.vendor_id}, {"_id": 0})
    if not vendor:
        raise HTTPException(status_code=404, detail="Vendor not found")
    from routes.accounting import _post_journal, _seed_coa_if_empty
    await _seed_coa_if_empty()
    ap_acc = await sdb.accounts.find_one({"name": "Accounts Payable"}, {"_id": 0})
    if not ap_acc:
        raise HTTPException(status_code=500, detail="Accounts Payable account missing – seed COA first")

    # Determine bill splits — FIFO over open bills for this vendor if none provided.
    remaining = float(payload.amount)
    bill_splits: dict = {}
    if payload.bill_ids:
        if len(payload.bill_ids) != len(set(payload.bill_ids)):
            raise HTTPException(status_code=400, detail="Duplicate bill IDs in payment")
        open_bills = []
        for bid in payload.bill_ids:
            b = await sdb.vendor_bills.find_one({"id": bid, "vendor_id": payload.vendor_id},
                                               {"_id": 0})
            if not b:
                raise HTTPException(status_code=404, detail=f"Vendor bill not found: {bid}")
            if b.get("status") in ("paid", "cancelled", "draft"):
                raise HTTPException(status_code=409, detail=f"Bill {b.get('bill_number')} is not payable")
            open_bills.append(b)
    else:
        open_bills = await sdb.vendor_bills.find(
            {"vendor_id": payload.vendor_id,
             "status": {"$in": ["received", "partially_paid", "overdue"]}},
            {"_id": 0}
        ).sort("bill_date", 1).to_list(500)

    for b in open_bills:
        if remaining <= 0.001:
            break
        outstanding = float(b.get("outstanding") or (b.get("total", 0) - b.get("paid_amount", 0)))
        if outstanding <= 0.001:
            continue
        if not b.get("journal_entry_id"):
            raise HTTPException(
                status_code=409,
                detail=f"Bill {b.get('bill_number')} is not posted to accounting; reconcile it before payment",
            )
        pay_here = min(outstanding, remaining)
        bill_splits[b["id"]] = round(pay_here, 2)
        remaining -= pay_here

    allocated = round(float(payload.amount) - remaining, 2)
    je_lines = []
    if allocated > 0:
        je_lines.append({
            "account_id": ap_acc["id"], "debit": allocated, "credit": 0,
            "description": f"Bills settled for {vendor.get('name')}",
        })
    if remaining > 0.001:
        advances = await sdb.accounts.find_one(
            {"name": "Vendor Advances", "type": "asset", "active": {"$ne": False}},
            {"_id": 0},
        )
        if not advances:
            raise HTTPException(status_code=500, detail="Vendor Advances account missing")
        je_lines.append({
            "account_id": advances["id"], "debit": round(remaining, 2), "credit": 0,
            "description": f"Advance to {vendor.get('name')}",
        })
    je_lines.append({
        "account_id": bank_acc["id"], "debit": 0, "credit": float(payload.amount),
        "description": f"Paid via {payload.payment_method}",
    })

    pmt = payload.model_dump()
    pmt["id"] = new_id("vpay_")
    pmt["vendor_name"] = vendor.get("name")
    pmt["bill_ids"] = list(bill_splits.keys()) if bill_splits else (payload.bill_ids or [])
    pmt["bill_splits"] = bill_splits
    pmt["unallocated"] = round(remaining, 2)         # excess advance (on-account)
    if idem:
        pmt["client_request_id"] = idem
        pmt["request_key"] = request_key
    pmt["created_at"] = iso_now()
    pmt["created_by"] = user["user_id"]
    je = await _post_journal(
        user, payload.payment_date, f"Vendor payment · {vendor.get('name')}",
        je_lines, reference=payload.reference, project_id=payload.project_id,
        vendor_id=payload.vendor_id, source="vendor_payment", source_id=pmt["id"],
    )
    pmt["journal_entry_id"] = je["id"]
    try:
        await sdb.vendor_payments.insert_one(dict(pmt))
    except Exception:
        # Compensate an incomplete technical write before the payment becomes
        # visible. User-facing posted journals are never deleted.
        await sdb.journal_entries.delete_one({"id": je["id"]})
        raise

    # Update bill statuses
    for bid in bill_splits.keys():
        await _refresh_bill_status(bid)

    await audit(user, "vendor_payment.create", target=pmt["id"],
                target_type="vendor_payment",
                meta={"journal_entry_id": je["id"], "allocated": allocated,
                      "advance": round(remaining, 2)})

    return await sdb.vendor_payments.find_one({"id": pmt["id"]}, {"_id": 0})


@router.get("/vendor-payments")
async def list_vendor_payments(request: Request,
                               vendor_id: Optional[str] = None,
                               project_id: Optional[str] = None,
                               session_token: Optional[str] = Cookie(default=None),
                               authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    _require(user, "finance.read")
    query: dict = {}
    if vendor_id:  query["vendor_id"] = vendor_id
    if project_id: query["project_id"] = project_id
    return await sdb.vendor_payments.find(query, {"_id": 0}).sort("payment_date", -1).to_list(1000)


@router.delete("/vendor-payments/{pmt_id}")
async def delete_vendor_payment(pmt_id: str, request: Request,
                                session_token: Optional[str] = Cookie(default=None),
                                authorization: Optional[str] = Header(default=None)):
    """Reverse a vendor payment: remove the payment record, post a balanced
    REVERSAL journal entry (ledger stays immutable / audit-safe), and refresh
    linked bill statuses."""
    user = await require_user(request, session_token, authorization)
    _require(user, "finance.delete")
    async with doc_lock(sdb.vendor_payments, pmt_id):
        return await _reverse_vendor_payment_locked(user, pmt_id)


async def _reverse_vendor_payment_locked(user: dict, pmt_id: str):
    pmt = await sdb.vendor_payments.find_one({"id": pmt_id}, {"_id": 0})
    if not pmt:
        raise HTTPException(status_code=404, detail="Payment not found")
    if pmt.get("status") == "reversed":
        return {"ok": True, "already_reversed": True,
                "reversal_je_id": pmt.get("reversal_je_id")}

    original_je_id = pmt.get("journal_entry_id")
    if not original_je_id:
        raise HTTPException(
            status_code=409,
            detail="Payment has no linked journal entry; reconcile it before reversal",
        )
    orig = await sdb.journal_entries.find_one({"id": original_je_id}, {"_id": 0})
    if not orig:
        raise HTTPException(
            status_code=409,
            detail="Linked journal entry is missing; reconcile it before reversal",
        )

    from routes.accounting import _post_journal
    reversal_key = (
        f"{user_org_id(user) or 'org_default'}:vendor_payment_reversal:{pmt_id}"
    )
    rev = await sdb.journal_entries.find_one(
        {"idempotency_key": reversal_key}, {"_id": 0}
    )
    if not rev and orig.get("reversal_je_id"):
        rev = await sdb.journal_entries.find_one(
            {"id": orig["reversal_je_id"]}, {"_id": 0}
        )
    if not rev:
        rev_lines = [{"account_id": l["account_id"], "debit": l.get("credit", 0),
                      "credit": l.get("debit", 0),
                      "description": f"Reversal · {l.get('description') or ''}".strip()}
                     for l in orig.get("lines") or []]
        rev = await _post_journal(
            user, iso_now()[:10],
            f"Vendor payment reversed · {pmt.get('vendor_name') or ''}".strip(),
            rev_lines, reference=orig.get("reference"), project_id=orig.get("project_id"),
            vendor_id=orig.get("vendor_id"), source="vendor_payment_reversal",
            source_id=pmt_id)
    await sdb.journal_entries.update_one(
        {"id": orig["id"]},
        {"$set": {"reversed": True, "reversal_je_id": rev["id"]}},
    )
    reversed_at = iso_now()
    result = await sdb.vendor_payments.update_one(
        {"id": pmt_id, "status": {"$ne": "reversed"}},
        {"$set": {
            "status": "reversed",
            "reversal_je_id": rev["id"],
            "reversed_at": reversed_at,
            "reversed_by": user.get("user_id"),
        }},
    )
    if result.matched_count == 0:
        return {"ok": True, "already_reversed": True,
                "reversal_je_id": rev["id"]}
    for bid in (pmt.get("bill_ids") or []):
        await _refresh_bill_status(bid)
    return {"ok": True, "reversed": True,
            "reversal_je_id": rev["id"]}


# ==================================================
# Vendor Ledger  (running balance across bills + payments)
# ==================================================
@router.get("/vendors/{vendor_id}/ledger")
async def vendor_full_ledger(vendor_id: str, request: Request,
                             from_date: Optional[str] = None,
                             to_date: Optional[str] = None,
                             session_token: Optional[str] = Cookie(default=None),
                             authorization: Optional[str] = Header(default=None)):
    """Chronological running-balance ledger: bills DR the vendor, payments CR them."""
    user = await require_user(request, session_token, authorization)
    _require(user, "finance.read")
    vendor = await sdb.vendors_acc.find_one({"id": vendor_id}, {"_id": 0})
    if not vendor:
        raise HTTPException(status_code=404, detail="Vendor not found")

    events: list = []
    async for b in sdb.vendor_bills.find(
        {"vendor_id": vendor_id, "status": {"$ne": "cancelled"}}, {"_id": 0}
    ):
        if b.get("status") == "draft":
            continue
        events.append({
            "type": "bill",
            "date": b.get("bill_date"),
            "ref": b.get("bill_number"),
            "narration": (b.get("notes") or "")[:120] or "Bill",
            "project_id": b.get("project_id"),
            "debit": 0.0,                        # payable increases → CR to A/P in accounting terms
            "credit": float(b.get("total") or 0),
            "id": b.get("id"),
        })
    async for p in sdb.vendor_payments.find({"vendor_id": vendor_id}, {"_id": 0}):
        events.append({
            "type": "payment",
            "date": p.get("payment_date"),
            "ref": p.get("reference") or "-",
            "narration": f"Payment · {p.get('payment_method', '').replace('_', ' ')}",
            "project_id": p.get("project_id"),
            "debit": float(p.get("amount") or 0), # payable settles → DR to A/P
            "credit": 0.0,
            "id": p.get("id"),
        })
        if p.get("status") == "reversed":
            events.append({
                "type": "payment_reversal",
                "date": (p.get("reversed_at") or p.get("payment_date") or "")[:10],
                "ref": p.get("reference") or "-",
                "narration": "Payment reversal",
                "project_id": p.get("project_id"),
                "debit": 0.0,
                "credit": float(p.get("amount") or 0),
                "id": p.get("id"),
            })

    event_order = {"bill": 0, "payment": 1, "payment_reversal": 2}
    events.sort(key=lambda e: (e.get("date") or "", event_order.get(e["type"], 9)))

    running = 0.0
    for e in events:
        # Outstanding-payable convention: bills push balance UP (owed to vendor),
        # payments push it DOWN.
        running += e["credit"] - e["debit"]
        e["balance"] = round(running, 2)

    opening_balance = 0.0
    if from_date:
        prior = [e for e in events if (e.get("date") or "") < from_date]
        if prior:
            opening_balance = prior[-1]["balance"]
    visible_events = [
        e for e in events
        if (not from_date or (e.get("date") or "") >= from_date)
        and (not to_date or (e.get("date") or "") <= to_date)
    ]

    total_billed = sum(e["credit"] for e in visible_events if e["type"] == "bill")
    total_paid = (
        sum(e["debit"] for e in visible_events if e["type"] == "payment")
        - sum(e["credit"] for e in visible_events if e["type"] == "payment_reversal")
    )
    return {
        "vendor": vendor,
        "from_date": from_date, "to_date": to_date,
        "opening_balance": round(opening_balance, 2),
        "total_billed": round(total_billed, 2),
        "total_paid": round(total_paid, 2),
        "outstanding": round(running, 2),
        "entries": visible_events,
    }


# ==================================================
# Performance score
# ==================================================
@router.get("/vendors/{vendor_id}/performance")
async def vendor_performance(vendor_id: str, request: Request,
                             session_token: Optional[str] = Cookie(default=None),
                             authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    _require(user, "vendors.read")
    vendor = await sdb.vendors_acc.find_one({"id": vendor_id}, {"_id": 0})
    if not vendor:
        raise HTTPException(status_code=404, detail="Vendor not found")

    # Task-based completion
    task_query = await _vendor_task_query(vendor)
    tasks = await sdb.tasks.find(
        merge_query(task_query, await task_visibility_query(user)), {"_id": 0}
    ).to_list(500)
    total_tasks = len(tasks)
    done_tasks = sum(1 for t in tasks if t.get("status") == "done"
                     or t.get("status_detail") == "Completed")
    open_tasks = total_tasks - done_tasks
    completion_rate = round((done_tasks / total_tasks) * 100, 1) if total_tasks else 0.0

    # Delay proxy: tasks past due & not done
    today = business_today().isoformat()
    delayed = sum(1 for t in tasks
                  if (t.get("due_date") or "") and t.get("due_date") < today
                  and t.get("status") != "done")
    delay_rate = round((delayed / total_tasks) * 100, 1) if total_tasks else 0.0

    # Payment reliability (vendor's perspective is inverted: how well WE pay them)
    can_finance = _can_read_vendor_financials(user)
    total_billed = 0.0
    outstanding = 0.0
    if can_finance:
        async for b in sdb.vendor_bills.find(
            {"vendor_id": vendor_id,
             "status": {"$in": ["received", "partially_paid", "overdue", "paid"]}},
            {"_id": 0},
        ):
            total_billed += float(b.get("total") or 0)
            if b.get("status") in ("received", "partially_paid", "overdue"):
                outstanding += float(b.get("outstanding") or 0)

    # Rating-based
    visible_ids = await visible_project_ids(user)
    ratings = await sdb.vendor_ratings.find({
        "vendor_id": vendor_id,
        "$or": [{"project_id": {"$in": visible_ids}}, {"project_id": None},
                {"project_id": {"$exists": False}}],
    }, {"_id": 0}).to_list(500)
    def _avg(k):
        vals = [float(r[k]) for r in ratings if r.get(k) is not None]
        return round(sum(vals) / len(vals), 2) if vals else None

    quality      = _avg("quality")
    timeliness   = _avg("timeliness")
    cost         = _avg("cost")
    communication = _avg("communication")

    # Composite performance (0-100). Weight scheme:
    #   completion 30 · on-time (1-delay) 25 · rating 35 · payment 10
    on_time_pct = max(0.0, 100.0 - delay_rate)
    rating_pct = 0.0
    dims = [d for d in (quality, timeliness, cost, communication) if d is not None]
    if dims:
        rating_pct = round((sum(dims) / (5 * len(dims))) * 100, 1)
    pay_pct = 100.0 if total_billed == 0 else round(
        max(0.0, 100.0 - (outstanding / total_billed) * 100), 1
    )
    performance_score = round(
        completion_rate * 0.30 + on_time_pct * 0.25 + rating_pct * 0.35 + pay_pct * 0.10,
        1,
    ) if can_finance else round(
        completion_rate * (30 / 90) + on_time_pct * (25 / 90) + rating_pct * (35 / 90),
        1,
    )

    result = {
        "vendor_id": vendor_id,
        "vendor_name": vendor.get("name"),
        "tasks": {"total": total_tasks, "done": done_tasks, "open": open_tasks,
                  "delayed": delayed,
                  "completion_rate": completion_rate, "delay_rate": delay_rate},
        "ratings": {"count": len(ratings), "quality": quality, "timeliness": timeliness,
                    "cost": cost, "communication": communication,
                    "overall": vendor.get("rating", 0.0)},
        "performance_score": performance_score,
    }
    if can_finance:
        result["financial"] = {"total_billed": round(total_billed, 2),
                               "outstanding": round(outstanding, 2),
                               "payment_reliability": pay_pct}
    return result


# ==================================================================
# COMMISSION MANAGEMENT
# ==================================================================
# Vendors like furniture / lighting / marble suppliers often pay us a
# commission on every purchase we route through them. This section:
#   - stores per-vendor commission config on the master (embedded)
#   - auto-computes a `vendor_commissions` row when a bill is created
#   - lets an Admin/Accountant mark commission received → posts a balanced
#     journal entry (DR Bank · CR Vendor Commission Income) so the income
#     shows up automatically on Dashboard, P&L, Cash Flow, everywhere.
# ==================================================================

def _bill_purchase_base(bill: dict) -> float:
    """The number commission percentages apply to — subtotal (pre-tax, pre-TDS)."""
    return float(bill.get("subtotal") or 0)


def _calc_commission_amount(cfg: dict, base: float) -> float:
    """Pure commission math. Returns amount for a given purchase base."""
    if not cfg or not cfg.get("applicable"):
        return 0.0
    min_p = float(cfg.get("min_purchase") or 0)
    if base < min_p:
        return 0.0
    t = (cfg.get("type") or "").lower()
    if t == "fixed":
        return round(float(cfg.get("fixed_amount") or 0), 2)
    if t == "percentage":
        return round(base * float(cfg.get("percentage") or 0) / 100.0, 2)
    if t == "slab":
        for s in (cfg.get("slabs") or []):
            lo = float(s.get("min_purchase") or 0)
            hi = s.get("max_purchase")
            hi = float(hi) if hi is not None else float("inf")
            if lo <= base < hi or (hi == float("inf") and base >= lo):
                return round(base * float(s.get("percentage") or 0) / 100.0, 2)
    return 0.0


async def _reverse_commission_je(commission_row: dict) -> Optional[str]:
    """Post an offsetting JE that undoes an already-received commission.

    Original settlement: DR Bank · CR Vendor Commission Income
    Reversal:            DR Vendor Commission Income · CR Bank

    Idempotent — no-op if a reversal has already been posted for this row.
    Marks the commission row as `reversed` and tracks `reversal_je_id`.
    Returns the reversal JE id if one was posted, else None.
    """
    if not commission_row:
        return None
    if commission_row.get("reversal_je_id"):
        return None  # already reversed
    received = float(commission_row.get("received_amount") or commission_row.get("amount") or 0)
    if received <= 0.001:
        # Nothing to reverse (received=0). Just mark cancelled.
        await sdb.vendor_commissions.update_one(
            {"id": commission_row["id"]},
            {"$set": {"status": "cancelled", "amount": 0.0, "updated_at": iso_now()}},
        )
        return None

    original_je_id = commission_row.get("journal_entry_id")
    original_je = None
    if original_je_id:
        original_je = await sdb.journal_entries.find_one({"id": original_je_id}, {"_id": 0})

    # Resolve bank & income accounts. Prefer the accounts used in the original JE
    # so the reversal targets the exact same accounts. Fall back to lookup by name.
    bank_acc = income_acc = None
    if original_je:
        for l in original_je.get("lines") or []:
            if float(l.get("debit") or 0) > 0 and l.get("account_type") in ("asset", "bank"):
                bank_acc = {"id": l["account_id"], "name": l["account_name"],
                            "type": l["account_type"]}
            if float(l.get("credit") or 0) > 0 and l.get("account_type") == "income":
                income_acc = {"id": l["account_id"], "name": l["account_name"],
                              "type": l["account_type"]}
    if not income_acc:
        label = (commission_row.get("commission_config_snapshot") or {}).get("income_label") \
                or "Vendor Commission Income"
        acc = await sdb.accounts.find_one({"name": label}, {"_id": 0})
        if acc:
            income_acc = {"id": acc["id"], "name": acc["name"], "type": acc["type"]}
    if not bank_acc:
        # Any bank/cash account to close the loop
        acc = await sdb.accounts.find_one({"is_bank": True}, {"_id": 0})
        if not acc:
            acc = await sdb.accounts.find_one({"name": "Cash"}, {"_id": 0})
        if acc:
            bank_acc = {"id": acc["id"], "name": acc["name"], "type": acc["type"]}

    if not (bank_acc and income_acc):
        # Cannot post reversal – flag for manual reconciliation.
        await sdb.vendor_commissions.update_one(
            {"id": commission_row["id"]},
            {"$set": {"reversal_pending": True,
                      "reversal_error": "bank_or_income_account_missing",
                      "updated_at": iso_now()}},
        )
        return None

    narration = f"Commission reversal – bill {commission_row.get('bill_number')} cancelled"
    rev_lines = [
        {"account_id": income_acc["id"], "debit": received, "credit": 0.0,
         "description": narration},
        {"account_id": bank_acc["id"], "debit": 0.0, "credit": received,
         "description": narration},
    ]
    # Use central _post_journal so the reversal is balanced, audited and shows
    # up in every report exactly like every other JE.
    from routes.accounting import _post_journal
    # Best-effort user context — bill cancellation may run from an API call
    # where we have the user in scope, but the callers pass `commission_row`
    # without a user. Grab from contextvar via scoped_db if possible.
    from core.scoped_db import current_org_id as _current_org
    _user = {"user_id": commission_row.get("_reverser_user_id") or "system",
             "name": "System (bill cancellation)"}
    rev = await _post_journal(
        _user, business_today().isoformat(), narration, rev_lines,
        reference=f"REV-{original_je_id or commission_row.get('id')}",
        project_id=commission_row.get("project_id"),
        vendor_id=commission_row.get("vendor_id"),
        source="commission_reversal", source_id=commission_row.get("id"),
    )
    # Track reverses relationship for auditability
    if original_je_id:
        await sdb.journal_entries.update_one(
            {"id": rev["id"]}, {"$set": {"reverses_je_id": original_je_id}})
    rev_je_id = rev["id"]

    await sdb.vendor_commissions.update_one(
        {"id": commission_row["id"]},
        {"$set": {"status": "reversed",
                  "reversal_je_id": rev_je_id,
                  "reversed_amount": received,
                  "reversed_at": iso_now(),
                  "bill_cancelled_after_receipt": True,
                  "updated_at": iso_now()}},
    )
    return rev_je_id


async def _compute_commission_for_bill(bill_id: str) -> Optional[dict]:
    """Create or update the commission row for a bill.
    Idempotent — safe to run on every bill update.
    Cancelled bills → cancel the commission (keep row for audit)."""
    bill = await sdb.vendor_bills.find_one({"id": bill_id}, {"_id": 0})
    if not bill:
        return None
    vendor = await sdb.vendors_acc.find_one({"id": bill["vendor_id"]}, {"_id": 0})
    if not vendor:
        return None
    cfg = vendor.get("commission") or {}
    existing = await sdb.vendor_commissions.find_one({"bill_id": bill_id}, {"_id": 0})

    if bill.get("status") == "draft":
        if existing and existing.get("status") in ("pending", "invoiced"):
            await sdb.vendor_commissions.delete_one({"id": existing["id"]})
        return None

    # Effective-date filter
    b_date = bill.get("bill_date") or ""
    if cfg.get("effective_from") and b_date and b_date < cfg["effective_from"]:
        cfg = {**cfg, "applicable": False}
    if cfg.get("effective_to") and b_date and b_date > cfg["effective_to"]:
        cfg = {**cfg, "applicable": False}

    base = _bill_purchase_base(bill)
    amount = _calc_commission_amount(cfg, base)

    # Bill cancelled → cancel commission AND reverse the accounting impact.
    #   - pending / invoiced rows: soft-cancel (no JE was ever posted)
    #   - received rows: post an offsetting reversal JE (DR Income / CR Bank) so
    #     the P&L, Balance Sheet and Cash Flow stop reflecting income that no
    #     longer applies. Idempotent — skips if a reversal_je_id already exists.
    if bill.get("status") == "cancelled":
        if existing:
            if float(existing.get("received_amount") or 0) > 0:
                await _reverse_commission_je(existing)
            else:
                await sdb.vendor_commissions.update_one(
                    {"id": existing["id"]},
                    {"$set": {"status": "cancelled",
                              "amount": 0.0,
                              "updated_at": iso_now()}},
                )
        return None

    # No commission earned → drop existing pending row (never delete received rows)
    if amount <= 0.001:
        if existing and existing.get("status") in ("pending", "invoiced"):
            await sdb.vendor_commissions.delete_one({"id": existing["id"]})
        return None

    doc = {
        "vendor_id": vendor["id"],
        "vendor_name": vendor.get("name"),
        "bill_id": bill_id,
        "bill_number": bill.get("bill_number"),
        "bill_date": bill.get("bill_date"),
        "due_date": bill.get("due_date"),
        "project_id": bill.get("project_id"),
        "purchase_amount": base,
        "commission_type": cfg.get("type"),
        "commission_config_snapshot": {
            "percentage": cfg.get("percentage"),
            "fixed_amount": cfg.get("fixed_amount"),
            "slabs": cfg.get("slabs"),
            "income_label": cfg.get("income_label") or "Vendor Commission Income",
        },
        "amount": amount,
        "earned_amount": amount,
        "recognition": "earned",
        "origin": "vendor_bill",
        "updated_at": iso_now(),
    }
    if existing:
        # Preserve received/invoiced status if any; only update pending rows numerically.
        if existing.get("status") == "received":
            # Already booked as income. Do not overwrite; log a discrepancy note.
            if abs(float(existing.get("amount") or 0) - amount) > 0.01:
                await sdb.vendor_commissions.update_one(
                    {"id": existing["id"]},
                    {"$set": {"recompute_variance": round(amount - float(existing["amount"]), 2),
                              "updated_at": iso_now()}}
                )
            return existing
        await sdb.vendor_commissions.update_one(
            {"id": existing["id"]}, {"$set": doc}
        )
        return await sdb.vendor_commissions.find_one({"id": existing["id"]}, {"_id": 0})
    doc["id"] = new_id("vcom_")
    doc["status"] = "pending"
    doc["created_at"] = iso_now()
    await sdb.vendor_commissions.insert_one(dict(doc))
    return doc


# ---------- Planned/manual commission receivable (no accounting entry) ----------
@router.post("/vendors/{vendor_id}/commissions")
async def create_expected_commission(vendor_id: str, payload: CommissionExpectedIn,
                                     request: Request,
                                     session_token: Optional[str] = Cookie(default=None),
                                     authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    _require(user, "finance.create")
    vendor = await sdb.vendors_acc.find_one({"id": vendor_id}, {"_id": 0})
    if not vendor:
        raise HTTPException(status_code=404, detail="Vendor not found")
    project_name = None
    if payload.project_id:
        project = await get_visible_project(user, payload.project_id)
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")
        project_name = project.get("name")
    doc = {
        "id": new_id("vcom_"),
        "vendor_id": vendor_id,
        "vendor_name": vendor.get("name"),
        "project_id": payload.project_id,
        "project_name": project_name,
        "amount": round(float(payload.amount), 2),
        "earned_amount": round(float(payload.amount), 2)
            if payload.recognition == "earned" else 0.0,
        "recognition": payload.recognition,
        "origin": "manual_expected",
        "due_date": payload.due_date,
        "reminder_date": payload.reminder_date,
        "reference": payload.reference,
        "notes": payload.notes,
        "received_amount": 0.0,
        "status": "pending",
        "created_at": iso_now(),
        "created_by": user["user_id"],
        "updated_at": iso_now(),
    }
    await sdb.vendor_commissions.insert_one(dict(doc))
    await audit(user, "vendor_commission.plan", target=doc["id"],
                target_type="vendor_commission",
                meta={"vendor_id": vendor_id, "amount": doc["amount"],
                      "recognition": doc["recognition"]})
    return doc


@router.patch("/vendors/{vendor_id}/commissions/{commission_id}")
async def update_expected_commission(vendor_id: str, commission_id: str,
                                     payload: CommissionExpectedUpdate, request: Request,
                                     session_token: Optional[str] = Cookie(default=None),
                                     authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    _require(user, "finance.update")
    row = await sdb.vendor_commissions.find_one(
        {"id": commission_id, "vendor_id": vendor_id}, {"_id": 0})
    if not row:
        raise HTTPException(status_code=404, detail="Commission not found")
    if row.get("origin") != "manual_expected":
        raise HTTPException(status_code=409,
                            detail="Bill-earned commissions must be corrected from the vendor bill")
    if float(row.get("received_amount") or 0) > 0:
        raise HTTPException(status_code=409,
                            detail="Reverse the linked receipt before changing this commission")
    patch = payload.model_dump(exclude_unset=True)
    if patch.get("project_id"):
        project = await get_visible_project(user, patch["project_id"])
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")
        patch["project_name"] = project.get("name")
    if "recognition" in patch:
        amount = float(patch.get("amount", row.get("amount")) or 0)
        patch["earned_amount"] = round(amount, 2) if patch["recognition"] == "earned" else 0.0
    elif "amount" in patch and row.get("recognition") == "earned":
        patch["earned_amount"] = round(float(patch["amount"]), 2)
    patch["updated_at"] = iso_now()
    await sdb.vendor_commissions.update_one({"id": commission_id}, {"$set": patch})
    await audit(user, "vendor_commission.update", target=commission_id,
                target_type="vendor_commission", meta={"fields": sorted(patch.keys())})
    return await sdb.vendor_commissions.find_one({"id": commission_id}, {"_id": 0})


@router.delete("/vendors/{vendor_id}/commissions/{commission_id}")
async def delete_expected_commission(vendor_id: str, commission_id: str, request: Request,
                                     session_token: Optional[str] = Cookie(default=None),
                                     authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    _require(user, "finance.delete")
    row = await sdb.vendor_commissions.find_one(
        {"id": commission_id, "vendor_id": vendor_id}, {"_id": 0})
    if not row:
        raise HTTPException(status_code=404, detail="Commission not found")
    if row.get("origin") != "manual_expected":
        raise HTTPException(status_code=409,
                            detail="Bill-earned commissions must be cancelled from the vendor bill")
    if float(row.get("received_amount") or 0) > 0:
        raise HTTPException(status_code=409,
                            detail="Reverse the linked receipt before deleting this commission")
    await sdb.vendor_commissions.update_one(
        {"id": commission_id},
        {"$set": {"status": "cancelled", "cancelled_at": iso_now(),
                  "cancelled_by": user["user_id"], "updated_at": iso_now()}},
    )
    await audit(user, "vendor_commission.cancel", target=commission_id,
                target_type="vendor_commission")
    return {"ok": True, "cancelled": True}


# ---------- Update vendor commission config ----------
@router.patch("/vendors/{vendor_id}/commercial")
async def update_vendor_commercial(vendor_id: str, payload: CommissionConfig, request: Request,
                                   session_token: Optional[str] = Cookie(default=None),
                                   authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    _require(user, "finance.update")
    if payload.type not in COMMISSION_TYPES:
        raise HTTPException(status_code=400,
                            detail=f"commission type must be one of {COMMISSION_TYPES}")
    cfg = payload.model_dump()
    res = await sdb.vendors_acc.update_one(
        {"id": vendor_id},
        {"$set": {"commission": cfg,
                  "commercial_updated_at": iso_now(),
                  "commercial_updated_by": user["user_id"]}}
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Vendor not found")
    # Recompute commissions for all bills of this vendor (idempotent).
    updated = 0
    async for b in sdb.vendor_bills.find({"vendor_id": vendor_id}, {"_id": 0, "id": 1}):
        await _compute_commission_for_bill(b["id"])
        updated += 1
    return {"ok": True, "recomputed_bills": updated,
            "vendor": await sdb.vendors_acc.find_one({"id": vendor_id}, {"_id": 0})}


# ---------- Get commission config (returns full vendor incl. computed rollup) ----------
@router.get("/vendors/{vendor_id}/commercial")
async def get_vendor_commercial(vendor_id: str, request: Request,
                                session_token: Optional[str] = Cookie(default=None),
                                authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    _require(user, "finance.read")
    vendor = await sdb.vendors_acc.find_one({"id": vendor_id}, {"_id": 0})
    if not vendor:
        raise HTTPException(status_code=404, detail="Vendor not found")
    return {"commission": vendor.get("commission") or {"applicable": False},
            "effective": bool((vendor.get("commission") or {}).get("applicable"))}


# ---------- List commissions for a vendor ----------
@router.get("/vendors/{vendor_id}/commissions")
async def list_vendor_commissions(vendor_id: str, request: Request,
                                  status: Optional[str] = None,
                                  session_token: Optional[str] = Cookie(default=None),
                                  authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    _require(user, "finance.read")
    q: dict = {"vendor_id": vendor_id}
    if status:
        q["status"] = status
    rows = await sdb.vendor_commissions.find(q, {"_id": 0}) \
                                      .sort("bill_date", -1).to_list(2000)
    return rows


async def _active_commission_settlements(query: dict) -> tuple[list[dict], set[str]]:
    """Return visible receipts whose accounting journal is still active.

    Settlements are the authoritative cash-receipt records. Commission rows only
    describe bill-based earnings and therefore cannot represent direct or excess
    receipts. Keep every settlement journal id for legacy de-duplication, even
    when that journal has subsequently been reversed.
    """
    settlements = await sdb.commission_settlements.find(query, {"_id": 0}) \
        .sort("received_date", -1).to_list(20000)
    journal_ids = {
        row.get("journal_entry_id") for row in settlements if row.get("journal_entry_id")
    }
    reversed_ids: set[str] = set()
    if journal_ids:
        async for journal in sdb.journal_entries.find(
            {"id": {"$in": list(journal_ids)}, "reversed": True},
            {"_id": 0, "id": 1},
        ):
            reversed_ids.add(journal["id"])
    reversed_commission_ids: set[str] = set()
    allocation_ids = {
        allocation.get("id")
        for row in settlements
        for allocation in (row.get("commissions") or [])
        if allocation.get("id")
    }
    if allocation_ids:
        async for commission in sdb.vendor_commissions.find(
                {"id": {"$in": list(allocation_ids)}, "status": "reversed"},
                {"_id": 0, "id": 1}):
            reversed_commission_ids.add(commission["id"])

    active = []
    for row in settlements:
        if (row.get("status") in ("cancelled", "reversed")
                or row.get("journal_entry_id") in reversed_ids):
            continue
        visible = dict(row)
        allocations = []
        reversed_amount = 0.0
        for allocation in row.get("commissions") or []:
            if allocation.get("id") in reversed_commission_ids:
                reversed_amount += float(allocation.get("applied") or 0)
            else:
                allocations.append(allocation)
        visible["commissions"] = allocations
        visible["original_amount"] = float(row.get("amount") or 0)
        visible["reversed_amount"] = round(reversed_amount, 2)
        visible["amount"] = round(max(0.0, visible["original_amount"] - reversed_amount), 2)
        active.append(visible)
    return active, journal_ids


async def _refresh_commission_allocations(commission_ids: list[str]) -> None:
    """Rebuild receipt totals from settlement rows so retries cannot double-apply cash."""
    for commission_id in set(commission_ids):
        row = await sdb.vendor_commissions.find_one({"id": commission_id}, {"_id": 0})
        if not row or row.get("status") in ("cancelled", "reversed"):
            continue
        received = 0.0
        latest = None
        async for settlement in sdb.commission_settlements.find(
                {"status": {"$nin": ["cancelled", "reversed"]},
                 "commissions.id": commission_id}, {"_id": 0}):
            for allocation in settlement.get("commissions") or []:
                if allocation.get("id") == commission_id:
                    received += float(allocation.get("applied") or 0)
                    latest = settlement
        received = round(received, 2)
        status = ("received" if received + 0.01 >= float(row.get("amount") or 0)
                  else "invoiced" if received > 0.001 else "pending")
        update = {"received_amount": received, "status": status, "updated_at": iso_now()}
        if row.get("origin") == "manual_expected" and received > 0:
            update["earned_amount"] = round(max(
                float(row.get("earned_amount") or 0),
                min(float(row.get("amount") or 0), received),
            ), 2)
            if row.get("recognition") == "planned":
                update["recognition"] = "earned_on_receipt"
        if latest:
            update.update({
                "received_date": latest.get("received_date"),
                "payment_method": latest.get("payment_method"),
                "reference": latest.get("reference"),
                "journal_entry_id": latest.get("journal_entry_id"),
            })
        await sdb.vendor_commissions.update_one({"id": commission_id}, {"$set": update})


# ---------- Vendor commission ledger (running totals) ----------
@router.get("/vendors/{vendor_id}/commission-ledger")
async def vendor_commission_ledger(vendor_id: str, request: Request,
                                   session_token: Optional[str] = Cookie(default=None),
                                   authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    _require(user, "finance.read")
    vendor = await sdb.vendors_acc.find_one({"id": vendor_id}, {"_id": 0})
    if not vendor:
        raise HTTPException(status_code=404, detail="Vendor not found")

    rows = await sdb.vendor_commissions.find({"vendor_id": vendor_id}, {"_id": 0}) \
                                      .sort("bill_date", 1).to_list(5000)
    receipts, settlement_journal_ids = await _active_commission_settlements(
        {"vendor_id": vendor_id}
    )
    allocated_by_commission: dict[str, float] = {}
    for receipt in receipts:
        for allocation in receipt.get("commissions") or []:
            cid = allocation.get("id")
            if cid:
                allocated_by_commission[cid] = round(
                    allocated_by_commission.get(cid, 0.0)
                    + float(allocation.get("applied") or 0),
                    2,
                )

    total_purchase = 0.0
    total_earned = 0.0
    legacy_received = 0.0
    display_rows = []
    for source_row in rows:
        r = dict(source_row)
        if r.get("status") in ("cancelled", "reversed"):
            display_rows.append(r)
            continue
        total_purchase += float(r.get("purchase_amount") or 0)
        total_earned += float(r.get("earned_amount")
                              if r.get("earned_amount") is not None
                              else r.get("amount") or 0)
        received = allocated_by_commission.get(r.get("id"), 0.0)
        # Preserve pre-settlement-schema receipts without counting modern rows twice.
        if r.get("journal_entry_id") not in settlement_journal_ids:
            legacy = float(r.get("received_amount") or 0)
            received += legacy
            legacy_received += legacy
        r["received_amount"] = round(received, 2)
        r["status"] = (
            "received" if received + 0.01 >= float(r.get("amount") or 0)
            else "invoiced" if received > 0.001
            else "pending"
        )
        display_rows.append(r)

    receipt_total = sum(float(row.get("amount") or 0) for row in receipts)
    total_received = receipt_total + legacy_received
    allocated_received = legacy_received + sum(
        float(allocation.get("applied") or 0)
        for receipt in receipts for allocation in (receipt.get("commissions") or []))
    unallocated_received = sum(float(row.get("unallocated") or 0) for row in receipts)

    return {
        "vendor_id": vendor_id,
        "vendor_name": vendor.get("name"),
        "config": vendor.get("commission") or {"applicable": False},
        "totals": {
            "total_purchase": round(total_purchase, 2),
            "total_earned": round(total_earned, 2),
            "total_received": round(total_received, 2),
            "allocated_received": round(allocated_received, 2),
            "pending": round(max(0.0, total_earned - allocated_received), 2),
            "unallocated_received": round(unallocated_received, 2),
        },
        "entries": display_rows,
        "receipts": receipts,
    }


# ---------- Receive commission (create Income journal entry) ----------
@router.post("/vendors/{vendor_id}/commissions/receive")
async def receive_commission(vendor_id: str, payload: CommissionReceiveIn, request: Request,
                             session_token: Optional[str] = Cookie(default=None),
                             authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    _require(user, "finance.create")
    if payload.amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be positive")
    bank = await require_asset_account(payload.bank_account_id, "Bank/cash account")
    if payload.commission_ids and len(set(payload.commission_ids)) != len(payload.commission_ids):
        raise HTTPException(status_code=400, detail="Duplicate commission IDs in request")
    idem = (request.headers.get("idempotency-key") or "").strip()[:100] or None
    request_key = f"{user_org_id(user)}:{vendor_id}:{idem}" if idem else None
    async with doc_lock(sdb.vendors_acc, vendor_id):
        if request_key:
            prior = await sdb.commission_settlements.find_one(
                {"request_key": request_key}, {"_id": 0})
            if prior:
                await _refresh_commission_allocations(
                    [row.get("id") for row in prior.get("commissions") or [] if row.get("id")])
                return {"ok": True, "settlement_id": prior["id"],
                        "journal_entry_id": prior.get("journal_entry_id"),
                        "settled": prior.get("commissions") or [],
                        "unallocated": float(prior.get("unallocated") or 0)}
        return await _receive_commission_locked(
            user, vendor_id, payload, bank, idem=idem, request_key=request_key)


async def _receive_commission_locked(user: dict, vendor_id: str, payload: CommissionReceiveIn,
                                     bank: dict, idem: Optional[str] = None,
                                     request_key: Optional[str] = None):
    vendor = await sdb.vendors_acc.find_one({"id": vendor_id}, {"_id": 0})
    if not vendor:
        raise HTTPException(status_code=404, detail="Vendor not found")

    income_label = ((vendor.get("commission") or {}).get("income_label")
                    or "Vendor Commission Income")
    inc = await sdb.accounts.find_one({"name": income_label}, {"_id": 0})
    if not inc:
        raise HTTPException(status_code=500,
                            detail=f"Income account '{income_label}' missing – seed COA first")

    # Pick rows to settle — FIFO across pending/invoiced if none provided.
    if payload.commission_ids:
        rows = []
        for cid in payload.commission_ids:
            r = await sdb.vendor_commissions.find_one({"id": cid, "vendor_id": vendor_id},
                                                    {"_id": 0})
            if r and r.get("status") in ("pending", "invoiced"):
                rows.append(r)
    else:
        rows = await sdb.vendor_commissions.find(
            {"vendor_id": vendor_id, "status": {"$in": ["pending", "invoiced"]}},
            {"_id": 0}
        ).sort("bill_date", 1).to_list(500)

    remaining = float(payload.amount)
    settled: list = []
    project_ids: list = []
    for r in rows:
        if remaining <= 0.001:
            break
        due = float(r.get("amount") or 0) - float(r.get("received_amount") or 0)
        if due <= 0.001:
            continue
        pay = min(due, remaining)
        settled.append({"id": r["id"], "applied": round(pay, 2),
                        "project_id": r.get("project_id"),
                        "bill_id": r.get("bill_id"),
                        "bill_number": r.get("bill_number")})
        if r.get("project_id"):
            project_ids.append(r["project_id"])
        remaining -= pay

    # Preserve the Vendor→Project relationship on the JE. If a single project
    # accounts for the settled commission, tag the JE with it (so it shows up on
    # project profitability). Multiple projects → we set `project_ids` on the
    # JE instead to keep every project link (used by commission dashboard).
    single_project = project_ids[0] if project_ids and len(set(project_ids)) == 1 else None

    # Post the journal through the central engine so audit + balanced-check +
    # reversal flow works exactly like every other JE.
    from routes.accounting import _post_journal
    allocated = round(float(payload.amount) - remaining, 2)
    je_lines = [{"account_id": bank["id"], "debit": float(payload.amount), "credit": 0.0,
                 "description": f"Commission received from {vendor.get('name')}"}]
    if allocated > 0:
        je_lines.append({"account_id": inc["id"], "debit": 0.0, "credit": allocated,
                         "description": income_label})
    if remaining > 0.001:
        from routes.accounting import _seed_coa_if_empty
        await _seed_coa_if_empty()
        advance = await sdb.accounts.find_one(
            {"name": "Commission Advances", "type": "liability", "active": {"$ne": False}},
            {"_id": 0, "id": 1})
        if not advance:
            raise HTTPException(status_code=500, detail="Commission Advances account missing")
        je_lines.append({"account_id": advance["id"], "debit": 0.0,
                         "credit": round(remaining, 2),
                         "description": f"Unallocated commission advance from {vendor.get('name')}"})
    settlement_id = (f"vcpay_{hashlib.sha256(request_key.encode('utf-8')).hexdigest()[:24]}"
                     if request_key else new_id("vcpay_"))
    je = await _post_journal(
        user, payload.received_date,
        f"Vendor commission – {vendor.get('name')}",
        je_lines, reference=payload.reference,
        project_id=single_project,
        vendor_id=vendor_id,
        source="commission_income",
        source_id=settlement_id,
    )
    # If commission covers multiple projects, retain all links for reporting.
    if project_ids and not single_project:
        await sdb.journal_entries.update_one(
            {"id": je["id"]},
            {"$set": {"project_ids": list(set(project_ids))}},
        )
    je_id = je["id"]

    # Persist a payment record + update settled commission rows
    settlement_doc = {
        "id": settlement_id,
        "vendor_id": vendor_id,
        "vendor_name": vendor.get("name"),
        "amount": float(payload.amount),
        "received_date": payload.received_date,
        "payment_method": payload.payment_method,
        "bank_account_id": payload.bank_account_id,
        "reference": payload.reference,
        "notes": payload.notes,
        "journal_entry_id": je_id,
        "status": "received",
        "commissions": settled,
        "project_ids": list(set(project_ids)) if project_ids else [],
        "unallocated": round(remaining, 2),
        "created_at": iso_now(),
        "created_by": user["user_id"],
    }
    if idem:
        settlement_doc["client_request_id"] = idem
        settlement_doc["request_key"] = request_key
    try:
        await sdb.commission_settlements.insert_one(settlement_doc)
    except Exception:
        # A lost database acknowledgement can raise even after persistence.
        # Only remove the technical journal when the settlement truly is absent.
        persisted = await sdb.commission_settlements.find_one(
            {"id": settlement_id}, {"_id": 0})
        if not persisted:
            await sdb.journal_entries.delete_one({"id": je_id})
            raise
        settlement_doc = persisted
    await _refresh_commission_allocations([s["id"] for s in settled])
    return {"ok": True, "settlement_id": settlement_id, "journal_entry_id": je_id,
            "settled": settled, "unallocated": round(remaining, 2)}


@router.delete("/commission-settlements/{settlement_id}")
async def delete_commission_settlement(settlement_id: str, request: Request,
                                       session_token: Optional[str] = Cookie(default=None),
                                       authorization: Optional[str] = Header(default=None)):
    """Remove a mistaken commission receipt without corrupting the books.

    The cash receipt is posted accounting history, so the user-facing Delete
    action creates a balanced reversal, hides both sides from ordinary books,
    preserves the audit trail, and rebuilds every affected commission balance.
    """
    user = await require_user(request, session_token, authorization)
    _require(user, "finance.delete")
    async with doc_lock(sdb.commission_settlements, settlement_id):
        return await _reverse_commission_settlement_locked(user, settlement_id)


async def _reverse_commission_settlement_locked(user: dict, settlement_id: str) -> dict:
    settlement = await sdb.commission_settlements.find_one(
        {"id": settlement_id}, {"_id": 0})
    if not settlement:
        raise HTTPException(status_code=404, detail="Commission receipt not found")
    if settlement.get("status") in ("cancelled", "reversed"):
        return {"ok": True, "already_reversed": True,
                "reversal_je_id": settlement.get("reversal_je_id")}

    journal_id = settlement.get("journal_entry_id")
    if not journal_id:
        raise HTTPException(
            status_code=409,
            detail="Commission receipt has no linked journal entry; reconcile it before deletion",
        )
    journal = await sdb.journal_entries.find_one({"id": journal_id}, {"_id": 0})
    if not journal:
        raise HTTPException(
            status_code=409,
            detail="Linked journal entry is missing; reconcile it before deletion",
        )

    reversal_id = journal.get("reversal_je_id")
    if not journal.get("reversed"):
        from routes.accounting import _reverse_journal_entry
        reversal = await _reverse_journal_entry(
            user, journal, action="delete",
            reversal_date=settlement.get("received_date"),
            hide_from_books=True,
        )
        reversal_id = reversal["id"]

    changed_at = iso_now()
    await sdb.commission_settlements.update_one(
        {"id": settlement_id},
        {"$set": {
            "status": "reversed",
            "reversal_je_id": reversal_id,
            "reversed_at": changed_at,
            "reversed_by": user["user_id"],
        }},
    )
    commission_ids = [
        row.get("id") for row in settlement.get("commissions") or [] if row.get("id")
    ]
    await _refresh_commission_allocations(commission_ids)
    await audit(
        user, "vendor_commission_receipt.delete", target=settlement_id,
        target_type="commission_settlement",
        meta={"journal_entry_id": journal_id, "reversal_je_id": reversal_id,
              "amount": settlement.get("amount")},
    )
    return {"ok": True, "deleted": True, "reversal_je_id": reversal_id}


# ---------- Cross-vendor commission dashboard ----------
@router.get("/commissions/dashboard")
async def commissions_dashboard(request: Request,
                                session_token: Optional[str] = Cookie(default=None),
                                authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    _require(user, "finance.read")
    from datetime import datetime, timezone
    today = business_today()
    month_start = f"{today.year:04d}-{today.month:02d}-01"

    totals = {"total_earned": 0.0, "total_received": 0.0,
              "allocated_received": 0.0, "pending": 0.0,
              "this_month": 0.0, "this_month_received": 0.0}
    by_vendor: dict = {}
    by_project: dict = {}
    rows = await sdb.vendor_commissions.find({"status": {"$nin": ["cancelled", "reversed"]}}, {"_id": 0}) \
                                      .to_list(20000)
    for r in rows:
        earned = float(r.get("earned_amount")
                       if r.get("earned_amount") is not None
                       else r.get("amount") or 0)
        totals["total_earned"] += earned
        if (r.get("bill_date") or "") >= month_start:
            totals["this_month"] += earned
        vid = r.get("vendor_id")
        by_vendor.setdefault(vid, {"vendor_id": vid, "vendor_name": r.get("vendor_name"),
                                    "earned": 0.0, "received": 0.0})
        by_vendor[vid]["earned"] += earned
        pid = r.get("project_id")
        if pid:
            by_project.setdefault(pid, {"project_id": pid, "earned": 0.0, "received": 0.0})
            by_project[pid]["earned"] += earned

    receipts, settlement_journal_ids = await _active_commission_settlements({})
    totals["unallocated_received"] = 0.0
    for receipt in receipts:
        received = float(receipt.get("amount") or 0)
        totals["total_received"] += received
        totals["unallocated_received"] += float(receipt.get("unallocated") or 0)
        if (receipt.get("received_date") or "") >= month_start:
            totals["this_month_received"] += received
        vid = receipt.get("vendor_id")
        by_vendor.setdefault(vid, {
            "vendor_id": vid,
            "vendor_name": receipt.get("vendor_name"),
            "earned": 0.0,
            "received": 0.0,
        })
        by_vendor[vid]["received"] += received
        for allocation in receipt.get("commissions") or []:
            totals["allocated_received"] += float(allocation.get("applied") or 0)
            pid = allocation.get("project_id")
            if not pid:
                continue
            by_project.setdefault(pid, {
                "project_id": pid, "earned": 0.0, "received": 0.0,
            })
            by_project[pid]["received"] += float(allocation.get("applied") or 0)

    # Preserve historical commission rows created before settlement records.
    for r in rows:
        if r.get("journal_entry_id") in settlement_journal_ids:
            continue
        legacy_received = float(r.get("received_amount") or 0)
        if legacy_received <= 0:
            continue
        totals["total_received"] += legacy_received
        totals["allocated_received"] += legacy_received
        vid = r.get("vendor_id")
        by_vendor.setdefault(vid, {"vendor_id": vid, "vendor_name": r.get("vendor_name"),
                                    "earned": 0.0, "received": 0.0})
        by_vendor[vid]["received"] += legacy_received
        pid = r.get("project_id")
        if pid:
            by_project.setdefault(pid, {"project_id": pid, "earned": 0.0, "received": 0.0})
            by_project[pid]["received"] += legacy_received

    top_vendors = sorted(
        by_vendor.values(),
        key=lambda x: -(float(x["earned"]) + float(x["received"])),
    )[:10]
    # Enrich projects with names
    project_ids = list(by_project.keys())
    proj_names = {}
    async for p in sdb.projects.find({"id": {"$in": project_ids}}, {"_id": 0, "id": 1, "name": 1}):
        proj_names[p["id"]] = p.get("name")
    project_rows = [
        {**v, "project_name": proj_names.get(v["project_id"], "—"),
         "earned": round(v["earned"], 2), "received": round(v["received"], 2)}
        for v in by_project.values()
    ]
    project_rows.sort(key=lambda x: -x["earned"])

    for k in list(totals.keys()):
        totals[k] = round(totals[k], 2)
    totals["pending"] = round(
        max(0.0, totals["total_earned"] - totals["allocated_received"]), 2)

    return {"totals": totals,
            "top_vendors": [{"vendor_id": v["vendor_id"],
                             "vendor_name": v["vendor_name"],
                             "earned": round(v["earned"], 2),
                             "received": round(v["received"], 2)} for v in top_vendors],
            "by_project": project_rows[:20]}


# ---------- Filterable commission report + CSV ----------
@router.get("/commissions/report")
async def commissions_report(request: Request,
                             vendor_id: Optional[str] = None,
                             project_id: Optional[str] = None,
                             status: Optional[str] = None,
                             from_date: Optional[str] = None,
                             to_date: Optional[str] = None,
                             session_token: Optional[str] = Cookie(default=None),
                             authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    _require(user, "finance.read")
    q: dict = {}
    if vendor_id:  q["vendor_id"] = vendor_id
    if project_id: q["project_id"] = project_id
    if status:     q["status"] = status
    if from_date or to_date:
        d = {}
        if from_date: d["$gte"] = from_date
        if to_date:   d["$lte"] = to_date
        q["bill_date"] = d
    rows = await sdb.vendor_commissions.find(q, {"_id": 0}) \
                                      .sort("bill_date", -1).to_list(5000)
    totals = {
        "earned":   round(sum(float(r.get("earned_amount")
                                    if r.get("earned_amount") is not None
                                    else r.get("amount") or 0)
                              for r in rows if r.get("status") not in ("cancelled", "reversed")), 2),
        "received": round(sum(float(r.get("received_amount") or 0)
                              for r in rows if r.get("status") not in ("cancelled", "reversed")), 2),
        "count":    len(rows),
    }
    totals["pending"] = round(totals["earned"] - totals["received"], 2)
    return {"filters": {"vendor_id": vendor_id, "project_id": project_id,
                        "status": status, "from_date": from_date, "to_date": to_date},
            "totals": totals, "rows": rows}


@router.get("/commissions/report.csv")
async def commissions_report_csv(request: Request,
                                 vendor_id: Optional[str] = None,
                                 project_id: Optional[str] = None,
                                 status: Optional[str] = None,
                                 from_date: Optional[str] = None,
                                 to_date: Optional[str] = None,
                                 session_token: Optional[str] = Cookie(default=None),
                                 authorization: Optional[str] = Header(default=None)):
    from fastapi.responses import Response as FastAPIResponse
    import csv, io
    data = await commissions_report(request, vendor_id, project_id, status,
                                    from_date, to_date, session_token, authorization)
    buf = io.StringIO()
    from core.csv_safe import SafeWriter
    w = SafeWriter(buf)
    w.writerow(["bill_date", "vendor", "bill_number", "project_id", "purchase_amount",
                "commission_type", "amount", "received_amount", "status",
                "received_date", "reference"])
    for r in data["rows"]:
        w.writerow([r.get("bill_date"), r.get("vendor_name"), r.get("bill_number"),
                    r.get("project_id"), r.get("purchase_amount"),
                    r.get("commission_type"), r.get("amount"),
                    r.get("received_amount") or 0, r.get("status"),
                    r.get("received_date"), r.get("reference")])
    return FastAPIResponse(
        content=buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="commissions.csv"'},
    )


# ---------- Meta helper for UI ----------
@router.get("/vendors/commissions/meta")
async def commission_meta(request: Request,
                          session_token: Optional[str] = Cookie(default=None),
                          authorization: Optional[str] = Header(default=None)):
    await require_user(request, session_token, authorization)
    return {"types": COMMISSION_TYPES, "statuses": COMMISSION_STATUSES}
