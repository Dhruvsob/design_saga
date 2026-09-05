"""Emergent Object Storage adapter.

Thin wrapper around the Emergent objstore v1 API. One session-scoped
`storage_key` is fetched at startup (or on-demand) and reused for every
subsequent request. All paths are prefixed with `APP_NAME` to isolate this
tenant's data from other apps sharing the platform.

Public helpers:
- `init_storage()`      – fetch a session key (idempotent)
- `put_object(...)`     – upload raw bytes at a given logical path
- `get_object(...)`     – fetch raw bytes back
- `upload_data_url(...)`- convenience for browser data-URL uploads
"""
import base64
import logging
import os
import re
import uuid
from typing import Optional, Tuple

import requests

logger = logging.getLogger("storage")

STORAGE_URL = "https://integrations.emergentagent.com/objstore/api/v1/storage"
APP_NAME = "designsaga-erp"
_EMERGENT_KEY: Optional[str] = os.environ.get("EMERGENT_LLM_KEY")

_storage_key: Optional[str] = None


MIME_TO_EXT = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/jpg": "jpg",
    "image/webp": "webp",
    "image/gif": "gif",
    "image/svg+xml": "svg",
    "application/pdf": "pdf",
}

MAX_LOGO_BYTES = 2 * 1024 * 1024   # 2MB decoded
ALLOWED_LOGO_MIME = {"image/png", "image/jpeg", "image/jpg", "image/webp", "image/svg+xml"}


def init_storage(force: bool = False) -> Optional[str]:
    """Fetch (or return cached) session storage key.

    Returns None if the Emergent key is unset – callers may then fall back to
    storing the payload inline. Failures are logged but never raised so the
    ERP keeps working even if object storage is temporarily unavailable.
    """
    global _storage_key
    if _storage_key and not force:
        return _storage_key
    key = _EMERGENT_KEY or os.environ.get("EMERGENT_LLM_KEY")
    if not key:
        logger.warning("EMERGENT_LLM_KEY missing – object storage disabled")
        return None
    try:
        resp = requests.post(f"{STORAGE_URL}/init",
                             json={"emergent_key": key}, timeout=15)
        resp.raise_for_status()
        _storage_key = resp.json()["storage_key"]
        return _storage_key
    except Exception as e:  # noqa: BLE001
        logger.error(f"Storage init failed: {e}")
        return None


def put_object(path: str, data: bytes, content_type: str) -> dict:
    key = init_storage()
    if not key:
        raise RuntimeError("Object storage not initialised")
    resp = requests.put(
        f"{STORAGE_URL}/objects/{path}",
        headers={"X-Storage-Key": key, "Content-Type": content_type},
        data=data, timeout=60,
    )
    if resp.status_code == 403:
        # Session expired – refresh and retry once.
        init_storage(force=True)
        key = _storage_key
        resp = requests.put(
            f"{STORAGE_URL}/objects/{path}",
            headers={"X-Storage-Key": key, "Content-Type": content_type},
            data=data, timeout=60,
        )
    resp.raise_for_status()
    return resp.json()


def get_object(path: str) -> Tuple[bytes, str]:
    key = init_storage()
    if not key:
        raise RuntimeError("Object storage not initialised")
    resp = requests.get(
        f"{STORAGE_URL}/objects/{path}",
        headers={"X-Storage-Key": key}, timeout=30,
    )
    if resp.status_code == 403:
        init_storage(force=True)
        key = _storage_key
        resp = requests.get(
            f"{STORAGE_URL}/objects/{path}",
            headers={"X-Storage-Key": key}, timeout=30,
        )
    resp.raise_for_status()
    return resp.content, resp.headers.get("Content-Type", "application/octet-stream")


_DATA_URL_RE = re.compile(r"^data:(?P<mime>[^;]+);base64,(?P<data>.+)$", re.DOTALL)


def parse_data_url(data_url: str) -> Tuple[bytes, str]:
    """Decode a browser `data:<mime>;base64,<...>` URL to (bytes, mime)."""
    m = _DATA_URL_RE.match(data_url or "")
    if not m:
        raise ValueError("Invalid data URL")
    mime = m.group("mime").lower()
    try:
        raw = base64.b64decode(m.group("data"))
    except Exception as e:
        raise ValueError(f"base64 decode failed: {e}")
    return raw, mime


def upload_data_url(data_url: str, folder: str, owner_id: str,
                    allowed_mimes: Optional[set] = None,
                    max_bytes: int = MAX_LOGO_BYTES) -> dict:
    """Upload a data URL to object storage.

    Returns a dict: {path, mime, size, object_url}
    Raises ValueError on invalid input.
    """
    raw, mime = parse_data_url(data_url)
    if allowed_mimes and mime not in allowed_mimes:
        raise ValueError(f"Content type {mime} not allowed")
    if len(raw) > max_bytes:
        raise ValueError(f"File too large: {len(raw)}B > {max_bytes}B")

    ext = MIME_TO_EXT.get(mime, "bin")
    path = f"{APP_NAME}/{folder}/{owner_id}/{uuid.uuid4().hex}.{ext}"
    result = put_object(path, raw, mime)
    return {
        "path": result.get("path", path),
        "mime": mime,
        "size": result.get("size", len(raw)),
        "etag": result.get("etag"),
    }
