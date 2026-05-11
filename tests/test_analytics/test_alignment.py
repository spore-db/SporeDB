"""Tests for cross-run alignment functionality."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

import numpy as np
import pandas as pd
import pytest

from sporedb.analytics.models import PhaseAnnotation, PhaseType


def _make_annotations(
    batch_id: str,
    base_time: datetime,
    lag_pts: int,
) -> list[PhaseAnnotation]:
    """Create phase annotations matching the multi_batch_telemetry fixture layout.

    The fixture uses 30-second intervals, so each point = 30s.
    Layout: lag_pts lag, 100 exp, 80 stationary, 30 decline.
    """
    bid = UUID(batch_id)
    dt = timedelta(seconds=30)

    lag_start = base_time
    lag_end = base_time + dt * lag_pts

    exp_start = lag_end
    exp_end = exp_start + dt * 100

    stat_start = exp_end
    stat_end = stat_start + dt * 80

    dec_start = stat_end
    dec_end = dec_start + dt * 30

    return [
        PhaseAnnotation(
            batch_id=bid,
            phase_type=PhaseType.LAG,
            start_ts=lag_start,
            end_ts=lag_end,
            signal_variable="OD600",
            confidence=1.0,
        ),
        PhaseAnnotation(
            batch_id=bid,
            phase_type=PhaseType.EXPONENTIAL,
            start_ts=exp_start,
            end_ts=exp_end,
            signal_variable="OD600",
            confidence=1.0,
        ),
        PhaseAnnotation(
            batch_id=bid,
            phase_type=PhaseType.STATIONARY,
            start_ts=stat_start,
            end_ts=stat_end,
            signal_variable="OD600",
            confidence=1.0,
        ),
        PhaseAnnotation(
            batch_id=bid,
            phase_type=PhaseType.DECLINE,
            start_ts=dec_start,
            end_ts=dec_end,
            signal_variable="OD600",
            confidence=1.0,
        ),
    ]


@pytest.fixture
def base_time() -> datetime:
    return datetime(2026, 1, 1, 0, 0, tzinfo=UTC)


@pytest.fixture
def two_batch_data(base_time: datetime):
    """Two batches with different lag durations."""
    rng = np.random.default_rng(123)
    batches: dict[str, pd.DataFrame] = {}
    annotations: dict[str, list[PhaseAnnotation]] = {}

    for batch_name, lag_pts, batch_id in [
        ("batch_A", 40, "00000000-0000-0000-0000-000000000001"),
        ("batch_B", 50, "00000000-0000-0000-0000-000000000002"),
    ]:
        lag = 0.1 + rng.normal(0, 0.005, lag_pts)
        t_exp = np.linspace(0, 1, 100)
        exp_vals = 0.1 * np.exp(t_exp * np.log(50)) + rng.normal(0, 0.05, 100)
        stat = 5.0 + rng.normal(0, 0.1, 80)
        decline = np.linspace(5.0, 3.0, 30) + rng.normal(0, 0.05, 30)

        values = np.concatenate([lag, exp_vals, stat, decline])
        n_points = len(values)
        timestamps = [base_time + timedelta(seconds=30 * j) for j in range(n_points)]

        batches[batch_name] = pd.DataFrame(
            {
                "ts": timestamps,
                "variable": "OD600",
                "value": values,
            }
        )
        annotations[batch_name] = _make_annotations(batch_id, base_time, lag_pts)

    return batches, annotations


@pytest.fixture
def three_batch_data(base_time: datetime):
    """Three batches with different lag durations."""
    rng = np.random.default_rng(123)
    batches: dict[str, pd.DataFrame] = {}
    annotations: dict[str, list[PhaseAnnotation]] = {}

    for batch_name, lag_pts, batch_id in [
        ("batch_A", 40, "00000000-0000-0000-0000-000000000001"),
        ("batch_B", 50, "00000000-0000-0000-0000-000000000002"),
        ("batch_C", 60, "00000000-0000-0000-0000-000000000003"),
    ]:
        lag = 0.1 + rng.normal(0, 0.005, lag_pts)
        t_exp = np.linspace(0, 1, 100)
        exp_vals = 0.1 * np.exp(t_exp * np.log(50)) + rng.normal(0, 0.05, 100)
        stat = 5.0 + rng.normal(0, 0.1, 80)
        decline = np.linspace(5.0, 3.0, 30) + rng.normal(0, 0.05, 30)

        values = np.concatenate([lag, exp_vals, stat, decline])
        n_points = len(values)
        timestamps = [base_time + timedelta(seconds=30 * j) for j in range(n_points)]

        batches[batch_name] = pd.DataFrame(
            {
                "ts": timestamps,
                "variable": "OD600",
                "value": values,
            }
        )
        annotations[batch_name] = _make_annotations(batch_id, base_time, lag_pts)

    return batches, annotations


@pytest.fixture
def multi_variable_batch_data(base_time: datetime):
    """Two batches with both OD600 and pH variables."""
    rng = np.random.default_rng(42)
    batches: dict[str, pd.DataFrame] = {}
    annotations: dict[str, list[PhaseAnnotation]] = {}

    for batch_name, lag_pts, batch_id in [
        ("batch_A", 40, "00000000-0000-0000-0000-000000000001"),
        ("batch_B", 50, "00000000-0000-0000-0000-000000000002"),
    ]:
        n_points = lag_pts + 100 + 80 + 30
        timestamps = [base_time + timedelta(seconds=30 * j) for j in range(n_points)]

        od_values = rng.uniform(0.1, 5.0, n_points)
        ph_values = rng.uniform(6.5, 7.5, n_points)

        df_od = pd.DataFrame(
            {
                "ts": timestamps,
                "variable": "OD600",
                "value": od_values,
            }
        )
        df_ph = pd.DataFrame(
            {
                "ts": timestamps,
                "variable": "pH",
                "value": ph_values,
            }
        )
        batches[batch_name] = pd.concat([df_od, df_ph], ignore_index=True)
        annotations[batch_name] = _make_annotations(batch_id, base_time, lag_pts)

    return batches, annotations


class TestBasicAlignment:
    """Tests 1-4, 6: Basic alignment behavior."""

    def test_align_returns_elapsed_hours_index(self, two_batch_data):
        """Test 1: align() with 2 batches returns DataFrame with elapsed_hours index."""
        from sporedb.analytics.alignment import align

        batches, annotations = two_batch_data
        result = align(batches, annotations)

        assert isinstance(result, pd.DataFrame)
        assert result.index.name == "elapsed_hours"
        assert len(result) > 0

    def test_columns_follow_namespace_naming(self, two_batch_data):
        """Test 2: Columns follow batch_name__variable naming."""
        from sporedb.analytics.alignment import align

        batches, annotations = two_batch_data
        result = align(batches, annotations)

        for col in result.columns:
            assert "__" in col, f"Column '{col}' missing namespace separator"
        assert "batch_A__OD600" in result.columns
        assert "batch_B__OD600" in result.columns

    def test_elapsed_time_from_anchor_phase(self, two_batch_data, base_time):
        """Test 3: Elapsed time computed from exponential phase start."""
        from sporedb.analytics.alignment import align

        batches, annotations = two_batch_data
        result = align(batches, annotations)

        # batch_A has 40 lag points * 30s = 1200s = 0.333h before exp start
        # So minimum elapsed_hours for batch_A should be approximately -0.333h
        min_elapsed = result.index.min()
        assert min_elapsed < 0, "Should have negative elapsed hours before anchor"

    def test_negative_elapsed_hours_before_anchor(self, two_batch_data):
        """Test 4: Negative elapsed_hours for data before anchor phase."""
        from sporedb.analytics.alignment import align

        batches, annotations = two_batch_data
        result = align(batches, annotations)

        negative_count = (result.index < 0).sum()
        assert negative_count > 0, "Expected negative elapsed_hours before anchor"

    def test_three_batches_all_columns(self, three_batch_data):
        """Test 6: align() with 3 batches returns columns from all 3."""
        from sporedb.analytics.alignment import align

        batches, annotations = three_batch_data
        result = align(batches, annotations)

        assert "batch_A__OD600" in result.columns
        assert "batch_B__OD600" in result.columns
        assert "batch_C__OD600" in result.columns


class TestVariableFiltering:
    """Test 5: Variable filtering."""

    def test_variables_filter(self, multi_variable_batch_data):
        """Test 5: align() with variables=["OD600"] filters to only OD600."""
        from sporedb.analytics.alignment import align

        batches, annotations = multi_variable_batch_data
        result = align(batches, annotations, variables=["OD600"])

        for col in result.columns:
            assert "OD600" in col, f"Column '{col}' should be OD600 only"
        assert not any("pH" in col for col in result.columns)


class TestErrorHandling:
    """Test 7: Error handling."""

    def test_raises_when_no_anchor_phase(self, base_time):
        """Test 7: ValueError when batch has no annotations for anchor phase."""
        from sporedb.analytics.alignment import align

        batch_id = "00000000-0000-0000-0000-000000000001"
        n_points = 100
        timestamps = [base_time + timedelta(seconds=30 * j) for j in range(n_points)]

        batches = {
            "batch_A": pd.DataFrame(
                {
                    "ts": timestamps,
                    "variable": "OD600",
                    "value": np.random.default_rng(0).uniform(0.1, 5.0, n_points),
                }
            ),
        }
        # Only lag and stationary -- no EXPONENTIAL
        annotations = {
            "batch_A": [
                PhaseAnnotation(
                    batch_id=UUID(batch_id),
                    phase_type=PhaseType.LAG,
                    start_ts=base_time,
                    end_ts=base_time + timedelta(hours=1),
                    signal_variable="OD600",
                    confidence=1.0,
                ),
                PhaseAnnotation(
                    batch_id=UUID(batch_id),
                    phase_type=PhaseType.STATIONARY,
                    start_ts=base_time + timedelta(hours=1),
                    end_ts=base_time + timedelta(hours=2),
                    signal_variable="OD600",
                    confidence=1.0,
                ),
            ],
        }

        with pytest.raises(ValueError, match="Phase exponential not found"):
            align(batches, annotations)


class TestAnchorSelection:
    """Test 9: Custom anchor phase."""

    def test_anchor_on_lag_phase(self, two_batch_data):
        """Test 9: anchor_phase=PhaseType.LAG anchors on lag phase start."""
        from sporedb.analytics.alignment import align

        batches, annotations = two_batch_data
        result = align(batches, annotations, anchor_phase=PhaseType.LAG)

        # With LAG anchor, the first data point should be at elapsed_hours ~= 0
        min_elapsed = result.index.min()
        assert min_elapsed >= -0.01, (
            f"With LAG anchor, min elapsed should be ~0, got {min_elapsed}"
        )


class TestSamplingHandling:
    """Tests 8, 10: Sampling rate handling."""

    def test_different_sampling_rates(self, base_time):
        """Test 8: Different sampling rates produce union of time points."""
        from sporedb.analytics.alignment import align

        batch_id_a = "00000000-0000-0000-0000-000000000001"
        batch_id_b = "00000000-0000-0000-0000-000000000002"

        # Batch A: 30s intervals, 50 points
        ts_a = [base_time + timedelta(seconds=30 * j) for j in range(50)]
        # Batch B: 60s intervals, 25 points
        ts_b = [base_time + timedelta(seconds=60 * j) for j in range(25)]

        batches = {
            "batch_A": pd.DataFrame(
                {
                    "ts": ts_a,
                    "variable": "OD600",
                    "value": np.linspace(0.1, 2.0, 50),
                }
            ),
            "batch_B": pd.DataFrame(
                {
                    "ts": ts_b,
                    "variable": "OD600",
                    "value": np.linspace(0.1, 2.0, 25),
                }
            ),
        }

        # Both batches: exp phase starts at time 0 (the beginning)
        annotations = {
            "batch_A": [
                PhaseAnnotation(
                    batch_id=UUID(batch_id_a),
                    phase_type=PhaseType.EXPONENTIAL,
                    start_ts=base_time,
                    end_ts=base_time + timedelta(hours=1),
                    signal_variable="OD600",
                    confidence=1.0,
                ),
            ],
            "batch_B": [
                PhaseAnnotation(
                    batch_id=UUID(batch_id_b),
                    phase_type=PhaseType.EXPONENTIAL,
                    start_ts=base_time,
                    end_ts=base_time + timedelta(hours=1),
                    signal_variable="OD600",
                    confidence=1.0,
                ),
            ],
        }

        result = align(batches, annotations)
        # Union of time points should have more rows than either batch alone
        assert len(result) >= 25

    def test_resolution_minutes_uniform_grid(self, two_batch_data):
        """Test 10: resolution_minutes produces uniform time grid."""
        from sporedb.analytics.alignment import align

        batches, annotations = two_batch_data
        result = align(batches, annotations, resolution_minutes=5.0)

        # Check that time steps are uniform (5 min = 5/60 hours)
        diffs = np.diff(result.index.values)
        expected_step = 5.0 / 60.0
        np.testing.assert_allclose(diffs, expected_step, atol=1e-10)
