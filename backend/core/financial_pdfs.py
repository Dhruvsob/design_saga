"""Branded finance documents shared by accounting and procurement routes."""
from __future__ import annotations

from datetime import date as _date
from typing import Optional

from core.pdf_brand import (
    Brand,
    BrandedPDF,
    CONTENT_W,
    GREY,
    INK,
    LEFT,
    LINE,
    RIGHT,
    SOFT,
    draw_letterhead,
    draw_signatory,
    safe_text,
    section_label,
    wrap,
)


def display_date(value) -> str:
    try:
        return _date.fromisoformat(str(value or "")[:10]).strftime("%d/%m/%Y")
    except ValueError:
        return str(value or "-")[:10] or "-"


def inr(value) -> str:
    amount = round(float(value or 0), 2)
    whole, paise = divmod(round(abs(amount) * 100), 100)
    digits = str(int(whole))
    if len(digits) > 3:
        head, tail = digits[:-3], digits[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        digits = ",".join(groups + [tail])
    return f"{'-' if amount < 0 else ''}Rs. {digits}" + (f".{paise:02d}" if paise else "")


def _detail_lines(pdf: BrandedPDF, rows: list[tuple[str, object]]) -> None:
    for label, value in rows:
        if value in (None, ""):
            continue
        pdf.set_x(LEFT)
        pdf.set_font("Helvetica", "", 8.5)
        pdf.set_text_color(*GREY)
        pdf.cell(39, 5.5, safe_text(label), 0, 0)
        pdf.set_font("Helvetica", "B", 9)
        pdf.set_text_color(*INK)
        text = safe_text(value)
        parts = wrap(text, 86)[:3]
        pdf.cell(CONTENT_W - 39, 5.5, parts[0], 0, 1)
        for part in parts[1:]:
            pdf.set_x(LEFT + 39)
            pdf.cell(CONTENT_W - 39, 5.5, part, 0, 1)


def generate_payment_receipt_pdf(receipt: dict, org: Optional[dict] = None) -> bytes:
    brand = Brand(org)
    number = receipt.get("number") or receipt.get("id") or "Receipt"
    pdf = BrandedPDF(brand, "Payment Receipt", str(number))
    pdf.add_page()
    draw_letterhead(pdf, "PAYMENT RECEIPT", [
        ("Receipt No.", number),
        ("Date", display_date(receipt.get("date"))),
        ("Status", str(receipt.get("status") or "Received").replace("_", " ").title()),
    ])

    pdf.set_fill_color(*SOFT)
    pdf.rect(LEFT, pdf.get_y(), CONTENT_W, 27, "F")
    pdf.set_xy(LEFT + 5, pdf.get_y() + 4)
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(*GREY)
    pdf.cell(CONTENT_W - 10, 5, "AMOUNT RECEIVED", 0, 1)
    pdf.set_x(LEFT + 5)
    pdf.set_font("Helvetica", "B", 22)
    pdf.set_text_color(*brand.primary)
    pdf.cell(CONTENT_W - 10, 12, safe_text(inr(receipt.get("amount"))), 0, 1)
    pdf.set_y(pdf.get_y() + 8)

    section_label(pdf, "Received from")
    _detail_lines(pdf, [
        ("Payer", receipt.get("party_name") or "Not specified"),
        ("Project", receipt.get("project_name")),
        ("For", receipt.get("collection_name") or receipt.get("source_label")),
        ("Payment method", receipt.get("payment_method_label") or receipt.get("payment_method")),
        ("Received into", receipt.get("account_name")),
        ("Reference", receipt.get("reference")),
        ("Notes", receipt.get("notes") or receipt.get("narration")),
    ])

    if str(receipt.get("status") or "").lower() in {"reversed", "cancelled"}:
        pdf.ln(4)
        pdf.set_fill_color(255, 239, 239)
        pdf.set_text_color(145, 30, 30)
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(CONTENT_W, 10, "THIS RECEIPT HAS BEEN REVERSED", 0, 1, "C", fill=True)
    pdf.ln(9)
    draw_signatory(pdf, 125, 70)
    return pdf.to_bytes()


def generate_purchase_order_pdf(po: dict, org: Optional[dict] = None,
                                vendor: Optional[dict] = None,
                                project: Optional[dict] = None) -> bytes:
    brand = Brand(org)
    number = po.get("po_number") or po.get("id") or "Purchase order"
    pdf = BrandedPDF(brand, "Purchase Order", str(number))
    pdf.add_page()
    draw_letterhead(pdf, "PURCHASE ORDER", [
        ("PO No.", number),
        ("Order date", display_date(po.get("order_date"))),
        ("Delivery", display_date(po.get("expected_delivery")) if po.get("expected_delivery") else "-"),
        ("Status", str(po.get("status") or "draft").replace("_", " ").title()),
    ])

    top = pdf.get_y()
    for x, label, values in (
        (LEFT, "VENDOR", [
            (vendor or {}).get("name") or po.get("vendor_name") or "-",
            (vendor or {}).get("address"), (vendor or {}).get("phone"), (vendor or {}).get("email"),
        ]),
        (110, "DELIVER TO", [
            po.get("delivery_address") or "Address not specified",
            (project or {}).get("name") and f"Project: {(project or {}).get('name')}",
            po.get("reference") and f"Reference: {po.get('reference')}",
        ]),
    ):
        pdf.set_xy(x, top)
        section_label(pdf, label)
        for index, value in enumerate(v for v in values if v):
            for part in wrap(str(value), 43)[:2]:
                pdf.set_x(x)
                pdf.set_font("Helvetica", "B" if index == 0 else "", 9.4 if index == 0 else 8.4)
                pdf.set_text_color(*(INK if index == 0 else GREY))
                pdf.cell(85, 4.8, part, 0, 1)
    pdf.set_y(max(pdf.get_y(), top + 24) + 5)

    widths = [9, 65, 18, 16, 27, 17, 28]
    headers = ["#", "ITEM / DESCRIPTION", "QTY", "UNIT", "RATE", "TAX", "AMOUNT"]

    def table_header() -> None:
        pdf.set_x(LEFT)
        pdf.set_fill_color(*brand.primary)
        pdf.set_text_color(255, 255, 255)
        pdf.set_font("Helvetica", "B", 7.7)
        for width, label in zip(widths, headers):
            pdf.cell(width, 7.5, label, 0, 0, "R" if label in {"QTY", "RATE", "TAX", "AMOUNT"} else "L", fill=True)
        pdf.ln()

    table_header()
    for index, line in enumerate(po.get("lines") or [], 1):
        if pdf.get_y() > pdf.h - 37:
            pdf.add_page()
            table_header()
        qty = float(line.get("quantity") or 0)
        rate = float(line.get("unit_price") or 0)
        amount = round(qty * rate, 2)
        description = str(line.get("item_name") or "Item")
        if line.get("description"):
            description += f" - {line['description']}"
        values = [str(index), safe_text(description)[:58], f"{qty:g}", line.get("unit") or "-",
                  inr(rate).replace("Rs. ", ""), f"{float(line.get('tax_rate') or 0):g}%",
                  inr(amount).replace("Rs. ", "")]
        pdf.set_x(LEFT)
        pdf.set_font("Helvetica", "", 8.2)
        pdf.set_text_color(*INK)
        for width, value, label in zip(widths, values, headers):
            pdf.cell(width, 7, safe_text(value), "B", 0,
                     "R" if label in {"QTY", "RATE", "TAX", "AMOUNT"} else "L")
        pdf.ln()

    pdf.ln(3)
    totals = [
        ("Subtotal", po.get("subtotal")),
        ("Tax", po.get("tax_total")),
        ("Grand total", po.get("grand_total")),
    ]
    for label, value in totals:
        pdf.set_x(125)
        pdf.set_font("Helvetica", "B" if label == "Grand total" else "", 10 if label == "Grand total" else 9)
        pdf.set_text_color(*(brand.primary if label == "Grand total" else INK))
        pdf.cell(35, 7, label, 0, 0)
        pdf.cell(35, 7, safe_text(inr(value)), 0, 1, "R")

    if po.get("payment_terms") or po.get("notes"):
        pdf.ln(3)
        section_label(pdf, "Terms and notes")
        for text in (po.get("payment_terms"), po.get("notes")):
            if text:
                pdf.set_font("Helvetica", "", 8.7)
                pdf.set_text_color(*INK)
                for part in wrap(str(text), 115):
                    pdf.cell(CONTENT_W, 4.8, part, 0, 1)
    pdf.ln(7)
    draw_signatory(pdf, 125, 70)
    return pdf.to_bytes()


def generate_client_statement_pdf(client: dict, rows: list[dict], summary: dict,
                                  org: Optional[dict] = None,
                                  from_date: Optional[str] = None,
                                  to_date: Optional[str] = None) -> bytes:
    brand = Brand(org)
    name = client.get("name") or client.get("company") or "Client"
    pdf = BrandedPDF(brand, "Client Statement", name)
    pdf.add_page()
    period = f"{display_date(from_date) if from_date else 'Beginning'} to {display_date(to_date) if to_date else 'Today'}"
    draw_letterhead(pdf, "CLIENT STATEMENT", [("Client", name), ("Period", period)])
    _detail_lines(pdf, [
        ("Client", name), ("Company", client.get("company")),
        ("Email", client.get("email")), ("Phone", client.get("phone")),
    ])
    pdf.ln(4)

    widths = [22, 59, 29, 23, 23, 24]
    headers = ["DATE", "DETAIL", "REFERENCE", "DEBIT", "CREDIT", "BALANCE"]

    def table_header() -> None:
        pdf.set_x(LEFT)
        pdf.set_fill_color(*brand.primary)
        pdf.set_text_color(255, 255, 255)
        pdf.set_font("Helvetica", "B", 7.5)
        for width, label in zip(widths, headers):
            pdf.cell(width, 7.5, label, 0, 0, "R" if label in {"DEBIT", "CREDIT", "BALANCE"} else "L", fill=True)
        pdf.ln()

    table_header()
    if summary.get("opening_balance"):
        rows = [{"date": from_date, "detail": "Opening balance", "reference": "",
                 "debit": 0, "credit": 0, "balance": summary["opening_balance"]}, *rows]
    for row in rows:
        if pdf.get_y() > pdf.h - 32:
            pdf.add_page()
            table_header()
        values = [display_date(row.get("date")), safe_text(row.get("detail") or "")[:48],
                  safe_text(row.get("reference") or "")[:22],
                  inr(row.get("debit")).replace("Rs. ", "") if row.get("debit") else "-",
                  inr(row.get("credit")).replace("Rs. ", "") if row.get("credit") else "-",
                  inr(row.get("balance")).replace("Rs. ", "")]
        pdf.set_x(LEFT)
        pdf.set_font("Helvetica", "", 7.9)
        pdf.set_text_color(*INK)
        for width, value, label in zip(widths, values, headers):
            pdf.cell(width, 6.6, safe_text(value), "B", 0,
                     "R" if label in {"DEBIT", "CREDIT", "BALANCE"} else "L")
        pdf.ln()

    pdf.ln(4)
    for label, value in (("Invoices / charges", summary.get("debit")),
                         ("Payments received", summary.get("credit")),
                         ("Closing balance", summary.get("closing_balance"))):
        pdf.set_x(120)
        pdf.set_font("Helvetica", "B" if label == "Closing balance" else "", 9.5)
        pdf.set_text_color(*(brand.primary if label == "Closing balance" else INK))
        pdf.cell(42, 7, label, 0, 0)
        pdf.cell(33, 7, safe_text(inr(value)), 0, 1, "R")
    return pdf.to_bytes()
