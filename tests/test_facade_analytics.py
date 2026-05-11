"""Tests for SporeDB facade analytics methods (BOCPD, golden batch, PAT, PhaseStore)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from sporedb.analytics.models import PhaseAnnotation
from sporedb.analytics.pat import LinearSoftSensor
from sporedb.analytics.phase_store import PhaseStore
from sporedb.client import SporeDB
from sporedb.models.timeseries import TelemetryRecord


def _ingest_synthetic_telemetry(db: SporeDB, batch_id, n: int = 100) -> None:
    """Ingest synthetic OD600 telemetry with a clear lag-to-exponential transition.

    First 40 points near-constant at 0.1 (lag), last 60 linearly increasing to 5.0.
    """
    timestamps = pd.date_range("2024-01-01", periods=n, freq="1h", tz="UTC")
    values = np.concatenate(
        [
            np.full(40, 0.1) + np.random.default_rng(42).normal(0, 0.005, 40),
            np.linspace(0.1, 5.0, 60),
        ]
    )
    records = [
        TelemetryRecord(
            batch_id=batch_id,
            ts=timestamps[i].to_pydatetime(),
            variable="OD600",
            value=float(values[i]),
        )
        for i in range(n)
    ]
    db._timeseries.append_telemetry(records)


@pytest.fixture()
def sample_db(tmp_path):
    """Create a SporeDB with one batch containing synthetic OD600 telemetry."""
    db = SporeDB(tmp_path / "data")
    batch = db.create_batch("TestBatch-001", strain="CHO-K1")
    _ingest_synthetic_telemetry(db, batch.batch_id)
    yield db, batch.batch_id
    db.close()


@pytest.fixture()
def two_batch_db(tmp_path):
    """Create a SporeDB with two batches of similar synthetic telemetry."""
    db = SporeDB(tmp_path / "data")
    bid1 = db.create_batch("Batch-A", strain="CHO-K1").batch_id
    bid2 = db.create_batch("Batch-B", strain="CHO-K1").batch_id
    for bid in (bid1, bid2):
        _ingest_synthetic_telemetry(db, bid)
    yield db, bid1, bid2
    db.close()


class TestDetectPhasesPersists:
    def test_detect_phases_persists(self, sample_db):
        """detect_phases() should persist results via PhaseStore."""
        db, batch_id = sample_db
        annotations = db.detect_phases(batch_id)
        assert isinstance(annotations, list)
        # Verify persistence
        stored = PhaseStore(db._engine).get_phases(batch_id)
        assert len(stored) > 0
        assert all(isinstance(a, PhaseAnnotation) for a in stored)


class TestDetectPhasesOnline:
    def test_detect_phases_online_returns_list(self, sample_db):
        """detect_phases_online() should return a list without error."""
        db, batch_id = sample_db
        annotations = db.detect_phases_online(batch_id)
        assert isinstance(annotations, list)
        # May be empty depending on BOCPD sensitivity, but must be a list
        assert all(isinstance(a, PhaseAnnotation) for a in annotations)


class TestCreateGoldenProfile:
    def test_create_golden_profile(self, two_batch_db):
        """create_golden_profile() should return a profile with mean trajectory."""
        db, bid1, bid2 = two_batch_db
        from sporedb.analytics.models import GoldenBatchProfile

        profile = db.create_golden_profile([bid1, bid2], variables=["OD600"])
        assert isinstance(profile, GoldenBatchProfile)
        assert len(profile.mean_trajectory) > 0
        assert profile.variables == ["OD600"]


class TestScoreBatch:
    def test_score_batch(self, two_batch_db):
        """score_batch() should return a BatchScore with score in [0, 100]."""
        db, bid1, bid2 = two_batch_db
        from sporedb.analytics.models import BatchScore

        profile = db.create_golden_profile([bid1, bid2], variables=["OD600"])
        score = db.score_batch(profile, bid1)
        assert isinstance(score, BatchScore)
        assert 0 <= score.score <= 100


class TestPredictPAT:
    def test_predict_pat(self, sample_db):
        """predict_pat() should return a DataFrame with the predicted variable."""
        db, batch_id = sample_db
        sensor = LinearSoftSensor(
            input_variable="OD600",
            output_variable="glucose_predicted",
            slope=-2.0,
            intercept=10.0,
        )
        result = db.predict_pat(batch_id, sensor)
        assert isinstance(result, pd.DataFrame)
        assert "glucose_predicted" in result["variable"].unique()
        # Original OD600 data should still be present
        assert "OD600" in result["variable"].unique()
