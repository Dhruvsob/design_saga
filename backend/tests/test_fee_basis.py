"""Still to receive is counted against the studio's fee (owner, 2026-11-23).

Hand-worked figures:
* Consultancy %: Rs 3,00,00,000 project x 6% = Rs 18,00,000 fee; Rs 14,42,500
  received -> Rs 3,57,500 still to receive (was Rs 2,85,57,500, project value).
* Lump sum: Rs 6,00,000 fee on a Rs 60,00,000 project; Rs 1,00,000 received -> Rs 5,00,000.
* Per sq ft: 2,400 sq ft x Rs 250 = Rs 6,00,000; Rs 2,00,000 received -> Rs 4,00,000.
* Turnkey: Rs 60,00,000 contract; Rs 10,00,000 received -> Rs 50,00,000.
* No fee type: the project value as before (Rs 10,00,000 - Rs 15,000 = Rs 9,85,000).
"""
import asyncio
from types import SimpleNamespace

import pytest

import server
from core.fees import agreed_fee, collection_basis


def money(project, received):
    return server._project_money(project, [], [], received)


def test_consultancy_percent_counts_against_the_fee_not_the_project_value():
    p = {"budget": 30000000, "fee_structure_type": "percentage_consultancy",
         "fee_project_value": 30000000, "fee_percentage": 6}
    m = money(p, 1442500)
    assert agreed_fee(p) == 1800000
    assert m["basis"] == 1800000 and m["basis_kind"] == "agreed_fee"
    assert m["project_value"] == 30000000          # still shown, separately
    assert m["still_to_receive"] == 357500


@pytest.mark.parametrize("project,received,basis,kind,still", [
    ({"budget": 6000000, "fee_structure_type": "lump_sum", "fee_lump_sum_amount": 600000},
     100000, 600000, "agreed_fee", 500000),
    ({"budget": 6000000, "fee_structure_type": "per_sqft", "site_area_sqft": 2400, "fee_rate_per_sqft": 250},
     200000, 600000, "agreed_fee", 400000),
    ({"budget": 6000000, "fee_structure_type": "turnkey", "fee_contract_value": 6000000},
     1000000, 6000000, "contract_value", 5000000),
    ({"budget": 1000000}, 15000, 1000000, "project_value", 985000),
])
def test_each_fee_type(project, received, basis, kind, still):
    m = money(project, received)
    assert (m["basis"], m["basis_kind"], m["still_to_receive"]) == (basis, kind, still)


def test_overpayment_never_goes_negative_and_incomplete_fee_falls_back():
    p = {"budget": 600000, "fee_structure_type": "lump_sum", "fee_lump_sum_amount": 600000}
    assert money(p, 650000)["still_to_receive"] == 0
    incomplete = {"budget": 5000000, "fee_structure_type": "percentage_consultancy", "fee_project_value": 5000000}
    assert collection_basis(incomplete) == (5000000.0, "project_value")
    turnkey_without_value = {"budget": 4000000, "fee_structure_type": "turnkey"}
    assert collection_basis(turnkey_without_value) == (4000000.0, "contract_value")


def test_percentage_milestone_is_a_share_of_the_fee(monkeypatch):
    import routes.accounting as acc
    project = {"id": "p1", "budget": 30000000, "fee_structure_type": "percentage_consultancy",
               "fee_project_value": 30000000, "fee_percentage": 6}
    inserted = []

    async def find_one(query, projection=None):
        return dict(project) if query.get("id") == "p1" else dict(inserted[-1]) if inserted else None

    async def insert_one(doc):
        inserted.append(doc)

    async def user(*_a, **_k):
        return {"user_id": "u1", "org_id": "org_a", "permissions": ["*.*"]}

    async def no_audit(*_a, **_k):
        return None

    monkeypatch.setattr(acc, "sdb", SimpleNamespace(
        projects=SimpleNamespace(find_one=find_one),
        payment_milestones=SimpleNamespace(insert_one=insert_one, find_one=find_one)))
    monkeypatch.setattr(acc, "require_user", user)
    monkeypatch.setattr(acc, "has_permission", lambda *_a: True)
    monkeypatch.setattr(acc, "audit", no_audit)
    out = asyncio.run(acc.add_milestone("p1", acc.MilestoneIn(project_id="p1", name="Concept 10%", percent=10), None))
    # 10% of the Rs 18,00,000 fee, not of the Rs 3 crore project.
    assert out["amount"] == 180000
