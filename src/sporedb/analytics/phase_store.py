"""Parquet persistence for phase annotations.

Follows the same pattern as LineageStore: module-level Arrow schema,
serialize/deserialize functions, and a store class that reads/writes
Parquet files via the ParquetLayout path conventions.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import UUID

import pyarrow as pa
import pyarrow.parquet as pq

from sporedb.analytics.models import PhaseAnnotation, PhaseType
from sporedb.storage.engine import StorageEngine
from sporedb.storage.parquet_layout import ParquetLayout

_PHASE_SCHEMA = pa.schema(
    [
        ("annotation_id", pa.string()),
        ("batch_id", pa.string()),
        ("phase_type", pa.string()),
        ("start_ts", pa.timestamp("us", tz="UTC")),
        ("end_ts", pa.timestamp("us", tz="UTC")),
        ("signal_variable", pa.string()),
        ("confidence", pa.float64()),
        ("metadata", pa.string()),  # JSON-serialized dict
    ]
)


def _serialize_phase(ann: PhaseAnnotation) -> dict[str, Any]:
    """Serialize a PhaseAnnotation to a flat dict for Parquet storage."""
    return {
        "annotation_id": str(ann.annotation_id),
        "batch_id": str(ann.batch_id),
        "phase_type": ann.phase_type.value,
        "start_ts": ann.start_ts,
        "end_ts": ann.end_ts,
        "signal_variable": ann.signal_variable,
        "confidence": ann.confidence,
        "metadata": json.dumps(ann.metadata),
    }


def _deserialize_phase(row: dict[str, Any]) -> PhaseAnnotation:
    """Deserialize a flat dict from Parquet back to a PhaseAnnotation."""
    return PhaseAnnotation(
        annotation_id=UUID(row["annotation_id"]),
        batch_id=UUID(row["batch_id"]),
        phase_type=PhaseType(row["phase_type"]),
        start_ts=row["start_ts"],
        end_ts=row["end_ts"],
        signal_variable=row["signal_variable"],
        confidence=row["confidence"],
        metadata=json.loads(row["metadata"]) if row["metadata"] else {},
    )


def _records_to_table(
    phases: list[PhaseAnnotation],
) -> pa.Table:
    """Convert a list of PhaseAnnotation models to a PyArrow table."""
    rows = [_serialize_phase(ann) for ann in phases]
    arrays = []
    for field in _PHASE_SCHEMA:
        vals = [row[field.name] for row in rows]
        arrays.append(pa.array(vals, type=field.type))
    return pa.table(arrays, schema=_PHASE_SCHEMA)


def _append_to_parquet(file_path: Path, new_table: pa.Table) -> int:
    """Append rows to a Parquet file (read-concat-write). Returns row count appended."""
    from sporedb.storage._locking import parquet_lock

    file_path.parent.mkdir(parents=True, exist_ok=True)
    with parquet_lock(file_path):
        if file_path.exists():
            existing = pq.read_table(file_path, schema=new_table.schema)  # type: ignore[no-untyped-call]
            combined = pa.concat_tables([existing, new_table])
        else:
            combined = new_table
        pq.write_table(combined, file_path, use_dictionary=False)  # type: ignore[no-untyped-call]
    return new_table.num_rows  # type: ignore[no-any-return]


class PhaseStore:
    """Storage for phase annotations using Parquet files.

    Persists PhaseAnnotation objects per batch using the same
    Hive-partitioned layout as other SporeDB stores. Supports
    save (append), get (read all), and delete operations.
    """

    def __init__(self, engine: StorageEngine) -> None:
        self._engine = engine
        self._layout = ParquetLayout(engine.data_root)

    def save_phases(self, batch_id: UUID, phases: list[PhaseAnnotation]) -> int:
        """Save phase annotations to Parquet. Returns count saved.

        Appends to existing file if one exists for this batch.
        """
        if not phases:
            return 0
        table = _records_to_table(phases)
        path = self._layout.phases_file(batch_id)
        return _append_to_parquet(path, table)

    def get_phases(self, batch_id: UUID) -> list[PhaseAnnotation]:
        """Get all phase annotations for a batch.

        Returns empty list if no phase file exists.
        """
        path = self._layout.phases_file(batch_id)
        if not path.exists():
            return []
        table = pq.read_table(path, schema=_PHASE_SCHEMA)  # type: ignore[no-untyped-call]
        df = table.to_pandas()
        return [_deserialize_phase(row.to_dict()) for _, row in df.iterrows()]

    def delete_phases(self, batch_id: UUID) -> bool:
        """Delete phase annotations for a batch.

        Returns True if file existed and was deleted, False otherwise.
        """
        path = self._layout.phases_file(batch_id)
        if path.exists():
            path.unlink()
            return True
        return False
