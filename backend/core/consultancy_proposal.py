"""Consultancy design proposal (letter-style quotation).

Modelled on the firm's own consultancy proposal format: greeting, project
details, scope of work, design process & approvals, design fees & payment
schedule, material procurement, communication, optional site-coordination
support and a signed closing. Every section is editable per quotation; empty
sections are left out of the PDF and the document flows naturally across
pages (no section-per-page gaps).

Money is exact to the paisa (core.money); the fee schedule always adds up to
the total fee.
"""
from __future__ import annotations

import re
from decimal import Decimal
from typing import Optional

from core.money import round_paise, to_decimal

MAX_ITEMS = 40
MAX_TEXT = 1200
MAX_SHORT = 160

DEFAULT_PROPOSAL = {
    "salutation": "Mr.",
    "greeting_name": "",
    "intro": ("Here is a simple overview of what we will be doing together for your space. "
              "This note includes what is covered, the design fees, and how we will move forward."),
    "scope_summary": "Interior Design Consultancy & Execution Coordination",
    "process_clauses": [
        ("The project scope includes one proposed design direction along with {revisions} additional "
         "revision/alternative concept, if required, during the concept stage. Further redesigns beyond "
         "this shall be considered additional scope and charged separately."),
        ("All design revisions and modifications are to be finalized during the 3D/concept stage. Once the "
         "3D design is approved and working drawings are initiated, further design changes will not be "
         "entertained. Any exceptional changes, if feasible, may involve additional charges and revised "
         "timelines."),
        ("{renders} final render view is included within the project scope after approval of the finalized "
         "3D design. Any additional render options, revisions, or changes thereafter will be charged "
         "separately."),
    ],
    "revisions_included": 1,
    "renders_included": 1,
    "fee": {
        "total_fee": 0,
        "advance_amount": 0,
        "instalment_amount": 0,
        "instalment_every_months": 2,
        "extra_work_note": "Any extra work outside the agreed scope will be discussed and charged separately.",
    },
    "procurement_note": ("We will guide you in selecting materials and finishes, but the actual buying or "
                         "placing orders will be handled by the client."),
    "communication_note": ("We will communicate mainly through WhatsApp/Telegram, and all drawings and updates "
                           "will be shared in a WhatsApp/Telegram group that includes the client, designer, "
                           "and all involved agencies, so everyone stays on the same page."),
    "office_phone": "",
    "site_coordinator": {
        "enabled": False,
        "monthly_fee": 0,
        "duties": [
            "Coordinating between vendors, agencies, designer, and client",
            "Following up on site-related communication and updates",
            "Assisting with execution coordination for smoother workflow",
            "Ensuring all involved parties remain updated on ongoing work",
            "Following up on material deliveries",
        ],
        "note": ("The Site Coordinator's role is limited to communication and coordination support only. "
                 "This role does not include Project Management Consultancy (PMC), site supervision, "
                 "quality checks, labour management, or execution responsibility."),
    },
    "closing": "Looking forward to creating something special together!",
    "signatory_name": "",
    "signatory_title": "Principal Designer",
}

DEFAULT_SCOPE = [
    "Concept development (Basic 3D model)",
    "Working drawings",
    "Site visits",
    "Material and finishes selection",
    "Vendor coordination (if required)",
]

SALUTATIONS = ["Mr.", "Ms.", "Mrs.", "Dr.", "M/s.", ""]


def _text(value, limit=MAX_TEXT) -> str:
    return re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", str(value or "")).strip()[:limit]


def _items(values, limit=MAX_ITEMS) -> list:
    if not isinstance(values, list):
        return []
    out = [_text(v, MAX_TEXT) for v in values]
    return [v for v in out if v][:limit]


def _money(value) -> float:
    try:
        d = to_decimal(value or 0)
    except Exception:  # noqa: BLE001
        return 0.0
    if d < 0 or d > Decimal("100000000000"):
        raise ValueError("Amounts must be between 0 and 10,000 crore")
    return float(round_paise(d))


