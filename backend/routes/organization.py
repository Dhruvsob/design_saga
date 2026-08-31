"""Organization (Company Admin) routes — the /api/org/* namespace.

Company Admins manage their own workspace here. Endpoints:
- GET  /api/org/current              — resolve the current user's org
- PATCH /api/org/current             — update branding / display name / etc
- POST /api/org/current/logo         — upload logo (multipart or base64 data URL)
- GET  /api/org/logo/{path}          — proxy-download a stored logo
- GET  /api/org/public/{slug}        — anon endpoint for Login page branding

Any authenticated user in an org can READ; only Admin/Director can WRITE.
Logo storage lives in Emergent Object Storage (see services/storage.py) so
Mongo documents never grow unbounded.
"""
from fastapi import APIRouter, HTTPException, Request, Cookie, Header, Body, UploadFile, File
from fastapi.responses import Response as FastAPIResponse
from typing import Optional
import logging

from core.db import db
from core.helpers import iso_now, new_id
from core.deps import require_user
from core.tenancy import (
    require_org_context, user_org_id, is_super_admin, DEFAULT_ORG_ID,
    get_org,
)
from core.rbac import has_permission
from models.organization import BrandingUpdateIn
from services import storage as _storage


router = APIRouter(prefix="/org")
_log = logging.getLogger("org")


DEFAULT_BRANDING = {
    "primary_color": "#002FA7",
    "accent_color": "#0A0A0A",
    "tagline": "Studio OS · v0.2",
    "logo_url": None,
}


def _pack_org(o: dict) -> dict:
    """Public projection of an org doc."""
    if not o:
        return o
    out = {k: v for k, v in o.items() if k not in ("_id", "notes")}
    out.setdefault("branding", {})
    for k, v in DEFAULT_BRANDING.items():
        out["branding"].setdefault(k, v)
    # Ensure business_mode + features are always present for the UI
    out.setdefault("business_mode", "hybrid")
    from models.organization import features_for_mode
    features = out.get("features") or {}
    modules = features.get("modules") or {}
    # Fill any missing keys from the mode preset (safety net)
    for k, v in features_for_mode(out["business_mode"]).items():
        modules.setdefault(k, v)
    features["modules"] = modules
    out["features"] = features
    return out


