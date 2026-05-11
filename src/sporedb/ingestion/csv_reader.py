"""CSV reader with encoding detection, dialect sniffing, and two-pass import."""

from __future__ import annotations

import contextlib
import csv
import time
from datetime import datetime
from pathlib import Path
from uuid import UUID

import pyarrow as pa
import pyarrow.parquet as pq
from charset_normalizer import from_bytes

from sporedb.ingestion.column_mapper import detect_columns
from sporedb.ingestion.result import ColumnMapping, ImportResult
from sporedb.ingestion.timestamp import (
    detect_elapsed_unit,
    detect_timestamp_column,
    parse_timestamps,
)
from sporedb.ingestion.units import (
    CANONICAL_UNITS,
    VARIABLE_CATEGORY,
    convert_unit,
    detect_unit_by_range,
    detect_unit_from_header,
    is_unit_row,
)
from sporedb.models.assay import AssayMeasurement
from sporedb.models.batch import Batch
from sporedb.models.timeseries import TelemetryRecord
from sporedb.storage.batch_store import BatchStore
from sporedb.storage.engine import StorageEngine
from sporedb.storage.ts_store import TimeSeriesStore

# Questionable value thresholds for warnings
_QUESTIONABLE_RULES: dict[str, tuple[float | None, float | None]] = {
    "ph": (0.0, 14.0),
    "biomass": (0.0, None),
    "dissolved_oxygen": (0.0, None),
}


def read_csv_safe(file_path: Path) -> tuple[list[str], list[list[str]], str]:
    """Read a CSV file with automatic encoding and dialect detection.

    Args:
        file_path: Path to the CSV file.

    Returns:
        Tuple of (headers, data_rows, detected_encoding).

    Raises:
        ValueError: If file is empty or unreadable.
    """
    file_path = Path(file_path).resolve()
    if not file_path.is_file():
        raise ValueError(f"File not found or not a regular file: {file_path}")

    raw_bytes = file_path.read_bytes()
    if not raw_bytes.strip():
        raise ValueError(f"File is empty: {file_path}")

    # Detect encoding
    detection = from_bytes(raw_bytes)
    best = detection.best()
    if best is None:
        # Fallback to UTF-8
        encoding = "utf-8"
        text = raw_bytes.decode("utf-8", errors="replace")
    else:
        encoding = str(best.encoding)
        text = str(best)

    # Detect dialect
    sample = text[:8192]
    try:
        dialect = csv.Sniffer().sniff(sample)
    except csv.Error:
        dialect = csv.excel

    # Parse CSV
    lines = text.splitlines()
    reader = csv.reader(lines, dialect)
    rows = list(reader)

    if not rows:
        raise ValueError(f"No parseable data in CSV: {file_path}")

    headers = rows[0]
    data_rows = rows[1:]

    if not headers or all(h.strip() == "" for h in headers):
        raise ValueError(f"No valid headers found in CSV: {file_path}")

    return (headers, data_rows, encoding)


def _parse_rows_to_records(
    rows: list[list[str]],
    headers: list[str],
    mapping: ColumnMapping,
    batch_id: UUID,
    timestamps: list[datetime],
    unit_conversions: dict[str, tuple[str, str]],
    data_type: str = "telemetry",
) -> tuple[
    list[TelemetryRecord | AssayMeasurement],
    list[str],
    dict[str, tuple[str, str]],
]:
    """Convert raw rows to TelemetryRecord or AssayMeasurement instances.

    Returns:
        Tuple of (records, warnings, units_converted).
    """
    records: list[TelemetryRecord | AssayMeasurement] = []
    warnings: list[str] = []
    units_converted: dict[str, tuple[str, str]] = dict(unit_conversions)

    # Map header index to variable name
    header_to_idx = {h: i for i, h in enumerate(headers)}

    for row_idx, row in enumerate(rows):
        if row_idx >= len(timestamps):
            break
        ts = timestamps[row_idx]

        for source_col, variable in mapping.variable_mappings.items():
            col_idx = header_to_idx.get(source_col)
            if col_idx is None or col_idx >= len(row):
                continue

            raw_value = row[col_idx].strip()
            if not raw_value:
                continue

            try:
                value = float(raw_value)
            except (ValueError, TypeError):
                continue

            # Apply unit conversion if applicable
            if source_col in unit_conversions:
                from_unit, to_unit = unit_conversions[source_col]
                converted, warn = convert_unit(from_unit, to_unit, value)
                if converted is not None:
                    value = converted
                elif warn:
                    warnings.append(f"Row {row_idx + 1}, {source_col}: {warn}")

            # Check questionable values
            var_lower = variable.lower()
            if var_lower in _QUESTIONABLE_RULES:
                lo, hi = _QUESTIONABLE_RULES[var_lower]
                if lo is not None and value < lo:
                    warnings.append(
                        f"Row {row_idx + 1}: questionable {variable} "
                        f"value {value} (< {lo})"
                    )
                if hi is not None and value > hi:
                    warnings.append(
                        f"Row {row_idx + 1}: questionable {variable} "
                        f"value {value} (> {hi})"
                    )

            # Determine unit
            unit: str | None = None
            if source_col in unit_conversions:
                _, unit = unit_conversions[source_col]
            else:
                category = VARIABLE_CATEGORY.get(variable)
                if category:
                    unit = CANONICAL_UNITS.get(category)

            if data_type == "assay":
                records.append(
                    AssayMeasurement(
                        batch_id=batch_id,
                        ts=ts,
                        variable=variable,
                        value=value,
                        unit=unit,
                    )
                )
            else:
                records.append(
                    TelemetryRecord(
                        batch_id=batch_id,
                        ts=ts,
                        variable=variable,
                        value=value,
                        unit=unit,
                    )
                )

    return (records, warnings, units_converted)


