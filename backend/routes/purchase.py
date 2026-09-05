"""Purchase Orders + GRN + 3-way match module.

Endpoints
---------
- CRUD /api/purchase-orders
- POST /api/purchase-orders/{id}/send        (draft → sent)
- POST /api/purchase-orders/{id}/cancel
- POST /api/grns                             (create Goods Receipt)
- GET  /api/grns?po_id=
- GET  /api/purchase-orders/{id}/match       (3-way match report)
"""
from fastapi import APIRouter, HTTPException, Request, Cookie, Header
from typing import Optional, List
from datetime import date as _date

from core.db import db
from core.scoped_db import sdb
from core.helpers import iso_now, new_id
from core.deps import require_user
from core.rbac import has_permission
from core.tenancy import user_org_id
from core.features import require_module
from core.audit import audit
from models.purchase import POCreateIn, POUpdateIn, GRNCreateIn


router = APIRouter()


# ------------------------------------------------------------
# Helpers
# ------------------------------------------------------------
async def _next_po_number() -> str:
    """Per-org PO sequence like PO-2026-0001."""
    year = _date.today().year
    prefix = f"PO-{year}-"
    latest = await sdb.purchase_orders.find(
        {"po_number": {"$regex": f"^{prefix}"}}, {"_id": 0, "po_number": 1},
    ).sort("po_number", -1).limit(1).to_list(1)
    n = 1
    if latest:
        try:
            n = int(latest[0]["po_number"].rsplit("-", 1)[-1]) + 1
        except Exception:
            pass
    return f"{prefix}{n:04d}"


async def _next_grn_number() -> str:
    year = _date.today().year
    prefix = f"GRN-{year}-"
    latest = await sdb.goods_receipts.find(
        {"grn_number": {"$regex": f"^{prefix}"}}, {"_id": 0, "grn_number": 1},
    ).sort("grn_number", -1).limit(1).to_list(1)
    n = 1
    if latest:
        try:
            n = int(latest[0]["grn_number"].rsplit("-", 1)[-1]) + 1
        except Exception:
            pass
    return f"{prefix}{n:04d}"


def _po_totals(lines: List[dict]) -> dict:
    subtotal = 0.0
    tax_total = 0.0
    for l in lines:
        qty = float(l.get("quantity", 0))
        up = float(l.get("unit_price", 0))
        rate = float(l.get("tax_rate", 0))
        line_total = qty * up
        subtotal += line_total
        tax_total += line_total * rate / 100.0
    return {
        "subtotal": round(subtotal, 2),
        "tax_total": round(tax_total, 2),
        "grand_total": round(subtotal + tax_total, 2),
    }


