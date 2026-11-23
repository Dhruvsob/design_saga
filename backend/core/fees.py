"""What a project is worth to the studio, by fee type.

The owner's rule (2026-11-23): money received is counted against what the
studio actually charges, not against the client's whole project cost.

* Lump sum            -> the fixed fee.
* Consultancy %       -> project value x fee %  (10% of a Rs 60 lakh project = Rs 6 lakh).
* Per square foot     -> site area x rate.
* Turnkey             -> the contract value (the studio delivers the whole project).
* No fee type set     -> the project value (budget), as before.

`budget` stays the client's project value (shown separately). Mirrors
`frontend/src/lib/fees.js feeCalc` so the screen and the server agree.
"""
from typing import Optional

FEE_KINDS = ("lump_sum", "percentage_consultancy", "per_sqft")


def _num(project: dict, key: str) -> float:
    try:
        return float(project.get(key) or 0)
    except (TypeError, ValueError):
        return 0.0


def agreed_fee(project: dict) -> Optional[float]:
    """The fee the studio charges, or None when the fee type is unset or incomplete."""
    kind = project.get("fee_structure_type")
    if kind == "lump_sum":
        fee = _num(project, "fee_lump_sum_amount")
    elif kind == "percentage_consultancy":
        fee = round(_num(project, "fee_project_value") * _num(project, "fee_percentage") / 100.0, 2)
    elif kind == "per_sqft":
        fee = round(_num(project, "site_area_sqft") * _num(project, "fee_rate_per_sqft"), 2)
    elif kind == "turnkey":
        fee = _num(project, "fee_contract_value")
    else:
        return None
    return fee if fee > 0 else None


def collection_basis(project: dict) -> tuple[float, str]:
    """(amount, kind): what the studio expects to collect on this project.

    kind is "agreed_fee", "contract_value" or "project_value" (no fee type).
    """
    kind = project.get("fee_structure_type")
    fee = agreed_fee(project)
    if kind in FEE_KINDS and fee:
        return fee, "agreed_fee"
    if kind == "turnkey":
        return (fee or _num(project, "budget")), "contract_value"
    return _num(project, "budget"), "project_value"
