"""Generated-document inspection (FINAL_UI_UX_REVIEW.md, PDFs section).

Builds long synthetic documents in a fresh local workspace (a 45-line
quotation BOQ, a 40-line invoice, a 30-line purchase order, a payslip), then
opens each PDF with pypdf and checks what a client, supplier or employee
would notice: A4 pages, the table header repeated on every page of a long
table, full descriptions (nothing cut off), no internal margin column,
Indian digit grouping and totals that match the screen.

    PROBE_BASE=http://127.0.0.1:4174 QA_SUPERADMIN_EMAIL=... QA_PASSWORD=... \
    QA_PIN=... OUT_DIR=... python scripts/pdf_inspection.py
"""
from __future__ import annotations

import io
import os
import re
import sys
import uuid

sys.path.insert(0, os.path.dirname(__file__))
from accounting_acceptance import RESULTS, check, new_workspace, ok  # noqa: E402

from pypdf import PdfReader  # noqa: E402

OUT_DIR = os.environ.get("OUT_DIR")
A4 = (595.28, 841.89)
LONG = ("Supply and install 18 mm BWP plywood carcass with 1 mm laminate outside, "
        "0.8 mm liner inside, soft-close hinges and channels, edge banding on all "
        "exposed edges, as per drawing A-{n} revision R2; tail-{tag}")


def indian(value: float) -> str:
    rupees, paise = divmod(int(round(abs(value) * 100)), 100)
    s = str(rupees)
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        s = ",".join(parts + [tail])
    return f"{'-' if value < 0 else ''}{s}.{paise:02d}"


def read(c, url: str, name: str) -> tuple[PdfReader, list[str]]:
    res = c.get(url)
    if res.status_code != 200 or not res.content.startswith(b"%PDF"):
        raise RuntimeError(f"{url} -> {res.status_code} {res.headers.get('content-type')}")
    if OUT_DIR:
        with open(os.path.join(OUT_DIR, f"{name}.pdf"), "wb") as fh:
            fh.write(res.content)
    reader = PdfReader(io.BytesIO(res.content))
    return reader, [(page.extract_text() or "") for page in reader.pages]


def common(case: str, reader: PdfReader, pages: list[str], header: str, min_pages: int = 2) -> None:
    check(case, "multi-page", True, len(pages) >= min_pages)
    sizes = {(round(float(p.mediabox.width), 1), round(float(p.mediabox.height), 1)) for p in reader.pages}
    check(case, "every page is A4 portrait", {(round(A4[0], 1), round(A4[1], 1))}, sizes)
    table_pages = [i for i, t in enumerate(pages) if re.search(r"tail-[0-9a-f]{6}", t)]
    missing = [i + 1 for i in table_pages if header not in pages[i]]
    check(case, f"column header '{header}' repeated on every table page", [], missing)
    whole = "\n".join(pages)
    for bad in ("undefined", "NaN", "None", "[object"):
        check(case, f"no '{bad}' text", False, bad in whole)


def quotation(c, client_id: str) -> None:
    case = "quotation PDF"
    q = ok(c.post("/api/quotations-adv", json={
        "type": "turnkey", "project_title": "Fixture Residence, Juhu", "client_id": client_id,
        "project_location": "Juhu, Mumbai", "area_sqft": 2400}))
    tags = []
    boq = []
    for cat in ("Carpentry", "Civil & Finishes", "Electrical"):
        items = []
        for n in range(15):
            tag = uuid.uuid4().hex[:6]
            tags.append(tag)
            items.append({"description": LONG.format(n=101 + n, tag=tag), "unit": "sqft",
                          "quantity": 12.5 + n, "rate": 1850 + 37 * n, "margin_pct": 15,
                          "room": "Master Bedroom"})
        boq.append({"category": cat, "items": items})
    saved = ok(c.put(f"/api/quotations-adv/{q['id']}", json={"boq": boq}))
    grand = float((saved.get("cost") or {}).get("grand_total") or 0)
    reader, pages = read(c, f"/api/quotations-adv/{q['id']}/pdf", "quotation")
    whole = "\n".join(pages)
    common(case, reader, pages, "Rate (Rs.)")
    check(case, "no internal margin column (Mgn%)", False, "Mgn" in whole)
    flat = whole.replace("\n", " ")
    cut = [t for t in tags if f"tail-{t}" not in flat]
    check(case, "every long description printed in full", [], cut)
    first = boq[0]["items"][0]
    client_rate = round(first["rate"] * 1.15, 2)
    check(case, "client rate includes the margin (1,850 x 1.15)", True, indian(client_rate) in whole)
    check(case, "base cost rate not printed as the rate", False, f" {indian(first['rate'])} " in f" {flat} ")
    check(case, "grand total with Indian grouping matches the screen", True, indian(grand) in whole)


