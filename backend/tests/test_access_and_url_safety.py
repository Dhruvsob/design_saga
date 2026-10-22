"""Focused regression tests for resource visibility and rendered URLs."""
import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from core.access_control import merge_query, require_permission
from core.url_security import external_http_url
from models.accounting import ExpenseIn
from models.expense import ExpenseLineIn
from models.task import Attachment, TaskIn
from models.vendor import VendorDocumentIn
from routes.organization import _sanitize_branding_update
from server import DocumentIn


@pytest.mark.parametrize("url", [
    "javascript:alert(1)",
    "data:text/html,<script>alert(1)</script>",
    "file:///etc/passwd",
    "//evil.example/path",
    "https://user:secret@example.com/file.pdf",
    "https://example.com:99999/file.pdf",
    "https://example.com/line\nbreak",
])
def test_external_urls_reject_unsafe_values(url):
    with pytest.raises(ValueError):
        external_http_url(url)


def test_external_urls_accept_http_and_https_and_trim_whitespace():
    assert external_http_url(" https://files.example.com/a.pdf ") == \
        "https://files.example.com/a.pdf"
    assert external_http_url("http://localhost:8080/file") == \
        "http://localhost:8080/file"


def test_all_attachment_models_use_the_shared_url_policy():
    with pytest.raises(ValidationError):
        Attachment(url="javascript:alert(1)")
    with pytest.raises(ValidationError):
        TaskIn(title="unsafe", reference_links=["data:text/html,bad"])
    with pytest.raises(ValidationError):
        VendorDocumentIn(label="unsafe", url="file:///tmp/a")
    with pytest.raises(ValidationError):
        DocumentIn(label="unsafe", url="javascript:alert(1)")
    with pytest.raises(ValidationError):
        ExpenseLineIn(category="travel", amount=1, receipt_url="javascript:x")
    with pytest.raises(ValidationError):
        ExpenseIn(
            date="2026-10-13", amount=1, expense_account_id="expense",
            paid_from_account_id="bank", bill_url="data:text/html,bad",
        )


def test_branding_update_cannot_replace_object_logo_with_inline_data():
    current = {
        "logo_url": "/api/org/logo/designsaga-erp/org-logos/org_1/"
                    "0123456789abcdef0123456789abcdef.png",
    }
    with pytest.raises(ValueError):
        _sanitize_branding_update(
            {"logo_url": "data:image/png;base64,AAAA"}, current, "org_1")


def test_branding_update_accepts_only_own_internal_logo():
    own = "/api/org/logo/designsaga-erp/org-logos/org_1/0123456789abcdef0123456789abcdef.png"
    assert _sanitize_branding_update({"logo_url": own}, {}, "org_1")["logo_url"] == own
    with pytest.raises(ValueError):
        _sanitize_branding_update({"logo_url": own}, {}, "org_2")


def test_permission_guard_and_query_merge():
    require_permission({"role": "Employee"}, "projects.read")
    with pytest.raises(HTTPException) as exc:
        require_permission({"role": "Employee"}, "projects.create")
    assert exc.value.status_code == 403
    assert merge_query({"archived": False}, {"team_ids": "emp_1"}) == {
        "$and": [{"archived": False}, {"team_ids": "emp_1"}]
    }
