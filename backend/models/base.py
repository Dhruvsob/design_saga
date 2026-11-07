"""Shared validation bases for business-domain request models."""
from datetime import date

from pydantic import BaseModel, ConfigDict, model_validator


def _is_date_field(name: str) -> bool:
    return name == "date" or name.endswith("_date") or name in {"due_by", "trial_ends_on"}


class FiniteModel(BaseModel):
    """Reject NaN and Infinity before values can reach persistence or calculations.

    Also: every date field (``date``, ``*_date``) that is filled in must be a real
    calendar date in YYYY-MM-DD form. A value like "31-10-2026" or "2026-02-30"
    would otherwise be stored as text and silently break due/overdue checks,
    period reports and sorting. Empty values stay allowed (optional dates).
    """

    model_config = ConfigDict(allow_inf_nan=False)

    @model_validator(mode="after")
    def _dates_are_real(self):
        for name in type(self).model_fields:
            if not _is_date_field(name):
                continue
            value = getattr(self, name, None)
            if not isinstance(value, str) or not value.strip():
                continue
            try:
                if len(value.strip()) != 10:
                    raise ValueError
                date.fromisoformat(value.strip())
            except ValueError:
                raise ValueError(f"{name.replace('_', ' ')} must be a date like 2026-11-30")
        return self
