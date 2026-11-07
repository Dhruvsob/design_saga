"""Regression guards for the bug sweep of 07/11/2026."""

import pytest
from pydantic import ValidationError

import server
from routes import payroll
from routes.notifications import _dmy


def test_payslip_attendance_matches_what_salary_was_calculated_from():
    # Ritika: 3 unpaid leave days deducted, but the slip used to show Leaves 0 / Absent 0.
    summary = {"present": 12, "late": 3, "site_visit": 0, "absent": 0, "half_day": 0,
               "paid_leave": 1, "unpaid_leave": 3, "week_off": 4, "holidays": 8}
    boxes = payroll._slip_attendance(summary, {"payable_days": 28, "lop_days": 3.0})
    assert boxes["present"] == 15 and boxes["unpaid_leave"] == 3 and boxes["paid_leave"] == 1
    assert boxes["offs"] == 12 and boxes["paid_days"] == 28 and boxes["lop_days"] == 3.0
    assert payroll._count(3.0) == "3" and payroll._count(2.5) == "2.5"


def test_salary_slip_pdf_renders_with_engine_boxes():
    run = {"year": 2026, "month": 10, "net": 25000, "status": "paid",
           "breakdown": {"basic": 25000, "gross": 25000, "deductions_total": 0, "net": 25000}}
    emp = {"first_name": "Ritika", "joining_date": "2026-09-01"}
    pdf = payroll._generate_salary_slip_pdf(emp, run, {"name": "DESIGN SAGA"},
                                            payroll._slip_attendance({"present": 20}, run["breakdown"]))
    assert pdf[:4] == b"%PDF"


def test_part_paid_invoices_count_what_was_received():
    invoices = [
        {"total": 600000, "paid_amount": 10000, "status": "partially_paid"},
        {"total": 50000, "status": "paid"},
        {"total": 9999, "status": "draft"},
        {"total": 8888, "status": "cancelled"},
        {"total": 7777, "status": "sent", "doc_type": "quotation"},
    ]
    billed, received = server._invoice_money(invoices)
    assert billed == 650000 and received == 60000


def test_dates_must_be_real_calendar_dates():
    server.InvoiceIn(due_date="2026-11-30")
    server.InvoiceIn(due_date="")                 # optional stays optional
    for bad in ("31-10-2026", "2026-02-30", "tomorrow", "2026-11-30T10:00:00"):
        with pytest.raises(ValidationError):
            server.InvoiceIn(due_date=bad)


def test_negative_money_and_quantities_are_refused():
    with pytest.raises(ValidationError):
        server.SalaryStructure(basic=-25000)
    with pytest.raises(ValidationError):
        server.ProjectIn(name="Villa", budget=-5)


def test_notification_dates_read_dd_mm_yyyy():
    assert _dmy("2026-11-07") == "07/11/2026"
    assert _dmy("") == ""


def test_foreign_site_cannot_post_even_without_a_session_cookie(monkeypatch):
    from types import SimpleNamespace
    from core import http_security as hs
    monkeypatch.setenv("CORS_ORIGINS", "https://gamaa.in")

    def req(origin=None, cookie=False, host="gamaa.in", method="POST"):
        headers = {"host": host}
        if origin:
            headers["origin"] = origin
        return SimpleNamespace(method=method, headers=headers,
                               cookies={"session_token": "t"} if cookie else {})

    assert hs.csrf_violation(req("https://evil.example"))                 # login CSRF blocked
    assert hs.csrf_violation(req("https://evil.example", cookie=True))    # classic CSRF blocked
    assert not hs.csrf_violation(req("https://gamaa.in"))                 # our own site
    assert not hs.csrf_violation(req(None))                               # API/server clients
    assert not hs.csrf_violation(req("https://evil.example", method="GET"))


def _sig_image(fmt="PNG", transparent=False):
    import io
    from PIL import Image, ImageDraw
    img = Image.new("RGBA" if transparent else "RGB", (400, 140), (0, 0, 0, 0) if transparent else "white")
    d = ImageDraw.Draw(img)
    d.line([(20, 100), (120, 30), (200, 110), (380, 40)], fill=(20, 20, 60, 255) if transparent else (20, 20, 60), width=6)
    out = io.BytesIO()
    img.save(out, fmt)
    return out.getvalue()


def test_signature_photo_on_white_paper_becomes_transparent_and_trimmed():
    import io
    from PIL import Image
    from services.storage import normalize_signature
    png = normalize_signature(_sig_image("JPEG"))                   # iPad photo / scan
    with Image.open(io.BytesIO(png)) as img:
        assert img.mode == "RGBA" and img.getpixel((0, 0))[3] == 0  # paper is gone
        assert img.width < 400 and img.height < 140                 # trimmed to the ink
    assert normalize_signature(_sig_image("PNG", transparent=True))[:4] == b"\x89PNG"
    import io as _io
    from PIL import Image as _Image
    blank = _io.BytesIO()
    _Image.new("RGB", (300, 100), "white").save(blank, "PNG")
    with pytest.raises(ValueError):                               # a blank page is not a signature
        normalize_signature(blank.getvalue())


def test_signature_prints_on_reminder_invoice_and_salary_slip(monkeypatch):
    from core import pdf_brand
    from routes import money_in
    sig = _sig_image("PNG", transparent=True)
    monkeypatch.setattr(pdf_brand, "signature_png", lambda org: sig if (org or {}).get("signature_path") else None)
    rem = {"number": "PR-0001", "party_name": "Client", "amount_due": 1000, "total_amount": 1000,
           "due_by": "2026-11-30", "created_at": "2026-11-07"}
    plain = money_in.generate_reminder_pdf(rem, {"name": "DESIGN SAGA"})
    signed = money_in.generate_reminder_pdf(rem, {"name": "DESIGN SAGA", "signature_path": "x"})
    assert signed.count(b"/Subtype /Image") > plain.count(b"/Subtype /Image")   # image (+ its transparency mask)
    inv = {"number": "INV-1", "doc_type": "invoice", "status": "sent", "items": [{"description": "Fee", "quantity": 1, "rate": 1000, "amount": 1000}],
           "subtotal": 1000, "tax": 0, "total": 1000, "issue_date": "2026-11-07"}
    assert server.generate_invoice_pdf(inv, {"name": "DESIGN SAGA", "signature_path": "x"}).count(b"/Subtype /Image") >= 1
    run = {"year": 2026, "month": 10, "net": 1000, "status": "paid",
           "breakdown": {"basic": 1000, "gross": 1000, "deductions_total": 0, "net": 1000}}
    slip = payroll._generate_salary_slip_pdf({"first_name": "A"}, run, {"name": "DESIGN SAGA", "signature_path": "x"},
                                             payroll._slip_attendance({}, run["breakdown"]))
    assert slip.count(b"/Subtype /Image") >= 1
