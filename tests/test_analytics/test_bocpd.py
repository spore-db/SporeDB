"""Tests for BOCPDDetector -- Bayesian Online Changepoint Detection."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

import numpy as np
import pandas as pd
import pytest
from uuid_utils import uuid7

from sporedb.analytics.models import BOCPDConfig, PhaseAnnotation, PhaseType


@pytest.fixture
def batch_id() -> UUID:
    return UUID(str(uuid7()))


@pytest.fixture
def base_time() -> datetime:
    return datetime(2026, 1, 1, 0, 0, tzinfo=UTC)


def _step_signal(rng: np.random.Generator) -> np.ndarray:
    """500 points N(0,0.1) then 500 points N(5,0.1). Changepoint at index 500."""
    seg1 = rng.normal(0, 0.1, 500)
    seg2 = rng.normal(5, 0.1, 500)
    return np.concatenate([seg1, seg2])


def _multi_changepoint_signal(rng: np.random.Generator) -> np.ndarray:
    """3 segments of 300 points at means 0, 5, 2. Changepoints at 300, 600."""
    seg1 = rng.normal(0, 0.1, 300)
    seg2 = rng.normal(5, 0.1, 300)
    seg3 = rng.normal(2, 0.1, 300)
    return np.concatenate([seg1, seg2, seg3])


class TestBOCPDUpdate:
    """Incremental update behavior."""

    def test_incremental_update(self):
        from sporedb.analytics.bocpd import BOCPDDetector

        detector = BOCPDDetector()
        result = detector.update(1.0)
        assert isinstance(result, tuple)
        assert len(result) == 2
        detected, prob = result
        assert isinstance(detected, bool)
        assert isinstance(prob, float)
        assert 0.0 <= prob <= 1.0

    def test_no_changepoint_constant(self):
        from sporedb.analytics.bocpd import BOCPDDetector

        rng = np.random.default_rng(42)
        signal = rng.normal(0, 0.1, 500)
        detector = BOCPDDetector()
        detections = []
        for x in signal:
            detected, _ = detector.update(x)
            detections.append(detected)
        # Constant signal should have very few or no detections
        # Allow up to 5 false positives on a constant signal
        assert sum(detections) <= 5


class TestBOCPDDetection:
    """Changepoint detection accuracy."""

    def test_step_changepoint(self):
        from sporedb.analytics.bocpd import BOCPDDetector

        rng = np.random.default_rng(42)
        signal = _step_signal(rng)
        config = BOCPDConfig(hazard_rate=0.01, threshold=0.3)
        detector = BOCPDDetector(config)
        changepoint_indices = []
        for i, x in enumerate(signal):
            detected, _ = detector.update(x)
            if detected:
                changepoint_indices.append(i)

        # Should detect at least one changepoint near index 500
        assert len(changepoint_indices) >= 1
        # At least one detection should be within 20 samples of the true changepoint
        near_500 = [idx for idx in changepoint_indices if abs(idx - 500) <= 20]
        assert len(near_500) >= 1, (
            f"No changepoint detected within 20 samples of index 500. "
            f"Detected at: {changepoint_indices}"
        )

    def test_multiple_changepoints(self):
        from sporedb.analytics.bocpd import BOCPDDetector

        rng = np.random.default_rng(42)
        signal = _multi_changepoint_signal(rng)
        config = BOCPDConfig(hazard_rate=0.01, threshold=0.3)
        detector = BOCPDDetector(config)
        changepoint_indices = []
        for i, x in enumerate(signal):
            detected, _ = detector.update(x)
            if detected:
                changepoint_indices.append(i)

        # Should detect approximately 2 changepoints (at ~300 and ~600)
        # BOCPD signals over a short window, so we cluster nearby detections.
        # At minimum we expect detections near both true changepoints.
        assert len(changepoint_indices) >= 2, "Expected at least 2 raw changepoints"

        # Cluster: detections within 20 samples are the same changepoint
        clusters: list[int] = []
        for idx in changepoint_indices:
            if not clusters or idx - clusters[-1] > 20:
                clusters.append(idx)
        assert len(clusters) >= 2, (
            f"Expected 2 clusters, got {len(clusters)}: {clusters}"
        )
        assert len(clusters) <= 4, f"Too many clusters: {len(clusters)}"


class TestBOCPDMemory:
    """Memory management and state reset."""

    def test_memory_truncation(self):
        from sporedb.analytics.bocpd import BOCPDDetector

        config = BOCPDConfig(max_run_length=500)
        detector = BOCPDDetector(config)
        rng = np.random.default_rng(42)
        for x in rng.normal(0, 1, 1000):
            detector.update(x)
        assert len(detector.run_length_probs) <= 501

    def test_reset(self):
        from sporedb.analytics.bocpd import BOCPDDetector

        detector = BOCPDDetector()
        rng = np.random.default_rng(42)
        for x in rng.normal(0, 1, 100):
            detector.update(x)
        assert detector.t > 0
        detector.reset()
        assert detector.t == 0
        assert len(detector.run_length_probs) == 1


class TestBOCPDIntegration:
    """Integration with PhaseAnnotation and DataFrame input."""

    def test_phase_annotation_output(self, batch_id, base_time):
        from sporedb.analytics.bocpd import BOCPDDetector

        rng = np.random.default_rng(42)
        signal = _step_signal(rng)
        n = len(signal)
        timestamps = [base_time + timedelta(seconds=30 * i) for i in range(n)]
        df = pd.DataFrame(
            {
                "ts": timestamps,
                "variable": "OD600",
                "value": signal,
            }
        )
        config = BOCPDConfig(hazard_rate=0.01, threshold=0.3)
        detector = BOCPDDetector(config)
        phases = detector.detect_batch(df, batch_id)
        assert isinstance(phases, list)
        assert all(isinstance(p, PhaseAnnotation) for p in phases)
        assert all(p.batch_id == batch_id for p in phases)
        assert all(isinstance(p.phase_type, PhaseType) for p in phases)

    def test_empty_input_raises(self, batch_id):
        from sporedb.analytics.bocpd import BOCPDDetector

        empty_df = pd.DataFrame(columns=["ts", "variable", "value"])
        detector = BOCPDDetector()
        with pytest.raises(ValueError):
            detector.detect_batch(empty_df, batch_id)
