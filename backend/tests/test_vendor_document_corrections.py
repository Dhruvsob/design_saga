"""Vendor document metadata correction regressions."""

import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from models.vendor import VendorDocumentUpdate
from routes import vendors


class _Vendors:
    def __init__(self):
        self.calls = []

    async def update_one(self, query, update):
        self.calls.append((query, update))
        return SimpleNamespace(matched_count=1)


def _install(monkeypatch, permissions):
    collection = _Vendors()
    audits = []

    async def require_user(*_args, **_kwargs):
        return {"user_id": "usr_1", "permissions": permissions}

    async def audit(*args, **kwargs):
        audits.append((args, kwargs))

    monkeypatch.setattr(vendors, "require_user", require_user)
    monkeypatch.setattr(vendors, "audit", audit)
    monkeypatch.setattr(vendors, "sdb", SimpleNamespace(vendors_acc=collection))
    return collection, audits


def test_vendor_document_metadata_edit_is_nested_scoped_and_audited(monkeypatch):
    collection, audits = _install(monkeypatch, ["vendors.update"])

    result = asyncio.run(vendors.update_vendor_document(
        "ven_1", "vdoc_1",
        VendorDocumentUpdate(label=" GST certificate ", kind="gst_certificate",
                             expires_on="2027-03-31"),
        object(), None, None,
    ))

    query, update = collection.calls[0]
    assert query == {"id": "ven_1", "documents.id": "vdoc_1"}
    assert update["$set"]["documents.$.label"] == "GST certificate"
    assert update["$set"]["documents.$.expires_on"] == "2027-03-31"
    assert result == {"ok": True, "id": "vdoc_1"}
    assert audits[0][0][1] == "vendor.document_update"
    assert audits[0][1]["meta"]["vendor_id"] == "ven_1"


def test_vendor_document_edit_rejects_invalid_expiry_before_database(monkeypatch):
    collection, _audits = _install(monkeypatch, ["vendors.update"])

    with pytest.raises(HTTPException) as exc:
        asyncio.run(vendors.update_vendor_document(
            "ven_1", "vdoc_1", VendorDocumentUpdate(expires_on="31/03/2027"),
            object(), None, None,
        ))

    assert exc.value.status_code == 422
    assert collection.calls == []


def test_vendor_document_edit_requires_vendor_update_permission(monkeypatch):
    collection, audits = _install(monkeypatch, ["vendors.read"])

    with pytest.raises(HTTPException) as exc:
        asyncio.run(vendors.update_vendor_document(
            "ven_1", "vdoc_1", VendorDocumentUpdate(label="New label"),
            object(), None, None,
        ))

    assert exc.value.status_code == 403
    assert collection.calls == []
    assert audits == []
