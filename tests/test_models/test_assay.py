"""Tests for the AssayMeasurement and UncertainValue domain models."""

from datetime import UTC, datetime
from uuid import UUID

from sporedb.models.assay import AssayMeasurement, UncertainValue


class TestUncertainValue:
    def test_uncertain_value_to_ufloat(self):
        """UncertainValue(4.5, 0.2).to_ufloat() returns ufloat(4.5, 0.2)."""
        uv = UncertainValue(value=4.5, uncertainty=0.2)
        result = uv.to_ufloat()
        assert result.nominal_value == 4.5
        assert result.std_dev == 0.2

    def test_uncertain_value_subtraction_propagates_uncertainty(self):
        """UncertainValue subtraction via to_ufloat propagates uncertainty correctly."""
        uv1 = UncertainValue(value=10.0, uncertainty=0.5)
        uv2 = UncertainValue(value=3.0, uncertainty=0.3)
        result = uv1.to_ufloat() - uv2.to_ufloat()
        assert abs(result.nominal_value - 7.0) < 1e-10
        assert result.std_dev > 0  # uncertainty propagated

    def test_uncertain_value_defaults(self):
        """UncertainValue uncertainty defaults to 0.0, unit to empty string."""
        uv = UncertainValue(value=5.0)
        assert uv.uncertainty == 0.0
        assert uv.unit == ""


class TestAssayMeasurement:
    def test_assay_measurement_with_method(self):
        """AssayMeasurement with method='HPLC' validates."""
        assay = AssayMeasurement(
            batch_id=UUID("019daaa3-f447-7cc0-9d52-f81ada15c2bb"),
            ts=datetime(2026, 4, 20, 10, 0, tzinfo=UTC),
            variable="glucose",
            value=4.5,
            uncertainty=0.2,
            unit="g/L",
            method="HPLC",
        )
        assert assay.method == "HPLC"
        assert assay.variable == "glucose"
        assert assay.value == 4.5
        assert assay.uncertainty == 0.2
        assert assay.unit == "g/L"

    def test_assay_measurement_required_fields(self):
        """AssayMeasurement requires batch_id, ts, variable, value."""
        assay = AssayMeasurement(
            batch_id=UUID("019daaa3-f447-7cc0-9d52-f81ada15c2bb"),
            ts=datetime(2026, 4, 20, 10, 0, tzinfo=UTC),
            variable="cell_count",
            value=1.2e6,
        )
        assert assay.uncertainty == 0.0  # default
        assert assay.unit is None  # optional
        assert assay.method is None  # optional

    def test_assay_measurement_roundtrip(self):
        """AssayMeasurement round-trips through model_dump/model_validate."""
        assay = AssayMeasurement(
            batch_id=UUID("019daaa3-f447-7cc0-9d52-f81ada15c2bb"),
            ts=datetime(2026, 4, 20, 10, 0, tzinfo=UTC),
            variable="titer",
            value=2.3,
            uncertainty=0.15,
            unit="g/L",
            method="LC-MS",
        )
        restored = AssayMeasurement.model_validate(assay.model_dump())
        assert restored == assay
