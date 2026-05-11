"""Batch CRUD operations with Parquet persistence."""

from __future__ import annotations

import json
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import UUID

import pyarrow as pa
import pyarrow.parquet as pq

from sporedb.models.batch import Batch
from sporedb.storage.engine import StorageEngine
from sporedb.storage.parquet_layout import ParquetLayout

if TYPE_CHECKING:
    from sporedb.query.filters import BatchFilter


# Flat Parquet schema for the batch catalog.
# Nested Pydantic models are flattened to avoid complex nested Parquet structures.
CATALOG_SCHEMA = pa.schema(
    [
        pa.field("batch_id", pa.string()),
        pa.field("name", pa.string()),
        pa.field("lifecycle", pa.string()),
        pa.field("ts_inoculation", pa.timestamp("us", tz="UTC")),
        pa.field("ts_feed_start", pa.timestamp("us", tz="UTC")),
        pa.field("ts_induction", pa.timestamp("us", tz="UTC")),
        pa.field("ts_harvest", pa.timestamp("us", tz="UTC")),
        pa.field("meta_strain", pa.string()),
        pa.field("meta_media", pa.string()),
        pa.field("meta_scale_liters", pa.float64()),
        pa.field("meta_operator", pa.string()),
        pa.field("meta_extra", pa.string()),  # JSON-encoded dict
        pa.field("tags", pa.string()),  # JSON-encoded list
        pa.field("created_at", pa.timestamp("us", tz="UTC")),
        pa.field("updated_at", pa.timestamp("us", tz="UTC")),
    ]
)


def _batch_to_flat_dict(batch: Batch) -> dict[str, Any]:
    """Flatten a Batch model into a dict matching the catalog Parquet schema."""
    return {
        "batch_id": str(batch.batch_id),
        "name": batch.name,
        "lifecycle": batch.lifecycle.value,
        "ts_inoculation": batch.timestamps.inoculation,
        "ts_feed_start": batch.timestamps.feed_start,
        "ts_induction": batch.timestamps.induction,
        "ts_harvest": batch.timestamps.harvest,
        "meta_strain": batch.metadata.strain,
        "meta_media": batch.metadata.media,
        "meta_scale_liters": batch.metadata.scale_liters,
        "meta_operator": batch.metadata.operator,
        "meta_extra": json.dumps(batch.metadata.extra),
        "tags": json.dumps(batch.tags),
        "created_at": batch.created_at,
        "updated_at": batch.updated_at,
    }


def _flat_dict_to_batch(row: dict[str, Any]) -> Batch:
    """Reconstruct a Batch model from a flat catalog row dict."""
    from sporedb.models.batch import (
        BatchLifecycle,
        BatchMetadata,
        CanonicalTimestamps,
    )

    return Batch.model_validate(
        {
            "batch_id": row["batch_id"],
            "name": row["name"],
            "lifecycle": BatchLifecycle(row["lifecycle"]),
            "timestamps": CanonicalTimestamps(
                inoculation=row.get("ts_inoculation"),
                feed_start=row.get("ts_feed_start"),
                induction=row.get("ts_induction"),
                harvest=row.get("ts_harvest"),
            ),
            "metadata": BatchMetadata(
                strain=row.get("meta_strain"),
                media=row.get("meta_media"),
                scale_liters=row.get("meta_scale_liters"),
                operator=row.get("meta_operator"),
                extra=json.loads(row.get("meta_extra") or "{}"),
            ),
            "tags": json.loads(row.get("tags") or "[]"),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }
    )


def _table_to_batches(table: pa.Table) -> list[Batch]:
    """Convert an Arrow table of catalog rows to a list of Batch models."""
    batches: list[Batch] = []
    for i in range(table.num_rows):
        row = {col: table.column(col)[i].as_py() for col in table.column_names}
        batches.append(_flat_dict_to_batch(row))
    return batches


def _atomic_write_table(table: pa.Table, path: Path) -> None:
    """Write a Parquet table atomically via tempfile + rename (HI-08).

    Ensures the catalog file is never left in a partially-written state
    if the process crashes mid-write.
    """
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), suffix=".parquet")
    os.close(fd)
    try:
        pq.write_table(table, tmp_name)  # type: ignore[no-untyped-call]
        os.replace(tmp_name, str(path))
    except BaseException:
        Path(tmp_name).unlink(missing_ok=True)
        raise


