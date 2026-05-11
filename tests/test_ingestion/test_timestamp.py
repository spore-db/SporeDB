from __future__ import annotations

from datetime import UTC, datetime

import pytest

from sporedb.ingestion.timestamp import (
    detect_timestamp_column,
    elapsed_to_absolute,
    parse_timestamps,
)


class TestDetectTimestampColumn:
    """Test timestamp column detection."""

    def test_elapsed_time_column(self):
        headers = ["time_h", "pH", "DO"]
        rows = [["0.0", "7.2", "95"], ["0.5", "7.1", "88"], ["1.0", "6.9", "82"]]
        col_name, is_elapsed = detect_timestamp_column(headers, rows)
        assert col_name == "time_h"
        assert is_elapsed is True

    def test_datetime_column(self):
        headers = ["timestamp", "pH", "DO"]
        rows = [
            ["2026-04-20 08:00:00", "7.2", "95"],
            ["2026-04-20 08:30:00", "7.1", "88"],
            ["2026-04-20 09:00:00", "6.9", "82"],
        ]
        col_name, is_elapsed = detect_timestamp_column(headers, rows)
        assert col_name == "timestamp"
        assert is_elapsed is False

    def test_no_timestamp_raises(self):
        headers = ["pH", "DO", "temp"]
        rows = [["7.2", "95", "37"], ["7.1", "88", "36.9"], ["6.9", "82", "37.1"]]
        with pytest.raises(ValueError, match="No timestamp column"):
            detect_timestamp_column(headers, rows)

    def test_unnamed_datetime_column(self):
        """Column not in TIMESTAMP_COLUMN_NAMES but values are datetime-parseable."""
        headers = ["measurement_time", "pH"]
        rows = [
            ["2026-04-20 08:00:00", "7.2"],
            ["2026-04-20 08:30:00", "7.1"],
            ["2026-04-20 09:00:00", "6.9"],
        ]
        col_name, is_elapsed = detect_timestamp_column(headers, rows)
        assert col_name == "measurement_time"
        assert is_elapsed is False


class TestElapsedToAbsolute:
    """Test elapsed time to absolute datetime conversion."""

    def test_hours_conversion(self):
        ref = datetime(2026, 4, 20, 8, 0, tzinfo=UTC)
        result = elapsed_to_absolute([0.0, 2.5, 5.0], "h", ref)
        assert len(result) == 3
        assert result[0] == datetime(2026, 4, 20, 8, 0, tzinfo=UTC)
        assert result[1] == datetime(2026, 4, 20, 10, 30, tzinfo=UTC)
        assert result[2] == datetime(2026, 4, 20, 13, 0, tzinfo=UTC)

    def test_utc_enforcement(self):
        ref = datetime(2026, 4, 20, 8, 0, tzinfo=UTC)
        result = elapsed_to_absolute([0.0], "h", ref)
        assert result[0].tzinfo is not None
        assert result[0].tzinfo == UTC

    def test_minutes_conversion(self):
        ref = datetime(2026, 4, 20, 8, 0, tzinfo=UTC)
        result = elapsed_to_absolute([0.0, 30.0, 60.0], "min", ref)
        assert result[1] == datetime(2026, 4, 20, 8, 30, tzinfo=UTC)
        assert result[2] == datetime(2026, 4, 20, 9, 0, tzinfo=UTC)

    def test_seconds_conversion(self):
        ref = datetime(2026, 4, 20, 8, 0, tzinfo=UTC)
        result = elapsed_to_absolute([0.0, 3600.0], "s", ref)
        assert result[1] == datetime(2026, 4, 20, 9, 0, tzinfo=UTC)


class TestParseTimestamps:
    """Test the parse_timestamps unified function."""

    def test_elapsed_path(self):
        ref = datetime(2026, 4, 20, 8, 0, tzinfo=UTC)
        result = parse_timestamps(
            ["0.0", "1.0", "2.0"], is_elapsed=True, reference_ts=ref
        )
        assert len(result) == 3
        assert result[0] == ref
        assert result[1] == datetime(2026, 4, 20, 9, 0, tzinfo=UTC)

    def test_absolute_path(self):
        result = parse_timestamps(
            ["2026-04-20 08:00:00", "2026-04-20 09:00:00"],
            is_elapsed=False,
        )
        assert len(result) == 2
        assert result[0].tzinfo is not None  # UTC enforced

    def test_elapsed_without_reference_raises(self):
        with pytest.raises(ValueError, match="reference_ts"):
            parse_timestamps(["0.0", "1.0"], is_elapsed=True, reference_ts=None)

    def test_output_always_utc(self):
        ref = datetime(2026, 4, 20, 8, 0, tzinfo=UTC)
        result = parse_timestamps(["0.0", "2.5"], is_elapsed=True, reference_ts=ref)
        for ts in result:
            assert ts.tzinfo == UTC
