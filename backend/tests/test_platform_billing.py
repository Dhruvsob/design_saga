"""P1.3 GAMAA billing: ledger, GST split, lifecycle (grace -> read-only -> lapsed), reactivation."""
import asyncio
import copy
from datetime import date
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import core.platform_billing as pb
import core.subscription as sub

TODAY = date(2026, 11, 12)


# ---------------------------------------------------------------- lifecycle
def _org(paid_through, status="active"):
    return {"subscription": {"status": status, "paid_through": paid_through}}


def test_paid_subscription_runs_through_grace_read_only_and_lapsed():
    s = sub.subscription_state(_org("2026-11-20"), TODAY)
    assert s["status"] == "active" and not s["read_only"] and s["days_left"] == 8
    s = sub.subscription_state(_org("2026-11-10"), TODAY)               # 2 days over: grace
    assert s["status"] == "grace" and not s["read_only"] and s["grace_ends_on"] == "2026-11-17"
    s = sub.subscription_state(_org("2026-11-01"), TODAY)               # 11 days over: read-only
    assert s["status"] == "expired" and s["read_only"] and not s["lapsed"]
    assert s["ended_on"] == "2026-11-08"
    s = sub.subscription_state(_org("2026-09-01"), TODAY)               # past grace + 30 days
    assert s["read_only"] and s["lapsed"]


def test_workspaces_without_paid_through_are_never_restricted():
    assert not sub.subscription_state({"subscription": {"status": "active"}}, TODAY)["read_only"]
    assert not sub.subscription_state({}, TODAY)["read_only"]


# ---------------------------------------------------------------- GST and numbering
SELLER = {"gstin": "24ABCDE1234F1Z5", "state": "Gujarat"}


def test_gst_split_by_place_of_supply():
    lines = [{"amount": 10000}]
    same = pb.compute_totals(lines, 18, SELLER, {"gstin": "24PQRSX6789K1Z2"})
    assert (same["cgst"], same["sgst"], same["igst"], same["total"]) == (900.0, 900.0, 0.0, 11800.0)
    other = pb.compute_totals(lines, 18, SELLER, {"state": "Maharashtra"})
    assert (other["cgst"], other["igst"]) == (0.0, 1800.0)
    unknown = pb.compute_totals(lines, 18, SELLER, {})                  # no place on file: supplier's state
    assert (unknown["cgst"], unknown["sgst"], unknown["igst"]) == (900.0, 900.0, 0.0)
    no_gstin = pb.compute_totals(lines, 18, {"gstin": ""}, {"state": "Gujarat"})
    assert no_gstin["tax"] == 0 and no_gstin["total"] == 10000.0        # unregistered seller: no GST


def test_financial_year_and_period_helpers():
    assert pb.fy_label(date(2026, 3, 31)) == "2025-26" and pb.fy_label(date(2026, 4, 1)) == "2026-27"
    assert pb.add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)
    start, end, cycle = pb.suggest_period({"subscription": {"paid_through": "2026-03-31"},
                                           "billing": {"billing_cycle": "yearly"}}, TODAY)
    assert (start, end, cycle) == (date(2026, 4, 1), date(2027, 3, 31), "yearly")


def test_invoice_status_is_computed():
    base = {"issued_on": "2026-11-01", "due_on": "2026-11-08", "total": 1000, "amount_paid": 0}
    assert pb.invoice_status({**base, "issued_on": None}, TODAY) == "draft"
    assert pb.invoice_status(base, TODAY) == "overdue"
    assert pb.invoice_status({**base, "due_on": "2026-11-30", "amount_paid": 400}, TODAY) == "partially_paid"
    assert pb.invoice_status({**base, "amount_paid": 1000}, TODAY) == "paid"
    assert pb.invoice_status({**base, "voided_at": "x"}, TODAY) == "void"


# ---------------------------------------------------------------- payments + reactivation
class _Coll:
    def __init__(self, rows=None):
        self.rows = rows or []

    async def insert_one(self, doc):
        self.rows.append(dict(doc))

    async def find_one(self, query, _p=None):
        for r in self.rows:
            if all(r.get(k) == v for k, v in query.items()):
                return copy.deepcopy(r)
        return None

    async def update_one(self, query, update, upsert=False):
        for r in self.rows:
            if all(r.get(k) == v for k, v in query.items()):
                r.update(copy.deepcopy(update.get("$set", {})))
                return SimpleNamespace(modified_count=1)
        return SimpleNamespace(modified_count=0)


