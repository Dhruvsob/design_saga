"""Tenant branding on every generated PDF and self-hosted logo storage."""
import base64
import io

import pytest
from PIL import Image

import server
from core import pdf_brand
from routes import payroll
from services import storage

LOGO_PATH = "designsaga-erp/org-logos/org_test/" + "a" * 32 + ".png"


def _png_bytes(size=(120, 48)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGBA", size, (139, 127, 106, 255)).save(buf, "PNG")
    return buf.getvalue()


def _org(logo_url=None):
    return {
        "display_name": "Sample Studio", "gstin": "TESTGSTIN00000", "phone": "+91 00000 00000",
        "address": {"line1": "Line 1", "city": "Ahmedabad", "state": "Gujarat", "pincode": "380001"},
        "bank_details": {"bank": "Test Bank", "account": "000000000000", "ifsc": "TEST0000000"},
        "branding": {"logo_url": logo_url, "primary_color": "#8B7F6A", "tagline": "Architecture"},
    }


@pytest.fixture(autouse=True)
def _clear_logo_cache():
    pdf_brand._LOGO_CACHE.clear()
    yield
    pdf_brand._LOGO_CACHE.clear()


def test_logo_storage_falls_back_to_local_volume_without_object_store(monkeypatch, tmp_path):
    monkeypatch.setattr(storage, "init_storage", lambda force=False: None)
    monkeypatch.setenv("FILE_STORAGE_ROOT", str(tmp_path))
    result = storage.put_object(LOGO_PATH, _png_bytes(), "image/png")
    assert result["backend"] == "local"
    data, ctype = storage.get_object(LOGO_PATH)
    assert ctype == "image/png" and data.startswith(b"\x89PNG")
    assert (tmp_path / "branding" / LOGO_PATH).is_file()


@pytest.mark.parametrize("path", ["../../etc/passwd", "designsaga-erp/org-logos/x/../../y.png",
                                  "designsaga-erp/other/org/" + "a" * 32 + ".png"])
def test_local_logo_storage_rejects_paths_outside_the_logo_allowlist(monkeypatch, tmp_path, path):
    monkeypatch.setattr(storage, "init_storage", lambda force=False: None)
    monkeypatch.setenv("FILE_STORAGE_ROOT", str(tmp_path))
    with pytest.raises(RuntimeError):
        storage.put_object(path, b"x", "image/png")


def test_invoice_pdf_embeds_logo_and_company_details():
    logo = "data:image/png;base64," + base64.b64encode(_png_bytes()).decode()
    doc = {"doc_type": "invoice", "number": "INV-1", "status": "sent", "client_name": "Client",
           "items": [{"description": "Design", "quantity": 1, "rate": 1000}], "tax_rate": 18}
    server.compute_invoice_totals(doc)
    pdf = server.generate_invoice_pdf(doc, _org(logo))
    assert pdf.startswith(b"%PDF") and b"/Subtype /Image" in pdf


def test_quotation_pdf_embeds_logo():
    logo = "data:image/png;base64," + base64.b64encode(_png_bytes((60, 120))).decode()
    pdf = server.generate_quotation_pdf_adv(
        {"type": "consultancy", "number": "QT-1", "project_title": "Residence"}, _org(logo))
    assert pdf.startswith(b"%PDF") and b"/Subtype /Image" in pdf


def test_pdfs_still_render_without_a_logo_or_with_a_broken_logo():
    doc = {"doc_type": "invoice", "number": "INV-2", "items": [], "tax_rate": 0}
    server.compute_invoice_totals(doc)
    for logo in (None, "data:image/png;base64,bm90LWFuLWltYWdl"):
        pdf = server.generate_invoice_pdf(doc, _org(logo))
        assert pdf.startswith(b"%PDF") and b"/Subtype /Image" not in pdf


def test_external_logo_urls_are_never_fetched_server_side(monkeypatch):
    def boom(*_a, **_k):
        raise AssertionError("no outbound fetch")
    monkeypatch.setattr(storage, "get_object", boom)
    assert pdf_brand.logo_png(_org("https://attacker.example/logo.png")) is None


def test_salary_slip_masks_employee_bank_account():
    assert payroll._mask_account("123456789012") == "XXXXXXXX9012"
    assert payroll._mask_account("") == "-"
