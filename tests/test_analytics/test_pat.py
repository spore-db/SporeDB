"""Tests for PAT soft-sensor integration.

Covers: SoftSensor ABC, LinearSoftSensor, apply_soft_sensor.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import numpy as np
import pandas as pd
import pytest


class TestSoftSensorProtocol:
    """SoftSensor ABC can be subclassed."""

    def test_protocol_implementation(self):
        from sporedb.analytics.pat import SoftSensor

        class MockSensor(SoftSensor):
            @property
            def output_variable(self) -> str:
                return "glucose_predicted"

            @property
            def input_variables(self) -> list[str]:
                return ["turbidity"]

            def predict(
                self,
                inputs: dict[str, np.ndarray],
                timestamps: np.ndarray,
            ) -> tuple[np.ndarray, np.ndarray | None]:
                return inputs["turbidity"] * 2.0, None

        sensor = MockSensor()
        assert sensor.output_variable == "glucose_predicted"
        assert sensor.input_variables == ["turbidity"]
        vals, unc = sensor.predict(
            {"turbidity": np.array([1.0, 2.0])},
            np.array([0.0, 1.0]),
        )
        np.testing.assert_array_equal(vals, [2.0, 4.0])
        assert unc is None


class TestLinearSoftSensor:
    """LinearSoftSensor calibration model."""

    def test_linear_sensor(self):
        from sporedb.analytics.pat import LinearSoftSensor

        sensor = LinearSoftSensor(
            input_variable="turbidity",
            output_variable="biomass_predicted",
            slope=2.0,
            intercept=0.5,
        )
        ts = np.array([0.0, 1.0, 2.0])
        vals, unc = sensor.predict({"turbidity": np.array([1.0, 2.0, 3.0])}, ts)
        np.testing.assert_array_almost_equal(vals, [2.5, 4.5, 6.5])
        assert unc is None

    def test_linear_sensor_uncertainty(self):
        from sporedb.analytics.pat import LinearSoftSensor

        sensor = LinearSoftSensor(
            input_variable="turbidity",
            output_variable="biomass_predicted",
            slope=2.0,
            intercept=0.5,
            prediction_std=0.1,
        )
        ts = np.array([0.0, 1.0, 2.0])
        vals, unc = sensor.predict({"turbidity": np.array([1.0, 2.0, 3.0])}, ts)
        np.testing.assert_array_almost_equal(vals, [2.5, 4.5, 6.5])
        assert unc is not None
        np.testing.assert_array_almost_equal(unc, [0.1, 0.1, 0.1])

    def test_linear_sensor_no_uncertainty(self):
        from sporedb.analytics.pat import LinearSoftSensor

        sensor = LinearSoftSensor(
            input_variable="turbidity",
            output_variable="biomass_predicted",
            slope=1.0,
            intercept=0.0,
            prediction_std=0.0,
        )
        ts = np.array([0.0])
        vals, unc = sensor.predict({"turbidity": np.array([5.0])}, ts)
        np.testing.assert_array_almost_equal(vals, [5.0])
        assert unc is None

    def test_missing_input_raises(self):
        from sporedb.analytics.pat import LinearSoftSensor

        sensor = LinearSoftSensor(
            input_variable="turbidity",
            output_variable="biomass_predicted",
            slope=1.0,
            intercept=0.0,
        )
        ts = np.array([0.0])
        with pytest.raises(ValueError, match="turbidity"):
            sensor.predict({"pH": np.array([7.0])}, ts)

    def test_output_variable_property(self):
        from sporedb.analytics.pat import LinearSoftSensor

        sensor = LinearSoftSensor(
            input_variable="turbidity",
            output_variable="biomass_predicted",
            slope=1.0,
            intercept=0.0,
        )
        assert sensor.output_variable == "biomass_predicted"
        assert sensor.input_variables == ["turbidity"]


class TestApplySoftSensor:
    """apply_soft_sensor integration with telemetry DataFrames."""

    def _make_telemetry(self) -> pd.DataFrame:
        """Create a simple telemetry DataFrame."""
        base = datetime(2026, 1, 1, tzinfo=UTC)
        return pd.DataFrame(
            {
                "ts": [base + timedelta(minutes=i) for i in range(5)],
                "variable": ["turbidity"] * 5,
                "value": [1.0, 2.0, 3.0, 4.0, 5.0],
            }
        )

    def test_apply_soft_sensor(self):
        from sporedb.analytics.pat import LinearSoftSensor, apply_soft_sensor

        sensor = LinearSoftSensor(
            input_variable="turbidity",
            output_variable="biomass_predicted",
            slope=2.0,
            intercept=0.5,
        )
        df = self._make_telemetry()
        result = apply_soft_sensor(sensor, df)

        assert isinstance(result, pd.DataFrame)
        assert len(result) == 5
        assert all(result["variable"] == "biomass_predicted")
        np.testing.assert_array_almost_equal(
            result["value"].values, [2.5, 4.5, 6.5, 8.5, 10.5]
        )
        assert all(result["source"] == "soft_sensor")

    def test_output_variable_naming(self):
        from sporedb.analytics.pat import LinearSoftSensor, apply_soft_sensor

        sensor = LinearSoftSensor(
            input_variable="turbidity",
            output_variable="biomass_predicted",
            slope=1.0,
            intercept=0.0,
        )
        df = self._make_telemetry()
        result = apply_soft_sensor(sensor, df)
        # All output rows should have the sensor's output_variable name
        assert all(result["variable"] == sensor.output_variable)

    def test_missing_input_variable_in_telemetry(self):
        from sporedb.analytics.pat import LinearSoftSensor, apply_soft_sensor

        sensor = LinearSoftSensor(
            input_variable="pH",
            output_variable="biomass_predicted",
            slope=1.0,
            intercept=0.0,
        )
        df = self._make_telemetry()  # Only has 'turbidity'
        with pytest.raises(ValueError, match="pH"):
            apply_soft_sensor(sensor, df)

    def test_uncertainty_propagation(self):
        from sporedb.analytics.pat import LinearSoftSensor, apply_soft_sensor

        sensor = LinearSoftSensor(
            input_variable="turbidity",
            output_variable="biomass_predicted",
            slope=2.0,
            intercept=0.0,
            prediction_std=0.5,
        )
        df = self._make_telemetry()
        result = apply_soft_sensor(sensor, df)
        assert "uncertainty" in result.columns
        np.testing.assert_array_almost_equal(result["uncertainty"].values, [0.5] * 5)