# ------------------------------------------------------------
# CRUD
# ------------------------------------------------------------
@router.get("/purchase-orders")
async def list_pos(request: Request, vendor_id: Optional[str] = None,
                   status: Optional[str] = None,
                   session_token: Optional[str] = Cookie(default=None),
                   authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    await require_module(user, "purchase_orders")
    if not has_permission(user, "vendors.read"):
        raise HTTPException(403, "Missing permission: vendors.read")
    q = {}
    if vendor_id: q["vendor_id"] = vendor_id
    if status: q["status"] = status
    rows = await sdb.purchase_orders.find(q, {"_id": 0}).sort("created_at", -1).to_list(500)
    return rows


@router.get("/purchase-orders/{po_id}")
async def get_po(po_id: str, request: Request,
                 session_token: Optional[str] = Cookie(default=None),
                 authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    await require_module(user, "purchase_orders")
    if not has_permission(user, "vendors.read"):
        raise HTTPException(403, "Missing permission")
    po = await sdb.purchase_orders.find_one({"id": po_id}, {"_id": 0})
    if not po:
        raise HTTPException(404, "PO not found")
    return po


@router.post("/purchase-orders")
async def create_po(payload: POCreateIn, request: Request,
                    session_token: Optional[str] = Cookie(default=None),
                    authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    await require_module(user, "purchase_orders")
    if not has_permission(user, "vendors.create"):
        raise HTTPException(403, "Missing permission: vendors.create")
    vendor = await sdb.vendors_acc.find_one({"id": payload.vendor_id}, {"_id": 0})
    if not vendor:
        raise HTTPException(404, "Vendor not found")
    lines = []
    for l in payload.lines:
        d = l.dict()
        d["id"] = new_id("pol_")
        d["received_qty_total"] = 0.0  # updated by GRN posts
        d["billed_qty_total"] = 0.0    # updated by bill matching
        lines.append(d)
    totals = _po_totals(lines)
    po_id = new_id("po_")
    doc = {
        "id": po_id,
        "org_id": user_org_id(user),
        "po_number": await _next_po_number(),
        "vendor_id": payload.vendor_id,
        "vendor_name": vendor.get("name"),
        "project_id": payload.project_id,
        "order_date": payload.order_date or _date.today().isoformat(),
        "expected_delivery": payload.expected_delivery,
        "delivery_address": payload.delivery_address,
        "payment_terms": payload.payment_terms,
        "lines": lines,
        **totals,
        "notes": payload.notes,
        "reference": payload.reference,
        "status": "draft",
        "created_at": iso_now(),
        "created_by": user["user_id"],
    }
    await sdb.purchase_orders.insert_one(dict(doc))
    await audit(user, "po.create", target=po_id, target_type="po",
                meta={"po_number": doc["po_number"], "vendor_id": payload.vendor_id,
                      "grand_total": totals["grand_total"]})
    return doc


@router.patch("/purchase-orders/{po_id}")
async def update_po(po_id: str, payload: POUpdateIn, request: Request,
                    session_token: Optional[str] = Cookie(default=None),
                    authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    await require_module(user, "purchase_orders")
    if not has_permission(user, "vendors.update"):
        raise HTTPException(403, "Missing permission")
    po = await sdb.purchase_orders.find_one({"id": po_id}, {"_id": 0})
    if not po:
        raise HTTPException(404, "PO not found")
    if po["status"] in ("received", "closed", "cancelled") and payload.status not in ("closed", "cancelled"):
        raise HTTPException(400, f"Cannot edit PO in status: {po['status']}")

    up = {k: v for k, v in payload.dict(exclude_unset=True).items() if v is not None}
    if "lines" in up:
        # Preserve line IDs where possible
        new_lines = []
        for i, l in enumerate(up["lines"]):
            d = l if isinstance(l, dict) else l.dict()
            d["id"] = (po["lines"][i].get("id") if i < len(po["lines"]) else new_id("pol_"))
            d.setdefault("received_qty_total", 0.0)
            d.setdefault("billed_qty_total", 0.0)
            new_lines.append(d)
        up["lines"] = new_lines
        up.update(_po_totals(new_lines))
    up["updated_at"] = iso_now()
    await sdb.purchase_orders.update_one({"id": po_id}, {"$set": up})
    return await sdb.purchase_orders.find_one({"id": po_id}, {"_id": 0})


@router.post("/purchase-orders/{po_id}/send")
async def send_po(po_id: str, request: Request,
                  session_token: Optional[str] = Cookie(default=None),
                  authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    await require_module(user, "purchase_orders")
    if not has_permission(user, "vendors.update"):
        raise HTTPException(403, "Missing permission")
    po = await sdb.purchase_orders.find_one({"id": po_id}, {"_id": 0})
    if not po:
        raise HTTPException(404, "PO not found")
    if po["status"] != "draft":
        raise HTTPException(400, f"PO already {po['status']}")
    await sdb.purchase_orders.update_one(
        {"id": po_id},
        {"$set": {"status": "sent", "sent_at": iso_now(), "sent_by": user["user_id"]}},
    )
    await audit(user, "po.send", target=po_id, target_type="po",
                meta={"po_number": po["po_number"]})
    return await sdb.purchase_orders.find_one({"id": po_id}, {"_id": 0})


@router.post("/purchase-orders/{po_id}/cancel")
async def cancel_po(po_id: str, request: Request,
                    session_token: Optional[str] = Cookie(default=None),
                    authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    await require_module(user, "purchase_orders")
    if not has_permission(user, "vendors.update"):
        raise HTTPException(403, "Missing permission")
    po = await sdb.purchase_orders.find_one({"id": po_id}, {"_id": 0})
    if not po:
        raise HTTPException(404, "PO not found")
    # Reject if any GRN exists
    grn_count = await sdb.goods_receipts.count_documents({"po_id": po_id})
    if grn_count > 0:
        raise HTTPException(400, "PO has GRNs — cannot cancel. Reverse GRNs first.")
    await sdb.purchase_orders.update_one(
        {"id": po_id},
        {"$set": {"status": "cancelled", "cancelled_at": iso_now(),
                  "cancelled_by": user["user_id"]}},
    )
    await audit(user, "po.cancel", target=po_id, target_type="po",
                meta={"po_number": po["po_number"]})
    return {"ok": True}


# ------------------------------------------------------------
# GRN
# ------------------------------------------------------------
async def _ensure_account(user: dict, name: str, type_: str,
                          category: Optional[str] = None) -> str:
    acc = await sdb.accounts.find_one({"name": name}, {"_id": 0})
    if acc:
        return acc["id"]
    doc = {
        "id": new_id("acc_"),
        "name": name, "type": type_,
        "category": category or type_.title(),
        "is_bank": False,
        "created_at": iso_now(),
        "created_by": user["user_id"],
    }
    await sdb.accounts.insert_one(dict(doc))
    return doc["id"]


@router.get("/grns")
async def list_grns(request: Request, po_id: Optional[str] = None,
                    session_token: Optional[str] = Cookie(default=None),
                    authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    await require_module(user, "purchase_orders")
    if not has_permission(user, "vendors.read"):
        raise HTTPException(403, "Missing permission")
    q = {}
    if po_id: q["po_id"] = po_id
    rows = await sdb.goods_receipts.find(q, {"_id": 0}).sort("created_at", -1).to_list(500)
    return rows


@router.post("/grns")
async def create_grn(payload: GRNCreateIn, request: Request,
                     session_token: Optional[str] = Cookie(default=None),
                     authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    await require_module(user, "purchase_orders")
    if not has_permission(user, "vendors.create"):
        raise HTTPException(403, "Missing permission")
    po = await sdb.purchase_orders.find_one({"id": payload.po_id}, {"_id": 0})
    if not po:
        raise HTTPException(404, "PO not found")
    if po["status"] in ("cancelled", "closed"):
        raise HTTPException(400, f"PO is {po['status']} — cannot record GRN")

    # Validate every GRN line points at a valid PO line + doesn't over-receive
    po_lines_by_id = {l["id"]: l for l in po.get("lines", [])}
    grn_lines_out = []
    line_updates = {}                                   # po_line_id -> new received_qty_total
    for gl in payload.lines:
        pol = po_lines_by_id.get(gl.po_line_id)
        if not pol:
            raise HTTPException(400, f"Invalid po_line_id: {gl.po_line_id}")
        already = float(pol.get("received_qty_total", 0))
        remaining = float(pol["quantity"]) - already
        if gl.received_qty > remaining + 0.001:
            raise HTTPException(
                400,
                f"Cannot receive {gl.received_qty} for '{pol.get('item_name')}' — "
                f"only {remaining} remaining out of ordered {pol['quantity']}",
            )
        grn_lines_out.append({
            "id": new_id("grnl_"),
            "po_line_id": gl.po_line_id,
            "item_name": pol.get("item_name"),
            "unit": pol.get("unit"),
            "unit_price": pol.get("unit_price"),
            "ordered_qty": pol.get("quantity"),
            "received_qty": gl.received_qty,
            "rejected_qty": gl.rejected_qty or 0,
            "remarks": gl.remarks,
        })
        line_updates[gl.po_line_id] = already + gl.received_qty

    # Auto-post JE: DR Inventory (or Direct Expense) / CR GRN Clearing
    from routes.accounting import _post_journal
    inv_acc_id = payload.inventory_account_id or await _ensure_account(
        user, "Inventory", "asset", category="Current Assets"
    )
    grn_clearing_id = await _ensure_account(
        user, "GRN Clearing", "liability", category="Accruals"
    )
    value = sum(
        float(l["received_qty"]) * float(l["unit_price"]) for l in grn_lines_out
    )
    grn_id = new_id("grn_")
    received_date = payload.received_date or _date.today().isoformat()
    je = None
    if value > 0:
        je = await _post_journal(
            user, received_date,
            f"GRN {payload.po_id} – {po.get('vendor_name')}",
            [
                {"account_id": inv_acc_id, "debit": round(value, 2), "credit": 0,
                 "description": f"Goods received against {po['po_number']}"},
                {"account_id": grn_clearing_id, "debit": 0, "credit": round(value, 2),
                 "description": "GRN clearing"},
            ],
            reference=payload.delivery_challan_no or f"GRN-{grn_id}",
            source="grn", source_id=grn_id,
        )

    grn_doc = {
        "id": grn_id,
        "org_id": user_org_id(user),
        "grn_number": await _next_grn_number(),
        "po_id": payload.po_id,
        "po_number": po["po_number"],
        "vendor_id": po["vendor_id"],
        "vendor_name": po.get("vendor_name"),
        "received_date": received_date,
        "received_by": payload.received_by or user.get("name"),
        "delivery_challan_no": payload.delivery_challan_no,
        "lines": grn_lines_out,
        "total_value": round(value, 2),
        "inventory_account_id": inv_acc_id,
        "grn_clearing_account_id": grn_clearing_id,
        "journal_id": (je or {}).get("id"),
        "notes": payload.notes,
        "created_at": iso_now(),
        "created_by": user["user_id"],
    }
    await sdb.goods_receipts.insert_one(dict(grn_doc))

    # Update PO line received totals + PO status (partial/received)
    updated_lines = []
    for l in po["lines"]:
        d = dict(l)
        if l["id"] in line_updates:
            d["received_qty_total"] = round(line_updates[l["id"]], 3)
        updated_lines.append(d)
    all_received = all(
        float(l.get("received_qty_total", 0)) + 0.001 >= float(l["quantity"])
        for l in updated_lines
    )
    any_received = any(
        float(l.get("received_qty_total", 0)) > 0 for l in updated_lines
    )
    new_status = "received" if all_received else ("partial" if any_received else po["status"])
    await sdb.purchase_orders.update_one(
        {"id": payload.po_id},
        {"$set": {"lines": updated_lines, "status": new_status, "updated_at": iso_now()}},
    )

    await audit(user, "grn.create", target=grn_id, target_type="grn",
                meta={"po_number": po["po_number"], "grn_number": grn_doc["grn_number"],
                      "value": grn_doc["total_value"]})
    return grn_doc


# ------------------------------------------------------------
# 3-WAY MATCH REPORT
# ------------------------------------------------------------
@router.get("/purchase-orders/{po_id}/match")
async def three_way_match(po_id: str, request: Request,
                          session_token: Optional[str] = Cookie(default=None),
                          authorization: Optional[str] = Header(default=None)):
    """Returns per-line variance across PO / GRN / Bill quantities & amounts."""
    user = await require_user(request, session_token, authorization)
    await require_module(user, "purchase_orders")
    if not has_permission(user, "vendors.read"):
        raise HTTPException(403, "Missing permission")
    po = await sdb.purchase_orders.find_one({"id": po_id}, {"_id": 0})
    if not po:
        raise HTTPException(404, "PO not found")

    # Aggregate all GRN lines per po_line_id
    grn_agg = {}   # pol_id -> {received, rejected}
    async for g in sdb.goods_receipts.find({"po_id": po_id}, {"_id": 0, "lines": 1}):
        for gl in g.get("lines", []):
            k = gl["po_line_id"]
            slot = grn_agg.setdefault(k, {"received": 0.0, "rejected": 0.0})
            slot["received"] += float(gl.get("received_qty", 0))
            slot["rejected"] += float(gl.get("rejected_qty", 0))

    # Aggregate bill lines linked to this PO
    bill_agg = {}  # pol_id -> {qty, amount}
    bill_total = 0.0
    bills = []
    async for b in sdb.vendor_bills.find({"po_id": po_id}, {"_id": 0}):
        bills.append({"id": b["id"], "bill_number": b.get("bill_number"),
                     "amount": b.get("amount"), "status": b.get("status")})
        bill_total += float(b.get("amount", 0))
        for bl in b.get("lines", []) if b.get("lines") else []:
            pol = bl.get("po_line_id")
            if not pol:
                continue
            slot = bill_agg.setdefault(pol, {"qty": 0.0, "amount": 0.0})
            slot["qty"] += float(bl.get("quantity", 0))
            slot["amount"] += float(bl.get("amount", 0))

    lines_out = []
    all_matched = True
    for l in po.get("lines", []):
        pol_id = l["id"]
        ordered = float(l["quantity"])
        unit_price = float(l["unit_price"])
        ordered_value = round(ordered * unit_price, 2)
        received = float(grn_agg.get(pol_id, {}).get("received", 0))
        billed = float(bill_agg.get(pol_id, {}).get("qty", 0))
        billed_amt = float(bill_agg.get(pol_id, {}).get("amount", 0))
        qty_variance = round(received - billed, 3) if billed else 0
        matched = (received > 0 and abs(received - billed) < 0.001 and
                   abs(billed_amt - received * unit_price) < 1.0)
        if not matched:
            all_matched = False
        lines_out.append({
            "po_line_id": pol_id,
            "item": l.get("item_name"),
            "unit_price": unit_price,
            "ordered_qty": ordered,
            "ordered_value": ordered_value,
            "received_qty": round(received, 3),
            "billed_qty": round(billed, 3),
            "billed_amount": round(billed_amt, 2),
            "qty_variance": qty_variance,
            "matched": matched,
        })
    return {
        "po_id": po_id,
        "po_number": po.get("po_number"),
        "po_grand_total": po.get("grand_total"),
        "bills": bills,
        "bill_total": round(bill_total, 2),
        "lines": lines_out,
        "all_matched": all_matched,
    }