def _fake_db(monkeypatch, sub_doc):
    import core.db
    db = SimpleNamespace(platform_payments=_Coll(), platform_invoices=_Coll(),
                         organizations=_Coll([{"org_id": "org_a", "subscription": sub_doc}]))
    monkeypatch.setattr(core.db, "db", db)
    return db


INV = {"id": "pinv_1", "number": "GAMAA/2026-27/0001", "org_id": "org_a", "issued_on": "2026-11-01",
       "due_on": "2026-11-08", "total": 11800.0, "amount_paid": 0.0,
       "period_start": "2026-11-02", "period_end": "2027-11-01"}


def test_full_payment_reactivates_a_read_only_workspace(monkeypatch):
    db = _fake_db(monkeypatch, {"status": "active", "paid_through": "2026-10-01"})
    org = asyncio.run(db.organizations.find_one({"org_id": "org_a"}))
    assert sub.subscription_state(org, TODAY)["read_only"]
    db.platform_invoices.rows.append(dict(INV))
    part = asyncio.run(pb.apply_payment(dict(INV), 5000, "upi", "UTR1", TODAY, {"user_id": "sa"}))
    assert not part["paid_in_full"] and part["paid_through"] is None
    inv = asyncio.run(db.platform_invoices.find_one({"id": "pinv_1"}))
    out = asyncio.run(pb.apply_payment(inv, 6800, "bank_transfer", "NEFT2", TODAY, {"user_id": "sa"}))
    assert out["paid_in_full"] and out["paid_through"] == "2027-11-01"
    org = asyncio.run(db.organizations.find_one({"org_id": "org_a"}))
    state = sub.subscription_state(org, TODAY)
    assert state["status"] == "active" and not state["read_only"]
    assert [p["amount"] for p in db.platform_payments.rows] == [5000.0, 6800.0]


def test_payment_rules(monkeypatch):
    _fake_db(monkeypatch, {"status": "active"})
    with pytest.raises(HTTPException):          # more than the balance
        asyncio.run(pb.apply_payment(dict(INV), 99999, "upi", "", TODAY, {"user_id": "sa"}))
    with pytest.raises(HTTPException):          # unknown method
        asyncio.run(pb.apply_payment(dict(INV), 100, "crypto", "", TODAY, {"user_id": "sa"}))
    with pytest.raises(HTTPException):          # draft
        asyncio.run(pb.apply_payment({**INV, "issued_on": None}, 100, "upi", "", TODAY, {"user_id": "sa"}))
    with pytest.raises(HTTPException):          # void
        asyncio.run(pb.apply_payment({**INV, "voided_at": "x"}, 100, "upi", "", TODAY, {"user_id": "sa"}))


def test_invoice_pdf_renders_with_gst_lines():
    settings = {**pb.DEFAULT_SETTINGS, "seller_name": "Gamaa", "gstin": "24ABCDE1234F1Z5", "state": "Gujarat",
                "bank": {**pb.DEFAULT_SETTINGS["bank"], "upi": "gamaa@upi"}}
    lines = [{"description": "Gamaa ERP - Professional plan, 02 Nov 2026 to 01 Nov 2027", "amount": 10000}]
    inv = {**INV, "lines": lines, "buyer": {"name": "Studio A", "gstin": "24PQRSX6789K1Z2"}, "plan_name": "Professional",
           **pb.compute_totals(lines, 18, settings, {"gstin": "24PQRSX6789K1Z2"})}
    data = pb.invoice_pdf(inv, settings)
    assert data.startswith(b"%PDF") and len(data) > 1500


def test_billing_routes_are_admin_only():
    import inspect
    import routes.platform_billing as routes
    for name in ("get_billing_settings", "save_billing_settings", "list_invoices", "create_invoice",
                 "issue_invoice", "void_invoice", "record_payment", "invoice_pdf", "delete_draft"):
        assert "require_super_admin(" in inspect.getsource(getattr(routes, name)), name
    for name in ("my_billing", "my_invoice_pdf"):
        assert 'has_permission(user, "*.*")' in inspect.getsource(getattr(routes, name)), name
    # a studio only ever sees its own issued invoices
    assert '"org_id": user_org_id(user)' in inspect.getsource(routes.my_invoice_pdf)
