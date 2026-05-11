"""Shared fixtures for visualization tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock
from uuid import UUID

import numpy as np
import pandas as pd
import pytest

from sporedb.analytics.models import (
    PhaseAnnotation,
    PhaseType,
)


@pytest.fixture
def base_time() -> datetime:
    return datetime(2026, 1, 1, 0, 0, tzinfo=UTC)


@pytest.fixture
def batch_ids() -> list[UUID]:
    return [
        UUID("00000000-0000-0000-0000-000000000001"),
        UUID("00000000-0000-0000-0000-000000000002"),
        UUID("00000000-0000-0000-0000-000000000003"),
    ]


@pytest.fixture
def batch_names(batch_ids: list[UUID]) -> list[str]:
    return [str(bid) for bid in batch_ids]


def _make_synthetic_telemetry(
    batch_id: UUID,
    base_time: datetime,
    n_points: int = 200,
    seed: int = 42,
) -> pd.DataFrame:
    """Create synthetic telemetry DataFrame matching SporeDB get_telemetry() format."""
    rng = np.random.default_rng(seed)
    timestamps = [base_time + timedelta(seconds=30 * i) for i in range(n_points)]
    values = 0.1 * np.exp(np.linspace(0, 3, n_points)) + rng.normal(0, 0.05, n_points)
    return pd.DataFrame(
        {
            "ts": timestamps,
            "variable": "OD600",
            "value": values,
            "batch_id": str(batch_id),
            "unit": "AU",
        }
    )


def _make_phase_annotations(
    batch_id: UUID,
    base_time: datetime,
) -> list[PhaseAnnotation]:
    """Create synthetic phase annotations matching detect_phases() output."""
    phases = [
        (PhaseType.LAG, 0, 50),
        (PhaseType.EXPONENTIAL, 50, 150),
        (PhaseType.STATIONARY, 150, 180),
        (PhaseType.DECLINE, 180, 200),
    ]
    return [
        PhaseAnnotation(
            batch_id=batch_id,
            phase_type=pt,
            start_ts=base_time + timedelta(seconds=30 * start),
            end_ts=base_time + timedelta(seconds=30 * end),
            signal_variable="OD600",
            confidence=0.9,
        )
        for pt, start, end in phases
    ]


def _make_aligned_df(
    batch_names: list[str],
    variables: list[str] | None = None,
    n_timepoints: int = 50,
    seed: int = 42,
) -> pd.DataFrame:
    """Create synthetic aligned DataFrame in align() output format."""
    if variables is None:
        variables = ["OD600"]
    rng = np.random.default_rng(seed)
    elapsed = np.linspace(0, 24, n_timepoints)
    data: dict[str, np.ndarray] = {}
    for bn in batch_names:
        for var in variables:
            base = 0.1 * np.exp(0.16 * elapsed)
            noise = rng.normal(0, 0.05, n_timepoints)
            data[f"{bn}__{var}"] = base + noise
    return pd.DataFrame(data, index=pd.Index(elapsed, name="elapsed_hours"))


@pytest.fixture
def mock_db(
    batch_ids: list[UUID], batch_names: list[str], base_time: datetime
) -> MagicMock:
    """Mock SporeDB client with synthetic data for viz testing."""
    db = MagicMock()

    def fake_get_telemetry(bid: UUID) -> pd.DataFrame:
        idx = batch_ids.index(bid)
        return _make_synthetic_telemetry(bid, base_time, seed=42 + idx)

    def fake_detect_phases(
        bid: UUID, signal: str = "OD600", min_size: int = 10
    ) -> list[PhaseAnnotation]:
        return _make_phase_annotations(bid, base_time)

    def fake_align(bids: list[UUID], signal: str = "OD600") -> pd.DataFrame:
        names = [str(b) for b in bids]
        return _make_aligned_df(names, [signal])

    db.get_telemetry = MagicMock(side_effect=fake_get_telemetry)
    db.detect_phases = MagicMock(side_effect=fake_detect_phases)
    db.align = MagicMock(side_effect=fake_align)
    db.compute_metrics = MagicMock(return_value=[])

    return db
