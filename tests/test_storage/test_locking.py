"""Tests for file-level locking on Parquet read-modify-write operations.

Verifies that concurrent writes to the same Parquet file don't lose data
when protected by parquet_lock.
"""

from __future__ import annotations

import inspect
import threading
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from sporedb.storage._locking import parquet_lock


class TestParquetLock:
    """Test the parquet_lock context manager."""

    def test_lock_creates_lock_file(self, tmp_path):
        """parquet_lock should create a .lock file adjacent to the target."""
        target = tmp_path / "data.parquet"
        target.touch()
        with parquet_lock(target):
            lock_file = Path(str(target) + ".lock")
            assert lock_file.exists()

    def test_lock_allows_single_writer(self, tmp_path):
        """Basic usage: lock, write, release."""
        target = tmp_path / "data.parquet"
        table = pa.table({"x": [1, 2, 3]})
        with parquet_lock(target):
            pq.write_table(table, target)
        result = pq.read_table(target)
        assert result.num_rows == 3

    def test_lock_serializes_concurrent_writers(self, tmp_path):
        """Two threads writing to the same file must not lose data."""
        target = tmp_path / "data.parquet"
        schema = pa.schema([("value", pa.int64())])
        # Create initial file
        pq.write_table(pa.table({"value": []}, schema=schema), target)

        errors = []
        writes_per_thread = 50

        def append_rows(thread_id: int):
            try:
                for i in range(writes_per_thread):
                    with parquet_lock(target):
                        existing = pq.read_table(target, schema=schema)
                        new_row = pa.table(
                            {"value": [thread_id * 1000 + i]}, schema=schema
                        )
                        combined = pa.concat_tables([existing, new_row])
                        pq.write_table(combined, target)
            except Exception as e:
                errors.append(e)

        t1 = threading.Thread(target=append_rows, args=(1,))
        t2 = threading.Thread(target=append_rows, args=(2,))
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        assert not errors, f"Errors during concurrent writes: {errors}"
        result = pq.read_table(target)
        assert result.num_rows == writes_per_thread * 2, (
            f"Expected {writes_per_thread * 2} rows, got {result.num_rows} — data lost!"
        )

    def test_lock_timeout_raises(self, tmp_path):
        """If lock is held too long, timeout should raise."""
        from filelock import Timeout

        target = tmp_path / "data.parquet"
        target.touch()

        acquired = threading.Event()
        release = threading.Event()

        def hold_lock():
            with parquet_lock(target, timeout=10):
                acquired.set()
                release.wait(timeout=5)

        holder = threading.Thread(target=hold_lock)
        holder.start()
        acquired.wait(timeout=2)

        # Try to acquire with very short timeout
        with pytest.raises(Timeout), parquet_lock(target, timeout=0.1):
            pass

        release.set()
        holder.join()


class TestTsStoreLocking:
    """Verify ts_store uses locking for append operations."""

    def test_append_telemetry_uses_lock(self, tmp_path):
        """append_telemetry should be protected by parquet_lock."""
        from sporedb.storage.ts_store import _append_to_parquet

        source = inspect.getsource(_append_to_parquet)
        assert "parquet_lock" in source, (
            "_append_to_parquet must use parquet_lock for concurrent safety"
        )


class TestBatchStoreLocking:
    """Verify batch_store uses locking for write operations."""

    def test_create_batch_uses_lock(self):
        """create_batch should be protected by parquet_lock."""
        from sporedb.storage.batch_store import BatchStore

        source = inspect.getsource(BatchStore.create_batch)
        assert "parquet_lock" in source, (
            "create_batch must use parquet_lock for TOCTOU safety"
        )
