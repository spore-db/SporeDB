from datetime import UTC, datetime
from enum import StrEnum
from math import isfinite
from uuid import UUID

from pydantic import BaseModel, Field, field_validator
from uuid_utils import uuid7


def _make_uuid7() -> UUID:
    """Generate a UUIDv7 and return as stdlib UUID for Pydantic compatibility."""
    return UUID(str(uuid7()))


class BatchLifecycle(StrEnum):
    """Lifecycle states for a fermentation batch.

    A batch progresses through these states from planning to completion:
    ``PLANNED`` -> ``INOCULATED`` -> ``RUNNING`` -> ``HARVESTED`` (or ``ABORTED``).
    """

    PLANNED = "planned"
    INOCULATED = "inoculated"
    RUNNING = "running"
    HARVESTED = "harvested"
    ABORTED = "aborted"


class CanonicalTimestamps(BaseModel):
    """Key timestamps in a fermentation batch lifecycle.

    Attributes:
        inoculation: When the bioreactor was inoculated.
        feed_start: When feed addition began (fed-batch).
        induction: When gene expression was induced.
        harvest: When the batch was harvested.
    """

    inoculation: datetime | None = None
    feed_start: datetime | None = None
    induction: datetime | None = None
    harvest: datetime | None = None

    @field_validator("inoculation", "feed_start", "induction", "harvest")
    @classmethod
    def datetime_must_be_aware(cls, v: datetime | None) -> datetime | None:
        if v is not None and v.tzinfo is None:
            raise ValueError("Datetime must be timezone-aware (use UTC)")
        return v


class BatchMetadata(BaseModel):
    """Metadata describing the conditions of a fermentation batch.

    Attributes:
        strain: Organism strain name (e.g. ``"CHO-K1"``, ``"E. coli BL21"``).
        media: Growth media description (e.g. ``"DMEM + 10% FBS"``).
        scale_liters: Bioreactor working volume in liters.
        operator: Name of the operator running the batch.
        extra: Additional key-value metadata. Values must be scalar types.
    """

    strain: str | None = None
    media: str | None = None
    scale_liters: float | None = Field(default=None, gt=0.0)
    operator: str | None = None
    extra: dict[str, str | int | float | bool] = Field(default_factory=dict)

    @field_validator("scale_liters")
    @classmethod
    def must_be_finite(cls, v: float | None) -> float | None:
        if v is not None and not isfinite(v):
            raise ValueError("scale_liters must be finite (no NaN or Infinity)")
        return v


class Batch(BaseModel):
    """A fermentation batch record.

    Represents a single bioreactor run with its metadata, lifecycle state,
    canonical timestamps, and tags.

    Attributes:
        batch_id: UUIDv7 identifier (auto-generated if not provided).
        name: Human-readable batch name (e.g. ``"CHO-Run-001"``).
        lifecycle: Current lifecycle state. Defaults to ``PLANNED``.
        timestamps: Canonical timestamps for key events.
        metadata: Strain, media, scale, and operator metadata.
        tags: Free-form tags for categorization and filtering.
        created_at: Creation timestamp (auto-set to current UTC time).
        updated_at: Last-modified timestamp (auto-set to current UTC time).

    Example:
        >>> from sporedb.models.batch import Batch
        >>> batch = Batch(name="CHO-Run-001")
        >>> print(batch.batch_id)
    """

    batch_id: UUID = Field(default_factory=_make_uuid7)
    name: str = Field(min_length=1)
    lifecycle: BatchLifecycle = BatchLifecycle.PLANNED
    timestamps: CanonicalTimestamps = Field(default_factory=CanonicalTimestamps)
    metadata: BatchMetadata = Field(default_factory=BatchMetadata)
    tags: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
