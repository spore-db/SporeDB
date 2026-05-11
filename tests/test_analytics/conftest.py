"""Shared fixtures for all analytics tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import numpy as np
import pandas as pd
import pytest

from sporedb.storage.engine import StorageEngine


@pytest.fixture
def base_time() -> datetime:
    return datetime(2026, 1, 1, 0, 0, tzinfo=UTC)


@pytest.fixture
def synthetic_growth_curve(base_time: datetime) -> tuple[np.ndarray, np.ndarray]:
    """Simulate a 4-phase growth curve (260 points at 30-second intervals).

    Phases:
      - Lag (50 pts): ~0.1 with slight noise
      - Exponential (100 pts): 0.1 -> 5.0 exponential growth
      - Stationary (80 pts): ~5.0 flat with noise
      - Decline (30 pts): 5.0 -> 3.0 linear decrease
    """
    rng = np.random.default_rng(42)

    # Lag phase: 50 points
    lag = 0.1 + rng.normal(0, 0.005, 50)

    # Exponential phase: 100 points
    t_exp = np.linspace(0, 1, 100)
    exp_vals = 0.1 * np.exp(t_exp * np.log(50))  # 0.1 -> 5.0
    exp_vals += rng.normal(0, 0.05, 100)

    # Stationary phase: 80 points
    stat = 5.0 + rng.normal(0, 0.1, 80)

    # Decline phase: 30 points
    decline = np.linspace(5.0, 3.0, 30) + rng.normal(0, 0.05, 30)

    values = np.concatenate([lag, exp_vals, stat, decline])

    timestamps = np.array(
        [base_time + timedelta(seconds=30 * i) for i in range(len(values))]
    )

    return timestamps, values


@pytest.fixture
def synthetic_telemetry_df(
    synthetic_growth_curve: tuple[np.ndarray, np.ndarray],
    sample_batch,
) -> pd.DataFrame:
    """DataFrame matching TelemetryRecord structure for OD600."""
    timestamps, values = synthetic_growth_curve
    return pd.DataFrame(
        {
            "ts": timestamps,
            "variable": "OD600",
            "value": values,
            "batch_id": str(sample_batch.batch_id),
            "unit": "AU",
        }
    )


@pytest.fixture
def multi_batch_telemetry(base_time: datetime) -> dict[str, pd.DataFrame]:
    """Three batches with different lag durations (40, 50, 60 points)."""
    rng = np.random.default_rng(123)
    result: dict[str, pd.DataFrame] = {}

    for i, (batch_name, lag_pts) in enumerate(
        [
            ("batch-A", 40),
            ("batch-B", 50),
            ("batch-C", 60),
        ]
    ):
        lag = 0.1 + rng.normal(0, 0.005, lag_pts)
        t_exp = np.linspace(0, 1, 100)
        exp_vals = 0.1 * np.exp(t_exp * np.log(50)) + rng.normal(0, 0.05, 100)
        stat = 5.0 + rng.normal(0, 0.1, 80)
        decline = np.linspace(5.0, 3.0, 30) + rng.normal(0, 0.05, 30)

        values = np.concatenate([lag, exp_vals, stat, decline])
        n_points = len(values)
        timestamps = [base_time + timedelta(seconds=30 * j) for j in range(n_points)]

        batch_id = f"00000000-0000-0000-0000-00000000000{i + 1}"
        result[batch_name] = pd.DataFrame(
            {
                "ts": timestamps,
                "variable": "OD600",
                "value": values,
                "batch_id": batch_id,
                "unit": "AU",
            }
        )

    return result


@pytest.fixture
def analytics_engine(data_root):
    """StorageEngine instance for analytics tests."""
    with StorageEngine(data_root) as engine:
        yield engine
