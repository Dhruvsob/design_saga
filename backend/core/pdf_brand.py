"""Shared tenant branding for every generated PDF.

One letterhead, running header, footer, payment block and signatory block so
invoices, quotations, salary slips, payslips and statements always carry the
tenant's own logo and company details from Company Settings. Nothing is
invented: a missing field is simply omitted.
"""
from __future__ import annotations

import io
import textwrap
from collections import OrderedDict
from typing import Iterable, Optional

from fpdf import FPDF

INK = (20, 20, 20)
GREY = (100, 100, 100)
LINE = (220, 220, 220)
SOFT = (246, 247, 249)
PAGE_W = 210
LEFT = 15
RIGHT = 195
CONTENT_W = RIGHT - LEFT

_LOGO_CACHE: "OrderedDict[str, Optional[bytes]]" = OrderedDict()
_LOGO_CACHE_MAX = 32


def safe_text(value) -> str:
    """Latin-1 safe text for the built-in Helvetica font."""
    if value is None:
        return ""
    s = str(value)
    for k, v in {
        "–": "-", "—": "-", "‘": "'", "’": "'", "“": '"',
        "”": '"', "•": "*", "…": "...", "₹": "Rs.", "™": "TM",
        "©": "(c)", "·": "|",
    }.items():
        s = s.replace(k, v)
    return s.encode("latin-1", "replace").decode("latin-1")


# Design Saga brand taupe (primary button colour) — readable on white paper.
BRAND_PRIMARY = "#76705E"
BRAND_ACCENT = "#2C2C2C"
# Every company used to be created with this blue by default. Nobody chose it, so
# treat it as "not set" and print the brand colour instead.
LEGACY_DEFAULT_PRIMARY = "#002FA7"


def brand_primary_hex(branding: Optional[dict]) -> str:
    """The PDF accent colour for a company: its own choice, else the brand taupe."""
    value = ((branding or {}).get("primary_color") or "").strip()
    if not value or value.upper() == LEGACY_DEFAULT_PRIMARY:
        return BRAND_PRIMARY
    return value


def hex_to_rgb(value: Optional[str], default=(118, 112, 94)):
    try:
        h = (value or "").lstrip("#")
        if len(h) == 3:
            h = "".join(c * 2 for c in h)
        if len(h) != 6:
            return default
        return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    except (TypeError, ValueError):
        return default


def _raw_logo_bytes(logo_url: str) -> Optional[bytes]:
    if logo_url.startswith("data:"):
        from services import storage
        raw, _mime = storage.parse_data_url(logo_url)
        return raw
    marker = "/api/org/logo/"
    if marker in logo_url:
        from services import storage
        path = logo_url.split(marker, 1)[1]
        if not storage.LOGO_PATH_RE.match(path):
            return None
        data, _ctype = storage.get_object(path)
        return data
    # External http(s) logos are not fetched server-side (SSRF risk); tenants
    # upload logos through Company Settings so they are stored internally.
    return None


def logo_png(org: Optional[dict]) -> Optional[bytes]:
    """Tenant logo normalised to a PNG FPDF can embed (WebP/JPEG/PNG input)."""
    url = (((org or {}).get("branding") or {}).get("logo_url") or "").strip()
    if not url:
        return None
    if url in _LOGO_CACHE:
        _LOGO_CACHE.move_to_end(url)
        return _LOGO_CACHE[url]
    png = None
    try:
        raw = _raw_logo_bytes(url)
        if raw:
            from PIL import Image
            with Image.open(io.BytesIO(raw)) as img:
                img.load()
                if img.mode not in ("RGB", "RGBA"):
                    img = img.convert("RGBA")
                img.thumbnail((900, 900))
                buf = io.BytesIO()
                img.save(buf, format="PNG")
                png = buf.getvalue()
    except Exception:  # noqa: BLE001 - a broken logo must never block a PDF
        png = None
    _LOGO_CACHE[url] = png
    while len(_LOGO_CACHE) > _LOGO_CACHE_MAX:
        _LOGO_CACHE.popitem(last=False)
    return png


