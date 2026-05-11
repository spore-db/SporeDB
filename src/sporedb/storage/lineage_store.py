"""Process lineage DAG storage and traversal."""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

import pyarrow as pa
import pyarrow.parquet as pq

from sporedb.models.lineage import UnitOperation
from sporedb.storage.batch_store import _atomic_write_table
from sporedb.storage.engine import StorageEngine
from sporedb.storage.parquet_layout import ParquetLayout

_LINEAGE_SCHEMA = pa.schema(
    [
        ("operation_id", pa.string()),
        ("batch_id", pa.string()),
        ("name", pa.string()),
        ("operation_type", pa.string()),
        ("parent_ids", pa.string()),  # JSON-serialized list of UUID strings
        ("started_at", pa.timestamp("us", tz="UTC")),
        ("ended_at", pa.timestamp("us", tz="UTC")),
        ("parameters", pa.string()),  # JSON-serialized dict
    ]
)


def _serialize_operation(op: UnitOperation) -> dict[str, Any]:
    """Serialize a UnitOperation to a flat dict for Parquet storage."""
    return {
        "operation_id": str(op.operation_id),
        "batch_id": str(op.batch_id),
        "name": op.name,
        "operation_type": op.operation_type,
        "parent_ids": json.dumps([str(pid) for pid in op.parent_ids]),
        "started_at": op.started_at,
        "ended_at": op.ended_at,
        "parameters": json.dumps(op.parameters),
    }


def _deserialize_operation(row: dict[str, Any]) -> UnitOperation:
    """Deserialize a flat dict from Parquet back to a UnitOperation."""
    parent_ids_raw = json.loads(row["parent_ids"]) if row["parent_ids"] else []
    parameters_raw = json.loads(row["parameters"]) if row["parameters"] else {}
    return UnitOperation(
        operation_id=UUID(row["operation_id"]),
        batch_id=UUID(row["batch_id"]),
        name=row["name"],
        operation_type=row["operation_type"],
        parent_ids=[UUID(pid) for pid in parent_ids_raw],
        started_at=row.get("started_at"),
        ended_at=row.get("ended_at"),
        parameters=parameters_raw,
    )


class LineageStore:
    """Storage and traversal for process lineage DAG.

    Persists unit operations as Parquet files per batch,
    with parent_ids encoding DAG edges. Supports BFS traversal
    in both upstream and downstream directions.

    Args:
        engine: A :class:`StorageEngine` instance providing the DuckDB
            connection and data root path.
    """

    def __init__(self, engine: StorageEngine) -> None:
        self._engine = engine
        self._layout = ParquetLayout(engine.data_root)

    def add_operation(self, operation: UnitOperation) -> UnitOperation:
        """Add a unit operation to the lineage DAG. Returns the operation."""
        from sporedb.storage._locking import parquet_lock

        row = _serialize_operation(operation)
        arrays = []
        for field in _LINEAGE_SCHEMA:
            arrays.append(pa.array([row[field.name]], type=field.type))
        new_table = pa.table(arrays, schema=_LINEAGE_SCHEMA)

        path = self._layout.lineage_file(operation.batch_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        with parquet_lock(path):
            if path.exists():
                existing = pq.read_table(path, schema=_LINEAGE_SCHEMA)  # type: ignore[no-untyped-call]
                combined = pa.concat_tables([existing, new_table])
            else:
                combined = new_table
            _atomic_write_table(combined, path)
        return operation

    def get_operations(self, batch_id: UUID) -> list[UnitOperation]:
        """Get all operations for a batch. Returns empty list if none."""
        path = self._layout.lineage_file(batch_id)
        if not path.exists():
            return []
        table = pq.read_table(path, schema=_LINEAGE_SCHEMA)  # type: ignore[no-untyped-call]
        df = table.to_pandas()
        return [_deserialize_operation(row.to_dict()) for _, row in df.iterrows()]

    def get_downstream(self, operation_id: UUID, batch_id: UUID) -> list[UnitOperation]:
        """Get all downstream operations from a given operation (BFS traversal)."""
        all_ops = self.get_operations(batch_id)

        visited: set[UUID] = set()
        queue = [operation_id]
        result: list[UnitOperation] = []

        while queue:
            current_id = queue.pop(0)
            if current_id in visited:
                continue
            visited.add(current_id)

            for op in all_ops:
                if current_id in op.parent_ids and op.operation_id not in visited:
                    result.append(op)
                    queue.append(op.operation_id)

        return result

    def get_upstream(self, operation_id: UUID, batch_id: UUID) -> list[UnitOperation]:
        """Get all upstream (ancestor) operations from a given operation."""
        all_ops = self.get_operations(batch_id)
        ops_by_id = {op.operation_id: op for op in all_ops}

        visited: set[UUID] = set()
        queue = [operation_id]
        result: list[UnitOperation] = []

        while queue:
            current_id = queue.pop(0)
            if current_id in visited:
                continue
            visited.add(current_id)

            current_op = ops_by_id.get(current_id)
            if current_op is None:
                continue

            for parent_id in current_op.parent_ids:
                if parent_id not in visited:
                    parent_op = ops_by_id.get(parent_id)
                    if parent_op:
                        result.append(parent_op)
                        queue.append(parent_id)

        return result
