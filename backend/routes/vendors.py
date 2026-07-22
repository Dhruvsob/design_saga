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
* Every new document carries an optional `org_id` – multi-tenant ready
  (not enforced).

RBAC
----
* `vendors.read`   – Admin, Director, ProjectManager, Designer, Accountant, Employee
* `vendors.create` – Admin, Director, ProjectManager, Accountant
* `vendors.update` – Admin, Director, ProjectManager, Accountant
* `vendors.delete` – Admin, Director
* `finance.create` – required for bills & payments (Admin, Director, Accountant)
"""
from fastapi import APIRouter, HTTPException, Request, Cookie, Header
from typing import Optional, List
from datetime import datetime, timezone

from core.db import db
from core.helpers import iso_now, new_id
from core.deps import require_user
from core.rbac import has_permission
from models.accounting import VendorIn
from models.vendor import (
    VendorUpdate, VendorBillIn, VendorBillUpdate, VendorPaymentIn,
    VendorRatingIn, VendorDocumentIn,
    CommissionConfig, CommissionReceiveIn,
    AGENCY_TYPES, VENDOR_BILL_STATUSES, COMMISSION_TYPES, COMMISSION_STATUSES,
)


router = APIRouter()


# ==================================================
# helpers
# ==================================================
def _require(user: dict, perm: str):
    if not has_permission(user, perm):
        raise HTTPException(status_code=403, detail=f"Missing permission: {perm}")


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


async def _paid_against_bill(bill_id: str) -> float:
    """Sum of all vendor payments settled against this bill."""
    total = 0.0
    async for pmt in db.vendor_payments.find({"bill_ids": bill_id}, {"_id": 0}):
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
    bill = await db.vendor_bills.find_one({"id": bill_id}, {"_id": 0})
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
                if datetime.fromisoformat(due).date() < datetime.now(timezone.utc).date():
                    new_status = "overdue" if new_status == "received" else new_status
            except Exception:
                pass
    await db.vendor_bills.update_one(
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
    if active is not None: query["active"] = active
    if q:
        rx = {"$regex": q, "$options": "i"}
        query["$or"] = [{"name": rx}, {"company": rx}, {"phone": rx},
                        {"email": rx}, {"gstin": rx}, {"contact_person": rx}]

    rows = await db.vendors_acc.find(query, {"_id": 0}).sort("name", 1).to_list(1000)

    # Filter by project: only vendors that have journal_entries or bills against this project
    if project_id:
        involved = set()
        async for e in db.journal_entries.find({"project_id": project_id,
                                                "vendor_id": {"$ne": None}},
                                               {"_id": 0, "vendor_id": 1}):
            if e.get("vendor_id"): involved.add(e["vendor_id"])
        async for b in db.vendor_bills.find({"project_id": project_id},
                                            {"_id": 0, "vendor_id": 1}):
            involved.add(b["vendor_id"])
        rows = [r for r in rows if r["id"] in involved]

    # Attach lightweight rollups (outstanding + rating) for the list view
    for v in rows:
        outstanding = 0.0
        async for b in db.vendor_bills.find(
            {"vendor_id": v["id"], "status": {"$in": ["received", "partially_paid", "overdue"]}},
            {"_id": 0, "outstanding": 1, "total": 1, "paid_amount": 1},
        ):
            outstanding += float(b.get("outstanding") or (b.get("total", 0) - b.get("paid_amount", 0)))
        v["outstanding"] = round(outstanding, 2)
    return rows


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
    doc["id"] = new_id("vnd_")
    doc["created_at"] = iso_now()
    doc["created_by"] = user["user_id"]
    doc["documents"] = []
    doc["rating"] = float(doc.get("rating") or 0)
    doc.setdefault("active", True)
    await db.vendors_acc.insert_one(dict(doc))
    return await db.vendors_acc.find_one({"id": doc["id"]}, {"_id": 0})


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
    v = await db.vendors_acc.find_one({"id": vendor_id}, {"_id": 0})
    if not v:
        raise HTTPException(status_code=404, detail="Vendor not found")

    # Aggregate detail: bills, payments, assigned tasks, projects, performance.
    bills = await db.vendor_bills.find({"vendor_id": vendor_id}, {"_id": 0}).sort("bill_date", -1).to_list(500)
    payments = await db.vendor_payments.find({"vendor_id": vendor_id}, {"_id": 0}).sort("payment_date", -1).to_list(500)

    outstanding = sum(float(b.get("outstanding") or 0)
                      for b in bills if b.get("status") in ("received", "partially_paid", "overdue"))
    total_billed = sum(float(b.get("total") or 0) for b in bills if b.get("status") != "cancelled")
    total_paid = sum(float(p.get("amount") or 0) for p in payments)

    # Assigned tasks / projects (backward compat: some tasks store vendor_id, others vendor_contact.vendor_name)
    task_query = {"$or": [
        {"vendor_id": vendor_id},
        {"vendor_contact.vendor_name": v.get("name")},
    ]}
    tasks = await db.tasks.find(task_query, {"_id": 0}).sort("created_at", -1).to_list(500)

    project_ids = list({t.get("project_id") for t in tasks if t.get("project_id")})
    # Also pull projects that appear in bills or journal entries
    async for b in db.vendor_bills.find({"vendor_id": vendor_id, "project_id": {"$ne": None}},
                                        {"_id": 0, "project_id": 1}):
        if b.get("project_id"): project_ids.append(b["project_id"])
    async for e in db.journal_entries.find({"vendor_id": vendor_id, "project_id": {"$ne": None}},
                                           {"_id": 0, "project_id": 1}):
        if e.get("project_id"): project_ids.append(e["project_id"])
    project_ids = list(set(project_ids))
    projects = await db.projects.find({"id": {"$in": project_ids}},
                                      {"_id": 0, "id": 1, "name": 1, "stage": 1,
                                       "client_name": 1}).to_list(200)

    v["summary"] = {
        "total_billed": round(total_billed, 2),
        "total_paid": round(total_paid, 2),
        "outstanding": round(outstanding, 2),
        "open_bills": sum(1 for b in bills if b.get("status") in ("received", "partially_paid", "overdue")),
        "task_count": len(tasks),
        "project_count": len(projects),
    }
    v["bills"] = bills
    v["payments"] = payments
    v["tasks"] = tasks
    v["projects"] = projects
    return v


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
    patch["updated_at"] = iso_now()
    patch["updated_by"] = user["user_id"]
    res = await db.vendors_acc.update_one({"id": vendor_id}, {"$set": patch})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Vendor not found")
    return await db.vendors_acc.find_one({"id": vendor_id}, {"_id": 0})


@router.delete("/vendors/{vendor_id}")
async def delete_vendor(vendor_id: str, request: Request,
                        session_token: Optional[str] = Cookie(default=None),
                        authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    _require(user, "vendors.delete")
    # Soft delete – preserve accounting audit trail.
    res = await db.vendors_acc.update_one(
        {"id": vendor_id},
        {"$set": {"active": False, "deleted_at": iso_now(), "deleted_by": user["user_id"]}}
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Vendor not found")
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
    v = await db.vendors_acc.find_one({"id": vendor_id}, {"_id": 0})
    if not v:
        raise HTTPException(status_code=404, detail="Vendor not found")
    doc = payload.model_dump()
    doc["id"] = new_id("vdoc_")
    doc["uploaded_at"] = iso_now()
    doc["uploaded_by"] = user["user_id"]
    await db.vendors_acc.update_one({"id": vendor_id}, {"$push": {"documents": doc}})
    return doc


@router.delete("/vendors/{vendor_id}/documents/{doc_id}")
async def remove_vendor_document(vendor_id: str, doc_id: str, request: Request,
                                 session_token: Optional[str] = Cookie(default=None),
                                 authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    _require(user, "vendors.update")
    await db.vendors_acc.update_one({"id": vendor_id},
                                    {"$pull": {"documents": {"id": doc_id}}})
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
    v = await db.vendors_acc.find_one({"id": vendor_id}, {"_id": 0})
    if not v:
        raise HTTPException(status_code=404, detail="Vendor not found")

    doc = payload.model_dump()
    doc["id"] = new_id("vrat_")
    doc["vendor_id"] = vendor_id
    doc["rated_by"] = user["user_id"]
    doc["rated_by_name"] = user.get("name")
    doc["created_at"] = iso_now()
    # composite = mean of provided dimensions
    dims = [doc.get(k) for k in ("quality", "timeliness", "cost", "communication")
            if doc.get(k) is not None]
    doc["overall"] = round(sum(dims) / len(dims), 2) if dims else None
    await db.vendor_ratings.insert_one(dict(doc))

    # Refresh aggregate rating on vendor master.
    agg = []
    async for r in db.vendor_ratings.find({"vendor_id": vendor_id}, {"_id": 0, "overall": 1}):
        if r.get("overall") is not None:
            agg.append(float(r["overall"]))
    new_avg = round(sum(agg) / len(agg), 2) if agg else 0.0
    await db.vendors_acc.update_one({"id": vendor_id},
                                    {"$set": {"rating": new_avg,
                                              "rating_count": len(agg)}})
    return doc


@router.get("/vendors/{vendor_id}/ratings")
async def list_vendor_ratings(vendor_id: str, request: Request,
                              session_token: Optional[str] = Cookie(default=None),
                              authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    _require(user, "vendors.read")
    return await db.vendor_ratings.find({"vendor_id": vendor_id}, {"_id": 0}) \
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

    vendor = await db.vendors_acc.find_one({"id": payload.vendor_id}, {"_id": 0})
    if not vendor:
        raise HTTPException(status_code=404, detail="Vendor not found")

    doc = payload.model_dump()
    doc["id"] = new_id("vbill_")
    # Auto-generate a sequential bill number if the vendor didn't provide one.
    if not doc.get("bill_number"):
        count = await db.vendor_bills.count_documents({})
        doc["bill_number"] = f"VB-{1000 + count + 1}"
    doc["items"] = [i if isinstance(i, dict) else i.model_dump()
                    for i in (doc.get("items") or [])]
    _bill_total(doc)
    doc["paid_amount"] = 0.0
    doc["outstanding"] = doc["total"]
    doc.setdefault("status", "received")
    doc["vendor_name"] = vendor.get("name")
    doc["created_at"] = iso_now()
    doc["created_by"] = user["user_id"]
    await db.vendor_bills.insert_one(dict(doc))
    await _refresh_bill_status(doc["id"])
    # Auto-compute commission for this bill (if vendor has commission enabled).
    await _compute_commission_for_bill(doc["id"])
    return await db.vendor_bills.find_one({"id": doc["id"]}, {"_id": 0})


@router.get("/vendor-bills")
async def list_vendor_bills(request: Request,
                            vendor_id: Optional[str] = None,
                            project_id: Optional[str] = None,
                            status: Optional[str] = None,
                            session_token: Optional[str] = Cookie(default=None),
                            authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    _require(user, "vendors.read")
    query: dict = {}
    if vendor_id:  query["vendor_id"] = vendor_id
    if project_id: query["project_id"] = project_id
    if status:     query["status"] = status
    rows = await db.vendor_bills.find(query, {"_id": 0}).sort("bill_date", -1).to_list(1000)
    return rows


@router.get("/vendor-bills/{bill_id}")
async def get_vendor_bill(bill_id: str, request: Request,
                          session_token: Optional[str] = Cookie(default=None),
                          authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    _require(user, "vendors.read")
    bill = await db.vendor_bills.find_one({"id": bill_id}, {"_id": 0})
    if not bill:
        raise HTTPException(status_code=404, detail="Bill not found")
    # Attach payments that touch this bill
    bill["payments"] = await db.vendor_payments.find(
        {"bill_ids": bill_id}, {"_id": 0}
    ).sort("payment_date", -1).to_list(200)
    return bill


@router.patch("/vendor-bills/{bill_id}")
async def update_vendor_bill(bill_id: str, payload: VendorBillUpdate, request: Request,
                             session_token: Optional[str] = Cookie(default=None),
                             authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    _require(user, "finance.create")
    bill = await db.vendor_bills.find_one({"id": bill_id}, {"_id": 0})
    if not bill:
        raise HTTPException(status_code=404, detail="Bill not found")
    patch = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not patch:
        raise HTTPException(status_code=400, detail="No fields to update")
    if patch.get("status") and patch["status"] not in VENDOR_BILL_STATUSES:
        raise HTTPException(status_code=400,
                            detail=f"status must be one of {VENDOR_BILL_STATUSES}")
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
    patch["updated_at"] = iso_now()
    await db.vendor_bills.update_one({"id": bill_id}, {"$set": patch})
    await _refresh_bill_status(bill_id)
    # If financials changed, re-compute commission for this bill.
    if "items" in patch or "tax_rate" in patch or "tds_rate" in patch or "status" in patch:
        await _compute_commission_for_bill(bill_id)
    return await db.vendor_bills.find_one({"id": bill_id}, {"_id": 0})


@router.delete("/vendor-bills/{bill_id}")
async def delete_vendor_bill(bill_id: str, request: Request,
                             session_token: Optional[str] = Cookie(default=None),
                             authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    _require(user, "finance.create")
    # Refuse to hard-delete a bill that has payments — force cancel instead.
    paid = await _paid_against_bill(bill_id)
    if paid > 0:
        await db.vendor_bills.update_one({"id": bill_id}, {"$set": {"status": "cancelled",
                                                                    "cancelled_at": iso_now()}})
        return {"ok": True, "cancelled": True}
    await db.vendor_bills.delete_one({"id": bill_id})
    return {"ok": True, "deleted": True}


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

    vendor = await db.vendors_acc.find_one({"id": payload.vendor_id}, {"_id": 0})
    if not vendor:
        raise HTTPException(status_code=404, detail="Vendor not found")
    bank_acc = await db.accounts.find_one({"id": payload.paid_from_account_id}, {"_id": 0})
    if not bank_acc:
        raise HTTPException(status_code=404, detail="Bank/cash account not found")
    ap_acc = await db.accounts.find_one({"name": "Accounts Payable"}, {"_id": 0})
    if not ap_acc:
        raise HTTPException(status_code=500, detail="Accounts Payable account missing – seed COA first")

    # Determine bill splits — FIFO over open bills for this vendor if none provided.
    remaining = float(payload.amount)
    bill_splits: dict = {}
    if payload.bill_ids:
        open_bills = []
        for bid in payload.bill_ids:
            b = await db.vendor_bills.find_one({"id": bid, "vendor_id": payload.vendor_id},
                                               {"_id": 0})
            if b and b.get("status") not in ("paid", "cancelled"):
                open_bills.append(b)
    else:
        open_bills = await db.vendor_bills.find(
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
        pay_here = min(outstanding, remaining)
        bill_splits[b["id"]] = round(pay_here, 2)
        remaining -= pay_here

    # Post the journal entry first (source of truth). Do it inline so we don't
    # need to import the private helper from routes/accounting.
    je_id = new_id("je_")
    je_lines = [
        {"account_id": ap_acc["id"], "account_name": ap_acc["name"],
         "account_type": ap_acc["type"], "debit": float(payload.amount), "credit": 0.0,
         "description": f"Payment to {vendor.get('name')}"},
        {"account_id": bank_acc["id"], "account_name": bank_acc["name"],
         "account_type": bank_acc["type"], "debit": 0.0, "credit": float(payload.amount),
         "description": f"Paid via {payload.payment_method}"},
    ]
    je_doc = {
        "id": je_id, "date": payload.payment_date,
        "narration": f"Vendor payment – {vendor.get('name')}",
        "reference": payload.reference,
        "project_id": payload.project_id,
        "vendor_id": payload.vendor_id,
        "source": "vendor_payment",
        "source_id": None,
        "total": float(payload.amount),
        "lines": je_lines,
        "created_at": iso_now(),
        "created_by": user["user_id"],
        "created_by_name": user.get("name"),
    }
    await db.journal_entries.insert_one(dict(je_doc))

    pmt = payload.model_dump()
    pmt["id"] = new_id("vpay_")
    pmt["vendor_name"] = vendor.get("name")
    pmt["bill_ids"] = list(bill_splits.keys()) if bill_splits else (payload.bill_ids or [])
    pmt["bill_splits"] = bill_splits
    pmt["unallocated"] = round(remaining, 2)         # excess advance (on-account)
    pmt["journal_entry_id"] = je_id
    pmt["created_at"] = iso_now()
    pmt["created_by"] = user["user_id"]
    await db.vendor_payments.insert_one(dict(pmt))

    # Update bill statuses
    for bid in bill_splits.keys():
        await _refresh_bill_status(bid)

    return await db.vendor_payments.find_one({"id": pmt["id"]}, {"_id": 0})


@router.get("/vendor-payments")
async def list_vendor_payments(request: Request,
                               vendor_id: Optional[str] = None,
                               project_id: Optional[str] = None,
                               session_token: Optional[str] = Cookie(default=None),
                               authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    _require(user, "vendors.read")
    query: dict = {}
    if vendor_id:  query["vendor_id"] = vendor_id
    if project_id: query["project_id"] = project_id
    return await db.vendor_payments.find(query, {"_id": 0}).sort("payment_date", -1).to_list(1000)


@router.delete("/vendor-payments/{pmt_id}")
async def delete_vendor_payment(pmt_id: str, request: Request,
                                session_token: Optional[str] = Cookie(default=None),
                                authorization: Optional[str] = Header(default=None)):
    """Reverse a vendor payment: soft-cancel the payment, delete the journal
    entry, and refresh linked bill statuses."""
    user = await require_user(request, session_token, authorization)
    _require(user, "finance.create")
    pmt = await db.vendor_payments.find_one({"id": pmt_id}, {"_id": 0})
    if not pmt:
        raise HTTPException(status_code=404, detail="Payment not found")
    if pmt.get("journal_entry_id"):
        await db.journal_entries.delete_one({"id": pmt["journal_entry_id"]})
    await db.vendor_payments.delete_one({"id": pmt_id})
    for bid in (pmt.get("bill_ids") or []):
        await _refresh_bill_status(bid)
    return {"ok": True}


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
    _require(user, "vendors.read")
    vendor = await db.vendors_acc.find_one({"id": vendor_id}, {"_id": 0})
    if not vendor:
        raise HTTPException(status_code=404, detail="Vendor not found")

    events: list = []
    async for b in db.vendor_bills.find({"vendor_id": vendor_id,
                                         "status": {"$ne": "cancelled"}}, {"_id": 0}):
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
    async for p in db.vendor_payments.find({"vendor_id": vendor_id}, {"_id": 0}):
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

    if from_date: events = [e for e in events if (e.get("date") or "") >= from_date]
    if to_date:   events = [e for e in events if (e.get("date") or "") <= to_date]
    events.sort(key=lambda e: (e.get("date") or "", 0 if e["type"] == "bill" else 1))

    running = 0.0
    for e in events:
        # Outstanding-payable convention: bills push balance UP (owed to vendor),
        # payments push it DOWN.
        running += e["credit"] - e["debit"]
        e["balance"] = round(running, 2)

    total_billed = sum(e["credit"] for e in events)
    total_paid = sum(e["debit"] for e in events)
    return {
        "vendor": vendor,
        "from_date": from_date, "to_date": to_date,
        "total_billed": round(total_billed, 2),
        "total_paid": round(total_paid, 2),
        "outstanding": round(total_billed - total_paid, 2),
        "entries": events,
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
    vendor = await db.vendors_acc.find_one({"id": vendor_id}, {"_id": 0})
    if not vendor:
        raise HTTPException(status_code=404, detail="Vendor not found")

    # Task-based completion
    task_query = {"$or": [{"vendor_id": vendor_id},
                          {"vendor_contact.vendor_name": vendor.get("name")}]}
    tasks = await db.tasks.find(task_query, {"_id": 0}).to_list(500)
    total_tasks = len(tasks)
    done_tasks = sum(1 for t in tasks if t.get("status") == "done"
                     or t.get("status_detail") == "Completed")
    open_tasks = total_tasks - done_tasks
    completion_rate = round((done_tasks / total_tasks) * 100, 1) if total_tasks else 0.0

    # Delay proxy: tasks past due & not done
    today = datetime.now(timezone.utc).date().isoformat()
    delayed = sum(1 for t in tasks
                  if (t.get("due_date") or "") and t.get("due_date") < today
                  and t.get("status") != "done")
    delay_rate = round((delayed / total_tasks) * 100, 1) if total_tasks else 0.0

    # Payment reliability (vendor's perspective is inverted: how well WE pay them)
    total_billed = 0.0
    outstanding = 0.0
    async for b in db.vendor_bills.find({"vendor_id": vendor_id, "status": {"$ne": "cancelled"}},
                                        {"_id": 0}):
        total_billed += float(b.get("total") or 0)
        if b.get("status") in ("received", "partially_paid", "overdue"):
            outstanding += float(b.get("outstanding") or 0)

    # Rating-based
    ratings = await db.vendor_ratings.find({"vendor_id": vendor_id}, {"_id": 0}).to_list(500)
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
    )

    return {
        "vendor_id": vendor_id,
        "vendor_name": vendor.get("name"),
        "tasks": {"total": total_tasks, "done": done_tasks, "open": open_tasks,
                  "delayed": delayed,
                  "completion_rate": completion_rate, "delay_rate": delay_rate},
        "ratings": {"count": len(ratings), "quality": quality, "timeliness": timeliness,
                    "cost": cost, "communication": communication,
                    "overall": vendor.get("rating", 0.0)},
        "financial": {"total_billed": round(total_billed, 2),
                      "outstanding": round(outstanding, 2),
                      "payment_reliability": pay_pct},
        "performance_score": performance_score,
    }


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


async def _compute_commission_for_bill(bill_id: str) -> Optional[dict]:
    """Create or update the commission row for a bill.
    Idempotent — safe to run on every bill update.
    Cancelled bills → cancel the commission (keep row for audit)."""
    bill = await db.vendor_bills.find_one({"id": bill_id}, {"_id": 0})
    if not bill:
        return None
    vendor = await db.vendors_acc.find_one({"id": bill["vendor_id"]}, {"_id": 0})
    if not vendor:
        return None
    cfg = vendor.get("commission") or {}
    existing = await db.vendor_commissions.find_one({"bill_id": bill_id}, {"_id": 0})

    # Effective-date filter
    b_date = bill.get("bill_date") or ""
    if cfg.get("effective_from") and b_date and b_date < cfg["effective_from"]:
        cfg = {**cfg, "applicable": False}
    if cfg.get("effective_to") and b_date and b_date > cfg["effective_to"]:
        cfg = {**cfg, "applicable": False}

    base = _bill_purchase_base(bill)
    amount = _calc_commission_amount(cfg, base)

    # Bill cancelled → cancel commission
    if bill.get("status") == "cancelled":
        if existing:
            await db.vendor_commissions.update_one(
                {"id": existing["id"]}, {"$set": {"status": "cancelled",
                                                   "amount": 0.0,
                                                   "updated_at": iso_now()}}
            )
        return None

    # No commission earned → drop existing pending row (never delete received rows)
    if amount <= 0.001:
        if existing and existing.get("status") in ("pending", "invoiced"):
            await db.vendor_commissions.delete_one({"id": existing["id"]})
        return None

    doc = {
        "vendor_id": vendor["id"],
        "vendor_name": vendor.get("name"),
        "bill_id": bill_id,
        "bill_number": bill.get("bill_number"),
        "bill_date": bill.get("bill_date"),
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
        "updated_at": iso_now(),
    }
    if existing:
        # Preserve received/invoiced status if any; only update pending rows numerically.
        if existing.get("status") == "received":
            # Already booked as income. Do not overwrite; log a discrepancy note.
            if abs(float(existing.get("amount") or 0) - amount) > 0.01:
                await db.vendor_commissions.update_one(
                    {"id": existing["id"]},
                    {"$set": {"recompute_variance": round(amount - float(existing["amount"]), 2),
                              "updated_at": iso_now()}}
                )
            return existing
        await db.vendor_commissions.update_one(
            {"id": existing["id"]}, {"$set": doc}
        )
        return await db.vendor_commissions.find_one({"id": existing["id"]}, {"_id": 0})
    doc["id"] = new_id("vcom_")
    doc["status"] = "pending"
    doc["created_at"] = iso_now()
    await db.vendor_commissions.insert_one(dict(doc))
    return doc


# ---------- Update vendor commission config ----------
@router.patch("/vendors/{vendor_id}/commercial")
async def update_vendor_commercial(vendor_id: str, payload: CommissionConfig, request: Request,
                                   session_token: Optional[str] = Cookie(default=None),
                                   authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    _require(user, "vendors.update")
    if payload.type not in COMMISSION_TYPES:
        raise HTTPException(status_code=400,
                            detail=f"commission type must be one of {COMMISSION_TYPES}")
    cfg = payload.model_dump()
    res = await db.vendors_acc.update_one(
        {"id": vendor_id},
        {"$set": {"commission": cfg,
                  "commercial_updated_at": iso_now(),
                  "commercial_updated_by": user["user_id"]}}
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Vendor not found")
    # Recompute commissions for all bills of this vendor (idempotent).
    updated = 0
    async for b in db.vendor_bills.find({"vendor_id": vendor_id}, {"_id": 0, "id": 1}):
        await _compute_commission_for_bill(b["id"])
        updated += 1
    return {"ok": True, "recomputed_bills": updated,
            "vendor": await db.vendors_acc.find_one({"id": vendor_id}, {"_id": 0})}


# ---------- Get commission config (returns full vendor incl. computed rollup) ----------
@router.get("/vendors/{vendor_id}/commercial")
async def get_vendor_commercial(vendor_id: str, request: Request,
                                session_token: Optional[str] = Cookie(default=None),
                                authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    _require(user, "vendors.read")
    vendor = await db.vendors_acc.find_one({"id": vendor_id}, {"_id": 0})
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
    _require(user, "vendors.read")
    q: dict = {"vendor_id": vendor_id}
    if status:
        q["status"] = status
    rows = await db.vendor_commissions.find(q, {"_id": 0}) \
                                      .sort("bill_date", -1).to_list(2000)
    return rows


# ---------- Vendor commission ledger (running totals) ----------
@router.get("/vendors/{vendor_id}/commission-ledger")
async def vendor_commission_ledger(vendor_id: str, request: Request,
                                   session_token: Optional[str] = Cookie(default=None),
                                   authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    _require(user, "vendors.read")
    vendor = await db.vendors_acc.find_one({"id": vendor_id}, {"_id": 0})
    if not vendor:
        raise HTTPException(status_code=404, detail="Vendor not found")

    rows = await db.vendor_commissions.find({"vendor_id": vendor_id}, {"_id": 0}) \
                                      .sort("bill_date", 1).to_list(5000)
    total_purchase = 0.0
    total_earned = 0.0
    total_received = 0.0
    for r in rows:
        if r.get("status") == "cancelled":
            continue
        total_purchase += float(r.get("purchase_amount") or 0)
        total_earned += float(r.get("amount") or 0)
        if r.get("status") == "received":
            total_received += float(r.get("received_amount") or r.get("amount") or 0)

    return {
        "vendor_id": vendor_id,
        "vendor_name": vendor.get("name"),
        "config": vendor.get("commission") or {"applicable": False},
        "totals": {
            "total_purchase": round(total_purchase, 2),
            "total_earned": round(total_earned, 2),
            "total_received": round(total_received, 2),
            "pending": round(total_earned - total_received, 2),
        },
        "entries": rows,
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

    vendor = await db.vendors_acc.find_one({"id": vendor_id}, {"_id": 0})
    if not vendor:
        raise HTTPException(status_code=404, detail="Vendor not found")
    bank = await db.accounts.find_one({"id": payload.bank_account_id}, {"_id": 0})
    if not bank:
        raise HTTPException(status_code=404, detail="Bank/cash account not found")

    income_label = ((vendor.get("commission") or {}).get("income_label")
                    or "Vendor Commission Income")
    inc = await db.accounts.find_one({"name": income_label}, {"_id": 0})
    if not inc:
        raise HTTPException(status_code=500,
                            detail=f"Income account '{income_label}' missing – seed COA first")

    # Pick rows to settle — FIFO across pending/invoiced if none provided.
    if payload.commission_ids:
        rows = []
        for cid in payload.commission_ids:
            r = await db.vendor_commissions.find_one({"id": cid, "vendor_id": vendor_id},
                                                    {"_id": 0})
            if r and r.get("status") in ("pending", "invoiced"):
                rows.append(r)
    else:
        rows = await db.vendor_commissions.find(
            {"vendor_id": vendor_id, "status": {"$in": ["pending", "invoiced"]}},
            {"_id": 0}
        ).sort("bill_date", 1).to_list(500)

    remaining = float(payload.amount)
    settled: list = []
    for r in rows:
        if remaining <= 0.001:
            break
        due = float(r.get("amount") or 0) - float(r.get("received_amount") or 0)
        if due <= 0.001:
            continue
        pay = min(due, remaining)
        settled.append({"id": r["id"], "applied": round(pay, 2)})
        remaining -= pay

    # Post the journal (DR Bank / CR Commission Income)
    je_id = new_id("je_")
    je_lines = [
        {"account_id": bank["id"], "account_name": bank["name"],
         "account_type": bank["type"], "debit": float(payload.amount), "credit": 0.0,
         "description": f"Commission received from {vendor.get('name')}"},
        {"account_id": inc["id"], "account_name": inc["name"],
         "account_type": inc["type"], "debit": 0.0, "credit": float(payload.amount),
         "description": income_label},
    ]
    je_doc = {
        "id": je_id, "date": payload.received_date,
        "narration": f"Vendor commission – {vendor.get('name')}",
        "reference": payload.reference,
        "vendor_id": vendor_id,
        "project_id": None,
        "source": "commission_income",
        "source_id": None,
        "total": float(payload.amount),
        "lines": je_lines,
        "created_at": iso_now(),
        "created_by": user["user_id"],
        "created_by_name": user.get("name"),
    }
    await db.journal_entries.insert_one(dict(je_doc))

    # Persist a payment record + update settled commission rows
    settlement_id = new_id("vcpay_")
    await db.commission_settlements.insert_one({
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
        "commissions": settled,
        "unallocated": round(remaining, 2),
        "created_at": iso_now(),
        "created_by": user["user_id"],
    })
    for s in settled:
        row = await db.vendor_commissions.find_one({"id": s["id"]}, {"_id": 0})
        already = float(row.get("received_amount") or 0)
        new_received = round(already + s["applied"], 2)
        status = "received" if new_received + 0.01 >= float(row.get("amount") or 0) else "invoiced"
        await db.vendor_commissions.update_one(
            {"id": s["id"]}, {"$set": {
                "received_amount": new_received,
                "received_date": payload.received_date,
                "payment_method": payload.payment_method,
                "reference": payload.reference,
                "journal_entry_id": je_id,
                "status": status,
                "updated_at": iso_now(),
            }}
        )
    return {"ok": True, "settlement_id": settlement_id, "journal_entry_id": je_id,
            "settled": settled, "unallocated": round(remaining, 2)}


# ---------- Cross-vendor commission dashboard ----------
@router.get("/commissions/dashboard")
async def commissions_dashboard(request: Request,
                                session_token: Optional[str] = Cookie(default=None),
                                authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    _require(user, "vendors.read")
    from datetime import datetime, timezone
    today = datetime.now(timezone.utc).date()
    month_start = f"{today.year:04d}-{today.month:02d}-01"

    totals = {"total_earned": 0.0, "total_received": 0.0, "pending": 0.0,
              "this_month": 0.0, "this_month_received": 0.0}
    by_vendor: dict = {}
    by_project: dict = {}
    rows = await db.vendor_commissions.find({"status": {"$ne": "cancelled"}}, {"_id": 0}) \
                                      .to_list(20000)
    for r in rows:
        earned = float(r.get("amount") or 0)
        received = float(r.get("received_amount") or 0)
        totals["total_earned"] += earned
        totals["total_received"] += received
        if (r.get("bill_date") or "") >= month_start:
            totals["this_month"] += earned
            totals["this_month_received"] += received
        vid = r.get("vendor_id")
        by_vendor.setdefault(vid, {"vendor_id": vid, "vendor_name": r.get("vendor_name"),
                                    "earned": 0.0, "received": 0.0})
        by_vendor[vid]["earned"] += earned
        by_vendor[vid]["received"] += received
        pid = r.get("project_id")
        if pid:
            by_project.setdefault(pid, {"project_id": pid, "earned": 0.0, "received": 0.0})
            by_project[pid]["earned"] += earned
            by_project[pid]["received"] += received

    top_vendors = sorted(by_vendor.values(), key=lambda x: -x["earned"])[:10]
    # Enrich projects with names
    project_ids = list(by_project.keys())
    proj_names = {}
    async for p in db.projects.find({"id": {"$in": project_ids}}, {"_id": 0, "id": 1, "name": 1}):
        proj_names[p["id"]] = p.get("name")
    project_rows = [
        {**v, "project_name": proj_names.get(v["project_id"], "—"),
         "earned": round(v["earned"], 2), "received": round(v["received"], 2)}
        for v in by_project.values()
    ]
    project_rows.sort(key=lambda x: -x["earned"])

    for k in list(totals.keys()):
        totals[k] = round(totals[k], 2)
    totals["pending"] = round(totals["total_earned"] - totals["total_received"], 2)

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
    _require(user, "vendors.read")
    q: dict = {}
    if vendor_id:  q["vendor_id"] = vendor_id
    if project_id: q["project_id"] = project_id
    if status:     q["status"] = status
    if from_date or to_date:
        d = {}
        if from_date: d["$gte"] = from_date
        if to_date:   d["$lte"] = to_date
        q["bill_date"] = d
    rows = await db.vendor_commissions.find(q, {"_id": 0}) \
                                      .sort("bill_date", -1).to_list(5000)
    totals = {
        "earned":   round(sum(float(r.get("amount") or 0)
                              for r in rows if r.get("status") != "cancelled"), 2),
        "received": round(sum(float(r.get("received_amount") or 0)
                              for r in rows if r.get("status") != "cancelled"), 2),
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
    w = csv.writer(buf)
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
