"""GAMAA billing endpoints (P1.3). Logic lives in core.platform_billing.

Super Admin:  /api/platform/billing/...  settings, invoices, payments, PDFs
Studio Admin: /api/org/current/billing   own subscription, invoices and how to pay
"""
from datetime import date, timedelta
from typing import List, Optional

from fastapi import APIRouter, Cookie, Header, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field, field_validator

from core import platform_billing as pb
from core.audit import audit
from core.db import db
from core.deps import require_user
from core.helpers import business_today, iso_now, new_id
from core.rbac import has_permission
from core.tenancy import get_org, require_super_admin, user_org_id

router = APIRouter()


# ------------------------------------------------------------------ models
class BankIn(BaseModel):
    account_name: str = Field(default="", max_length=120)
    bank: str = Field(default="", max_length=120)
    account: str = Field(default="", max_length=40)
    ifsc: str = Field(default="", max_length=20)
    upi: str = Field(default="", max_length=80)


class BillingSettingsIn(BaseModel):
    seller_name: str = Field(min_length=2, max_length=120)
    address: str = Field(default="", max_length=300)
    state: str = Field(default="", max_length=60)
    gstin: str = Field(default="", max_length=15)
    pan: str = Field(default="", max_length=10)
    email: str = Field(default="", max_length=254)
    phone: str = Field(default="", max_length=32)
    tax_rate: float = Field(default=0, ge=0, le=28)
    sac: str = Field(default="", max_length=8)
    invoice_prefix: str = Field(default="GAMAA", min_length=1, max_length=12)
    payment_terms_days: int = Field(default=7, ge=0, le=90)
    notes: str = Field(default="", max_length=600)
    bank: BankIn = BankIn()

    @field_validator("gstin")
    @classmethod
    def gstin_shape(cls, v: str) -> str:
        v = (v or "").strip().upper()
        if v and not pb._GSTIN_RE.match(v):
            raise ValueError("GSTIN must be 15 characters starting with the 2-digit state code")
        return v


class LineIn(BaseModel):
    description: str = Field(min_length=1, max_length=200)
    amount: float = Field(gt=0, le=100_000_000)


class InvoiceIn(BaseModel):
    org_id: str
    period_start: str
    period_end: str
    lines: List[LineIn] = Field(min_length=1, max_length=20)
    notes: str = Field(default="", max_length=600)
    issue: bool = False


class PaymentIn(BaseModel):
    amount: float = Field(gt=0, le=100_000_000)
    method: str = "bank_transfer"
    reference: str = Field(default="", max_length=120)
    received_on: Optional[str] = None


class VoidIn(BaseModel):
    reason: str = Field(min_length=3, max_length=200)


def _iso(value: str, label: str) -> date:
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        raise HTTPException(400, f"{label} must be YYYY-MM-DD")


async def _invoice(invoice_id: str) -> dict:
    inv = await db.platform_invoices.find_one({"id": invoice_id}, {"_id": 0})
    if not inv:
        raise HTTPException(404, "Invoice not found")
    return inv


# ------------------------------------------------------------------ settings
@router.get("/platform/billing/settings")
async def get_billing_settings(request: Request, session_token: Optional[str] = Cookie(default=None),
                               authorization: Optional[str] = Header(default=None)):
    await require_super_admin(request, session_token, authorization)
    return await pb.get_settings()


@router.put("/platform/billing/settings")
async def save_billing_settings(payload: BillingSettingsIn, request: Request,
                                session_token: Optional[str] = Cookie(default=None),
                                authorization: Optional[str] = Header(default=None)):
    sa = await require_super_admin(request, session_token, authorization)
    doc = {"key": "default", **payload.model_dump(), "updated_at": iso_now(), "updated_by": sa["user_id"]}
    await db.platform_billing_settings.update_one({"key": "default"}, {"$set": doc}, upsert=True)
    await audit(sa, "platform.billing_settings", target="default", target_type="billing",
                meta={"gstin_set": bool(doc["gstin"]), "tax_rate": doc["tax_rate"]})
    return await pb.get_settings()


# ------------------------------------------------------------------ invoices
@router.get("/platform/billing/summary")
async def billing_summary(request: Request, session_token: Optional[str] = Cookie(default=None),
                          authorization: Optional[str] = Header(default=None)):
    await require_super_admin(request, session_token, authorization)
    return await pb.billing_summary()


@router.get("/platform/billing/invoices")
async def list_invoices(request: Request, org_id: Optional[str] = None, status: Optional[str] = None,
                        session_token: Optional[str] = Cookie(default=None),
                        authorization: Optional[str] = Header(default=None)):
    await require_super_admin(request, session_token, authorization)
    q = {"org_id": org_id} if org_id else {}
    rows = [pb.public_invoice(r) async for r in
            db.platform_invoices.find(q, {"_id": 0}).sort("created_at", -1).limit(1000)]
    return [r for r in rows if not status or r["status"] == status]


