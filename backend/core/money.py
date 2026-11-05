"""Shared money arithmetic.

Policy (ACC-01): amounts are computed in Decimal and rounded to paise with
ROUND_HALF_UP at each displayed boundary (line amount, subtotal, tax, total),
so every printed figure foots. Values are returned as floats only at the API
boundary for backward compatibility with stored documents and the frontend.
Inputs go through ``str()`` first so binary-float noise (2.675 stored as
2.67499...) does not decide the rounding direction.
"""
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation

PAISA = Decimal("0.01")


def to_decimal(value, default: str = "0") -> Decimal:
    if value is None or value == "":
        return Decimal(default)
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError(f"Invalid money value: {value!r}")
    if not result.is_finite():
        raise ValueError(f"Invalid money value: {value!r}")
    return result


def round_paise(value) -> Decimal:
    return to_decimal(value).quantize(PAISA, rounding=ROUND_HALF_UP)


def money_float(value) -> float:
    return float(round_paise(value))


def percent_of(amount, rate) -> Decimal:
    """Rounded percentage of an already-rounded amount."""
    return round_paise(to_decimal(amount) * to_decimal(rate) / Decimal(100))