class Brand:
    """Display-ready company details derived from the organisation record."""

    def __init__(self, org: Optional[dict]):
        org = org or {}
        branding = org.get("branding") or {}
        self.org = org
        self.name = org.get("display_name") or org.get("name") or "Company"
        self.tagline = branding.get("tagline") or org.get("industry") or ""
        self.primary = hex_to_rgb(brand_primary_hex(branding))
        addr = org.get("address") or {}
        city_line = ", ".join(x for x in [addr.get("city"), addr.get("state")] if x)
        if addr.get("pincode"):
            city_line = f"{city_line} - {addr['pincode']}" if city_line else str(addr["pincode"])
        self.address_lines = [x for x in [addr.get("line1"), addr.get("line2"), city_line] if x]
        self.contact_line = "  |  ".join(
            str(x) for x in [org.get("phone"), org.get("email"), org.get("website")] if x)
        tax = []
        if org.get("gstin"):
            tax.append(f"GSTIN: {org['gstin']}")
        if org.get("pan"):
            tax.append(f"PAN: {org['pan']}")
        self.tax_line = "   ".join(tax)
        self.footer_note = branding.get("pdf_footer") or f"Thank you for choosing {self.name}."
        bank = org.get("bank_details") or {}
        self.bank_rows = [(label, bank.get(key)) for label, key in (
            ("Account name", "account_name"), ("Bank", "bank"), ("Account no.", "account"),
            ("IFSC", "ifsc"), ("UPI", "upi")) if bank.get(key)]
        if self.bank_rows and not bank.get("account_name"):
            self.bank_rows.insert(0, ("Account name", self.name))
        self.has_bank = any(bank.get(k) for k in ("bank", "account", "ifsc", "upi"))
        self.logo = logo_png(org)
        self.logo_ratio = 1.0
        if self.logo:
            try:
                from PIL import Image
                with Image.open(io.BytesIO(self.logo)) as img:
                    self.logo_ratio = max(0.2, min(5.0, img.width / max(1, img.height)))
            except Exception:  # noqa: BLE001
                self.logo = None


class BrandedPDF(FPDF):
    """A4 document with the tenant letterhead, running header and page footer."""

    def __init__(self, brand: Brand, doc_title: str, doc_number: str = "", *,
                 bottom_margin: float = 22):
        super().__init__(format="A4", unit="mm")
        self.brand = brand
        self.doc_title = doc_title
        self.doc_number = doc_number or ""
        self.set_margins(LEFT, 14, PAGE_W - RIGHT)
        self.set_auto_page_break(auto=True, margin=bottom_margin)
        self.alias_nb_pages()
        self.set_title(safe_text(f"{doc_title} {doc_number}".strip()))
        self.set_author(safe_text(brand.name))
        self.set_creator(safe_text(brand.name))

    # -- running header on continuation pages (page 1 uses the letterhead) --
    def header(self):
        self.set_fill_color(*self.brand.primary)
        self.rect(0, 0, PAGE_W, 2.5, "F")
        if self.page_no() == 1:
            return
        y = 7
        x = LEFT
        if self.brand.logo:
            try:
                w = min(9 * self.brand.logo_ratio, 26)
                self.image(io.BytesIO(self.brand.logo), x=LEFT, y=y, w=w, h=w / self.brand.logo_ratio)
                x = LEFT + w + 4
            except Exception:  # noqa: BLE001
                x = LEFT
        self.set_xy(x, y + 1)
        self.set_font("Helvetica", "B", 9.5)
        self.set_text_color(*INK)
        name = safe_text(self.brand.name.upper())
        room = 128 - x
        while name and self.get_string_width(name) > room:
            name = name[:-2].rstrip() + "."
        self.cell(room, 6, name, 0, 0)
        self.set_xy(130, y + 1)
        self.set_font("Helvetica", "", 8.5)
        self.set_text_color(*GREY)
        self.cell(RIGHT - 130, 6, safe_text(f"{self.doc_title}  {self.doc_number}".strip()), 0, 0, "R")
        self.set_draw_color(*LINE)
        self.set_line_width(0.3)
        self.line(LEFT, y + 10, RIGHT, y + 10)
        self.set_y(y + 14)

    def footer(self):
        self.set_y(-16)
        self.set_draw_color(*LINE)
        self.set_line_width(0.3)
        self.line(LEFT, self.get_y(), RIGHT, self.get_y())
        self.ln(1.5)
        self.set_font("Helvetica", "", 7.5)
        self.set_text_color(*GREY)
        left = self.brand.name + (f"  |  {self.brand.tax_line}" if self.brand.tax_line else "")
        self.cell(CONTENT_W * 0.7, 4, safe_text(left), 0, 0, "L")
        self.cell(CONTENT_W * 0.3, 4, f"Page {self.page_no()} of {{nb}}", 0, 1, "R")
        self.set_font("Helvetica", "I", 7.5)
        self.cell(CONTENT_W, 4, safe_text(
            f"{self.brand.footer_note}  This is a computer-generated document."), 0, 0, "C")

    def to_bytes(self) -> bytes:
        out = self.output()
        return out.encode("latin-1") if isinstance(out, str) else bytes(out)