class BatchStore:
    """Batch CRUD operations backed by a Parquet catalog file.

    Uses PyArrow for direct catalog reads/writes (small file),
    and DuckDB for search queries with predicate pushdown.

    Args:
        engine: A :class:`StorageEngine` instance providing the DuckDB
            connection and data root path.
    """

    def __init__(self, engine: StorageEngine) -> None:
        self._engine = engine
        self._layout = ParquetLayout(engine.data_root)

    def create_batch(self, batch: Batch) -> Batch:
        """Persist a new batch to the catalog.

        Raises ValueError if batch_id already exists.
        """
        from sporedb.storage._locking import parquet_lock

        flat = _batch_to_flat_dict(batch)
        new_table = pa.Table.from_pylist([flat], schema=CATALOG_SCHEMA)

        catalog_path = self._layout.batches_catalog()
        with parquet_lock(catalog_path):
            if catalog_path.exists():
                existing = pq.read_table(catalog_path, schema=CATALOG_SCHEMA)  # type: ignore[no-untyped-call]
                bid_str = str(batch.batch_id)
                existing_ids = existing.column("batch_id").to_pylist()
                if bid_str in existing_ids:
                    raise ValueError(f"Batch {batch.batch_id} already exists")
                combined = pa.concat_tables([existing, new_table])
            else:
                combined = new_table

            _atomic_write_table(combined, catalog_path)
        return batch

    def get_batch(self, batch_id: UUID) -> Batch | None:
        """Retrieve a batch by ID. Returns None if not found."""
        catalog_path = self._layout.batches_catalog()
        if not catalog_path.exists():
            return None

        table = pq.read_table(catalog_path, schema=CATALOG_SCHEMA)  # type: ignore[no-untyped-call]
        bid_str = str(batch_id)
        for i in range(table.num_rows):
            if table.column("batch_id")[i].as_py() == bid_str:
                row = {col: table.column(col)[i].as_py() for col in table.column_names}
                return _flat_dict_to_batch(row)
        return None

    def list_batches(self) -> list[Batch]:
        """Return all batches in the catalog. Empty list if no catalog exists."""
        catalog_path = self._layout.batches_catalog()
        if not catalog_path.exists():
            return []

        table = pq.read_table(catalog_path, schema=CATALOG_SCHEMA)  # type: ignore[no-untyped-call]
        return _table_to_batches(table)

    def search_batches(self, filter: BatchFilter | None = None) -> list[Batch]:
        """Search batches using compound filter conditions via DuckDB.

        All filter values are passed as parameterized query parameters
        to prevent SQL injection.
        """
        catalog_path = self._layout.batches_catalog()
        if not catalog_path.exists():
            return []

        if filter is None:
            return self.list_batches()

        clauses, params = filter.to_sql_clauses()
        if not clauses:
            return self.list_batches()

        where = " AND ".join(clauses)
        sql = f"SELECT * FROM read_parquet(?) WHERE {where}"
        # First parameter is always the file path
        all_params = [str(catalog_path)] + params

        cursor = self._engine.con.execute(sql, all_params)
        result = cursor.fetchall()
        col_names = [desc[0] for desc in cursor.description]

        batches: list[Batch] = []
        for row_tuple in result:
            row = dict(zip(col_names, row_tuple, strict=False))
            batches.append(_flat_dict_to_batch(row))
        return batches

    def update_batch(self, batch: Batch) -> Batch:
        """Update a batch in the catalog. Sets updated_at to now(UTC).

        Reads all rows, replaces the matching batch_id, and rewrites.
        """
        catalog_path = self._layout.batches_catalog()
        if not catalog_path.exists():
            msg = f"Batch {batch.batch_id} not found"
            raise ValueError(msg)

        table = pq.read_table(catalog_path, schema=CATALOG_SCHEMA)  # type: ignore[no-untyped-call]
        bid_str = str(batch.batch_id)
        found = False
        rows: list[dict[str, Any]] = []

        for i in range(table.num_rows):
            row = {col: table.column(col)[i].as_py() for col in table.column_names}
            if row["batch_id"] == bid_str:
                batch.updated_at = datetime.now(UTC)
                rows.append(_batch_to_flat_dict(batch))
                found = True
            else:
                rows.append(row)

        if not found:
            msg = f"Batch {batch.batch_id} not found"
            raise ValueError(msg)

        new_table = pa.Table.from_pylist(rows, schema=CATALOG_SCHEMA)
        _atomic_write_table(new_table, catalog_path)
        return batch

    def delete_batch(self, batch_id: UUID) -> bool:
        """Remove a batch from the catalog. Returns True if found and deleted."""
        catalog_path = self._layout.batches_catalog()
        if not catalog_path.exists():
            return False

        table = pq.read_table(catalog_path, schema=CATALOG_SCHEMA)  # type: ignore[no-untyped-call]
        bid_str = str(batch_id)
        rows: list[dict[str, Any]] = []
        found = False

        for i in range(table.num_rows):
            row = {col: table.column(col)[i].as_py() for col in table.column_names}
            if row["batch_id"] == bid_str:
                found = True
            else:
                rows.append(row)

        if not found:
            return False

        if rows:
            new_table = pa.Table.from_pylist(rows, schema=CATALOG_SCHEMA)
            _atomic_write_table(new_table, catalog_path)
        else:
            # All batches deleted -- remove catalog file
            catalog_path.unlink()

        return True
