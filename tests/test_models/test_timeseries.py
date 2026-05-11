"""Tests for the TelemetryRecord domain model."""

from datetime import UTC, datetime
from uuid import UUID

from sporedb.models.timeseries import TelemetryRecord


class TestTelemetryRecord:
    def test_telemetry_record_required_fields(self):
        """TelemetryRecord requires batch_id, ts, variable, value."""
        record = TelemetryRecord(
            batch_id=UUID("019daaa3-f447-7cc0-9d52-f81ada15c2bb"),
            ts=datetime(2026, 4, 20, 8, 30, tzinfo=UTC),
            variable="dissolved_oxygen",
            value=45.2,
            unit="%",
        )
        assert isinstance(record.batch_id, UUID)
        assert record.variable == "dissolved_oxygen"
        assert record.value == 45.2
        assert record.unit == "%"

    def test_telemetry_record_unit_optional(self):
        """TelemetryRecord unit is optional, defaults to None."""
        record = TelemetryRecord(
            batch_id=UUID("019daaa3-f447-7cc0-9d52-f81ada15c2bb"),
            ts=datetime(2026, 4, 20, 8, 30, tzinfo=UTC),
            variable="ph",
            value=7.2,
        )
        assert record.unit is None

    def test_telemetry_record_model_dump_json_serializable(self):
        """TelemetryRecord model_dump produces JSON-serializable dict."""
        record = TelemetryRecord(
            batch_id=UUID("019daaa3-f447-7cc0-9d52-f81ada15c2bb"),
            ts=datetime(2026, 4, 20, 8, 30, tzinfo=UTC),
            variable="temperature",
            value=37.0,
            unit="C",
        )
        dumped = record.model_dump(mode="json")
        assert isinstance(dumped["batch_id"], str)
        assert isinstance(dumped["ts"], str)
        assert dumped["variable"] == "temperature"
        assert dumped["value"] == 37.0

    def test_telemetry_record_roundtrip(self):
        """TelemetryRecord round-trips through model_dump/model_validate."""
        record = TelemetryRecord(
            batch_id=UUID("019daaa3-f447-7cc0-9d52-f81ada15c2bb"),
            ts=datetime(2026, 4, 20, 8, 30, tzinfo=UTC),
            variable="agitation",
            value=250.0,
            unit="rpm",
        )
        restored = TelemetryRecord.model_validate(record.model_dump())
        assert restored == record
