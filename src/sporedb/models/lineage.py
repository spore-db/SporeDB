from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator
from uuid_utils import uuid7


def _make_uuid7() -> UUID:
    """Generate a UUIDv7 and return as stdlib UUID for Pydantic compatibility."""
    return UUID(str(uuid7()))


class UnitOperation(BaseModel):
    """A single processing step in a batch's lineage (DAG node).

    Each unit operation represents one step in the bioprocess workflow
    (e.g. seed train, fermentation, centrifugation). Operations form a
    directed acyclic graph (DAG) via ``parent_ids``.

    Attributes:
        operation_id: UUIDv7 identifier (auto-generated).
        batch_id: UUID of the batch this operation belongs to.
        name: Operation name (e.g. ``"seed_train"``, ``"centrifugation"``).
        operation_type: Category
            (e.g. ``"upstream"``, ``"downstream"``, ``"analytical"``).
        parent_ids: UUIDs of parent operations in the DAG.
        started_at: When this operation started (timezone-aware).
        ended_at: When this operation completed (timezone-aware).
        parameters: Process parameters as key-value pairs.

    Raises:
        ValueError: If *started_at* or *ended_at* is not timezone-aware.
    """

    operation_id: UUID = Field(default_factory=_make_uuid7)
    batch_id: UUID
    name: str = Field(
        min_length=1
    )  # e.g., "seed_train", "fermentation", "centrifugation"
    operation_type: str = Field(
        min_length=1
    )  # e.g., "upstream", "downstream", "analytical"
    parent_ids: list[UUID] = Field(
        default_factory=list
    )  # DAG edges to parent operations
    started_at: datetime | None = None
    ended_at: datetime | None = None
    parameters: dict[str, str | int | float | bool] = Field(default_factory=dict)

    @field_validator("started_at", "ended_at")
    @classmethod
    def datetime_must_be_aware(cls, v: datetime | None) -> datetime | None:
        if v is not None and v.tzinfo is None:
            raise ValueError("Datetime must be timezone-aware (use UTC)")
        return v
