"""Studio Product & Material Library (roadmap P2.2).

A tenant-owned catalogue of the products a studio specifies again and again
(fans, fittings, tiles, laminates, hardware ...): brand, model/SKU, specs,
finish, images, datasheets, default vendor and an append-only price history.
Quotation BOQ lines are filled from it as a *snapshot* (name, spec summary,
unit, latest price, vendor), so editing the library never changes a quotation
that was already sent.

Access (existing permissions, so tenant role overrides keep working):
  read    quotations.read | vendors.read | purchase_orders.read
  manage  quotations.create | quotations.update | vendors.update   (create, edit, prices, files)
  delete  quotations.delete | vendors.delete   (only products never used in a quotation;
          otherwise mark them discontinued)

Files are stored with services.local_files (tenant folder, signature-checked,
counted against the tenant storage quota) and served only through
/api/products/{id}/files/{file_id}.
"""
import re
from datetime import date as _date
from typing import List, Literal, Optional

from fastapi import APIRouter, Cookie, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import Field, field_validator

from core.audit import audit
from core.deps import require_user
from core.helpers import business_today, iso_now, new_id
from core.limits import MAX_LIST_ROWS, tenant_storage_quota_bytes
from core.rbac import has_any_permission
from core.refs import ensure_in_tenant
from core.scoped_db import sdb
from core.tenancy import user_org_id
from core.url_security import external_http_url
from models.base import FiniteModel

router = APIRouter()

READ = ("quotations.read", "vendors.read", "purchase_orders.read")
MANAGE = ("quotations.create", "quotations.update", "vendors.update")
DELETE = ("quotations.delete", "vendors.delete")
IMAGE_TYPES = {"image/png", "image/jpeg", "image/webp"}
MAX_IMAGES, MAX_DATASHEETS = 12, 10


def _require_access(user: dict, perms: tuple) -> None:
    if not has_any_permission(user, *perms):
        raise HTTPException(status_code=403, detail="You do not have access to the product library")


def _text(v: Optional[str], limit: int) -> Optional[str]:
    v = re.sub(r"\s+", " ", (v or "")).strip()
    return v[:limit] or None


class SpecIn(FiniteModel):
    label: str = Field(min_length=1, max_length=60)
    value: str = Field(default="", max_length=200)


class ProductIn(FiniteModel):
    name: str = Field(min_length=1, max_length=160)
    brand: Optional[str] = Field(default=None, max_length=80)
    category: Optional[str] = Field(default=None, max_length=80)
    model: Optional[str] = Field(default=None, max_length=80)
    sku: Optional[str] = Field(default=None, max_length=60)
    finish: Optional[str] = Field(default=None, max_length=120)
    dimensions: Optional[str] = Field(default=None, max_length=120)
    unit: Optional[str] = Field(default="nos", max_length=20)
    warranty: Optional[str] = Field(default=None, max_length=120)
    notes: Optional[str] = Field(default=None, max_length=2000)
    product_url: Optional[str] = Field(default=None, max_length=500)
    specs: List[SpecIn] = Field(default_factory=list, max_length=40)
    tags: List[str] = Field(default_factory=list, max_length=20)
    default_vendor_id: Optional[str] = None
    preferred: bool = False

    @field_validator("product_url")
    @classmethod
    def _url(cls, v):
        return external_http_url(v) if v else None

    @field_validator("tags")
    @classmethod
    def _tags(cls, v):
        out = []
        for t in v or []:
            t = re.sub(r"\s+", " ", str(t)).strip()[:40]
            if t and t.lower() not in {x.lower() for x in out}:
                out.append(t)
        return out


class ProductUpdate(ProductIn):
    name: Optional[str] = Field(default=None, min_length=1, max_length=160)
    specs: Optional[List[SpecIn]] = Field(default=None, max_length=40)
    tags: Optional[List[str]] = Field(default=None, max_length=20)
    preferred: Optional[bool] = None
    unit: Optional[str] = Field(default=None, max_length=20)
    status: Optional[Literal["active", "discontinued"]] = None


