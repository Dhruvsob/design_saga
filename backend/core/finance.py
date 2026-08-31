"""Financial period helpers.

Indian FY convention: Apr 1 → Mar 31. The FY label is written as
`YYYY-YY` (e.g. `2025-26` covers 2025-04-01 → 2026-03-31).

Public helpers:
- `resolve_period(fy=None, from_date=None, to_date=None, as_of=None)`
    → (from_date, to_date, label) — used by every report endpoint.
- `current_fy_label()` → the FY that today's date falls into.
- `fy_choices(back=5, forward=1)` → dropdown options for the UI.
"""
from datetime import date, datetime, timedelta
from typing import Optional, Tuple, List


FY_START_MONTH = 4      # April


def current_fy_label(today: Optional[date] = None) -> str:
    today = today or datetime.utcnow().date()
    if today.month >= FY_START_MONTH:
        start_year = today.year
    else:
        start_year = today.year - 1
    end_year = start_year + 1
    return f"{start_year}-{str(end_year)[-2:]}"


def fy_range(label: str) -> Tuple[str, str]:
    """`2025-26` → ('2025-04-01', '2026-03-31')."""
    try:
        start_str, end_short = label.split("-")
        start_year = int(start_str)
        # end_short like "26" → 2026 (assumes 2000s)
        end_year = 2000 + int(end_short) if len(end_short) == 2 else int(end_short)
    except Exception:
        raise ValueError(f"Invalid FY label: {label}")
    start = date(start_year, FY_START_MONTH, 1)
    end = date(end_year, FY_START_MONTH, 1) - timedelta(days=1)
    return start.isoformat(), end.isoformat()


def resolve_period(fy: Optional[str] = None,
                   from_date: Optional[str] = None,
                   to_date: Optional[str] = None,
                   as_of: Optional[str] = None) -> Tuple[Optional[str], Optional[str], str]:
    """Reconcile the FY/date-range/as-of triplet used by every report endpoint.

    Precedence:
        1. explicit from_date / to_date if either supplied
        2. FY label
        3. `as_of` (end date only, from_date=None → all history up to as_of)
        4. current FY

    Returns (from_date, to_date, label).
    """
    if from_date or to_date:
        return from_date, to_date, "Custom"
    if fy:
        s, e = fy_range(fy)
        return s, e, f"FY {fy}"
    if as_of:
        return None, as_of, f"As of {as_of}"
    label = current_fy_label()
    s, e = fy_range(label)
    return s, e, f"FY {label}"


def fy_choices(back: int = 5, forward: int = 1) -> List[dict]:
    """Return `back` past FYs + current + `forward` future ones."""
    curr = current_fy_label()
    start_year = int(curr.split("-")[0])
    out = []
    for i in range(-back, forward + 1):
        y = start_year + i
        label = f"{y}-{str(y + 1)[-2:]}"
        s, e = fy_range(label)
        out.append({"label": label, "from": s, "to": e,
                    "is_current": label == curr})
    return out