def _store_original_values(
    data_root: Path,
    batch_id: UUID,
    headers: list[str],
    rows: list[list[str]],
) -> None:
    """Write original pre-conversion values to a sidecar Parquet file.

    Stored at: data_root/original/{batch_id}/telemetry.parquet
    """
    sidecar_dir = data_root / "original" / str(batch_id)
    sidecar_dir.mkdir(parents=True, exist_ok=True)

    # Build Arrow table from raw data
    arrays = {}
    for col_idx, header in enumerate(headers):
        col_values = [row[col_idx] if col_idx < len(row) else "" for row in rows]
        arrays[header] = pa.array(col_values, type=pa.string())

    table = pa.table(arrays)
    pq.write_table(table, sidecar_dir / "telemetry.parquet")  # type: ignore[no-untyped-call]


def _detect_unit_conversions(
    headers: list[str],
    mapping: ColumnMapping,
    data_rows: list[list[str]],
    unit_row_values: list[str] | None = None,
) -> dict[str, tuple[str, str]]:
    """Detect which columns need unit conversion.

    Returns:
        Dict of {source_col: (from_unit, to_unit)}.
    """
    conversions: dict[str, tuple[str, str]] = {}
    header_to_idx = {h: i for i, h in enumerate(headers)}

    for source_col, variable in mapping.variable_mappings.items():
        # Priority 1: Unit row
        from_unit: str | None = None
        if unit_row_values is not None:
            col_idx = header_to_idx.get(source_col)
            if col_idx is not None and col_idx < len(unit_row_values):
                unit_val = unit_row_values[col_idx].strip()
                if unit_val:
                    from_unit = unit_val

        # Priority 2: Header suffix
        if from_unit is None:
            from_unit = detect_unit_from_header(source_col)

        # Priority 3: Range heuristic
        if from_unit is None:
            col_idx = header_to_idx.get(source_col)
            if col_idx is not None:
                sample_values = []
                for row in data_rows[:10]:
                    if col_idx < len(row):
                        with contextlib.suppress(ValueError, TypeError):
                            sample_values.append(float(row[col_idx]))
                if sample_values:
                    from_unit = detect_unit_by_range(variable, sample_values)

        if from_unit is None:
            continue

        # Determine canonical unit
        category = VARIABLE_CATEGORY.get(variable)
        if category is None:
            continue
        canonical = CANONICAL_UNITS.get(category)
        if canonical is None:
            continue

        # Only record if conversion is needed
        if from_unit != canonical:
            conversions[source_col] = (from_unit, canonical)

    return conversions


