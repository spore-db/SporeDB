"""Tests for BatchFilter and search_batches compound queries."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from sporedb.models.batch import (
    Batch,
    BatchLifecycle,
    BatchMetadata,
    CanonicalTimestamps,
)
from sporedb.query.filters import BatchFilter
from sporedb.storage import BatchStore, StorageEngine


@pytest.fixture
def populated_store(data_root):
    """Create a store with 5 diverse batches for filter testing."""
    engine = StorageEngine(data_root)
    store = BatchStore(engine)

    batches = [
        Batch(
            name="CHO-Run-001",
            lifecycle=BatchLifecycle.RUNNING,
            timestamps=CanonicalTimestamps(
                inoculation=datetime(2026, 1, 15, 8, 0, tzinfo=UTC),
            ),
            metadata=BatchMetadata(strain="CHO-K1", operator="Dr. Smith"),
            tags=["mAb", "scale-up"],
        ),
        Batch(
            name="CHO-Run-002",
            lifecycle=BatchLifecycle.HARVESTED,
            timestamps=CanonicalTimestamps(
                inoculation=datetime(2026, 3, 10, 10, 0, tzinfo=UTC),
            ),
            metadata=BatchMetadata(strain="CHO-K1", operator="Dr. Jones"),
            tags=["mAb", "production"],
        ),
        Batch(
            name="HEK-Run-001",
            lifecycle=BatchLifecycle.RUNNING,
            timestamps=CanonicalTimestamps(
                inoculation=datetime(2026, 5, 20, 12, 0, tzinfo=UTC),
            ),
            metadata=BatchMetadata(strain="HEK-293", operator="Dr. Smith"),
            tags=["AAV", "research"],
        ),
        Batch(
            name="EColi-Run-001",
            lifecycle=BatchLifecycle.ABORTED,
            timestamps=CanonicalTimestamps(
                inoculation=datetime(2026, 2, 1, 6, 0, tzinfo=UTC),
            ),
            metadata=BatchMetadata(strain="E.coli-BL21", operator="Dr. Patel"),
            tags=["enzyme", "scale-up"],
        ),
        Batch(
            name="CHO-Run-003",
            lifecycle=BatchLifecycle.PLANNED,
            metadata=BatchMetadata(strain="CHO-K1", operator="Dr. Smith"),
            tags=["mAb"],
        ),
    ]

    for b in batches:
        store.create_batch(b)

    yield store, batches
    engine.close()


class TestBatchFilterSQL:
    def test_empty_filter_no_clauses(self):
        """BatchFilter with no conditions produces no SQL clauses."""
        f = BatchFilter()
        clauses, params = f.to_sql_clauses()
        assert clauses == []
        assert params == []

    def test_strain_filter_clause(self):
        """BatchFilter(strain=...) produces parameterized clause."""
        f = BatchFilter(strain="CHO-K1")
        clauses, params = f.to_sql_clauses()
        assert len(clauses) == 1
        assert "meta_strain = ?" in clauses[0]
        assert params == ["CHO-K1"]

    def test_compound_filter_clauses(self):
        """Multiple fields produce AND-joined clauses."""
        f = BatchFilter(strain="CHO-K1", operator="Dr. Smith", tags=["mAb"])
        clauses, params = f.to_sql_clauses()
        assert len(clauses) == 3
        assert all("?" in c for c in clauses)


class TestSearchBatches:
    def test_empty_filter_returns_all(self, populated_store):
        """BatchFilter() with no conditions returns all batches."""
        store, batches = populated_store
        results = store.search_batches(BatchFilter())
        assert len(results) == 5

    def test_none_filter_returns_all(self, populated_store):
        """search_batches(None) returns all batches."""
        store, batches = populated_store
        results = store.search_batches(None)
        assert len(results) == 5

    def test_filter_by_strain(self, populated_store):
        """Filter by strain returns only matching batches."""
        store, _ = populated_store
        results = store.search_batches(BatchFilter(strain="CHO-K1"))
        assert len(results) == 3
        assert all(b.metadata.strain == "CHO-K1" for b in results)

    def test_filter_by_operator(self, populated_store):
        """Filter by operator returns only matching batches."""
        store, _ = populated_store
        results = store.search_batches(BatchFilter(operator="Dr. Smith"))
        assert len(results) == 3
        assert all(b.metadata.operator == "Dr. Smith" for b in results)

    def test_filter_by_tags(self, populated_store):
        """Filter by tags returns batches containing the specified tag."""
        store, _ = populated_store
        results = store.search_batches(BatchFilter(tags=["mAb"]))
        assert len(results) == 3
        assert all("mAb" in b.tags for b in results)

    def test_filter_by_date_range(self, populated_store):
        """Filter by inoculation date range returns correct subset."""
        store, _ = populated_store
        results = store.search_batches(
            BatchFilter(
                inoculation_after=datetime(2026, 1, 1, tzinfo=UTC),
                inoculation_before=datetime(2026, 4, 1, tzinfo=UTC),
            )
        )
        assert len(results) == 3  # Jan, Feb, Mar inoculations

    def test_filter_by_lifecycle(self, populated_store):
        """Filter by lifecycle state returns correct batches."""
        store, _ = populated_store
        results = store.search_batches(BatchFilter(lifecycle=BatchLifecycle.RUNNING))
        assert len(results) == 2
        assert all(b.lifecycle == BatchLifecycle.RUNNING for b in results)

    def test_compound_filter(self, populated_store):
        """Compound filter (strain + tags) applies AND condition."""
        store, _ = populated_store
        results = store.search_batches(
            BatchFilter(
                strain="CHO-K1",
                tags=["scale-up"],
            )
        )
        assert len(results) == 1
        assert results[0].name == "CHO-Run-001"

    def test_compound_filter_strain_operator(self, populated_store):
        """Compound filter strain + operator narrows correctly."""
        store, _ = populated_store
        results = store.search_batches(
            BatchFilter(
                strain="CHO-K1",
                operator="Dr. Smith",
            )
        )
        assert len(results) == 2
        names = {b.name for b in results}
        assert "CHO-Run-001" in names
        assert "CHO-Run-003" in names

    def test_search_batches_with_compound_filter_returns_correct_subset(
        self, populated_store
    ):
        """Full compound filter with strain + tags + lifecycle."""
        store, _ = populated_store
        results = store.search_batches(
            BatchFilter(
                strain="CHO-K1",
                lifecycle=BatchLifecycle.RUNNING,
                tags=["mAb"],
            )
        )
        assert len(results) == 1
        assert results[0].name == "CHO-Run-001"
