"""Consultancy design proposal (DS-087): fee maths, input safety, PDF and modes."""
import asyncio
import re

import pytest
from fastapi import HTTPException

from core import consultancy_proposal as cp


def _sample_doc(**proposal_overrides):
    p = cp.default_proposal(client_name="Krunal Soni", org={"phone": "7383277303"}, user={"name": "Yash Soni"})
    p["fee"].update(total_fee=600000, advance_amount=50000, instalment_amount=30000, instalment_every_months=2)
    p["site_coordinator"].update(enabled=True, monthly_fee=7500)
    p.update(proposal_overrides)
    return {
        "number": "Q-2026-7", "date": "2026-05-28", "type": "consultancy", "client_name": "Krunal Soni",
        "project_title": "4 BHK Apartment", "project_location": "Cloud 9, Near Shivranjani Cross Road.",
        "design_scope": list(cp.DEFAULT_SCOPE) + ["Landscape Design"],
        "proposal": cp.clean_proposal(p),
        "terms": [{"section": "Validity", "content": "Valid for 30 days."}],
        "cost": {"tax_pct": 0, "grand_total": 600000},
    }


def _pages(pdf: bytes) -> int:
    return len(re.findall(rb"/Type\s*/Page[^s]", pdf))


def test_fee_schedule_sums_exactly_and_last_instalment_takes_the_remainder():
    rows = cp.fee_schedule({"total_fee": 600000, "advance_amount": 50000,
                            "instalment_amount": 30000, "instalment_every_months": 2})
    assert rows[0] == {"label": "Advance on confirmation", "month": 0, "amount": 50000.0}
    assert len(rows) == 20 and rows[-1]["amount"] == 10000.0 and rows[-1]["month"] == 38
    assert round(sum(r["amount"] for r in rows), 2) == 600000.0


def test_fee_schedule_paise_and_edge_cases():
    rows = cp.fee_schedule({"total_fee": 1000.10, "advance_amount": 0.05, "instalment_amount": 333.33,
                            "instalment_every_months": 1})
    assert round(sum(r["amount"] for r in rows), 2) == 1000.10
    assert cp.fee_schedule({"total_fee": 0}) == []
    assert cp.fee_schedule({"total_fee": 5000, "advance_amount": 5000}) == [
        {"label": "Advance on confirmation", "month": 0, "amount": 5000.0}]
    balance = cp.fee_schedule({"total_fee": 5000, "advance_amount": 1000})
    assert balance[-1] == {"label": "Balance fee", "month": None, "amount": 4000.0}


def test_clean_proposal_whitelists_trims_and_validates_money():
    cleaned = cp.clean_proposal({
        "salutation": "<script>", "intro": "x" * 5000, "unknown_key": "drop me",
        "process_clauses": ["  keep  ", "", None], "revisions_included": 999,
        "fee": {"total_fee": "1234.567", "instalment_every_months": 0},
        "site_coordinator": {"enabled": "yes", "duties": ["a"] * 50},
    })
    assert cleaned["salutation"] == "" and len(cleaned["intro"]) == cp.MAX_TEXT
    assert "unknown_key" not in cleaned and cleaned["process_clauses"] == ["keep"]
    assert cleaned["revisions_included"] == 20
    assert cleaned["fee"]["total_fee"] == 1234.57 and cleaned["fee"]["instalment_every_months"] == 1
    assert cleaned["site_coordinator"]["enabled"] is True and len(cleaned["site_coordinator"]["duties"]) == 20
    with pytest.raises(ValueError):
        cp.clean_proposal({"fee": {"total_fee": -1}})
    with pytest.raises(ValueError):
        cp.clean_proposal({"fee": {"total_fee": 1000, "advance_amount": 2000}})


def test_clauses_render_the_included_counts():
    p = cp.clean_proposal({"revisions_included": 2, "renders_included": 3})
    text = [cp.render_clause(c, p) for c in p["process_clauses"]]
    assert "along with two additional revision" in text[0]
    assert text[2].startswith("Three final render view")


def test_indian_money_text():
    assert cp.inr_plain(600000) == "Rs. 6,00,000/-"
    assert cp.inr_plain(7500) == "Rs. 7,500/-"
    assert cp.inr_plain(12345678.5) == "Rs. 1,23,45,678.50"


