"""Tests for derived bioprocess metrics and analytics barrel export."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

import numpy as np
import pytest


@pytest.fixture
def base_time() -> datetime:
    return datetime(2026, 1, 1, 0, 0, tzinfo=UTC)


class TestSpecificGrowthRate:
    """Tests 1-3: Specific growth rate (mu) via log-linear regression."""

    def test_correct_mu_from_synthetic_exponential(self):
        """Test 1: Known exponential data returns correct mu ~0.3 h^-1."""
        from sporedb.analytics.metrics import compute_specific_growth_rate

        time_hours = np.linspace(0, 10, 100)
        biomass = 0.1 * np.exp(0.3 * time_hours)

        mu, r_squared, std_error = compute_specific_growth_rate(time_hours, biomass)

        assert mu == pytest.approx(0.3, abs=0.01)

    def test_r_squared_high_for_clean_data(self):
        """Test 2: R-squared > 0.95 for clean exponential data."""
        from sporedb.analytics.metrics import compute_specific_growth_rate

        time_hours = np.linspace(0, 10, 100)
        biomass = 0.1 * np.exp(0.3 * time_hours)

        mu, r_squared, std_error = compute_specific_growth_rate(time_hours, biomass)

        assert r_squared > 0.95

    def test_returns_std_error(self):
        """Test 3: Returns std_error for the regression."""
        from sporedb.analytics.metrics import compute_specific_growth_rate

        rng = np.random.default_rng(42)
        time_hours = np.linspace(0, 10, 100)
        biomass = 0.1 * np.exp(0.3 * time_hours) + rng.normal(0, 0.01, 100)
        # Ensure all positive
        biomass = np.clip(biomass, 0.001, None)

        mu, r_squared, std_error = compute_specific_growth_rate(time_hours, biomass)

        assert isinstance(std_error, float)
        assert std_error >= 0

    def test_raises_on_nonpositive_values(self):
        """Biomass values must be positive for log transform."""
        from sporedb.analytics.metrics import compute_specific_growth_rate

        time_hours = np.array([0, 1, 2, 3, 4])
        biomass = np.array([0.1, 0.5, 0.0, 1.5, 2.0])  # contains zero

        with pytest.raises(ValueError, match="positive"):
            compute_specific_growth_rate(time_hours, biomass)


class TestVolumetricProductivity:
    """Tests 4-5: Volumetric productivity (Qp)."""

    def test_correct_qp(self):
        """Test 4: Qp = (P_final - P_initial) / (t_final - t_initial)."""
        from sporedb.analytics.metrics import compute_volumetric_productivity

        product = np.array([0.0, 0.5, 1.0, 1.5, 2.0])
        time_hours = np.array([0.0, 1.0, 2.0, 3.0, 4.0])

        qp = compute_volumetric_productivity(product, time_hours)

        # (2.0 - 0.0) / (4.0 - 0.0) = 0.5
        assert qp == pytest.approx(0.5)

    def test_returns_zero_when_delta_t_zero(self):
        """Test 5: Returns 0.0 when delta_t is 0."""
        from sporedb.analytics.metrics import compute_volumetric_productivity

        product = np.array([1.0, 2.0])
        time_hours = np.array([5.0, 5.0])  # same time

        qp = compute_volumetric_productivity(product, time_hours)

        assert qp == 0.0


class TestYieldCoefficient:
    """Tests 6-8: Yield coefficients (Yx/s, Yp/s)."""

    def test_yx_s_correct(self):
        """Test 6: Yx/s = (X_final - X_initial) / (S_initial - S_final)."""
        from sporedb.analytics.metrics import compute_yield_coefficient

        # Biomass goes from 0.5 to 5.0 (produced)
        # Substrate goes from 20.0 to 10.0 (consumed)
        produced = np.array([0.5, 1.0, 2.0, 3.5, 5.0])
        consumed = np.array([20.0, 18.0, 15.0, 12.0, 10.0])

        yx_s = compute_yield_coefficient(consumed=consumed, produced=produced)

        # (5.0 - 0.5) / (20.0 - 10.0) = 4.5 / 10.0 = 0.45
        assert yx_s == pytest.approx(0.45)

    def test_returns_zero_when_no_consumption(self):
        """Test 7: Returns 0.0 when substrate consumption is near-zero."""
        from sporedb.analytics.metrics import compute_yield_coefficient

        produced = np.array([0.5, 1.0, 1.5])
        consumed = np.array([20.0, 20.0, 20.0])  # no consumption

        yx_s = compute_yield_coefficient(consumed=consumed, produced=produced)

        assert yx_s == 0.0

    def test_uncertainty_propagation(self):
        """Test 8: UncertainValue inputs propagate uncertainty via ufloat."""
        from sporedb.analytics.metrics import compute_yield_coefficient
        from sporedb.models.assay import UncertainValue

        consumed_uncertain = [
            UncertainValue(value=20.0, uncertainty=0.5, unit="g/L"),
            UncertainValue(value=10.0, uncertainty=0.5, unit="g/L"),
        ]
        produced_uncertain = [
            UncertainValue(value=0.5, uncertainty=0.1, unit="g/L"),
            UncertainValue(value=5.0, uncertainty=0.2, unit="g/L"),
        ]

        result = compute_yield_coefficient(
            consumed_uncertain=consumed_uncertain,
            produced_uncertain=produced_uncertain,
        )

        assert isinstance(result, tuple)
        yield_val, uncertainty = result
        assert yield_val == pytest.approx(0.45, abs=0.01)
        assert uncertainty > 0


class TestComputeBatchMetrics:
    """Test 9: Orchestrated per-phase metrics."""

    def test_returns_batch_metrics_with_mu(self, base_time):
        """Test 9: compute_batch_metrics returns BatchMetrics with mu."""
        import pandas as pd

        from sporedb.analytics.metrics import compute_batch_metrics
        from sporedb.analytics.models import PhaseAnnotation, PhaseType

        batch_id = UUID("00000000-0000-0000-0000-000000000001")

        # Create synthetic telemetry with known exponential growth
        # Lag: 0-2h, Exp: 2-6h (mu=0.3), Stationary: 6-10h
        dt = timedelta(minutes=10)
        timestamps = []
        values = []
        t = base_time

        # Lag phase (0-2h): flat at OD 0.1
        for _ in range(12):  # 12 points * 10min = 2h
            timestamps.append(t)
            values.append(0.1)
            t += dt

        # Exponential phase (2-6h): exponential growth
        exp_start = t
        for i in range(24):  # 24 points * 10min = 4h
            hours_since_exp = i * 10 / 60.0
            timestamps.append(t)
            values.append(0.1 * np.exp(0.3 * hours_since_exp))
            t += dt
        exp_end = t

        # Stationary phase (6-10h): flat at ~0.33
        stat_start = t
        for _ in range(24):
            timestamps.append(t)
            values.append(0.33)
            t += dt
        stat_end = t

        telemetry_df = pd.DataFrame(
            {
                "ts": timestamps,
                "variable": "OD600",
                "value": values,
                "batch_id": str(batch_id),
            }
        )

        phases = [
            PhaseAnnotation(
                batch_id=batch_id,
                phase_type=PhaseType.LAG,
                start_ts=base_time,
                end_ts=exp_start,
                signal_variable="OD600",
                confidence=1.0,
            ),
            PhaseAnnotation(
                batch_id=batch_id,
                phase_type=PhaseType.EXPONENTIAL,
                start_ts=exp_start,
                end_ts=exp_end,
                signal_variable="OD600",
                confidence=1.0,
            ),
            PhaseAnnotation(
                batch_id=batch_id,
                phase_type=PhaseType.STATIONARY,
                start_ts=stat_start,
                end_ts=stat_end,
                signal_variable="OD600",
                confidence=1.0,
            ),
        ]

        results = compute_batch_metrics(telemetry_df, phases, batch_id)

        assert len(results) >= 1
        # Find exponential phase metrics
        exp_metrics = [m for m in results if m.phase_type == PhaseType.EXPONENTIAL]
        assert len(exp_metrics) == 1
        assert exp_metrics[0].mu is not None
        assert exp_metrics[0].mu == pytest.approx(0.3, abs=0.05)
        assert exp_metrics[0].r_squared is not None
        assert exp_metrics[0].r_squared > 0.9


class TestBarrelExport:
    """Test 10: analytics __init__.py exports."""

    def test_all_public_apis_importable(self):
        """Test 10: All expected symbols importable from sporedb.analytics."""
        from sporedb.analytics import (
            align,
            compute_batch_metrics,
            compute_specific_growth_rate,
            compute_volumetric_productivity,
            compute_yield_coefficient,
        )

        # Verify they are the right types
        assert callable(align)
        assert callable(compute_batch_metrics)
        assert callable(compute_specific_growth_rate)
        assert callable(compute_volumetric_productivity)
        assert callable(compute_yield_coefficient)
