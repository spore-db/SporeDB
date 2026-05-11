"""Tests for PhaseStore -- Parquet persistence of phase annotations."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from uuid_utils import uuid7

from sporedb.analytics.models import PhaseAnnotation, PhaseType
from sporedb.analytics.phase_store import PhaseStore


def _make_batch_id() -> UUID:
    return UUID(str(uuid7()))


def _make_phase_annotations(batch_id: UUID, count: int = 3) -> list[PhaseAnnotation]:
    """Create a list of contiguous phase annotations for testing."""
    base = datetime(2026, 1, 1, 0, 0, tzinfo=UTC)
    phases = [
        (PhaseType.LAG, 0, 50),
        (PhaseType.EXPONENTIAL, 50, 150),
        (PhaseType.STATIONARY, 150, 230),
        (PhaseType.DECLINE, 230, 260),
    ]
    annotations = []
    for i in range(min(count, len(phases))):
        ptype, start_min, end_min = phases[i]
        annotations.append(
            PhaseAnnotation(
                batch_id=batch_id,
                phase_type=ptype,
                start_ts=base + timedelta(minutes=start_min),
                end_ts=base + timedelta(minutes=end_min),
                signal_variable="OD600",
                confidence=0.95,
                metadata={"growth_rate": 0.05 * (i + 1)},
            )
        )
    return annotations


class TestPhaseStore:
    """Tests 1-6: PhaseStore Parquet persistence."""

    def test_save_phases_writes_parquet(self, analytics_engine):
        """Test 1: save_phases writes PhaseAnnotation list to Parquet file."""
        store = PhaseStore(analytics_engine)
        batch_id = _make_batch_id()
        annotations = _make_phase_annotations(batch_id, count=3)

        count = store.save_phases(batch_id, annotations)
        assert count == 3

    def test_get_phases_returns_saved(self, analytics_engine):
        """Test 2: get_phases returns list[PhaseAnnotation] matching what was saved."""
        store = PhaseStore(analytics_engine)
        batch_id = _make_batch_id()
        annotations = _make_phase_annotations(batch_id, count=3)

        store.save_phases(batch_id, annotations)
        loaded = store.get_phases(batch_id)

        assert len(loaded) == 3
        for orig, loaded_ann in zip(annotations, loaded, strict=True):
            assert loaded_ann.batch_id == orig.batch_id
            assert loaded_ann.phase_type == orig.phase_type
            assert loaded_ann.signal_variable == orig.signal_variable

    def test_get_phases_empty_when_no_file(self, analytics_engine):
        """Test 3: get_phases returns empty list when no phase file exists."""
        store = PhaseStore(analytics_engine)
        batch_id = _make_batch_id()
        result = store.get_phases(batch_id)
        assert result == []

    def test_save_phases_appends(self, analytics_engine):
        """Test 4: save_phases appends to existing file."""
        store = PhaseStore(analytics_engine)
        batch_id = _make_batch_id()

        first_batch = _make_phase_annotations(batch_id, count=2)
        store.save_phases(batch_id, first_batch)

        second_batch = _make_phase_annotations(batch_id, count=1)
        store.save_phases(batch_id, second_batch)

        loaded = store.get_phases(batch_id)
        assert len(loaded) == 3  # 2 + 1

    def test_round_trip_fidelity(self, analytics_engine):
        """Test 5: PhaseAnnotation round-trips with correct types."""
        store = PhaseStore(analytics_engine)
        batch_id = _make_batch_id()
        original = _make_phase_annotations(batch_id, count=4)

        store.save_phases(batch_id, original)
        loaded = store.get_phases(batch_id)

        assert len(loaded) == 4
        for orig, rt in zip(original, loaded, strict=True):
            assert isinstance(rt.annotation_id, UUID)
            assert isinstance(rt.batch_id, UUID)
            assert rt.annotation_id == orig.annotation_id
            assert rt.batch_id == orig.batch_id
            assert rt.phase_type == orig.phase_type
            assert isinstance(rt.phase_type, PhaseType)
            assert rt.start_ts == orig.start_ts
            assert rt.end_ts == orig.end_ts
            assert rt.confidence == pytest.approx(orig.confidence)
            assert rt.metadata == orig.metadata

    def test_delete_phases(self, analytics_engine):
        """Test 6: delete_phases removes the phase annotation file."""
        store = PhaseStore(analytics_engine)
        batch_id = _make_batch_id()
        annotations = _make_phase_annotations(batch_id, count=2)

        store.save_phases(batch_id, annotations)
        assert len(store.get_phases(batch_id)) == 2

        result = store.delete_phases(batch_id)
        assert result is True

        assert store.get_phases(batch_id) == []

        # Second delete returns False (file already gone)
        assert store.delete_phases(batch_id) is False