def test_sample_proposal_fits_two_pages_with_every_section():
    pdf = cp.generate_proposal_pdf(_sample_doc(), {"name": "DESIGN SAGA", "phone": "7383277303"})
    assert pdf.startswith(b"%PDF") and _pages(pdf) == 2


def test_empty_optional_sections_do_not_add_pages():
    doc = _sample_doc()
    doc["proposal"]["site_coordinator"]["enabled"] = False
    doc["proposal"]["process_clauses"] = []
    doc["design_scope"] = []
    doc["terms"] = []
    pdf = cp.generate_proposal_pdf(doc, {"name": "Studio"})
    assert _pages(pdf) == 1


def test_long_proposal_flows_across_pages_without_blank_trailing_page():
    doc = _sample_doc()
    doc["design_scope"] = [f"Service line {i} " + "detail " * 30 for i in range(40)]
    pdf = cp.generate_proposal_pdf(doc, {"name": "Studio"})
    assert 3 <= _pages(pdf) <= 6


# ---- API rules: business mode, type lock, cleaning ---------------------------
import server  # noqa: E402


class _Org:
    def __init__(self, mode):
        self.mode = mode

    async def find_one(self, *_a, **_k):
        return {"business_mode": self.mode}


@pytest.mark.parametrize("mode,allowed", [
    ("consultancy", ["consultancy"]), ("turnkey", ["turnkey"]), ("hybrid", ["turnkey", "consultancy"]),
    (None, ["turnkey", "consultancy"]),
])
def test_allowed_types_follow_the_business_mode(monkeypatch, mode, allowed):
    class DB:
        organizations = _Org(mode)
    monkeypatch.setattr(server, "db", DB())
    assert asyncio.run(server._allowed_quotation_types({"org_id": "org_a"})) == allowed


def test_consultancy_only_workspace_cannot_create_turnkey(monkeypatch):
    async def fake_user(*_a, **_k):
        return {"user_id": "u1", "org_id": "org_a", "role": "Admin", "permissions": ["*.*"]}

    class DB:
        organizations = _Org("consultancy")
    monkeypatch.setattr(server, "require_user", fake_user)
    monkeypatch.setattr(server, "_require_perm", lambda *_a, **_k: None)
    monkeypatch.setattr(server, "db", DB())
    with pytest.raises(HTTPException) as exc:
        asyncio.run(server.adv_create(server.QuotationCreate(type="turnkey", project_title="X"), request=None))
    assert exc.value.status_code == 400 and "Consultancy" in exc.value.detail


def test_new_consultancy_doc_is_a_proposal_with_fee_driven_total():
    doc = server._new_quotation_doc({"type": "consultancy", "project_title": "4 BHK", "client_name": "Krunal"},
                                    {"user_id": "u1", "name": "Yash Soni"}, {"phone": "7383277303"})
    assert doc["proposal"]["greeting_name"] == "Krunal" and doc["proposal"]["signatory_name"] == "Yash Soni"
    assert doc["proposal"]["office_phone"] == "7383277303"
    assert doc["payment_plan"] == [] and doc["cost"]["tax_pct"] == 0
    doc["proposal"]["fee"]["total_fee"] = 600000
    out = server._q_compute_costs(doc)
    assert out["cost"]["grand_total"] == 600000.0
    doc["cost"]["tax_pct"] = 18
    assert server._q_compute_costs(doc)["cost"]["grand_total"] == 708000.0


def test_turnkey_doc_is_unchanged_and_has_no_proposal():
    doc = server._new_quotation_doc({"type": "turnkey", "project_title": "Villa"}, {"user_id": "u1"})
    assert doc["proposal"] is None and doc["payment_plan"] and doc["cost"]["tax_pct"] == 18


def test_turnkey_quotation_sections_flow_instead_of_one_page_each():
    doc = server._new_quotation_doc({"type": "turnkey", "project_title": "Villa", "client_name": "C"}, {"user_id": "u"})
    doc["number"] = "Q-1"
    doc["design_scope"] = ["Concept"]
    doc["boq"] = [{"category": k, "items": [dict(it, room="Kitchen") for it in v]}
                  for k, v in list(server.BOQ_TEMPLATES.items())[:3]]
    doc = server._q_compute_costs(doc)
    pdf = server.generate_quotation_pdf_adv(doc, {"name": "Studio"})
    # cover + flowing sections; previously every section forced its own page (10+)
    assert _pages(pdf) <= 6
