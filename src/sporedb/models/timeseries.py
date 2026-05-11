from datetime import datetime
from math import isfinite
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class TelemetryRecord(BaseModel):
    """A single telemetry data point from a bioreactor sensor.

    Represents one time-stamped measurement from an online sensor
    (e.g. dissolved oxygen, pH, temperature, optical density).

    Attributes:
        batch_id: UUID of the batch this record belongs to.
        ts: Measurement timestamp (must be timezone-aware).
        variable: Sensor variable name (e.g. ``"OD600"``, ``"dissolved_oxygen"``).
        value: Measured value.
        unit: Unit of measurement (e.g. ``"%"``, ``"deg_C"``).

    Raises:
        ValueError: If *ts* is not timezone-aware.
    """

    batch_id: UUID
    ts: datetime
    variable: str = Field(min_length=1)
    value: float
    unit: str | None = None

    @field_validator("ts")
    @classmethod
    def ts_must_be_aware(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("ts must be timezone-aware (use UTC)")
        return v

    @field_validator("value")
    @classmethod
    def must_be_finite(cls, v: float) -> float:
        if not isfinite(v):
            raise ValueError("Value must be finite (no NaN or Infinity)")
        return v
