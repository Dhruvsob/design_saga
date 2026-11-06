"""Invoice money footing and scoped-DB passthrough regressions (ACC-01, SEC-03)."""
import pytest

import core.scoped_db as scoped_db
from server import compute_invoice_totals


def test_invoice_lines_always_foot_to_subtotal_and_total():
    doc = {"items": [{"quantity": 3, "rate": 33.335},
                     {"quantity": 1, "rate": 0.005},
                     {"quantity": 7, "rate": 14.285}], "tax_rate": 18}
    out = compute_invoice_totals(doc)
    line_sum = round(sum(it["amount"] for it in out["items"]), 2)
    assert out["subtotal"] == line_sum
    assert out["total"] == round(out["subtotal"] + out["tax"], 2)


def test_half_paisa_rounds_up_not_to_even():
    out = compute_invoice_totals({"items": [{"quantity": 1, "rate": 2.675}], "tax_rate": 0})
    assert out["items"][0]["amount"] == 2.68
    assert out["subtotal"] == 2.68 and out["total"] == 2.68


def test_tax_is_half_up_on_rounded_subtotal():
    # 1000.05 * 18% = 180.009 -> 180.01
    out = compute_invoice_totals({"items": [{"quantity": 1, "rate": 1000.05}], "tax_rate": 18})
    assert out["tax"] == 180.01
    assert out["total"] == 1180.06


def test_amounts_stay_json_floats():
    out = compute_invoice_totals({"items": [{"quantity": 2, "rate": 10}], "tax_rate": 5})
    assert all(isinstance(out[k], float) for k in ("subtotal", "tax", "total"))
    assert isinstance(out["items"][0]["amount"], float)


@pytest.mark.parametrize("method", ["estimated_document_count", "bulk_write", "watch",
                                    "rename", "drop", "find_raw_batches", "aggregate_raw_batches"])
def test_scoped_collection_refuses_tenant_unsafe_passthrough(method):
    token = scoped_db._scope.set({"org_id": "org_a"})
    try:
        coll = scoped_db._ScopedColl(object())
        with pytest.raises(AttributeError, match="tenant"):
            getattr(coll, method)
    finally:
        scoped_db._scope.reset(token)


# --- ACC-04: every money document foots with half-up paise -------------------
from decimal import Decimal, ROUND_HALF_UP

import server
from routes import loans, payroll, purchase, vendors


def _hu(x):
    return float(Decimal(str(x)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def test_purchase_order_totals_foot_line_by_line():
    lines = [{"quantity": 3, "unit_price": 33.335, "tax_rate": 18},
             {"quantity": 1, "unit_price": 2.675, "tax_rate": 18},
             {"quantity": 7, "unit_price": 14.285, "tax_rate": 5}]
    t = purchase._po_totals(lines)
    line_totals = [_hu(3 * 33.335), _hu(2.675), _hu(7 * 14.285)]
    assert t["subtotal"] == _hu(sum(line_totals))
    assert t["grand_total"] == _hu(t["subtotal"] + t["tax_total"])
    assert t["subtotal"] == 202.69  # 100.01 + 2.68 + 100.00 (Python round gives 202.68)


def test_vendor_bill_lines_subtotal_tax_tds_total_foot():
    bill = {"items": [{"quantity": 3, "rate": 33.335}, {"quantity": 1, "rate": 2.675}],
            "tax_rate": 18, "tds_rate": 1}
    total = vendors._bill_total(bill)
    assert bill["subtotal"] == _hu(sum(i["amount"] for i in bill["items"])) == 102.69
    assert total == bill["total"] == _hu(bill["subtotal"] + bill["tax_amount"] - bill["tds_amount"])


def test_commission_percentage_rounds_half_up():
    cfg = {"applicable": True, "type": "percentage", "percentage": 1}
    assert vendors._calc_commission_amount(cfg, 267.5) == 2.68


def test_quotation_cost_sheet_and_payment_plan_foot():
    q = {"boq": [{"category": "Joinery", "items": [
            {"quantity": 3, "rate": 33.335, "margin_pct": 0},
            {"quantity": 1, "rate": 2.675, "margin_pct": 10}]}],
         "cost": {"discount_pct": 5, "tax_pct": 18, "contingency_pct": 2},
         "payment_plan": [{"percentage": 33.33}, {"percentage": 33.33}, {"percentage": 33.34}]}

    out = server._q_compute_costs(q)
    items = out["boq"][0]["items"]
    c = out["cost"]
    assert c["subtotal"] == _hu(sum(i["amount"] for i in items))
    after = _hu(c["subtotal"] - c["discount_amt"])
    assert c["grand_total"] == _hu(after + c["contingency_amt"] + c["tax_amt"])
    assert _hu(sum(p["amount"] for p in out["payment_plan"])) == c["grand_total"]


def test_loan_schedule_principal_reconciles_and_rows_foot():
    rows = loans._build_schedule(100000, 11.5, 7, "2026-04-01")
    assert _hu(sum(r["principal"] for r in rows)) == 100000
    assert all(r["emi"] == _hu(r["principal"] + r["interest"]) for r in rows)
    assert rows[-1]["balance_after"] == 0


def test_payroll_net_is_exact_to_the_paisa():
    out = payroll._compute_net({"basic": 0.1, "hra": 0.2, "tds": 0.3}, {"bonus": 0.7})
    assert out["gross"] == 1.0 and out["deductions_total"] == 0.3 and out["net"] == 0.7
