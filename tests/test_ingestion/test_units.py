from __future__ import annotations

import math

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from sporedb.ingestion.units import (
    CANONICAL_UNITS,
    UnitConversionLog,
    convert_unit,
    detect_unit_by_range,
    detect_unit_from_header,
    is_unit_row,
)


class TestCanonicalUnits:
    """Verify CANONICAL_UNITS mapping."""

    def test_concentration(self):
        assert CANONICAL_UNITS["concentration"] == "g/L"

    def test_temperature(self):
        assert CANONICAL_UNITS["temperature"] == "C"

    def test_dissolved_oxygen(self):
        assert CANONICAL_UNITS["dissolved_oxygen"] == "%"

    def test_time(self):
        assert CANONICAL_UNITS["time"] == "h"

    def test_volume(self):
        assert CANONICAL_UNITS["volume"] == "L"

    def test_ph_dimensionless(self):
        assert CANONICAL_UNITS["ph"] is None


class TestConvertUnit:
    """Test unit conversion pairs."""

    def test_mg_ml_to_g_l(self):
        value, warning = convert_unit("mg/mL", "g/L", 5.0)
        assert value == 5.0
        assert warning is None

    def test_mg_l_to_g_l(self):
        value, warning = convert_unit("mg/L", "g/L", 5000.0)
        assert value == 5.0
        assert warning is None

    def test_kelvin_to_celsius(self):
        value, warning = convert_unit("K", "C", 310.15)
        assert value == pytest.approx(37.0)
        assert warning is None

    def test_fahrenheit_to_celsius(self):
        value, warning = convert_unit("F", "C", 98.6)
        assert value == pytest.approx(37.0)
        assert warning is None

    def test_min_to_h(self):
        value, warning = convert_unit("min", "h", 120.0)
        assert value == 2.0
        assert warning is None

    def test_ml_to_l(self):
        value, warning = convert_unit("mL", "L", 500.0)
        assert value == 0.5
        assert warning is None

    def test_unknown_unit(self):
        value, warning = convert_unit("frobbles", "g/L", 1.0)
        assert value is None
        assert warning is not None
        assert "frobbles" in warning

    def test_seconds_to_hours(self):
        value, warning = convert_unit("s", "h", 3600.0)
        assert value == 1.0
        assert warning is None

    def test_g_ml_to_g_l(self):
        value, warning = convert_unit("g/mL", "g/L", 1.0)
        assert value == 1000.0
        assert warning is None

    def test_ug_ml_to_g_l(self):
        value, warning = convert_unit("ug/mL", "g/L", 1000.0)
        assert value == 1.0
        assert warning is None


class TestDetectUnitFromHeader:
    """Test header-based unit extraction."""

    def test_glucose_mg_ml(self):
        assert detect_unit_from_header("glucose_mg_mL") == "mg/mL"

    def test_temp_k(self):
        assert detect_unit_from_header("temp_K") == "K"

    def test_ph_dimensionless(self):
        assert detect_unit_from_header("pH") is None

    def test_glucose_g_l(self):
        assert detect_unit_from_header("glucose_g_L") == "g/L"

    def test_time_h(self):
        assert detect_unit_from_header("time_h") == "h"

    def test_volume_mL(self):
        assert detect_unit_from_header("volume_mL") == "mL"


class TestIsUnitRow:
    """Test unit row detection."""

    def test_unit_row(self):
        assert is_unit_row(["g/L", "C", "%", "h"]) is True

    def test_data_row(self):
        assert is_unit_row(["1.5", "37.0", "95.3", "0.5"]) is False

    def test_mixed_row_with_blanks(self):
        assert is_unit_row(["g/L", "", "C", "%"]) is True

    def test_header_row(self):
        assert is_unit_row(["glucose", "temperature", "DO", "time"]) is False


class TestDetectUnitByRange:
    """Test range-based unit heuristics."""

    def test_temperature_kelvin(self):
        assert detect_unit_by_range("temperature", [305.0, 310.0, 315.0]) == "K"

    def test_temperature_celsius(self):
        assert detect_unit_by_range("temperature", [30.0, 35.0, 37.0]) == "C"

    def test_concentration_ambiguous_returns_none(self):
        # Small values are ambiguous -- could be g/mL or g/L, so return None
        assert detect_unit_by_range("glucose", [0.005, 0.01, 0.02]) is None

    def test_concentration_g_l(self):
        assert detect_unit_by_range("glucose", [5.0, 10.0, 15.0]) == "g/L"


class TestUnitConversionLog:
    """Test UnitConversionLog model."""

    def test_log_fields(self):
        log = UnitConversionLog(
            column="temp_K",
            from_unit="K",
            to_unit="C",
            rows_converted=100,
        )
        assert log.column == "temp_K"
        assert log.from_unit == "K"
        assert log.to_unit == "C"
        assert log.rows_converted == 100


class TestConvertUnitHypothesis:
    """Property-based tests for unit conversion."""

    @given(st.floats(allow_nan=False, allow_infinity=False))
    @settings(max_examples=100)
    def test_kelvin_to_celsius_no_nan(self, value: float):
        result, warning = convert_unit("K", "C", value)
        assert result is not None
        assert not math.isnan(result)
        assert not math.isinf(result)

    @given(st.floats(allow_nan=False, allow_infinity=False))
    @settings(max_examples=100)
    def test_mg_l_to_g_l_no_nan(self, value: float):
        result, warning = convert_unit("mg/L", "g/L", value)
        assert result is not None
        assert not math.isnan(result)
        assert not math.isinf(result)

    @given(st.floats(allow_nan=False, allow_infinity=False))
    @settings(max_examples=100)
    def test_min_to_h_no_nan(self, value: float):
        result, warning = convert_unit("min", "h", value)
        assert result is not None
        assert not math.isnan(result)
        assert not math.isinf(result)
