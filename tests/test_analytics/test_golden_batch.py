"""Tests for golden batch profiling and DTW-based scoring."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from sporedb.analytics.golden_batch import (
    create_golden_profile,
    extract_batch_trajectory,
    score_against_profile,
)
from sporedb.analytics.models import GoldenBatchProfile, _make_uuid7

# ---------------------------------------------------------------------------
# Fixtures: synthetic aligned data (mimics align() output format)
# ---------------------------------------------------------------------------


def _make_aligned_df(
    batch_names: list[str],
    variables: list[str],
    n_timepoints: int = 50,
    seed: int = 42,
) -> pd.DataFrame:
    """Create synthetic aligned DataFrame in align() output format.

    Columns: elapsed_hours (index), batch_A__OD600, batch_A__pH, ...
    Values: exponential growth with per-batch noise.
    """
    rng = np.random.default_rng(seed)
    elapsed = np.linspace(0, 24, n_timepoints)
    data: dict[str, np.ndarray] = {}
    for bn in batch_names:
        for var in variables:
            if var == "OD600":
                # Exponential growth 0.1 -> ~5
                base = 0.1 * np.exp(0.16 * elapsed)
                noise = rng.normal(0, 0.05, n_timepoints)
                data[f"{bn}__{var}"] = base + noise
            elif var == "DO":
                # DO drops from 100 to ~20 (different scale)
                base = 100 - 3.0 * elapsed
                noise = rng.normal(0, 1.0, n_timepoints)
                data[f"{bn}__{var}"] = np.clip(base + noise, 0, 100)
            elif var == "pH":
                base = 7.0 - 0.04 * elapsed
                noise = rng.normal(0, 0.02, n_timepoints)
                data[f"{bn}__{var}"] = base + noise
    df = pd.DataFrame(data, index=pd.Index(elapsed, name="elapsed_hours"))
    return df


class TestProfileCreation:
    """Tests for create_golden_profile."""

    def test_profile_creation(self) -> None:
        batch_names = ["B001", "B002", "B003"]
        variables = ["OD600", "pH"]
        df = _make_aligned_df(batch_names, variables, n_timepoints=50)

        profile = create_golden_profile(df, batch_names, variables)

        assert isinstance(profile, GoldenBatchProfile)
        assert profile.variables == variables
        # mean_trajectory shape: n_timepoints rows, each with n_variables values
        assert len(profile.mean_trajectory) == 50
        assert len(profile.mean_trajectory[0]) == 2
        assert len(profile.std_trajectory) == 50
        assert len(profile.std_trajectory[0]) == 2
        assert len(profile.elapsed_hours) == 50
        assert profile.source_batch_ids == batch_names

    def test_empty_profile_raises(self) -> None:
        df = pd.DataFrame()
        with pytest.raises(ValueError):
            create_golden_profile(df, [], ["OD600"])

    def test_profile_serialization(self) -> None:
        batch_names = ["B001", "B002"]
        variables = ["OD600"]
        df = _make_aligned_df(batch_names, variables, n_timepoints=20)

        profile = create_golden_profile(df, batch_names, variables)
        dumped = profile.model_dump()
        restored = GoldenBatchProfile.model_validate(dumped)

        assert restored.variables == profile.variables
        assert len(restored.mean_trajectory) == len(profile.mean_trajectory)
        assert restored.source_batch_ids == profile.source_batch_ids


class TestScoring:
    """Tests for score_against_profile with DTW."""

    def test_identical_score(self) -> None:
        batch_names = ["B001", "B002", "B003"]
        variables = ["OD600", "pH"]
        df = _make_aligned_df(batch_names, variables, n_timepoints=50)

        profile = create_golden_profile(df, batch_names, variables)

        # Extract B001's trajectory as numpy array
        traj = np.column_stack([df[f"B001__{v}"].values for v in variables])

        batch_id = _make_uuid7()
        result = score_against_profile(profile, traj, batch_id)

        assert result.score >= 90, (
            f"Identical batch should score >= 90, got {result.score}"
        )
        assert 0 <= result.score <= 100

    def test_dissimilar_score(self) -> None:
        batch_names = ["B001", "B002", "B003"]
        variables = ["OD600"]
        df = _make_aligned_df(batch_names, variables, n_timepoints=50)

        profile = create_golden_profile(df, batch_names, variables)

        # Create an inverted trajectory (decreasing instead of exponential growth)
        # This is maximally different from the exponential growth pattern
        rng = np.random.default_rng(99)
        elapsed = np.linspace(0, 24, 50)
        inverted = 5.0 * np.exp(-0.16 * elapsed) + rng.normal(0, 0.05, 50)
        traj = inverted.reshape(-1, 1)

        batch_id = _make_uuid7()
        result = score_against_profile(profile, traj, batch_id)

        assert result.score < 60, (
            f"Dissimilar batch should score < 60, got {result.score}"
        )

    def test_multivariate_scoring(self) -> None:
        batch_names = ["B001", "B002", "B003"]
        variables = ["OD600", "pH", "DO"]
        df = _make_aligned_df(batch_names, variables, n_timepoints=50)

        profile = create_golden_profile(df, batch_names, variables)

        # Use B002's trajectory
        traj = np.column_stack([df[f"B002__{v}"].values for v in variables])

        batch_id = _make_uuid7()
        result = score_against_profile(profile, traj, batch_id)

        assert result.score >= 80, (
            f"Similar batch with 3 vars should score high, got {result.score}"
        )
        assert result.variables == variables

    def test_zscore_normalization(self) -> None:
        """Variables with different scales should contribute comparably."""
        batch_names = ["B001", "B002"]
        variables = ["OD600", "DO"]  # OD600 ~0-10, DO ~0-100
        df = _make_aligned_df(batch_names, variables, n_timepoints=50)

        profile = create_golden_profile(df, batch_names, variables)

        # Use B001 trajectory
        traj = np.column_stack([df[f"B001__{v}"].values for v in variables])

        batch_id = _make_uuid7()
        result = score_against_profile(profile, traj, batch_id)

        # Should score high despite different scales
        assert result.score >= 80, (
            f"Z-normalized scoring should handle scale diff, got {result.score}"
        )


class TestValidation:
    """Tests for input validation."""

    def test_mismatched_variables_raises(self) -> None:
        batch_names = ["B001", "B002"]
        variables = ["OD600", "pH"]
        df = _make_aligned_df(batch_names, variables, n_timepoints=20)

        profile = create_golden_profile(df, batch_names, variables)

        # Wrong number of variables (1 instead of 2)
        traj = np.random.default_rng(42).random((20, 1))
        batch_id = _make_uuid7()

        with pytest.raises(ValueError, match="variable"):
            score_against_profile(profile, traj, batch_id)


class TestExtractBatchTrajectory:
    """Tests for extract_batch_trajectory helper."""

    def test_extract(self) -> None:
        rng = np.random.default_rng(42)
        n = 30
        ts = pd.date_range("2024-01-01", periods=n, freq="h")
        rows = []
        for t in ts:
            rows.append({"ts": t, "variable": "OD600", "value": rng.random()})
            rows.append({"ts": t, "variable": "pH", "value": 7.0 + rng.random() * 0.5})
        df = pd.DataFrame(rows)

        result = extract_batch_trajectory(df, ["OD600", "pH"])
        assert result.shape == (n, 2)
