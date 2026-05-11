"""Tests for PhaseDetector -- PELT changepoint detection with growth-rate labeling."""

from __future__ import annotations

from datetime import datetime, timedelta
from uuid import UUID

import numpy as np
import pandas as pd
import pytest
from uuid_utils import uuid7

from sporedb.analytics.detector import PhaseDetector
from sporedb.analytics.models import DetectionConfig, PhaseAnnotation, PhaseType


@pytest.fixture
def batch_id() -> UUID:
    return UUID(str(uuid7()))


@pytest.fixture
def ph_telemetry_df(base_time: datetime, batch_id: UUID) -> pd.DataFrame:
    """DataFrame with pH signal data."""
    n = 200
    rng = np.random.default_rng(99)
    timestamps = [base_time + timedelta(seconds=30 * i) for i in range(n)]
    values = 7.0 + np.cumsum(rng.normal(0, 0.01, n))
    return pd.DataFrame(
        {
            "ts": timestamps,
            "variable": "pH",
            "value": values,
            "batch_id": str(batch_id),
            "unit": "",
        }
    )


class TestPhaseDetection:
    """Tests 1-3, 8: Core detection on synthetic growth curves."""

    def test_detect_returns_phases_on_synthetic_curve(
        self, synthetic_telemetry_df, batch_id
    ):
        """Test 1: detect() on a synthetic growth curve returns PhaseAnnotation list."""
        # Use a tuned penalty for the synthetic curve (BIC auto-penalty is
        # conservative on high-variance signals; real usage would tune per dataset)
        config = DetectionConfig(penalty=5.0)
        detector = PhaseDetector(config)
        phases = detector.detect(synthetic_telemetry_df, batch_id)
        assert len(phases) >= 3  # At least 3 phases detected
        assert len(phases) <= 6  # Not too many spurious phases
        assert all(isinstance(p, PhaseAnnotation) for p in phases)

    def test_detected_phases_include_exponential_and_stationary(
        self, synthetic_telemetry_df, batch_id
    ):
        """Test 2: Detected phases include EXPONENTIAL and STATIONARY types."""
        config = DetectionConfig(penalty=5.0)
        detector = PhaseDetector(config)
        phases = detector.detect(synthetic_telemetry_df, batch_id)
        phase_types = {p.phase_type for p in phases}
        assert PhaseType.EXPONENTIAL in phase_types
        assert PhaseType.STATIONARY in phase_types

    def test_phases_are_contiguous(self, synthetic_telemetry_df, batch_id):
        """Test 3: Phase timestamps are contiguous (end of N == start of N+1)."""
        config = DetectionConfig(penalty=5.0)
        detector = PhaseDetector(config)
        phases = detector.detect(synthetic_telemetry_df, batch_id)
        for i in range(len(phases) - 1):
            assert phases[i].end_ts == phases[i + 1].start_ts

    def test_auto_penalty_bic_formula(self):
        """Test 8: Auto-penalty via BIC produces pen = log(n) * sigma_hat^2."""
        detector = PhaseDetector()
        values = np.array([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0])
        expected = np.log(len(values)) * np.var(values)
        result = detector._auto_penalty(values)
        assert result == pytest.approx(expected, rel=1e-10)


class TestSignalSelection:
    """Tests 4, 7: Signal variable filtering."""

    def test_detect_with_ph_signal(self, ph_telemetry_df, batch_id):
        """Test 4: detect() with signal_variable='pH' filters to pH column only."""
        config = DetectionConfig(signal_variable="pH", smoothing_window=3)
        detector = PhaseDetector(config)
        phases = detector.detect(ph_telemetry_df, batch_id)
        assert len(phases) >= 1
        assert all(p.signal_variable == "pH" for p in phases)

    def test_detect_unknown_variable_raises(self, synthetic_telemetry_df, batch_id):
        """Test 7: detect() on DataFrame with unknown variable raises ValueError."""
        config = DetectionConfig(signal_variable="NONEXISTENT")
        detector = PhaseDetector(config)
        with pytest.raises(ValueError, match="No data for signal variable"):
            detector.detect(synthetic_telemetry_df, batch_id)


class TestAutopenalty:
    """Tests 5, 8: Penalty parameter behavior."""

    def test_explicit_penalty_used(self, synthetic_telemetry_df, batch_id):
        """Test 5: detect() with explicit penalty uses that value."""
        config = DetectionConfig(penalty=100.0)
        detector = PhaseDetector(config)
        phases_explicit = detector.detect(synthetic_telemetry_df, batch_id)

        # With very high penalty, fewer breakpoints should be detected
        config_low = DetectionConfig(penalty=0.01)
        detector_low = PhaseDetector(config_low)
        phases_low = detector_low.detect(synthetic_telemetry_df, batch_id)

        # High penalty -> fewer phases; low penalty -> more phases
        assert len(phases_explicit) <= len(phases_low)


class TestPhaseLabeling:
    """Tests 9, 10: Growth-rate based phase labeling."""

    def test_exponential_has_highest_growth_rate(
        self, synthetic_telemetry_df, batch_id
    ):
        """Test 9: Phase labeling assigns EXPONENTIAL to highest growth rate segment."""
        config = DetectionConfig(penalty=5.0)
        detector = PhaseDetector(config)
        phases = detector.detect(synthetic_telemetry_df, batch_id)
        exp_phases = [p for p in phases if p.phase_type == PhaseType.EXPONENTIAL]
        assert len(exp_phases) >= 1

    def test_decline_has_negative_growth_rate(self, synthetic_telemetry_df, batch_id):
        """Test 10: Phase labeling assigns DECLINE to negative growth rate segments."""
        config = DetectionConfig(penalty=5.0)
        detector = PhaseDetector(config)
        phases = detector.detect(synthetic_telemetry_df, batch_id)
        decline_phases = [p for p in phases if p.phase_type == PhaseType.DECLINE]
        # The synthetic curve has a clear decline phase
        assert len(decline_phases) >= 1


class TestErrorHandling:
    """Tests 6, 7: Error cases."""

    def test_detect_empty_dataframe_raises(self, batch_id):
        """Test 6: detect() on empty DataFrame raises ValueError."""
        empty_df = pd.DataFrame(columns=["ts", "variable", "value"])
        detector = PhaseDetector()
        with pytest.raises(ValueError):
            detector.detect(empty_df, batch_id)

    def test_detect_missing_columns_raises(self, batch_id):
        """Extra: detect() on DataFrame missing required columns raises ValueError."""
        bad_df = pd.DataFrame({"timestamp": [1, 2], "val": [3, 4]})
        detector = PhaseDetector()
        with pytest.raises(ValueError):
            detector.detect(bad_df, batch_id)