def draw_letterhead(pdf: BrandedPDF, title: str,
                    meta_rows: Iterable[tuple[str, str]] = ()) -> float:
    """Full first-page letterhead. Returns the y position below it.

    Left column: logo then company name and details (wrapped to the column).
    Right column (fixed 55 mm): document title and meta rows. The columns can
    never overlap regardless of logo shape or text length.
    """
    b = pdf.brand
    top = 10.0
    meta_x = 140.0
    text_x = LEFT
    if b.logo:
        logo_h = 22.0
        logo_w = logo_h * b.logo_ratio
        if logo_w > 42:
            logo_w, logo_h = 42.0, 42.0 / b.logo_ratio
        try:
            pdf.image(io.BytesIO(b.logo), x=LEFT, y=top, w=logo_w, h=logo_h)
            text_x = LEFT + logo_w + 4
        except Exception:  # noqa: BLE001
            text_x = LEFT
    width = meta_x - 4 - text_x
    chars = max(24, int(width / 1.75))

    pdf.set_xy(text_x, top)
    pdf.set_font("Helvetica", "B", 13.5 if len(b.name) > 26 else 15)
    pdf.set_text_color(*INK)
    for part in wrap(b.name.upper(), max(16, int(width / 3.1)))[:2]:
        pdf.set_x(text_x)
        pdf.cell(width, 6.5, part, 0, 1)
    details = [("I", b.tagline)] + [("", x) for x in b.address_lines] +               [("", b.contact_line), ("", b.tax_line)]
    for style, value in details:
        if not value:
            continue
        pdf.set_font("Helvetica", style, 8.2)
        pdf.set_text_color(*GREY)
        for part in wrap(value, chars)[:2]:
            pdf.set_x(text_x)
            pdf.cell(width, 4.2, part, 0, 1)
    left_bottom = pdf.get_y()

    # Shrink long titles to the fixed right column; wrap as a last resort.
    pdf.set_xy(meta_x, top)
    pdf.set_text_color(*b.primary)
    title_text = safe_text(title.upper())
    size = 20.0
    pdf.set_font("Helvetica", "B", size)
    while size > 12 and pdf.get_string_width(title_text) > RIGHT - meta_x:
        size -= 0.5
        pdf.set_font("Helvetica", "B", size)
    if pdf.get_string_width(title_text) > RIGHT - meta_x:
        for part in wrap(title_text, 16)[:2]:
            pdf.set_x(meta_x)
            pdf.cell(RIGHT - meta_x, 6, part, 0, 1, "R")
    else:
        pdf.cell(RIGHT - meta_x, 9, title_text, 0, 1, "R")
    pdf.ln(1)
    for label, value in meta_rows:
        if value in (None, ""):
            continue
        pdf.set_x(meta_x)
        pdf.set_font("Helvetica", "", 8.3)
        pdf.set_text_color(*GREY)
        pdf.cell(22, 5, safe_text(label), 0, 0, "L")
        pdf.set_font("Helvetica", "B", 8.6)
        pdf.set_text_color(*INK)
        pdf.cell(RIGHT - meta_x - 22, 5, safe_text(str(value))[:24], 0, 1, "R")
    y = max(left_bottom, pdf.get_y(), top + 20) + 4
    pdf.set_draw_color(*b.primary)
    pdf.set_line_width(0.6)
    pdf.line(LEFT, y, RIGHT, y)
    pdf.set_line_width(0.3)
    pdf.set_y(y + 4)
    return y + 4


