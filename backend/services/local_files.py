"""Tenant-isolated, content-validated storage for user-uploaded documents."""
from __future__ import annotations

import hashlib
import threading
import os
import re
import uuid
import zipfile
from io import BytesIO
from pathlib import Path

from fastapi import UploadFile


MAX_FILE_BYTES = 15 * 1024 * 1024
MAX_STORAGE_BYTES = int(os.environ.get("FILE_STORAGE_MAX_BYTES", 5 * 1024 * 1024 * 1024))
MAX_TENANT_STORAGE_BYTES = int(os.environ.get("FILE_STORAGE_TENANT_MAX_BYTES", 512 * 1024 * 1024))
STORAGE_ROOT = Path(os.environ.get("FILE_STORAGE_ROOT", "/data/files"))
_STORAGE_LOCK = threading.Lock()

_SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9._ -]+")
_EXTENSION_MIME = {
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".csv": "text/csv",
    ".txt": "text/plain",
}


def clean_filename(value: str | None) -> str:
    name = Path(value or "document").name.strip()
    name = _SAFE_NAME_RE.sub("_", name).strip(" .")
    return (name or "document")[:180]


def _ooxml_type(raw: bytes) -> str | None:
    try:
        with zipfile.ZipFile(BytesIO(raw)) as archive:
            names = set(archive.namelist())
            if "[Content_Types].xml" not in names:
                return None
            if any(name.startswith("word/") for name in names):
                return _EXTENSION_MIME[".docx"]
            if any(name.startswith("xl/") for name in names):
                return _EXTENSION_MIME[".xlsx"]
    except (OSError, zipfile.BadZipFile):
        return None
    return None


def detect_content_type(raw: bytes, filename: str) -> tuple[str, str]:
    """Return a verified MIME and extension; reject active or ambiguous formats."""
    suffix = Path(filename).suffix.lower()
    expected = _EXTENSION_MIME.get(suffix)
    if not expected:
        raise ValueError("Allowed file types: PDF, PNG, JPG, WebP, DOCX, XLSX, CSV and TXT")

    detected = None
    if raw.startswith(b"%PDF-"):
        detected = "application/pdf"
    elif raw.startswith(b"\x89PNG\r\n\x1a\n"):
        detected = "image/png"
    elif raw[:3] == b"\xff\xd8\xff":
        detected = "image/jpeg"
    elif len(raw) >= 12 and raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
        detected = "image/webp"
    elif raw.startswith(b"PK\x03\x04"):
        detected = _ooxml_type(raw)
    elif suffix in {".csv", ".txt"}:
        if b"\x00" in raw:
            raise ValueError("Text files cannot contain binary data")
        try:
            raw.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise ValueError("CSV and TXT uploads must be UTF-8") from exc
        detected = expected

    if detected != expected:
        raise ValueError("File content does not match its extension")
    return detected, ".jpg" if suffix == ".jpeg" else suffix


def resolve_storage_key(storage_key: str) -> Path:
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}/[a-f0-9]{32}\.[a-z0-9]{2,5}", storage_key or ""):
        raise ValueError("Invalid storage key")
    root = STORAGE_ROOT.resolve()
    target = (root / storage_key).resolve()
    if root not in target.parents:
        raise ValueError("Invalid storage path")
    return target


async def save_upload(upload: UploadFile, org_id: str) -> dict:
    filename = clean_filename(upload.filename)
    raw = await upload.read(MAX_FILE_BYTES + 1)
    if not raw:
        raise ValueError("The selected file is empty")
    if len(raw) > MAX_FILE_BYTES:
        raise ValueError("File is larger than the 15 MB limit")
    content_type, extension = detect_content_type(raw, filename)

    safe_org = re.sub(r"[^A-Za-z0-9_-]", "_", org_id)[:64]
    storage_key = f"{safe_org}/{uuid.uuid4().hex}{extension}"
    target = resolve_storage_key(storage_key)
    with _STORAGE_LOCK:
        root = STORAGE_ROOT.resolve()
        tenant_root = target.parent
        global_usage = sum(p.stat().st_size for p in root.rglob("*") if p.is_file()) if root.exists() else 0
        tenant_usage = sum(p.stat().st_size for p in tenant_root.glob("*") if p.is_file()) if tenant_root.exists() else 0
        if global_usage + len(raw) > MAX_STORAGE_BYTES:
            raise ValueError("File storage capacity is full; contact the administrator")
        if tenant_usage + len(raw) > MAX_TENANT_STORAGE_BYTES:
            raise ValueError("Your company file-storage quota has been reached")
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        temporary = target.with_suffix(target.suffix + ".tmp")
        temporary.write_bytes(raw)
        os.chmod(temporary, 0o600)
        temporary.replace(target)
    return {
        "storage_key": storage_key,
        "original_name": filename,
        "content_type": content_type,
        "size": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
    }


def remove_upload(storage_key: str | None) -> None:
    if not storage_key:
        return
    try:
        resolve_storage_key(storage_key).unlink(missing_ok=True)
    except (OSError, ValueError):
        # Database deletion must not fail because an already-missing blob cannot
        # be removed. Orphan detection is handled by the operational audit.
        return
