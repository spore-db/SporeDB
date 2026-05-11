"""Integration tests for BatchStore CRUD operations."""

from __future__ import annotations

import time
from unittest.mock import patch
from uuid import UUID

import pyarrow.parquet as pq
import pytest

from sporedb.models.batch import Batch
from sporedb.storage import BatchStore, StorageEngine


class TestBatchStoreCreate:
    def test_create_and_get_batch(self, data_root, sample_batch):
        """Create a batch, retrieve by ID, and verify all fields match."""
        with StorageEngine(data_root) as engine:
            store = BatchStore(engine)
            created = store.create_batch(sample_batch)

            assert created.batch_id == sample_batch.batch_id

            retrieved = store.get_batch(sample_batch.batch_id)
            assert retrieved is not None
            assert retrieved.batch_id == sample_batch.batch_id
            assert retrieved.name == sample_batch.name
            assert retrieved.lifecycle == sample_batch.lifecycle
            assert retrieved.metadata.strain == sample_batch.metadata.strain
            assert retrieved.metadata.operator == sample_batch.metadata.operator
            assert retrieved.metadata.scale_liters == sample_batch.metadata.scale_liters
            assert retrieved.tags == sample_batch.tags
            assert (
                retrieved.timestamps.inoculation == sample_batch.timestamps.inoculation
            )

    def test_create_persists_to_parquet(self, data_root, sample_batch):
        """Verify the catalog Parquet file exists after creating a batch."""
        with StorageEngine(data_root) as engine:
            store = BatchStore(engine)
            store.create_batch(sample_batch)

        catalog = data_root / "batches.parquet"
        assert catalog.exists()

    def test_batch_survives_engine_restart(self, data_root, sample_batch):
        """Batch persists across engine close + reopen."""
        with StorageEngine(data_root) as engine:
            store = BatchStore(engine)
            store.create_batch(sample_batch)

        # Reopen engine
        with StorageEngine(data_root) as engine2:
            store2 = BatchStore(engine2)
            retrieved = store2.get_batch(sample_batch.batch_id)
            assert retrieved is not None
            assert retrieved.name == sample_batch.name


class TestBatchStoreList:
    def test_list_batches_empty(self, data_root):
        """list_batches on empty store returns empty list."""
        with StorageEngine(data_root) as engine:
            store = BatchStore(engine)
            assert store.list_batches() == []

    def test_list_batches(self, data_root):
        """list_batches returns all created batches."""
        with StorageEngine(data_root) as engine:
            store = BatchStore(engine)
            names = ["Run-A", "Run-B", "Run-C"]
            for name in names:
                store.create_batch(Batch(name=name))

            batches = store.list_batches()
            assert len(batches) == 3
            assert {b.name for b in batches} == set(names)


class TestBatchStoreUpdate:
    def test_update_batch(self, data_root, sample_batch):
        """update_batch changes metadata and updated_at advances."""
        with StorageEngine(data_root) as engine:
            store = BatchStore(engine)
            store.create_batch(sample_batch)

            original_updated_at = sample_batch.updated_at
            time.sleep(0.01)  # Ensure time advances

            sample_batch.metadata.strain = "HEK-293"
            updated = store.update_batch(sample_batch)

            assert updated.metadata.strain == "HEK-293"
            assert updated.updated_at > original_updated_at

            retrieved = store.get_batch(sample_batch.batch_id)
            assert retrieved is not None
            assert retrieved.metadata.strain == "HEK-293"


class TestBatchStoreDelete:
    def test_delete_batch(self, data_root, sample_batch):
        """delete_batch removes batch from catalog."""
        with StorageEngine(data_root) as engine:
            store = BatchStore(engine)
            store.create_batch(sample_batch)

            result = store.delete_batch(sample_batch.batch_id)
            assert result is True

            retrieved = store.get_batch(sample_batch.batch_id)
            assert retrieved is None

    def test_delete_nonexistent_batch(self, data_root):
        """delete_batch returns False for unknown batch_id."""
        with StorageEngine(data_root) as engine:
            store = BatchStore(engine)
            fake_id = UUID("00000000-0000-0000-0000-000000000001")
            assert store.delete_batch(fake_id) is False


class TestBatchStoreGetMissing:
    def test_get_batch_returns_none_for_nonexistent(self, data_root, sample_batch):
        """get_batch returns None for non-existent batch_id."""
        with StorageEngine(data_root) as engine:
            store = BatchStore(engine)
            store.create_batch(sample_batch)

            fake_id = UUID("00000000-0000-0000-0000-000000000099")
            assert store.get_batch(fake_id) is None

    def test_get_batch_empty_store(self, data_root):
        """get_batch returns None when no catalog exists."""
        with StorageEngine(data_root) as engine:
            store = BatchStore(engine)
            fake_id = UUID("00000000-0000-0000-0000-000000000001")
            assert store.get_batch(fake_id) is None


class TestBatchStoreAtomicWrite:
    """Tests for atomic file write behavior (HI-08)."""

    def test_catalog_valid_after_create(self, data_root, sample_batch):
        """After create_batch, the catalog file is valid Parquet."""
        with StorageEngine(data_root) as engine:
            store = BatchStore(engine)
            store.create_batch(sample_batch)

        catalog = data_root / "batches.parquet"
        assert catalog.exists()
        table = pq.read_table(catalog)
        assert table.num_rows == 1
        assert table.column("batch_id")[0].as_py() == str(sample_batch.batch_id)

    def test_catalog_unchanged_on_write_failure(self, data_root, sample_batch):
        """If Parquet write fails, the original catalog is preserved."""
        with StorageEngine(data_root) as engine:
            store = BatchStore(engine)
            store.create_batch(sample_batch)

        catalog = data_root / "batches.parquet"
        original_size = catalog.stat().st_size

        # Attempt to create a second batch but make pq.write_table fail
        batch2 = Batch(name="Run-B")
        with StorageEngine(data_root) as engine:
            store = BatchStore(engine)
            with (
                patch(
                    "sporedb.storage.batch_store.pq.write_table",
                    side_effect=OSError("disk full"),
                ),
                pytest.raises(OSError, match="disk full"),
            ):
                store.create_batch(batch2)

        # Original catalog should be unchanged
        assert catalog.exists()
        assert catalog.stat().st_size == original_size
        with StorageEngine(data_root) as engine:
            store = BatchStore(engine)
            batches = store.list_batches()
            assert len(batches) == 1
            assert batches[0].name == sample_batch.name

    def test_atomic_write_uses_tempfile(self, data_root, sample_batch):
        """Verify that batch store writes go through _atomic_write_table."""
        import inspect

        from sporedb.storage.batch_store import _atomic_write_table

        source = inspect.getsource(_atomic_write_table)
        assert "tempfile.mkstemp" in source
        assert "os.replace(" in source or ".rename(" in source