def section_label(pdf: FPDF, text: str) -> None:
    pdf.set_font("Helvetica", "B", 8)
    pdf.set_text_color(*GREY)
    pdf.cell(0, 5, safe_text(text.upper()), 0, 1)
    pdf.set_text_color(*INK)


def draw_bank_block(pdf: BrandedPDF, x: float = LEFT, width: float = 105) -> float:
    """Payment details box from Company Settings; returns its height (0 if none)."""
    b = pdf.brand
    if not b.has_bank:
        return 0
    y = pdf.get_y()
    value_chars = max(18, int((width - 36) / 1.95))
    rows = sum(min(2, len(wrap(str(v), value_chars))) for _, v in b.bank_rows)
    h = 9 + rows * 4.8 + 2
    pdf.set_fill_color(*SOFT)
    pdf.rect(x, y, width, h, "F")
    pdf.set_xy(x + 4, y + 2.5)
    pdf.set_font("Helvetica", "B", 8)
    pdf.set_text_color(*GREY)
    pdf.cell(width - 8, 4.5, "PAYMENT DETAILS", 0, 1)
    value_chars = max(18, int((width - 36) / 1.95))
    for label, value in b.bank_rows:
        parts = wrap(str(value), value_chars)[:2]
        for i, part in enumerate(parts):
            pdf.set_x(x + 4)
            pdf.set_font("Helvetica", "", 8.8)
            pdf.set_text_color(*GREY)
            pdf.cell(28, 4.8, safe_text(label) if i == 0 else "", 0, 0)
            pdf.set_font("Helvetica", "B", 8.8)
            pdf.set_text_color(*INK)
            pdf.cell(width - 36, 4.8, part, 0, 1)
    h = max(h, pdf.get_y() - y + 2)
    pdf.set_fill_color(*SOFT)
    pdf.set_y(y + h)
    return h


def draw_signatory(pdf: BrandedPDF, x: float = 125, width: float = 70) -> None:
    """'For <Company> / Authorised Signatory' block at the current y."""
    y = pdf.get_y()
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_text_color(*INK)
    lines = wrap(f"For {pdf.brand.name}", max(20, int(width / 1.95)))[:2]
    for i, part in enumerate(lines):
        pdf.set_xy(x, y + i * 4.6)
        pdf.cell(width, 4.6, part, 0, 0, "R")
    line_y = y + 22
    pdf.set_draw_color(*INK)
    pdf.line(x + 5, line_y, x + width, line_y)
    pdf.set_xy(x, line_y + 1)
    pdf.set_font("Helvetica", "", 8.5)
    pdf.set_text_color(*GREY)
    pdf.cell(width, 5, "Authorised Signatory", 0, 1, "R")


def wrap(text: str, width: int) -> list[str]:
    return textwrap.wrap(safe_text(text), width=width, break_long_words=True,
                         break_on_hyphens=False) or [""]