def invoice(c, client_id: str) -> None:
    case = "invoice PDF"
    tags, items = [], []
    for n in range(40):
        tag = uuid.uuid4().hex[:6]
        tags.append(tag)
        items.append({"description": LONG.format(n=201 + n, tag=tag), "quantity": 1 + n % 3,
                      "rate": 123456.78 + n})
    inv = ok(c.post("/api/invoices", json={"client_id": client_id, "doc_type": "invoice",
                                           "status": "draft", "tax_rate": 18, "items": items}))
    reader, pages = read(c, f"/api/invoices/{inv['id']}/pdf", "invoice")
    whole = "\n".join(pages)
    common(case, reader, pages, "DESCRIPTION", min_pages=3)
    flat = whole.replace("\n", " ")
    cut = [t for t in tags if f"tail-{t}" not in flat]
    check(case, "every long description printed in full", [], cut)
    check(case, "total with Indian grouping matches the screen", True, indian(float(inv["total"])) in whole)
    check(case, "amount in words present", True, "Amount in words" in whole)


def purchase_order(c) -> None:
    case = "purchase order PDF"
    vendor = ok(c.post("/api/vendors", json={"name": f"Fixture Joinery Works {uuid.uuid4().hex[:4]}"}))
    vid = vendor.get("id") or vendor.get("vendor", {}).get("id")
    tags, lines = [], []
    for n in range(30):
        tag = uuid.uuid4().hex[:6]
        tags.append(tag)
        lines.append({"item_name": f"Wardrobe module W{n + 1}", "description": LONG.format(n=301 + n, tag=tag),
                      "quantity": 2 + n % 4, "unit": "nos", "unit_price": 45250.5 + n, "tax_rate": 18})
    po = ok(c.post("/api/purchase-orders", json={"vendor_id": vid, "lines": lines,
                                                 "delivery_address": "Site: Juhu, Mumbai"}))
    po = po.get("purchase_order", po)
    reader, pages = read(c, f"/api/purchase-orders/{po['id']}/pdf", "purchase-order")
    whole = "\n".join(pages)
    common(case, reader, pages, "ITEM / DESCRIPTION", min_pages=3)
    flat = whole.replace("\n", " ")
    cut = [t for t in tags if f"tail-{t}" not in flat]
    check(case, "every specification printed in full (was cut at 58 characters)", [], cut)
    check(case, "grand total matches the screen", True, indian(float(po.get("grand_total") or 0)) in whole)


def payslip(c) -> None:
    case = "payslip PDF"
    emp = ok(c.post("/api/employees", json={
        "first_name": "Fixture", "last_name": "Designer", "email": f"fx-{uuid.uuid4().hex[:6]}@qa.example.com",
        "designation": "Interior Designer", "joining_date": "2026-04-01", "monthly_salary": 85000}))
    eid = emp.get("id") or emp.get("employee", {}).get("id")
    reader, pages = read(c, f"/api/payroll/payslip.pdf?employee_id={eid}&year=2026&month=10", "payslip")
    whole = "\n".join(pages)
    sizes = {(round(float(p.mediabox.width), 1), round(float(p.mediabox.height), 1)) for p in reader.pages}
    check(case, "A4 portrait", {(round(A4[0], 1), round(A4[1], 1))}, sizes)
    check(case, "employee name printed", True, "Fixture" in whole)
    check(case, "period printed", True, bool(re.search(r"Oct(ober)?\s*2026|10/2026|2026-10", whole)))
    for bad in ("undefined", "NaN", "None"):
        check(case, f"no '{bad}' text", False, bad in whole)


def main() -> None:
    c = new_workspace()
    client = ok(c.post("/api/clients", json={"name": "Fixture Client With A Deliberately Long Name Private Limited"}))
    for fn in (lambda: quotation(c, client["id"]), lambda: invoice(c, client["id"]),
               lambda: purchase_order(c), lambda: payslip(c)):
        try:
            fn()
        except Exception as exc:  # report and continue
            RESULTS.append({"case": "pdf", "check": "ran", "expected": "no error",
                            "observed": str(exc)[:300], "pass": False})
            print("ERROR", exc)
    failed = [r for r in RESULTS if r["pass"] is False]
    print(f"\n{len(RESULTS)} checks, {len(failed)} failed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