def _count(value, lo=0, hi=50) -> int:
    try:
        return max(lo, min(hi, int(value)))
    except (TypeError, ValueError):
        return lo


def default_proposal(*, client_name: str = "", org: Optional[dict] = None, user: Optional[dict] = None) -> dict:
    import copy
    p = copy.deepcopy(DEFAULT_PROPOSAL)
    p["greeting_name"] = client_name or ""
    p["office_phone"] = (org or {}).get("phone") or ""
    p["signatory_name"] = (user or {}).get("name") or ""
    return p


def clean_proposal(raw: Optional[dict], existing: Optional[dict] = None) -> dict:
    """Whitelist and normalise a proposal payload (raises ValueError on bad money)."""
    base = dict(existing or DEFAULT_PROPOSAL)
    raw = raw if isinstance(raw, dict) else {}
    merged = {**base, **{k: v for k, v in raw.items() if k in DEFAULT_PROPOSAL}}
    fee_in = {**(base.get("fee") or {}), **(raw.get("fee") or {})} if isinstance(raw.get("fee", {}), dict) else base.get("fee") or {}
    sc_in = {**(base.get("site_coordinator") or {}), **(raw.get("site_coordinator") or {})} \
        if isinstance(raw.get("site_coordinator", {}), dict) else base.get("site_coordinator") or {}

    salutation = _text(merged.get("salutation"), 8)
    fee = {
        "total_fee": _money(fee_in.get("total_fee")),
        "advance_amount": _money(fee_in.get("advance_amount")),
        "instalment_amount": _money(fee_in.get("instalment_amount")),
        "instalment_every_months": _count(fee_in.get("instalment_every_months"), 1, 12) or 1,
        "extra_work_note": _text(fee_in.get("extra_work_note"), MAX_TEXT),
    }
    if fee["advance_amount"] > fee["total_fee"] and fee["total_fee"] > 0:
        raise ValueError("The advance cannot be more than the total fee")
    if fee["instalment_amount"] > fee["total_fee"] and fee["total_fee"] > 0:
        raise ValueError("The instalment cannot be more than the total fee")
    return {
        "salutation": salutation if salutation in SALUTATIONS else "",
        "greeting_name": _text(merged.get("greeting_name"), MAX_SHORT),
        "intro": _text(merged.get("intro")),
        "scope_summary": _text(merged.get("scope_summary"), MAX_SHORT),
        "process_clauses": _items(merged.get("process_clauses")),
        "revisions_included": _count(merged.get("revisions_included"), 0, 20),
        "renders_included": _count(merged.get("renders_included"), 0, 50),
        "fee": fee,
        "procurement_note": _text(merged.get("procurement_note")),
        "communication_note": _text(merged.get("communication_note")),
        "office_phone": _text(merged.get("office_phone"), 40),
        "site_coordinator": {
            "enabled": bool(sc_in.get("enabled")),
            "monthly_fee": _money(sc_in.get("monthly_fee")),
            "duties": _items(sc_in.get("duties"), 20),
            "note": _text(sc_in.get("note")),
        },
        "closing": _text(merged.get("closing"), 400),
        "signatory_name": _text(merged.get("signatory_name"), MAX_SHORT),
        "signatory_title": _text(merged.get("signatory_title"), MAX_SHORT),
    }


def fee_schedule(fee: dict) -> list[dict]:
    """Advance, then equal instalments; the last instalment takes the remainder.

    Returns [] when no total fee is set. Always sums exactly to total_fee.
    """
    total = round_paise(to_decimal(fee.get("total_fee") or 0))
    if total <= 0:
        return []
    advance = min(round_paise(to_decimal(fee.get("advance_amount") or 0)), total)
    step = round_paise(to_decimal(fee.get("instalment_amount") or 0))
    every = int(fee.get("instalment_every_months") or 1)
    rows = []
    if advance > 0:
        rows.append({"label": "Advance on confirmation", "month": 0, "amount": float(advance)})
    balance = total - advance
    if balance <= 0:
        return rows
    if step <= 0:
        rows.append({"label": "Balance fee", "month": None, "amount": float(balance)})
        return rows
    n = 0
    while balance > 0 and n < 120:
        n += 1
        part = min(step, balance)
        rows.append({"label": f"Instalment {n}", "month": n * every, "amount": float(part)})
        balance -= part
    return rows