def import_csv(
    file_path: Path | str,
    batch_name: str,
    engine: StorageEngine,
    mapping: ColumnMapping | None = None,
    inoculation_ts: datetime | None = None,
    custom_vocab: dict[str, list[str]] | None = None,
    data_type: str = "telemetry",
) -> ImportResult:
    """Import a CSV file into SporeDB.

    Supports two-pass flow:
    - Pass 1: Call with mapping=None to auto-detect column mapping.
    - Pass 2: Call with mapping=<confirmed ColumnMapping> to import with
      user-confirmed mapping.

    Args:
        file_path: Path to the CSV file.
        batch_name: Name for the new batch.
        engine: Storage engine instance.
        mapping: Pre-built column mapping (two-pass flow). If None, auto-detects.
        inoculation_ts: Reference timestamp for elapsed time conversion.
        custom_vocab: Additional vocabulary for column matching.
        data_type: Either "telemetry" or "assay".

    Returns:
        ImportResult with import statistics.

    Raises:
        ValueError: If file is empty, has no data, or elapsed time
            without inoculation_ts.
    """
    start_time = time.time()

    # 1. Resolve and validate path (T-02-05 mitigation)
    file_path = Path(file_path).resolve()
    if not file_path.is_file():
        raise ValueError(f"File not found or not a regular file: {file_path}")

    # 2. Read with encoding/dialect detection
    headers, data_rows, _encoding = read_csv_safe(file_path)

    if not data_rows:
        raise ValueError(f"CSV has headers but no data rows: {file_path}")

    # 3. Check for unit row in row 0 of data
    unit_row_values: list[str] | None = None
    if data_rows and is_unit_row(data_rows[0]):
        unit_row_values = data_rows[0]
        data_rows = data_rows[1:]
        if not data_rows:
            raise ValueError(f"CSV has only a unit row and no data: {file_path}")

    # 4. Auto-detect column mapping if not provided
    if mapping is None:
        mapping = detect_columns(headers, data_rows[:5], custom_vocab=custom_vocab)

    # 5. Detect and parse timestamps
    ts_col, is_elapsed = detect_timestamp_column(headers, data_rows[:5])

    # Override mapping's timestamp_col with detected one
    mapping_ts_col = mapping.timestamp_col or ts_col

    ts_col_idx = headers.index(mapping_ts_col) if mapping_ts_col in headers else None
    if ts_col_idx is None:
        raise ValueError(f"Timestamp column '{mapping_ts_col}' not found in headers")

    ts_values = [row[ts_col_idx] for row in data_rows if ts_col_idx < len(row)]

    if is_elapsed and inoculation_ts is None:
        raise ValueError(
            "Elapsed time detected but no inoculation_ts provided. "
            "Pass inoculation_ts parameter for elapsed-time CSV files."
        )

    elapsed_unit = detect_elapsed_unit(mapping_ts_col) if is_elapsed else "h"
    timestamps = parse_timestamps(
        ts_values, is_elapsed, reference_ts=inoculation_ts, elapsed_unit=elapsed_unit
    )

    # 6. Detect unit conversions
    unit_conversions = _detect_unit_conversions(
        headers, mapping, data_rows, unit_row_values
    )

    # 7. Store original values
    _store_original_values(
        engine.data_root, _placeholder_batch_id := _temp_batch_id(), headers, data_rows
    )

    # 8. Create Batch
    batch = Batch(name=batch_name)
    batch_store = BatchStore(engine)
    batch = batch_store.create_batch(batch)

    # Move sidecar to correct batch_id location if placeholder was different
    _relocate_sidecar(engine.data_root, _placeholder_batch_id, batch.batch_id)

    # 9. Convert rows to records
    records, warnings, units_converted_final = _parse_rows_to_records(
        data_rows,
        headers,
        mapping,
        batch.batch_id,
        timestamps,
        unit_conversions,
        data_type,
    )

    # 10. Persist
    ts_store = TimeSeriesStore(engine)
    if data_type == "assay":
        ts_store.append_assay(records)  # type: ignore[arg-type]
    else:
        ts_store.append_telemetry(records)  # type: ignore[arg-type]

    # 11. Build ImportResult
    elapsed = time.time() - start_time
    return ImportResult(
        batch_id=batch.batch_id,
        rows_imported=len(records),
        columns_mapped=mapping.variable_mappings,
        units_converted=units_converted_final,
        warnings=warnings,
        elapsed_seconds=elapsed,
    )


def _temp_batch_id() -> UUID:
    """Generate a temporary batch_id for sidecar storage before batch creation."""
    from uuid_utils import uuid7

    return UUID(str(uuid7()))


def _relocate_sidecar(data_root: Path, old_id: UUID, new_id: UUID) -> None:
    """Move sidecar Parquet from temp batch_id dir to actual batch_id dir."""
    if old_id == new_id:
        return
    old_dir = data_root / "original" / str(old_id)
    new_dir = data_root / "original" / str(new_id)
    if old_dir.exists():
        new_dir.mkdir(parents=True, exist_ok=True)
        for f in old_dir.iterdir():
            f.rename(new_dir / f.name)
        old_dir.rmdir()