class PriceIn(FiniteModel):
    price: float = Field(ge=0, le=1_000_000_000)
    vendor_id: Optional[str] = None
    gst_pct: Optional[float] = Field(default=None, ge=0, le=100)
    unit: Optional[str] = Field(default=None, max_length=20)
    valid_from: Optional[str] = None
    source: Literal["manual", "quote", "po"] = "manual"
    note: Optional[str] = Field(default=None, max_length=300)

    @field_validator("valid_from")
    @classmethod
    def _date(cls, v):
        if not v:
            return None
        try:
            return _date.fromisoformat(v.strip()[:10]).isoformat()
        except ValueError as exc:
            raise ValueError("valid_from must be a date like 2026-11-30") from exc


def _clean(payload: dict) -> dict:
    out = {}
    for key, limit in (("name", 160), ("brand", 80), ("category", 80), ("model", 80), ("sku", 60),
                       ("finish", 120), ("dimensions", 120), ("unit", 20), ("warranty", 120)):
        if key in payload:
            out[key] = _text(payload[key], limit)
    if "notes" in payload:
        out["notes"] = (payload["notes"] or "").strip()[:2000] or None
    if "specs" in payload and payload["specs"] is not None:
        out["specs"] = [{"label": _text(s["label"], 60), "value": _text(s.get("value"), 200) or ""}
                        for s in payload["specs"] if _text(s["label"], 60)]
    for key in ("tags", "product_url", "default_vendor_id", "preferred", "status"):
        if key in payload:
            out[key] = payload[key]
    if "default_vendor_id" in out:
        out["default_vendor_id"] = out["default_vendor_id"] or None
    return out


async def _vendor_name(vendor_id: Optional[str]) -> Optional[str]:
    if not vendor_id:
        return None
    v = await sdb.vendors_acc.find_one({"id": vendor_id}, {"_id": 0, "name": 1})
    return (v or {}).get("name")


def _file_url(product_id: str, f: dict) -> str:
    return f"/api/products/{product_id}/files/{f['id']}"


def _shape(p: dict) -> dict:
    """Public view: storage keys never leave the server."""
    images = [{"id": f["id"], "name": f.get("name"), "url": _file_url(p["id"], f)} for f in p.get("images") or []]
    sheets = [{"id": f["id"], "name": f.get("name"), "url": _file_url(p["id"], f), "size": f.get("size")}
              for f in p.get("datasheets") or []]
    out = {k: v for k, v in p.items() if k not in ("images", "datasheets")}
    out.update(images=images, datasheets=sheets, cover_url=images[0]["url"] if images else None)
    return out


async def _product(product_id: str) -> dict:
    p = await sdb.products.find_one({"id": product_id}, {"_id": 0})
    if not p:
        raise HTTPException(status_code=404, detail="Product not found")
    return p


async def _used_in(product_id: str) -> int:
    return await sdb.quotations_adv.count_documents({"boq.items.product_id": product_id})


