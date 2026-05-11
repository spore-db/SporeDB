from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field


class ColumnMapping(BaseModel):
    """Result of column detection: maps source columns to SporeDB variables."""

    timestamp_col: str
    variable_mappings: dict[str, str] = Field(default_factory=dict)
    unit_mappings: dict[str, str] = Field(default_factory=dict)
    unmapped_cols: list[str] = Field(default_factory=list)
    confidence: dict[str, float] = Field(default_factory=dict)


class ImportResult(BaseModel):
    """Result of a data import operation.

    Returned by :meth:`~sporedb.SporeDB.import_csv` and
    :meth:`~sporedb.SporeDB.import_excel` to report import statistics.

    Attributes:
        batch_id: UUID of the batch that was created or updated.
        rows_imported: Total number of rows successfully imported.
        columns_mapped: Mapping of source column names to SporeDB variable names.
        units_converted: Mapping of variable names to ``(source_unit, target_unit)``
            tuples where unit conversion was applied.
        warnings: List of warning messages generated during import.
        elapsed_seconds: Wall-clock time for the import operation.

    Example:
        >>> result = db.import_csv("telemetry.csv", "CHO-Run-001")
        >>> print(
        ...     f"Imported {result.rows_imported} rows in {result.elapsed_seconds:.2f}s"
        ... )
    """

    batch_id: UUID
    rows_imported: int
    columns_mapped: dict[str, str] = Field(default_factory=dict)
    units_converted: dict[str, tuple[str, str]] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    elapsed_seconds: float
