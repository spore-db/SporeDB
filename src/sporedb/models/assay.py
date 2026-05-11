from datetime import datetime
from math import isfinite
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class UncertainValue(BaseModel):
    """A measurement with associated uncertainty (1 sigma).

    Attributes:
        value: The measured value.
        uncertainty: One standard deviation uncertainty. Defaults to ``0.0``.
        unit: Unit of measurement (e.g. ``"g/L"``, ``"cells/mL"``).
    """

    value: float
    uncertainty: float = Field(default=0.0, ge=0.0)
    unit: str = ""

    @field_validator("value", "uncertainty")
    @classmethod
    def must_be_finite(cls, v: float) -> float:
        if not isfinite(v):
            raise ValueError("Value must be finite (no NaN or Infinity)")
        return v

    def to_ufloat(self) -> object:
        """Convert to uncertainties.ufloat for error propagation."""
        from uncertainties import ufloat

        return ufloat(self.value, self.uncertainty)


class AssayMeasurement(BaseModel):
    """An offline assay measurement for a batch.

    Represents a single analytical measurement taken outside the bioreactor
    (e.g. HPLC, cell count, LC-MS).

    Attributes:
        batch_id: UUID of the batch this measurement belongs to.
        ts: Sampling timestamp (must be timezone-aware).
        variable: Measured quantity name (e.g. ``"glucose"``, ``"viable_cells"``).
        value: Measured value.
        uncertainty: Measurement uncertainty (1 sigma). Defaults to ``0.0``.
        unit: Unit of measurement (e.g. ``"g/L"``).
        method: Analytical method used (e.g. ``"HPLC"``, ``"cell_count"``).

    Raises:
        ValueError: If *ts* is not timezone-aware.
    """

    batch_id: UUID
    ts: datetime
    variable: str = Field(min_length=1)
    value: float
    uncertainty: float = Field(default=0.0, ge=0.0)
    unit: str | None = None
    method: str | None = None  # e.g., "HPLC", "cell_count", "LC-MS"

    @field_validator("ts")
    @classmethod
    def ts_must_be_aware(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("ts must be timezone-aware (use UTC)")
        return v

    @field_validator("value", "uncertainty")
    @classmethod
    def must_be_finite(cls, v: float) -> float:
        if not isfinite(v):
            raise ValueError("Value must be finite (no NaN or Infinity)")
        return v