@router.get("/platform/billing/suggest/{org_id}")
async def suggest_invoice(org_id: str, request: Request,
                          session_token: Optional[str] = Cookie(default=None),
                          authorization: Optional[str] = Header(default=None)):
    """Prefill for the next invoice: period from the paid-through date and the
    workspace's billing cycle; amount from its recorded maintenance charge."""
    await require_super_admin(request, session_token, authorization)
    org = await get_org(org_id)
    if not org:
        raise HTTPException(404, "Organisation not found")
    from core.entitlements import for_org
    ent = await for_org(org)
    start, end, cycle = pb.suggest_period(org, business_today())
    amount = (org.get("billing") or {}).get("maintenance_charge") or 0
    return {"org_id": org_id, "period_start": start.isoformat(), "period_end": end.isoformat(),
            "cycle": cycle, "lines": [{"description": f"Gamaa ERP - {ent['plan_name']} plan, "
                                                     f"{start.strftime('%d %b %Y')} to {end.strftime('%d %b %Y')}",
                                       "amount": amount}]}


@router.post("/platform/billing/invoices")
async def create_invoice(payload: InvoiceIn, request: Request,
                         session_token: Optional[str] = Cookie(default=None),
                         authorization: Optional[str] = Header(default=None)):
    sa = await require_super_admin(request, session_token, authorization)
    org = await get_org(payload.org_id)
    if not org:
        raise HTTPException(404, "Organisation not found")
    start, end = _iso(payload.period_start, "period_start"), _iso(payload.period_end, "period_end")
    if end < start:
        raise HTTPException(400, "The period must end on or after it starts")
    settings = await pb.get_settings()
    buyer = pb.buyer_snapshot(org)
    lines = [{"description": x.description.strip(), "amount": pb.money(x.amount)} for x in payload.lines]
    from core.entitlements import for_org
    inv = {"id": new_id("pinv_"), "number": None, "org_id": payload.org_id, "buyer": buyer,
           "plan": org.get("plan") or "starter", "plan_name": (await for_org(org))["plan_name"],
           "period_start": start.isoformat(), "period_end": end.isoformat(), "lines": lines,
           **pb.compute_totals(lines, settings["tax_rate"], settings, buyer),
           "amount_paid": 0.0, "notes": payload.notes.strip(), "issued_on": None, "due_on": None,
           "voided_at": None, "created_at": iso_now(), "created_by": sa["user_id"]}
    await db.platform_invoices.insert_one(dict(inv))
    await audit(sa, "platform.invoice_create", target=inv["id"], target_type="platform_invoice",
                meta={"total": inv["total"]}, org_id=payload.org_id)
    if payload.issue:
        return await _issue(inv, sa, settings)
    return pb.public_invoice(inv)


async def _issue(inv: dict, sa: dict, settings: Optional[dict] = None) -> dict:
    if inv.get("voided_at"):
        raise HTTPException(409, "A void invoice cannot be issued")
    if inv.get("issued_on"):
        raise HTTPException(409, "This invoice is already issued")
    settings = settings or await pb.get_settings()
    today = business_today()
    number = await pb.next_invoice_number(settings["invoice_prefix"], today)
    upd = {"number": number, "issued_on": today.isoformat(),
           "due_on": (today + timedelta(days=int(settings["payment_terms_days"]))).isoformat(),
           "issued_by": sa["user_id"], "seller": {k: settings[k] for k in ("seller_name", "gstin", "state")}}
    res = await db.platform_invoices.update_one({"id": inv["id"], "issued_on": None}, {"$set": upd})
    if not getattr(res, "modified_count", 1):
        raise HTTPException(409, "This invoice is already issued")
    await audit(sa, "platform.invoice_issue", target=inv["id"], target_type="platform_invoice",
                meta={"number": number, "total": inv["total"]}, org_id=inv["org_id"])
    from core.notifications import emit_admins
    await emit_admins("reminder", f"New Gamaa invoice {number}",
                      f"Rs. {pb.money(inv['total']):,.2f} for {inv['period_start']} to {inv['period_end']}, "
                      f"due {upd['due_on']}. Download it in Company Settings > Plan & usage.",
                      link="/settings/company", dedup_key=f"gamaa-invoice:{inv['id']}", org_id=inv["org_id"])
    return pb.public_invoice({**inv, **upd})


@router.post("/platform/billing/invoices/{invoice_id}/issue")
async def issue_invoice(invoice_id: str, request: Request,
                        session_token: Optional[str] = Cookie(default=None),
                        authorization: Optional[str] = Header(default=None)):
    sa = await require_super_admin(request, session_token, authorization)
    return await _issue(await _invoice(invoice_id), sa)


@router.delete("/platform/billing/invoices/{invoice_id}")
async def delete_draft(invoice_id: str, request: Request,
                       session_token: Optional[str] = Cookie(default=None),
                       authorization: Optional[str] = Header(default=None)):
    """Only an unissued draft can be deleted; issued invoices are voided instead."""
    sa = await require_super_admin(request, session_token, authorization)
    inv = await _invoice(invoice_id)
    if inv.get("issued_on"):
        raise HTTPException(409, "Issued invoices are kept; void it instead")
    await db.platform_invoices.delete_one({"id": invoice_id, "issued_on": None})
    await audit(sa, "platform.invoice_draft_delete", target=invoice_id, target_type="platform_invoice",
                org_id=inv["org_id"])
    return {"ok": True}