# ------------------------------------------------------------------ catalogue
@router.get("/products")
async def list_products(request: Request, q: Optional[str] = None, category: Optional[str] = None,
                        brand: Optional[str] = None, vendor_id: Optional[str] = None, tag: Optional[str] = None,
                        preferred: Optional[bool] = None, status: str = "active",
                        page: int = 1, page_size: int = 48,
                        session_token: Optional[str] = Cookie(default=None),
                        authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    _require_access(user, READ)
    page, page_size = max(1, page), max(1, min(page_size, 100))
    query: dict = {}
    if status in ("active", "discontinued"):
        query["status"] = status
    for key, value in (("category", category), ("brand", brand), ("default_vendor_id", vendor_id)):
        if value:
            query[key] = value
    if tag:
        query["tags"] = tag
    if preferred is not None:
        query["preferred"] = preferred
    if q and q.strip():
        rx = {"$regex": re.escape(q.strip()[:80]), "$options": "i"}
        query["$or"] = [{"name": rx}, {"brand": rx}, {"model": rx}, {"sku": rx}, {"category": rx}, {"tags": rx}]
    rows = await sdb.products.find(query, {"_id": 0}).to_list(MAX_LIST_ROWS)
    rows.sort(key=lambda p: (not p.get("preferred"), (p.get("name") or "").lower()))
    facet_rows = await sdb.products.find({"status": {"$ne": "discontinued"}},
                                         {"_id": 0, "category": 1, "brand": 1, "tags": 1}).to_list(MAX_LIST_ROWS)
    start = (page - 1) * page_size
    return {
        "items": [_shape(p) for p in rows[start:start + page_size]],
        "total": len(rows), "page": page, "page_size": page_size,
        "facets": {"categories": sorted({r["category"] for r in facet_rows if r.get("category")}),
                   "brands": sorted({r["brand"] for r in facet_rows if r.get("brand")}),
                   "tags": sorted({t for r in facet_rows for t in r.get("tags") or []})},
        "can_manage": has_any_permission(user, *MANAGE),
        "can_delete": has_any_permission(user, *DELETE),
    }


@router.get("/products/{product_id}")
async def get_product(product_id: str, request: Request,
                      session_token: Optional[str] = Cookie(default=None),
                      authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    _require_access(user, READ)
    p = await _product(product_id)
    prices = await sdb.product_prices.find({"product_id": product_id}, {"_id": 0}) \
        .sort("created_at", -1).to_list(500)
    return {**_shape(p), "prices": prices, "used_in_quotations": await _used_in(product_id),
            "can_manage": has_any_permission(user, *MANAGE), "can_delete": has_any_permission(user, *DELETE)}


@router.post("/products")
async def create_product(payload: ProductIn, request: Request,
                         session_token: Optional[str] = Cookie(default=None),
                         authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    _require_access(user, MANAGE)
    data = _clean(payload.model_dump())
    await ensure_in_tenant(vendor_id=data.get("default_vendor_id"))
    now = iso_now()
    doc = {"id": new_id("prd_"), **data, "unit": data.get("unit") or "nos", "status": "active",
           "default_vendor_name": await _vendor_name(data.get("default_vendor_id")),
           "images": [], "datasheets": [], "latest_price": None,
           "created_at": now, "updated_at": now, "created_by": user["user_id"],
           "created_by_name": user.get("name")}
    await sdb.products.insert_one(dict(doc))
    await audit(user, "product.create", target=doc["id"], target_type="product",
                meta={"name": doc["name"], "brand": doc.get("brand"), "model": doc.get("model")})
    return _shape(doc)


@router.patch("/products/{product_id}")
async def update_product(product_id: str, payload: ProductUpdate, request: Request,
                         session_token: Optional[str] = Cookie(default=None),
                         authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    _require_access(user, MANAGE)
    p = await _product(product_id)
    data = _clean(payload.model_dump(exclude_unset=True))
    if "name" in data and not data["name"]:
        raise HTTPException(status_code=400, detail="Give the product a name")
    if data.get("default_vendor_id") and data["default_vendor_id"] != p.get("default_vendor_id"):
        await ensure_in_tenant(vendor_id=data["default_vendor_id"])
    if "default_vendor_id" in data:
        data["default_vendor_name"] = await _vendor_name(data["default_vendor_id"])
    if not data:
        return _shape(p)
    data["updated_at"] = iso_now()
    await sdb.products.update_one({"id": product_id}, {"$set": data})
    action = ("product.discontinue" if data.get("status") == "discontinued" else
              "product.reactivate" if data.get("status") == "active" and p.get("status") != "active" else
              "product.update")
    await audit(user, action, target=product_id, target_type="product",
                meta={"name": p.get("name"), "fields": sorted(k for k in data if k != "updated_at")})
    return _shape(await _product(product_id))


@router.post("/products/{product_id}/duplicate")
async def duplicate_product(product_id: str, request: Request,
                            session_token: Optional[str] = Cookie(default=None),
                            authorization: Optional[str] = Header(default=None)):
    """Copy the details (not files or prices) to start a similar product."""
    user = await require_user(request, session_token, authorization)
    _require_access(user, MANAGE)
    p = await _product(product_id)
    now = iso_now()
    keep = ("brand", "category", "model", "finish", "dimensions", "unit", "warranty", "notes",
            "product_url", "specs", "tags", "default_vendor_id", "default_vendor_name")
    doc = {"id": new_id("prd_"), "name": f"{p.get('name')} (copy)"[:160], **{k: p.get(k) for k in keep},
           "sku": None, "preferred": False, "status": "active", "images": [], "datasheets": [],
           "latest_price": None, "created_at": now, "updated_at": now, "created_by": user["user_id"],
           "created_by_name": user.get("name"), "duplicated_from": product_id}
    await sdb.products.insert_one(dict(doc))
    await audit(user, "product.create", target=doc["id"], target_type="product",
                meta={"name": doc["name"], "duplicated_from": product_id})
    return _shape(doc)


@router.delete("/products/{product_id}")
async def delete_product(product_id: str, request: Request,
                         session_token: Optional[str] = Cookie(default=None),
                         authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    _require_access(user, DELETE)
    p = await _product(product_id)
    used = await _used_in(product_id)
    if used:
        raise HTTPException(status_code=409, detail=(
            f"Used in {used} quotation{'s' if used != 1 else ''}. Mark it discontinued instead so those stay intact."))
    await sdb.products.delete_one({"id": product_id})
    await sdb.product_prices.delete_many({"product_id": product_id})
    from services.local_files import remove_upload
    for f in (p.get("images") or []) + (p.get("datasheets") or []):
        remove_upload(f.get("storage_key"))
    await audit(user, "product.delete", target=product_id, target_type="product", meta={"name": p.get("name")})
    return {"ok": True}


# ------------------------------------------------------------------ prices
@router.get("/products/{product_id}/prices")
async def list_prices(product_id: str, request: Request,
                      session_token: Optional[str] = Cookie(default=None),
                      authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    _require_access(user, READ)
    await _product(product_id)
    return await sdb.product_prices.find({"product_id": product_id}, {"_id": 0}).sort("created_at", -1).to_list(500)


@router.post("/products/{product_id}/prices")
async def add_price(product_id: str, payload: PriceIn, request: Request,
                    session_token: Optional[str] = Cookie(default=None),
                    authorization: Optional[str] = Header(default=None)):
    """Prices are append-only: a new price is added, earlier ones stay as history."""
    user = await require_user(request, session_token, authorization)
    _require_access(user, MANAGE)
    p = await _product(product_id)
    vendor_id = payload.vendor_id or p.get("default_vendor_id")
    if payload.vendor_id:
        await ensure_in_tenant(vendor_id=payload.vendor_id)
    row = {"id": new_id("prc_"), "product_id": product_id, "price": round(payload.price, 2),
           "gst_pct": payload.gst_pct, "unit": _text(payload.unit, 20) or p.get("unit") or "nos",
           "vendor_id": vendor_id, "vendor_name": await _vendor_name(vendor_id),
           "valid_from": payload.valid_from or business_today().isoformat(), "source": payload.source,
           "note": _text(payload.note, 300), "created_at": iso_now(), "created_by": user["user_id"],
           "created_by_name": user.get("name")}
    await sdb.product_prices.insert_one(dict(row))
    latest = {k: row[k] for k in ("id", "price", "gst_pct", "unit", "vendor_id", "vendor_name", "valid_from", "source")}
    await sdb.products.update_one({"id": product_id}, {"$set": {"latest_price": latest, "updated_at": iso_now()}})
    await audit(user, "product.price.add", target=product_id, target_type="product",
                meta={"name": p.get("name"), "price": row["price"], "vendor": row["vendor_name"],
                      "valid_from": row["valid_from"], "source": row["source"]})
    return row


# ------------------------------------------------------------------ files
@router.post("/products/{product_id}/files")
async def upload_product_file(product_id: str, request: Request, kind: str = Form("image"),
                              upload: UploadFile = File(...),
                              session_token: Optional[str] = Cookie(default=None),
                              authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    _require_access(user, MANAGE)
    if kind not in ("image", "datasheet"):
        raise HTTPException(status_code=400, detail="kind must be image or datasheet")
    p = await _product(product_id)
    field = "images" if kind == "image" else "datasheets"
    limit = MAX_IMAGES if kind == "image" else MAX_DATASHEETS
    if len(p.get(field) or []) >= limit:
        raise HTTPException(status_code=409, detail=f"A product can have up to {limit} {field}")
    from services.local_files import remove_upload, save_upload
    org_id = user_org_id(user)
    try:
        stored = await save_upload(upload, org_id, await tenant_storage_quota_bytes(org_id))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(status_code=503, detail="File storage is unavailable") from exc
    allowed = IMAGE_TYPES if kind == "image" else {"application/pdf"}
    if stored["content_type"] not in allowed:
        remove_upload(stored["storage_key"])
        raise HTTPException(status_code=422, detail=("Images must be PNG, JPG or WebP" if kind == "image"
                                                     else "Datasheets must be PDF files"))
    entry = {"id": new_id("pf_"), "name": stored["original_name"][:180], "storage_key": stored["storage_key"],
             "content_type": stored["content_type"], "size": stored["size"], "sha256": stored["sha256"],
             "uploaded_at": iso_now(), "uploaded_by": user["user_id"]}
    result = await sdb.products.update_one({"id": product_id}, {"$push": {field: entry},
                                                                "$set": {"updated_at": iso_now()}})
    if not result.modified_count:
        remove_upload(stored["storage_key"])
        raise HTTPException(status_code=404, detail="Product not found")
    await audit(user, "product.file.add", target=product_id, target_type="product",
                meta={"kind": kind, "name": entry["name"], "size": entry["size"], "sha256": entry["sha256"]})
    return _shape(await _product(product_id))


def _find_file(p: dict, file_id: str) -> tuple[Optional[str], Optional[dict]]:
    for field in ("images", "datasheets"):
        for f in p.get(field) or []:
            if f.get("id") == file_id:
                return field, f
    return None, None


@router.get("/products/{product_id}/files/{file_id}")
async def product_file(product_id: str, file_id: str, request: Request,
                       session_token: Optional[str] = Cookie(default=None),
                       authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    _require_access(user, READ)
    _, f = _find_file(await _product(product_id), file_id)
    if not f:
        raise HTTPException(status_code=404, detail="File not found")
    from services.local_files import resolve_storage_key
    try:
        path = resolve_storage_key(f["storage_key"])
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="File not found") from exc
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Stored file is unavailable")
    return FileResponse(path, media_type=f.get("content_type") or "application/octet-stream",
                        filename=f.get("name") or "file", content_disposition_type="inline",
                        headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"})


@router.delete("/products/{product_id}/files/{file_id}")
async def remove_product_file(product_id: str, file_id: str, request: Request,
                              session_token: Optional[str] = Cookie(default=None),
                              authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    _require_access(user, MANAGE)
    field, f = _find_file(await _product(product_id), file_id)
    if not f:
        raise HTTPException(status_code=404, detail="File not found")
    p = await _product(product_id)
    remaining = [x for x in p.get(field) or [] if x.get("id") != file_id]
    await sdb.products.update_one({"id": product_id}, {"$set": {field: remaining, "updated_at": iso_now()}})
    from services.local_files import remove_upload
    remove_upload(f.get("storage_key"))
    await audit(user, "product.file.remove", target=product_id, target_type="product",
                meta={"kind": field, "name": f.get("name")})
    return _shape(await _product(product_id))


# ------------------------------------------------------------------ quotation hook
def boq_line(p: dict, room: Optional[str] = None) -> dict:
    """A BOQ line filled from the library as a snapshot (not a live link)."""
    latest = p.get("latest_price") or {}
    maker = " ".join(x for x in (p.get("brand"), p.get("model")) if x)
    spec_summary = "; ".join(f"{s['label']}: {s['value']}" for s in (p.get("specs") or [])[:4] if s.get("value"))
    description = p.get("name") or ""
    if maker:
        description += f" - {maker}"
    if p.get("finish"):
        description += f" ({p['finish']})"
    if spec_summary:
        description += f". {spec_summary}"
    return {
        "code": (p.get("sku") or f"LIB-{p['id'][-4:].upper()}")[:30],
        "description": description[:400],
        "unit": latest.get("unit") or p.get("unit") or "nos",
        "quantity": 1,
        "rate": float(latest.get("price") or 0),
        "margin_pct": 15,
        "amount": 0,
        "room": room or "Unassigned",
        "brand_tier": "Standard",
        "vendor": latest.get("vendor_name") or p.get("default_vendor_name") or "",
        "product_id": p["id"],
        "product_snapshot": {
            "name": p.get("name"), "brand": p.get("brand"), "model": p.get("model"), "sku": p.get("sku"),
            "finish": p.get("finish"), "spec_summary": spec_summary or None,
            "price": latest.get("price"), "gst_pct": latest.get("gst_pct"), "price_valid_from": latest.get("valid_from"),
            "vendor_name": latest.get("vendor_name") or p.get("default_vendor_name"), "taken_at": iso_now(),
        },
    }


@router.get("/products/{product_id}/boq-line")
async def product_boq_line(product_id: str, request: Request, room: Optional[str] = None,
                           session_token: Optional[str] = Cookie(default=None),
                           authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    _require_access(user, READ)
    p = await _product(product_id)
    if p.get("status") == "discontinued":
        raise HTTPException(status_code=409, detail="This product is discontinued; pick a current one")
    return boq_line(p, _text(room, 60))
