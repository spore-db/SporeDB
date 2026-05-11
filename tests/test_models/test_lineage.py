"""Tests for the UnitOperation (lineage) domain model."""

from datetime import UTC, datetime
from uuid import UUID

from sporedb.models.lineage import UnitOperation


class TestUnitOperation:
    def test_unit_operation_required_fields(self):
        """UnitOperation requires batch_id, name, operation_type; auto operation_id."""
        op = UnitOperation(
            batch_id=UUID("019daaa3-f447-7cc0-9d52-f81ada15c2bb"),
            name="fermentation",
            operation_type="upstream",
        )
        assert isinstance(op.operation_id, UUID)
        assert op.operation_id.version == 7
        assert op.batch_id == UUID("019daaa3-f447-7cc0-9d52-f81ada15c2bb")
        assert op.name == "fermentation"
        assert op.operation_type == "upstream"

    def test_unit_operation_parent_ids_defaults_empty(self):
        """UnitOperation.parent_ids defaults to empty list."""
        op = UnitOperation(
            batch_id=UUID("019daaa3-f447-7cc0-9d52-f81ada15c2bb"),
            name="seed_train",
            operation_type="upstream",
        )
        assert op.parent_ids == []

    def test_unit_operation_dag_edges(self):
        """UnitOperation with parent_ids=[uuid1, uuid2] validates (DAG edges)."""
        parent1 = UUID("019daaa3-f447-7cc0-9d52-f81ada15c2b1")
        parent2 = UUID("019daaa3-f447-7cc0-9d52-f81ada15c2b2")
        op = UnitOperation(
            batch_id=UUID("019daaa3-f447-7cc0-9d52-f81ada15c2bb"),
            name="centrifugation",
            operation_type="downstream",
            parent_ids=[parent1, parent2],
        )
        assert len(op.parent_ids) == 2
        assert parent1 in op.parent_ids
        assert parent2 in op.parent_ids

    def test_unit_operation_parameters(self):
        """UnitOperation.parameters stores dict[str, str]."""
        op = UnitOperation(
            batch_id=UUID("019daaa3-f447-7cc0-9d52-f81ada15c2bb"),
            name="fermentation",
            operation_type="upstream",
            parameters={
                "temperature": "37C",
                "ph_setpoint": "7.0",
                "do_setpoint": "40%",
            },
        )
        assert op.parameters["temperature"] == "37C"
        assert len(op.parameters) == 3

    def test_unit_operation_parameters_defaults_empty(self):
        """UnitOperation.parameters defaults to empty dict."""
        op = UnitOperation(
            batch_id=UUID("019daaa3-f447-7cc0-9d52-f81ada15c2bb"),
            name="seed_train",
            operation_type="upstream",
        )
        assert op.parameters == {}

    def test_unit_operation_timestamps(self):
        """UnitOperation started_at and ended_at are optional datetime fields."""
        op = UnitOperation(
            batch_id=UUID("019daaa3-f447-7cc0-9d52-f81ada15c2bb"),
            name="fermentation",
            operation_type="upstream",
            started_at=datetime(2026, 4, 20, 8, 0, tzinfo=UTC),
            ended_at=datetime(2026, 4, 25, 10, 0, tzinfo=UTC),
        )
        assert op.started_at is not None
        assert op.ended_at is not None

    def test_unit_operation_model_dump_roundtrip(self):
        """UnitOperation model_dump round-trips through model_validate."""
        parent1 = UUID("019daaa3-f447-7cc0-9d52-f81ada15c2b1")
        op = UnitOperation(
            batch_id=UUID("019daaa3-f447-7cc0-9d52-f81ada15c2bb"),
            name="chromatography",
            operation_type="downstream",
            parent_ids=[parent1],
            parameters={"column": "Protein-A", "flow_rate": "2mL/min"},
            started_at=datetime(2026, 4, 25, 10, 0, tzinfo=UTC),
        )
        restored = UnitOperation.model_validate(op.model_dump())
        assert restored == op