@router.post("/platform/billing/invoices/{invoice_id}/void")
async def void_invoice(invoice_id: str, payload: VoidIn, request: Request,
                       session_token: Optional[str] = Cookie(default=None),
                       authorization: Optional[str] = Header(default=None)):
    sa = await require_super_admin(request, session_token, authorization)
    inv = await _invoice(invoice_id)
    if inv.get("voided_at"):
        raise HTTPException(409, "Already void")
    if pb.money(inv.get("amount_paid")) > 0:
        raise HTTPException(409, "Payments are recorded against this invoice; it cannot be voided")
    await db.platform_invoices.update_one({"id": invoice_id}, {"$set": {
        "voided_at": iso_now(), "void_reason": payload.reason.strip(), "voided_by": sa["user_id"]}})
    await audit(sa, "platform.invoice_void", target=invoice_id, target_type="platform_invoice",
                meta={"number": inv.get("number"), "reason": payload.reason.strip()}, org_id=inv["org_id"])
    return pb.public_invoice({**inv, "voided_at": iso_now(), "void_reason": payload.reason.strip()})


@router.post("/platform/billing/invoices/{invoice_id}/payments")
async def record_payment(invoice_id: str, payload: PaymentIn, request: Request,
                         session_token: Optional[str] = Cookie(default=None),
                         authorization: Optional[str] = Header(default=None)):
    sa = await require_super_admin(request, session_token, authorization)
    inv = await _invoice(invoice_id)
    received = _iso(payload.received_on, "received_on") if payload.received_on else business_today()
    if received > business_today():
        raise HTTPException(400, "The payment date cannot be in the future")
    out = await pb.apply_payment(inv, payload.amount, payload.method, payload.reference, received, sa)
    await audit(sa, "platform.payment_record", target=invoice_id, target_type="platform_invoice",
                meta={"amount": out["payment"]["amount"], "method": payload.method,
                      "paid_in_full": out["paid_in_full"], "paid_through": out["paid_through"]},
                org_id=inv["org_id"])
    return {**out, "invoice": pb.public_invoice(await _invoice(invoice_id))}


@router.get("/platform/billing/invoices/{invoice_id}/payments")
async def list_payments(invoice_id: str, request: Request,
                        session_token: Optional[str] = Cookie(default=None),
                        authorization: Optional[str] = Header(default=None)):
    await require_super_admin(request, session_token, authorization)
    return [p async for p in db.platform_payments.find({"invoice_id": invoice_id}, {"_id": 0})]


def _pdf_response(inv: dict, settings: dict) -> Response:
    name = (inv.get("number") or f"draft-{inv['id']}").replace("/", "-")
    return Response(pb.invoice_pdf(inv, settings), media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{name}.pdf"'})


@router.get("/platform/billing/invoices/{invoice_id}/pdf")
async def invoice_pdf(invoice_id: str, request: Request,
                      session_token: Optional[str] = Cookie(default=None),
                      authorization: Optional[str] = Header(default=None)):
    await require_super_admin(request, session_token, authorization)
    return _pdf_response(await _invoice(invoice_id), await pb.get_settings())


# ------------------------------------------------------------------ studio side

@router.get("/org/current/billing")
async def my_billing(request: Request, session_token: Optional[str] = Cookie(default=None),
                     authorization: Optional[str] = Header(default=None)):
    """The studio's subscription state, its GAMAA invoices and how to pay."""
    user = await require_user(request, session_token, authorization)
    if not has_permission(user, "*.*"):
        raise HTTPException(403, "Admin only")
    oid = user_org_id(user)
    org = await get_org(oid) or {}
    from core.subscription import subscription_state
    settings = await pb.get_settings()
    invoices = [pb.public_invoice(r) async for r in db.platform_invoices.find(
        {"org_id": oid, "issued_on": {"$ne": None}}, {"_id": 0}).sort("issued_on", -1).limit(200)]
    return {"subscription": subscription_state(org), "invoices": invoices,
            "pay_to": {"name": settings["seller_name"], **settings["bank"]},
            "seller": {"name": settings["seller_name"], "email": settings["email"], "phone": settings["phone"]}}


@router.get("/org/current/billing/invoices/{invoice_id}/pdf")
async def my_invoice_pdf(invoice_id: str, request: Request,
                         session_token: Optional[str] = Cookie(default=None),
                         authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    if not has_permission(user, "*.*"):
        raise HTTPException(403, "Admin only")
    inv = await db.platform_invoices.find_one({"id": invoice_id, "org_id": user_org_id(user),
                                               "issued_on": {"$ne": None}}, {"_id": 0})
    if not inv:
        raise HTTPException(404, "Invoice not found")
    return _pdf_response(inv, await pb.get_settings())