# ------------------------------------------------------------------
# CURRENT ORG
# ------------------------------------------------------------------
@router.get("/current")
async def get_current_org(user=None, request: Request = None,
                          session_token: Optional[str] = Cookie(default=None),
                          authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    oid = user_org_id(user)
    o = await get_org(oid)
    if not o:
        # Bootstrap default org for legacy installs
        o = await get_org(DEFAULT_ORG_ID)
    return _pack_org(o) if o else {"org_id": None}


@router.patch("/current")
async def update_current_org(payload: BrandingUpdateIn, request: Request,
                             session_token: Optional[str] = Cookie(default=None),
                             authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    if not (has_permission(user, "*.*") or has_permission(user, "settings.update")):
        raise HTTPException(403, "Admin only")
    oid = user_org_id(user)
    if not oid:
        raise HTTPException(400, "No organisation context")
    org = await get_org(oid)
    if not org:
        raise HTTPException(404, "Organisation not found")

    up = {k: v for k, v in payload.dict(exclude_unset=True).items() if v is not None}
    if "address" in up and hasattr(up["address"], "dict"):
        up["address"] = up["address"].dict()
    if "branding" in up and hasattr(up["branding"], "dict"):
        # merge with existing branding
        existing = org.get("branding") or {}
        merged = {**existing, **up["branding"].dict(exclude_unset=True)}
        up["branding"] = merged
    up["updated_at"] = iso_now()
    up["updated_by"] = user["user_id"]
    await db.organizations.update_one({"org_id": oid}, {"$set": up}, upsert=True)
    return _pack_org(await get_org(oid))


@router.post("/current/logo")
async def upload_logo(request: Request,
                      session_token: Optional[str] = Cookie(default=None),
                      authorization: Optional[str] = Header(default=None),
                      payload: dict = Body(...)):
    """Accepts {logo_data_url: "data:image/png;base64,...."} or {logo_url: "..."}.

    Data-URL payloads are streamed straight into Emergent Object Storage; the
    org's `branding.logo_url` is then set to the internal proxy URL
    `/api/org/logo/{path}` (auth cookie required to view).
    Falling back to inline base64 storage only if the object-storage upload
    fails — that keeps the ERP usable in offline environments.
    """
    user = await require_user(request, session_token, authorization)
    if not has_permission(user, "*.*"):
        raise HTTPException(403, "Admin only")
    oid = user_org_id(user)
    if not oid:
        raise HTTPException(400, "No organisation context")
    logo = payload.get("logo_data_url") or payload.get("logo_url")
    if not logo:
        raise HTTPException(400, "logo_data_url or logo_url required")

    stored_logo_value = logo
    storage_meta = None

    if isinstance(logo, str) and logo.startswith("data:"):
        # Guard on decoded size (~1.37× base64 overhead)
        if len(logo) > 2_800_000:
            raise HTTPException(413, "Logo too large. Please upload an image under 2MB.")
        try:
            info = _storage.upload_data_url(
                logo, folder="org-logos", owner_id=oid,
                allowed_mimes=_storage.ALLOWED_LOGO_MIME,
            )
            stored_logo_value = f"/api/org/logo/{info['path']}"
            storage_meta = {
                "path": info["path"],
                "mime": info["mime"],
                "size": info["size"],
                "uploaded_at": iso_now(),
            }
        except ValueError as e:
            raise HTTPException(400, str(e))
        except Exception as e:  # noqa: BLE001
            _log.warning(f"Object-storage upload failed – falling back to inline: {e}")
            stored_logo_value = logo  # inline fallback
    # else: external URL was supplied directly

    update = {"branding.logo_url": stored_logo_value,
              "updated_at": iso_now(),
              "updated_by": user["user_id"]}
    if storage_meta:
        update["branding.logo_storage"] = storage_meta
    await db.organizations.update_one({"org_id": oid}, {"$set": update}, upsert=True)
    return {"ok": True, "logo_url": stored_logo_value, "storage": storage_meta}


@router.post("/current/logo/upload")
async def upload_logo_multipart(request: Request,
                                file: UploadFile = File(...),
                                session_token: Optional[str] = Cookie(default=None),
                                authorization: Optional[str] = Header(default=None)):
    """Multipart alternative to the JSON data-URL upload. Same result."""
    user = await require_user(request, session_token, authorization)
    if not has_permission(user, "*.*"):
        raise HTTPException(403, "Admin only")
    oid = user_org_id(user)
    if not oid:
        raise HTTPException(400, "No organisation context")
    if file.content_type not in _storage.ALLOWED_LOGO_MIME:
        raise HTTPException(415, f"Unsupported content type: {file.content_type}")
    data = await file.read()
    if len(data) > _storage.MAX_LOGO_BYTES:
        raise HTTPException(413, "Logo too large (>2MB).")
    import uuid as _uuid
    ext = _storage.MIME_TO_EXT.get(file.content_type, "bin")
    path = f"{_storage.APP_NAME}/org-logos/{oid}/{_uuid.uuid4().hex}.{ext}"
    try:
        result = _storage.put_object(path, data, file.content_type)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"Storage error: {e}")
    stored_path = result.get("path", path)
    logo_url = f"/api/org/logo/{stored_path}"
    await db.organizations.update_one(
        {"org_id": oid},
        {"$set": {"branding.logo_url": logo_url,
                  "branding.logo_storage": {
                      "path": stored_path, "mime": file.content_type,
                      "size": result.get("size", len(data)),
                      "uploaded_at": iso_now(),
                  },
                  "updated_at": iso_now(),
                  "updated_by": user["user_id"]}},
        upsert=True,
    )
    return {"ok": True, "logo_url": logo_url,
            "storage": {"path": stored_path, "mime": file.content_type,
                        "size": result.get("size", len(data))}}


@router.get("/logo/{full_path:path}")
async def download_logo(full_path: str):
    """Public proxy for org logos.

    Logos are branding assets shown on the pre-auth login screen, so no
    auth check is enforced here. The `full_path` is opaque (UUID under
    a per-org prefix) so it cannot be guessed.
    """
    try:
        data, ctype = _storage.get_object(full_path)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(404, f"Logo not found: {e}")
    return FastAPIResponse(content=data, media_type=ctype,
                           headers={"Cache-Control": "public, max-age=3600"})


# ------------------------------------------------------------------
# PUBLIC BRANDING — for the Login page pre-auth
# ------------------------------------------------------------------
@router.get("/public/{slug}")
async def public_branding(slug: str):
    o = await db.organizations.find_one({"slug": slug}, {"_id": 0})
    if not o:
        raise HTTPException(404, "Org not found")
    return {
        "org_id": o.get("org_id"),
        "slug": o.get("slug"),
        "name": o.get("name"),
        "display_name": o.get("display_name") or o.get("name"),
        "branding": (o.get("branding") or {}),
    }
