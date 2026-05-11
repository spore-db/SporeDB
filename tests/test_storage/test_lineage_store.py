"""Integration tests for LineageStore: DAG persistence and traversal."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import pytest
from uuid_utils import uuid7

from sporedb.models.lineage import UnitOperation
from sporedb.storage import StorageEngine
from sporedb.storage.lineage_store import LineageStore


def _make_uuid() -> UUID:
    return UUID(str(uuid7()))


@pytest.fixture
def batch_id() -> UUID:
    return _make_uuid()


@pytest.fixture
def lineage_store(data_root):
    with StorageEngine(data_root) as engine:
        yield LineageStore(engine)


def _make_dag(batch_id: UUID):
    """Create a 3-level DAG: seed_train -> fermentation -> centrifugation."""
    seed_train = UnitOperation(
        operation_id=_make_uuid(),
        batch_id=batch_id,
        name="seed_train",
        operation_type="upstream",
        parent_ids=[],
        started_at=datetime(2026, 4, 20, 8, 0, tzinfo=UTC),
        ended_at=datetime(2026, 4, 21, 8, 0, tzinfo=UTC),
        parameters={"volume_L": "0.5", "media": "CD-CHO"},
    )

    fermentation = UnitOperation(
        operation_id=_make_uuid(),
        batch_id=batch_id,
        name="fermentation",
        operation_type="upstream",
        parent_ids=[seed_train.operation_id],
        started_at=datetime(2026, 4, 21, 9, 0, tzinfo=UTC),
        ended_at=datetime(2026, 4, 28, 9, 0, tzinfo=UTC),
        parameters={"volume_L": "5.0", "temperature_C": "37"},
    )

    centrifugation = UnitOperation(
        operation_id=_make_uuid(),
        batch_id=batch_id,
        name="centrifugation",
        operation_type="downstream",
        parent_ids=[fermentation.operation_id],
        started_at=datetime(2026, 4, 28, 10, 0, tzinfo=UTC),
        ended_at=datetime(2026, 4, 28, 12, 0, tzinfo=UTC),
        parameters={"rpm": "4000", "duration_min": "30"},
    )

    return seed_train, fermentation, centrifugation


class TestAddAndGetOperations:
    def test_add_and_get_operations(self, lineage_store, batch_id):
        """Add operations and retrieve all for a batch."""
        seed, ferm, cent = _make_dag(batch_id)

        lineage_store.add_operation(seed)
        lineage_store.add_operation(ferm)
        lineage_store.add_operation(cent)

        ops = lineage_store.get_operations(batch_id)
        assert len(ops) == 3
        names = {op.name for op in ops}
        assert names == {"seed_train", "fermentation", "centrifugation"}

    def test_get_operations_empty_batch(self, lineage_store):
        """Get operations for a batch with no operations returns empty list."""
        empty_id = _make_uuid()
        ops = lineage_store.get_operations(empty_id)
        assert ops == []

    def test_operations_round_trip_parameters(self, lineage_store, batch_id):
        """Parameters dict preserved through storage round-trip."""
        seed, _, _ = _make_dag(batch_id)
        lineage_store.add_operation(seed)

        ops = lineage_store.get_operations(batch_id)
        assert len(ops) == 1
        assert ops[0].parameters == {"volume_L": "0.5", "media": "CD-CHO"}

    def test_add_operation_returns_operation(self, lineage_store, batch_id):
        """add_operation returns the UnitOperation that was added."""
        seed, _, _ = _make_dag(batch_id)
        result = lineage_store.add_operation(seed)
        assert isinstance(result, UnitOperation)
        assert result.operation_id == seed.operation_id


class TestDAGTraversal:
    def test_get_downstream(self, lineage_store, batch_id):
        """get_downstream from root returns all descendant operations."""
        seed, ferm, cent = _make_dag(batch_id)
        lineage_store.add_operation(seed)
        lineage_store.add_operation(ferm)
        lineage_store.add_operation(cent)

        downstream = lineage_store.get_downstream(seed.operation_id, batch_id)
        downstream_names = {op.name for op in downstream}
        assert downstream_names == {"fermentation", "centrifugation"}
        assert len(downstream) == 2

    def test_get_upstream(self, lineage_store, batch_id):
        """get_upstream from leaf returns all ancestor operations."""
        seed, ferm, cent = _make_dag(batch_id)
        lineage_store.add_operation(seed)
        lineage_store.add_operation(ferm)
        lineage_store.add_operation(cent)

        upstream = lineage_store.get_upstream(cent.operation_id, batch_id)
        upstream_names = {op.name for op in upstream}
        assert upstream_names == {"seed_train", "fermentation"}
        assert len(upstream) == 2

    def test_dag_three_levels_traversal(self, lineage_store, batch_id):
        """3-level DAG traverses correctly in both directions."""
        seed, ferm, cent = _make_dag(batch_id)
        lineage_store.add_operation(seed)
        lineage_store.add_operation(ferm)
        lineage_store.add_operation(cent)

        # From middle node
        downstream_from_ferm = lineage_store.get_downstream(ferm.operation_id, batch_id)
        assert len(downstream_from_ferm) == 1
        assert downstream_from_ferm[0].name == "centrifugation"

        upstream_from_ferm = lineage_store.get_upstream(ferm.operation_id, batch_id)
        assert len(upstream_from_ferm) == 1
        assert upstream_from_ferm[0].name == "seed_train"

    def test_dag_edges_from_parent_ids(self, lineage_store, batch_id):
        """add_operation with parent_ids creates DAG edges correctly."""
        seed, ferm, _ = _make_dag(batch_id)
        lineage_store.add_operation(seed)
        lineage_store.add_operation(ferm)

        ops = lineage_store.get_operations(batch_id)
        ferm_op = next(op for op in ops if op.name == "fermentation")
        assert seed.operation_id in ferm_op.parent_ids
