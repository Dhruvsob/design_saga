"""Superseded drawing revisions are served stamped; current ones and the stored
originals are never changed."""
import asyncio
import io
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import core.stamp as stamp
import routes.drawings as drawings


def _pdf(sizes):
    from fpdf import FPDF
    pdf = FPDF(unit="pt")
    pdf.set_font("Helvetica", size=14)
    for w, h in sizes:
        pdf.add_page(format=(w, h))
        pdf.text(40, 60, "Ground floor plan")
    return bytes(pdf.output())


def _text(data):
    from pypdf import PdfReader
    return [p.extract_text() for p in PdfReader(io.BytesIO(data)).pages]


def test_pdf_every_page_is_stamped_whatever_its_size():
    original = _pdf([(595, 842), (1191, 842)])          # A4 portrait + A3 landscape
    out = stamp.stamp(original, "application/pdf", "C")
    pages = _text(out)
    assert len(pages) == 2
    for text in pages:
        assert "SUPERSEDED" in text and "revision C is current" in text and "Ground floor plan" in text


def test_image_is_stamped_and_keeps_its_size_and_format():
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (800, 500), "white").save(buf, "PNG")
    out = stamp.stamp(buf.getvalue(), "image/png", "B")
    with Image.open(io.BytesIO(out)) as im:
        assert im.format == "PNG" and im.size == (800, 500)
        assert im.convert("RGB").getpixel((400, 5)) != (255, 255, 255)        # red banner drawn
    jpg = io.BytesIO()
    Image.new("RGB", (300, 300), "white").save(jpg, "JPEG")
    with Image.open(io.BytesIO(stamp.stamp(jpg.getvalue(), "image/jpeg", "B"))) as im:
        assert im.format == "JPEG"


def test_other_types_pass_through_and_broken_pdf_raises():
    assert stamp.stamp(b"dwg-bytes", "application/acad", "B") == b"dwg-bytes"
    with pytest.raises(Exception):
        stamp.stamp(b"%PDF-1.4 not really", "application/pdf", "B")


# ---------------------------------------------------------------- route
@pytest.fixture
def drawing(monkeypatch, tmp_path):
    stored = tmp_path / "a101-a.pdf"
    stored.write_bytes(_pdf([(595, 842)]))
    files = {"f_a": {"id": "f_a", "project_id": "p1", "storage_key": "k_a", "content_type": "application/pdf",
                     "name": "A-101 rev A.pdf"},
             "f_b": {"id": "f_b", "project_id": "p1", "storage_key": "k_b", "content_type": "application/pdf",
                     "name": "A-101 rev B.pdf"}}
    d = {"id": "drw_1", "project_id": "p1", "number": "A-101",
         "revisions": [{"rev": "A", "file_id": "f_a", "status": "superseded"},
                       {"rev": "B", "file_id": "f_b", "status": "issued"}]}

    class Drawings:
        async def find_one(self, q, _p=None):
            return dict(d) if q.get("id") == "drw_1" else None

    class Files:
        async def find_one(self, q, _p=None):
            f = files.get(q.get("id"))
            return dict(f) if f and f["project_id"] == q.get("project_id") else None

    async def user(*_a, **_k):
        return {"user_id": "u", "org_id": "org_a", "permissions": ["files.read"]}

    async def visible(*_a, **_k):
        return {"id": "p1"}

    import services.local_files as lf
    monkeypatch.setattr(lf, "resolve_storage_key", lambda key: stored)
    monkeypatch.setattr(drawings, "sdb", SimpleNamespace(drawings=Drawings(), files=Files()))
    monkeypatch.setattr(drawings, "require_user", user)
    monkeypatch.setattr(drawings, "has_permission", lambda u, p: p in u["permissions"])
    monkeypatch.setattr(drawings, "get_visible_project", visible)
    return stored


def test_superseded_revision_is_served_stamped_and_the_original_is_untouched(drawing):
    before = drawing.read_bytes()
    resp = asyncio.run(drawings.revision_file("drw_1", "a", request=None))
    assert resp.headers["X-Superseded-Stamp"] == "applied"
    assert "SUPERSEDED" in resp.headers["content-disposition"]
    assert all("SUPERSEDED" in t for t in _text(resp.body))
    assert drawing.read_bytes() == before


def test_current_revision_is_served_as_is(drawing):
    resp = asyncio.run(drawings.revision_file("drw_1", "B", request=None))
    assert "X-Superseded-Stamp" not in resp.headers and resp.path == drawing


def test_unknown_revision_or_drawing_is_404(drawing):
    for args in (("drw_1", "Z"), ("drw_other_workspace", "A")):
        with pytest.raises(HTTPException) as exc:
            asyncio.run(drawings.revision_file(*args, request=None))
        assert exc.value.status_code == 404
