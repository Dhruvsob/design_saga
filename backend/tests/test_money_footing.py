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
