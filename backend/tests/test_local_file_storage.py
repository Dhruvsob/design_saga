import asyncio
from io import BytesIO

import pytest
from fastapi import UploadFile

from services import local_files


def test_content_type_uses_file_bytes_not_browser_claims():
    mime, extension = local_files.detect_content_type(b"%PDF-1.7\nexample", "drawing.pdf")
    assert mime == "application/pdf"
    assert extension == ".pdf"
    with pytest.raises(ValueError, match="does not match"):
        local_files.detect_content_type(b"<script>alert(1)</script>", "drawing.pdf")
    with pytest.raises(ValueError, match="Allowed file types"):
        local_files.detect_content_type(b"PK\x03\x04", "archive.zip")


def test_storage_keys_cannot_escape_the_tenant_root(tmp_path, monkeypatch):
    monkeypatch.setattr(local_files, "STORAGE_ROOT", tmp_path)
    expected = tmp_path / "org_demo" / ("a" * 32 + ".pdf")
    assert local_files.resolve_storage_key(f"org_demo/{'a' * 32}.pdf") == expected
    with pytest.raises(ValueError, match="Invalid storage key"):
        local_files.resolve_storage_key("../production.env")


def test_upload_is_private_and_removable(tmp_path, monkeypatch):
    monkeypatch.setattr(local_files, "STORAGE_ROOT", tmp_path)
    upload = UploadFile(filename="Site Plan.pdf", file=BytesIO(b"%PDF-1.7\nprivate"))
    result = asyncio.run(local_files.save_upload(upload, "org_demo"))
    stored = local_files.resolve_storage_key(result["storage_key"])

    assert stored.read_bytes() == b"%PDF-1.7\nprivate"
    assert result["content_type"] == "application/pdf"
    assert len(result["sha256"]) == 64
    local_files.remove_upload(result["storage_key"])
    assert not stored.exists()


def test_tenant_quota_prevents_disk_exhaustion(tmp_path, monkeypatch):
    monkeypatch.setattr(local_files, "STORAGE_ROOT", tmp_path)
    monkeypatch.setattr(local_files, "MAX_STORAGE_BYTES", 100)
    monkeypatch.setattr(local_files, "MAX_TENANT_STORAGE_BYTES", 10)
    upload = UploadFile(filename="large.txt", file=BytesIO(b"more than ten bytes"))
    with pytest.raises(ValueError, match="company file-storage quota"):
        asyncio.run(local_files.save_upload(upload, "org_demo"))
