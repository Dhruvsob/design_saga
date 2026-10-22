"""Shared validation bases for business-domain request models."""
from pydantic import BaseModel, ConfigDict


class FiniteModel(BaseModel):
    """Reject NaN and Infinity before values can reach persistence or calculations."""

    model_config = ConfigDict(allow_inf_nan=False)
