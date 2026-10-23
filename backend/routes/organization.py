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


def _sanitize_branding_update(branding: dict, existing: dict, org_id: str) -> dict:
    """Validate browser-rendered asset URLs and preserve legacy inline logos."""
    cleaned = dict(branding or {})
    current_logo = (existing or {}).get("logo_url")
    if "logo_url" in cleaned and cleaned["logo_url"] is not None:
        logo_url = cleaned["logo_url"]
        if not isinstance(logo_url, str):
            raise ValueError("Logo URL must be text")
        if logo_url.startswith("/api/org/logo/"):
            path = logo_url.removeprefix("/api/org/logo/")
            if (not _storage.LOGO_PATH_RE.fullmatch(path)
                    or path.split("/", 3)[2] != org_id):
                raise ValueError("Logo does not belong to this organisation")
        elif logo_url.startswith("data:"):
            # The upload endpoint may retain an inline logo only when object
            # storage is unavailable. Do not let the general settings route
            # introduce or replace large inline payloads.
            if logo_url != current_logo:
                raise ValueError("Upload logos through the logo endpoint")
        else:
            from core.url_security import external_http_url
            cleaned["logo_url"] = external_http_url(logo_url)

    if cleaned.get("favicon_url") is not None:
        from core.url_security import external_http_url
        cleaned["favicon_url"] = external_http_url(cleaned["favicon_url"])
    return cleaned


def _safe_branding_projection(branding: dict, org_id: str) -> dict:
    """Drop unsafe legacy asset values before returning branding to a browser."""
    cleaned = dict(branding or {})
    logo_url = cleaned.get("logo_url")
    if logo_url:
        try:
            if logo_url.startswith("/api/org/logo/"):
                path = logo_url.removeprefix("/api/org/logo/")
                if (not _storage.LOGO_PATH_RE.fullmatch(path)
                        or path.split("/", 3)[2] != org_id):
                    raise ValueError("Invalid internal logo")
            elif logo_url.startswith("data:"):
                raw, mime = _storage.parse_data_url(logo_url)
                if mime not in _storage.ALLOWED_LOGO_MIME:
                    raise ValueError("Unsupported inline logo")
                _storage.validate_logo_bytes(raw, mime)
            else:
                from core.url_security import external_http_url
                cleaned["logo_url"] = external_http_url(logo_url)
        except (AttributeError, TypeError, ValueError):
            cleaned["logo_url"] = None

    if cleaned.get("favicon_url"):
        from core.url_security import external_http_url
        try:
            cleaned["favicon_url"] = external_http_url(cleaned["favicon_url"])
        except (TypeError, ValueError):
            cleaned["favicon_url"] = None
    return cleaned


def _pack_org(o: dict) -> dict:
    """Public projection of an org doc."""
    if not o:
        return o
    out = {k: v for k, v in o.items() if k not in ("_id", "notes")}
    out["branding"] = _safe_branding_projection(
        out.get("branding") or {}, out.get("org_id") or DEFAULT_ORG_ID)
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
        try:
            incoming = _sanitize_branding_update(
                up["branding"].dict(exclude_unset=True), existing, oid)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        merged = {**existing, **incoming}
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
    Storage failures are returned to the caller. Inline base64 is never
    persisted because it bypasses the hardened raster-object path and can
    bloat every organisation response.
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
            _log.warning("Object-storage logo upload failed: %s", type(e).__name__)
            raise HTTPException(
                503, "Logo storage is temporarily unavailable. Try again later.") from e
    else:
        from core.url_security import external_http_url
        try:
            stored_logo_value = external_http_url(logo)
        except ValueError as e:
            raise HTTPException(400, f"Invalid logo URL: {e}")

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
    data = await file.read(_storage.MAX_LOGO_BYTES + 1)
    if len(data) > _storage.MAX_LOGO_BYTES:
        raise HTTPException(413, "Logo too large (>2MB).")
    try:
        _storage.validate_logo_bytes(data, file.content_type)
    except ValueError as e:
        raise HTTPException(415, str(e))
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
    # Only logo objects written by this app may be proxied; anything else in
    # the shared object store (other folders/apps, traversal) is refused.
    if not _storage.LOGO_PATH_RE.match(full_path or ""):
        raise HTTPException(404, "Logo not found")
    owner_org_id = full_path.split("/", 3)[2]
    owner = await db.organizations.find_one(
        {"org_id": owner_org_id, "is_active": {"$ne": False}}, {"_id": 0, "org_id": 1})
    if not owner:
        raise HTTPException(404, "Logo not found")
    try:
        data, ctype = _storage.get_object(full_path)
    except Exception:  # noqa: BLE001
        raise HTTPException(404, "Logo not found")
    headers = {
        "Cache-Control": "public, max-age=3600",
        "X-Content-Type-Options": "nosniff",
        # Legacy SVG logos cannot execute script when opened directly.
        "Content-Security-Policy": "default-src 'none'; img-src 'self' data:; style-src 'unsafe-inline'; sandbox",
    }
    if (ctype or "").split(";")[0].strip().lower() not in (
            "image/png", "image/jpeg", "image/webp", "image/gif", "image/svg+xml"):
        ctype = "application/octet-stream"
        headers["Content-Disposition"] = "attachment"
    return FastAPIResponse(content=data, media_type=ctype, headers=headers)


# ------------------------------------------------------------------
# PUBLIC BRANDING — for the Login page pre-auth
# ------------------------------------------------------------------
@router.get("/public/{slug}")
async def public_branding(slug: str):
    o = await db.organizations.find_one({
        "slug": slug,
        "is_active": {"$ne": False},
        "is_suspended": {"$ne": True},
    }, {"_id": 0})
    if not o:
        raise HTTPException(404, "Org not found")
    return {
        "org_id": o.get("org_id"),
        "slug": o.get("slug"),
        "name": o.get("name"),
        "display_name": o.get("display_name") or o.get("name"),
        "branding": _safe_branding_projection(
            o.get("branding") or {}, o.get("org_id") or DEFAULT_ORG_ID),
    }