def render_clause(text: str, proposal: dict) -> str:
    words = {0: "no", 1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six"}
    rev = proposal.get("revisions_included", 1)
    ren = proposal.get("renders_included", 1)
    out = text.replace("{revisions}", words.get(rev, str(rev)))
    ren_word = words.get(ren, str(ren))
    out = out.replace("{renders}", ren_word[:1].upper() + ren_word[1:])
    return out


def inr_plain(amount) -> str:
    """Indian grouping without paise when whole: 600000 -> 'Rs. 6,00,000/-'."""
    d = round_paise(to_decimal(amount or 0))
    rupees = int(d)
    paise = int((d - rupees) * 100)
    s = str(abs(rupees))
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        s = ",".join(parts + [tail])
    sign = "-" if rupees < 0 else ""
    return f"Rs. {sign}{s}.{paise:02d}" if paise else f"Rs. {sign}{s}/-"


# --------------------------------------------------------------------------- PDF
def generate_proposal_pdf(doc: dict, org: Optional[dict] = None) -> bytes:
    from core.pdf_brand import (Brand, BrandedPDF, CONTENT_W, GREY, INK, LEFT, LINE, SOFT,
                                draw_bank_block, draw_letterhead, safe_text)

    brand = Brand(org)
    pdf = BrandedPDF(brand, "Design Proposal", doc.get("number") or "")
    p = clean_proposal(doc.get("proposal") or {}, DEFAULT_PROPOSAL)
    fee = p["fee"]
    cost = doc.get("cost") or {}
    firm = brand.name

    def date_text(value):
        from datetime import datetime
        try:
            return datetime.strptime(str(value)[:10], "%Y-%m-%d").strftime("%d/%m/%Y")
        except ValueError:
            return str(value or "")[:10]

    pdf.add_page()
    y = draw_letterhead(pdf, "Proposal", [
        ("Proposal No.", doc.get("number") or "-"),
        ("Date", date_text(doc.get("date") or doc.get("created_at"))),
        ("Version", doc.get("version_label") or "v1"),
    ])
    pdf.set_y(y + 4)

    bottom = pdf.h - pdf.b_margin

    def ensure(space):
        if pdf.get_y() + space > bottom:
            pdf.add_page()

    def heading(text):
        # keep the heading with at least two lines of its section
        ensure(22)
        pdf.ln(3)
        pdf.set_x(LEFT)
        pdf.set_font("Helvetica", "B", 10.5)
        pdf.set_text_color(*brand.primary)
        pdf.cell(CONTENT_W, 6, safe_text(text.upper()), 0, 1)
        pdf.set_draw_color(*LINE)
        pdf.set_line_width(0.3)
        pdf.line(LEFT, pdf.get_y(), LEFT + CONTENT_W, pdf.get_y())
        pdf.ln(2)
        pdf.set_text_color(*INK)

    def para(text, size=9.6, style=""):
        if not text:
            return
        pdf.set_x(LEFT)
        pdf.set_font("Helvetica", style, size)
        pdf.set_text_color(*INK)
        pdf.multi_cell(CONTENT_W, 5, safe_text(text))

    def dot(x, y, sub=False):
        pdf.set_fill_color(*(GREY if sub else INK))
        r = 0.55 if sub else 0.75
        pdf.ellipse(x + 1.4 - r, y + 2.5 - r, 2 * r, 2 * r, "F")

    def bullet(text, indent=0.0, mark="dot"):
        if not text:
            return
        ensure(6)
        x = LEFT + indent
        pdf.set_font("Helvetica", "", 9.6)
        pdf.set_text_color(*INK)
        dot(x, pdf.get_y(), sub=(mark == "-"))
        pdf.set_x(x + 5)
        pdf.multi_cell(CONTENT_W - indent - 5, 5, safe_text(text))
        pdf.ln(0.6)

    def kv(label, value):
        if not value:
            return
        ensure(6)
        dot(LEFT, pdf.get_y())
        pdf.set_x(LEFT + 5)
        pdf.set_font("Helvetica", "B", 9.6)
        pdf.cell(26, 5, safe_text(f"{label}:"), 0, 0)
        pdf.set_font("Helvetica", "", 9.6)
        pdf.multi_cell(CONTENT_W - 31, 5, safe_text(value))
        pdf.ln(0.6)

    # ---- title + greeting
    pdf.set_x(LEFT)
    pdf.set_font("Helvetica", "B", 15)
    pdf.set_text_color(*INK)
    pdf.cell(CONTENT_W, 8, "DESIGN PROPOSAL & WORK DETAILS", 0, 1)
    pdf.ln(1)
    name = p["greeting_name"] or doc.get("client_name") or ""
    greet = " ".join(x for x in [p["salutation"], name] if x).strip()
    para(f"Greetings, {greet}," if greet else "Greetings,", style="B")
    pdf.ln(1)
    para(p["intro"])

    # ---- project details
    heading("Project details")
    kv("Project", doc.get("project_title"))
    kv("Location", doc.get("project_location"))
    if float(doc.get("area_sqft") or 0) > 0:
        kv("Area", f"{float(doc['area_sqft']):g} sq.ft")
    kv("Scope", p["scope_summary"])
    kv("Designer", firm)

    # ---- scope of work
    scope = doc.get("design_scope") or []
    if scope:
        heading("Scope of work")
        for item in scope:
            bullet(item)
    if doc.get("exclusions"):
        heading("Not included")
        for item in doc["exclusions"]:
            bullet(item)

    # ---- process & approvals
    if p["process_clauses"]:
        heading("Design process & approvals")
        for clause in p["process_clauses"]:
            bullet(render_clause(clause, p))

    # ---- fees
    schedule = fee_schedule(fee)
    if fee["total_fee"] > 0:
        heading("Design fees & payment schedule")
        bullet(f"The total professional design fee for the project shall be a fixed amount of "
               f"{inr_plain(fee['total_fee'])}.")
        if fee["advance_amount"] > 0:
            bullet(f"An initial advance of {inr_plain(fee['advance_amount'])} shall be payable at the time of "
                   f"project confirmation to commence the design process.")
        if fee["instalment_amount"] > 0:
            every = fee["instalment_every_months"]
            period = "every month" if every == 1 else f"once every {every} months"
            bullet(f"Thereafter, {inr_plain(fee['instalment_amount'])} shall be payable {period} during the "
                   f"project duration until the total fee is paid.")
        tax_pct = float(cost.get("tax_pct") or 0)
        if tax_pct > 0:
            bullet(f"GST at {tax_pct:g}% ({inr_plain(cost.get('tax_amt'))}) is payable in addition, making the "
                   f"total {inr_plain(cost.get('grand_total'))}.")
        bullet(fee["extra_work_note"])

        # one-line fee summary (the full instalment list lives in the ERP)
        cells = [("Total design fee", inr_plain(fee["total_fee"]))]
        if fee["advance_amount"] > 0:
            cells.append(("Advance on confirmation", inr_plain(fee["advance_amount"])))
        instalments = [r for r in schedule if r["label"].startswith("Instalment")]
        if instalments:
            every = fee["instalment_every_months"]
            cells.append((f"Then every {every} month{'s' if every > 1 else ''}", inr_plain(fee["instalment_amount"])))
            last = instalments[-1]["amount"]
            plan = f"{len(instalments)}"
            if len(instalments) > 1 and last != fee["instalment_amount"]:
                plan += f" (last {inr_plain(last)})"
            cells.append(("Instalments", plan))
        elif len(schedule) > 1:
            cells.append(("Balance", inr_plain(schedule[-1]["amount"])))
        if float(cost.get("tax_pct") or 0) > 0:
            cells.append(("Total incl. GST", inr_plain(cost.get("grand_total"))))
        ensure(18)
        pdf.ln(1.5)
        top = pdf.get_y()
        w = CONTENT_W / len(cells)
        pdf.set_fill_color(*SOFT)
        pdf.set_draw_color(*LINE)
        pdf.rect(LEFT, top, CONTENT_W, 13, "DF")
        for i, (label, value) in enumerate(cells):
            x = LEFT + i * w
            if i:
                pdf.line(x, top + 2, x, top + 11)
            pdf.set_xy(x + 3, top + 2)
            pdf.set_font("Helvetica", "", 7.4)
            pdf.set_text_color(*GREY)
            pdf.cell(w - 6, 4, safe_text(label.upper()), 0, 2)
            pdf.set_x(x + 3)
            pdf.set_font("Helvetica", "B", 9.6 if len(value) < 22 else 8.4)
            pdf.set_text_color(*INK)
            pdf.cell(w - 6, 5, safe_text(value), 0, 0)
        pdf.set_y(top + 15)

    # ---- procurement / communication
    if p["procurement_note"]:
        heading("Material procurement")
        bullet(p["procurement_note"])
    if p["communication_note"] or p["office_phone"]:
        heading("Communication")
        bullet(p["communication_note"])
        if p["office_phone"]:
            bullet(f"Here is our office number {p['office_phone']}")

    # ---- optional site coordinator
    sc = p["site_coordinator"]
    if sc["enabled"]:
        heading("Optional site coordination support")
        fee_text = f" at an additional charge of {inr_plain(sc['monthly_fee'])} per month" if sc["monthly_fee"] else ""
        bullet(f"For the convenience and smoother coordination of the project, {firm} can appoint a dedicated "
               f"Site Coordinator{fee_text}.")
        if sc["duties"]:
            bullet("The Site Coordinator's responsibilities will include:")
            for duty in sc["duties"]:
                bullet(duty, indent=6, mark="-")
        if sc["note"]:
            bullet(f"Please note: {sc['note']}")

    # ---- other terms carried on the quotation
    terms = [t for t in (doc.get("terms") or []) if (t.get("content") or "").strip()]
    if terms:
        heading("Terms")
        for t in terms:
            label = (t.get("section") or "").strip()
            bullet(f"{label}: {t['content']}" if label else t["content"])

    # ---- closing + signatory (kept together)
    ensure(48 if brand.has_bank else 34)
    pdf.ln(4)
    para(p["closing"], style="I")
    pdf.ln(5)
    pdf.set_x(LEFT)
    pdf.set_font("Helvetica", "", 9.6)
    pdf.cell(CONTENT_W, 5, "Regards,", 0, 1)
    sign_top = pdf.get_y()
    pdf.set_font("Helvetica", "B", 10)
    if p["signatory_name"]:
        pdf.set_x(LEFT)
        pdf.cell(90, 5, safe_text(p["signatory_name"]), 0, 1)
    pdf.set_font("Helvetica", "", 9.6)
    if p["signatory_title"]:
        pdf.set_x(LEFT)
        pdf.cell(90, 5, safe_text(p["signatory_title"]), 0, 1)
    pdf.set_x(LEFT)
    pdf.cell(90, 5, safe_text(f"{firm}."), 0, 1)
    # client acceptance on the right
    pdf.set_xy(125, sign_top + 10)
    pdf.set_draw_color(*INK)
    pdf.set_line_width(0.3)
    pdf.line(125, sign_top + 10, 195, sign_top + 10)
    pdf.set_xy(125, sign_top + 11)
    pdf.set_font("Helvetica", "", 8.5)
    pdf.set_text_color(*GREY)
    pdf.cell(70, 4.5, safe_text(f"Accepted by {greet or 'client'}"), 0, 1, "C")
    pdf.set_x(125)
    pdf.cell(70, 4.5, "Signature & date", 0, 1, "C")
    pdf.set_text_color(*INK)
    if brand.has_bank:
        pdf.set_y(max(pdf.get_y(), sign_top + 22) + 4)
        ensure(30)
        draw_bank_block(pdf, LEFT, 110)
    return pdf.to_bytes()
