"""Time-series storage for telemetry and assay data with ASOF JOIN unified view."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any
from uuid import UUID

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from sporedb.models.assay import AssayMeasurement, UncertainValue
from sporedb.models.timeseries import TelemetryRecord
from sporedb.storage.batch_store import _atomic_write_table
from sporedb.storage.engine import StorageEngine
from sporedb.storage.parquet_layout import ParquetLayout

# Arrow schemas for consistent Parquet files
_TELEMETRY_SCHEMA = pa.schema(
    [
        ("batch_id", pa.string()),
        ("ts", pa.timestamp("us", tz="UTC")),
        ("variable", pa.string()),
        ("value", pa.float64()),
        ("unit", pa.string()),
    ]
)

_ASSAY_SCHEMA = pa.schema(
    [
        ("batch_id", pa.string()),
        ("ts", pa.timestamp("us", tz="UTC")),
        ("variable", pa.string()),
        ("value", pa.float64()),
        ("uncertainty", pa.float64()),
        ("unit", pa.string()),
        ("method", pa.string()),
    ]
)


def _records_to_table(
    records: list[Any], schema: pa.Schema, serialize_fn: Callable[[Any], dict[str, Any]]
) -> pa.Table:
    """Convert a list of Pydantic models to a PyArrow table."""
    rows = [serialize_fn(r) for r in records]
    arrays = []
    for field in schema:
        vals = [row[field.name] for row in rows]
        arrays.append(pa.array(vals, type=field.type))
    return pa.table(arrays, schema=schema)


def _serialize_telemetry(r: TelemetryRecord) -> dict[str, Any]:
    return {
        "batch_id": str(r.batch_id),
        "ts": r.ts,
        "variable": r.variable,
        "value": r.value,
        "unit": r.unit or "",
    }


def _serialize_assay(r: AssayMeasurement) -> dict[str, Any]:
    return {
        "batch_id": str(r.batch_id),
        "ts": r.ts,
        "variable": r.variable,
        "value": r.value,
        "uncertainty": r.uncertainty,
        "unit": r.unit or "",
        "method": r.method or "",
    }


def _append_to_parquet(file_path: Path, new_table: pa.Table) -> int:
    """Append rows to a Parquet file (read-concat-write). Returns row count appended.

    Uses ``parquet_lock`` to serialize concurrent access and prevent data loss.
    """
    from sporedb.storage._locking import parquet_lock

    file_path.parent.mkdir(parents=True, exist_ok=True)
    with parquet_lock(file_path):
        if file_path.exists():
            existing = pq.read_table(file_path, schema=new_table.schema)  # type: ignore[no-untyped-call]
            combined = pa.concat_tables([existing, new_table])
        else:
            combined = new_table
        _atomic_write_table(combined, file_path)
    return new_table.num_rows  # type: ignore[no-any-return]


class TimeSeriesStore:
    """Storage for telemetry and assay time-series data.

    Uses Parquet files organized by batch_id (Hive partitioning)
    and DuckDB ASOF JOIN for unified temporal views.

    Args:
        engine: A :class:`StorageEngine` instance providing the DuckDB
            connection and data root path.
    """

    def __init__(self, engine: StorageEngine) -> None:
        self._engine = engine
        self._layout = ParquetLayout(engine.data_root)

    def append_telemetry(self, records: list[TelemetryRecord]) -> int:
        """Append telemetry records to batch Parquet file. Returns count appended.

        All records must share the same batch_id.
        """
        if not records:
            return 0
        batch_ids = {r.batch_id for r in records}
        if len(batch_ids) != 1:
            raise ValueError(
                f"All records must share the same batch_id; got {batch_ids}"
            )
        batch_id = records[0].batch_id
        table = _records_to_table(records, _TELEMETRY_SCHEMA, _serialize_telemetry)
        path = self._layout.telemetry_file(batch_id)
        return _append_to_parquet(path, table)

    def get_telemetry(self, batch_id: UUID) -> pd.DataFrame:
        """Get all telemetry for a batch. Returns empty DataFrame if none."""
        path = self._layout.telemetry_file(batch_id)
        if not path.exists():
            return pd.DataFrame()
        return pq.read_table(path, schema=_TELEMETRY_SCHEMA).to_pandas()  # type: ignore[no-untyped-call, no-any-return]

    def append_assay(self, records: list[AssayMeasurement]) -> int:
        """Append assay measurements to batch Parquet file. Returns count appended.

        All records must share the same batch_id.
        """
        if not records:
            return 0
        batch_ids = {r.batch_id for r in records}
        if len(batch_ids) != 1:
            raise ValueError(
                f"All records must share the same batch_id; got {batch_ids}"
            )
        batch_id = records[0].batch_id
        table = _records_to_table(records, _ASSAY_SCHEMA, _serialize_assay)
        path = self._layout.assay_file(batch_id)
        return _append_to_parquet(path, table)

    def get_assay(self, batch_id: UUID) -> pd.DataFrame:
        """Get all assay data for a batch. Returns empty DataFrame if none."""
        path = self._layout.assay_file(batch_id)
        if not path.exists():
            return pd.DataFrame()
        return pq.read_table(path, schema=_ASSAY_SCHEMA).to_pandas()  # type: ignore[no-untyped-call, no-any-return]

    def get_assay_as_uncertain(
        self, batch_id: UUID, variable: str
    ) -> list[UncertainValue]:
        """Get assay measurements as UncertainValue objects.

        Used for uncertainty propagation.
        """
        df = self.get_assay(batch_id)
        if df.empty:
            return []
        filtered = df[df["variable"] == variable]
        return [
            UncertainValue(
                value=row["value"],
                uncertainty=row["uncertainty"],
                unit=row.get("unit", ""),
            )
            for _, row in filtered.iterrows()
        ]

    def get_unified_view(self, batch_id: UUID) -> pd.DataFrame:
        """ASOF JOIN telemetry and assay for a unified time-series view.

        Links each assay measurement to the nearest prior telemetry timestamp.
        Uses DuckDB ASOF JOIN for efficient temporal alignment.
        """
        telemetry_path = self._layout.telemetry_file(batch_id)
        assay_path = self._layout.assay_file(batch_id)

        if not telemetry_path.exists() or not assay_path.exists():
            return pd.DataFrame()

        # File paths are constructed from validated UUID objects (T-03-01 mitigation).
        # Paths passed as parameterized values, not interpolated into SQL
        # (T-03-02 mitigation).
        sql = """
            SELECT
                a.ts       AS assay_ts,
                a.variable AS analyte,
                a.value    AS assay_value,
                a.uncertainty AS assay_uncertainty,
                a.unit     AS assay_unit,
                a.method   AS assay_method,
                t.ts       AS telemetry_ts,
                t.variable AS sensor,
                t.value    AS sensor_value,
                t.unit     AS sensor_unit
            FROM read_parquet(?) a
            ASOF JOIN read_parquet(?) t
                ON a.ts >= t.ts
            ORDER BY a.ts
        """
        return self._engine.con.execute(
            sql, [str(assay_path), str(telemetry_path)]
        ).fetchdf()
