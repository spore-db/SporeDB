"""Result model for connector pull operations."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field


class PullResult(BaseModel):
    """Result of a connector pull operation.

    Extends the pattern from ``sporedb.ingestion.result.ImportResult``
    with connector-specific fields: source_system, source_identifier,
    and external_ids for cross-system traceability.
    """

    batch_id: UUID
    source_system: str  # "influxdb", "osisoft_pi", "labvantage", "scinote"
    source_identifier: str  # measurement name, PI point path, sample ID
    rows_imported: int
    columns_mapped: dict[str, str] = Field(default_factory=dict)
    external_ids: dict[str, str] = Field(
        default_factory=dict
    )  # lims_sample_id, eln_experiment_id
    warnings: list[str] = Field(default_factory=list)
    elapsed_seconds: float
