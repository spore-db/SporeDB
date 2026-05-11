"""Tests for analytics Pydantic models."""

from datetime import UTC, datetime
from uuid import UUID

import pytest
from pydantic import ValidationError


class TestPhaseType:
    def test_all_five_values(self):
        from sporedb.analytics.models import PhaseType

        expected = {"LAG", "EXPONENTIAL", "STATIONARY", "DECLINE", "UNKNOWN"}
        actual = {member.name for member in PhaseType}
        assert actual == expected

    def test_serializes_to_lowercase(self):
        from sporedb.analytics.models import PhaseType

        assert PhaseType.LAG.value == "lag"
        assert PhaseType.EXPONENTIAL.value == "exponential"
        assert PhaseType.STATIONARY.value == "stationary"
        assert PhaseType.DECLINE.value == "decline"
        assert PhaseType.UNKNOWN.value == "unknown"


class TestPhaseAnnotation:
    def test_requires_timezone_aware_start_ts(self):
        from sporedb.analytics.models import PhaseAnnotation, PhaseType

        with pytest.raises(ValidationError, match="timezone-aware"):
            PhaseAnnotation(
                batch_id=UUID("00000000-0000-0000-0000-000000000001"),
                phase_type=PhaseType.LAG,
                start_ts=datetime(2026, 1, 1, 0, 0),  # naive
                end_ts=datetime(2026, 1, 1, 1, 0, tzinfo=UTC),
                signal_variable="OD600",
            )

    def test_requires_timezone_aware_end_ts(self):
        from sporedb.analytics.models import PhaseAnnotation, PhaseType

        with pytest.raises(ValidationError, match="timezone-aware"):
            PhaseAnnotation(
                batch_id=UUID("00000000-0000-0000-0000-000000000001"),
                phase_type=PhaseType.LAG,
                start_ts=datetime(2026, 1, 1, 0, 0, tzinfo=UTC),
                end_ts=datetime(2026, 1, 1, 1, 0),  # naive
                signal_variable="OD600",
            )

    def test_default_confidence_is_zero(self):
        from sporedb.analytics.models import PhaseAnnotation, PhaseType

        ann = PhaseAnnotation(
            batch_id=UUID("00000000-0000-0000-0000-000000000001"),
            phase_type=PhaseType.LAG,
            start_ts=datetime(2026, 1, 1, 0, 0, tzinfo=UTC),
            end_ts=datetime(2026, 1, 1, 1, 0, tzinfo=UTC),
            signal_variable="OD600",
        )
        assert ann.confidence == 0.0

    def test_default_metadata_is_empty_dict(self):
        from sporedb.analytics.models import PhaseAnnotation, PhaseType

        ann = PhaseAnnotation(
            batch_id=UUID("00000000-0000-0000-0000-000000000001"),
            phase_type=PhaseType.LAG,
            start_ts=datetime(2026, 1, 1, 0, 0, tzinfo=UTC),
            end_ts=datetime(2026, 1, 1, 1, 0, tzinfo=UTC),
            signal_variable="OD600",
        )
        assert ann.metadata == {}


class TestBatchMetrics:
    def test_optional_float_fields_default_none(self):
        from sporedb.analytics.models import BatchMetrics, PhaseType

        metrics = BatchMetrics(
            batch_id=UUID("00000000-0000-0000-0000-000000000001"),
            phase_type=PhaseType.EXPONENTIAL,
        )
        assert metrics.mu is None
        assert metrics.qp is None
        assert metrics.yx_s is None
        assert metrics.yp_s is None


class TestDetectionConfig:
    def test_defaults(self):
        from sporedb.analytics.models import DetectionConfig

        config = DetectionConfig()
        assert config.signal_variable == "OD600"
        assert config.kernel == "rbf"
        assert config.min_size == 10
        assert config.penalty is None


class TestParquetLayoutPhases:
    def test_phases_dir(self, data_root):
        from sporedb.storage.parquet_layout import ParquetLayout

        layout = ParquetLayout(data_root)
        bid = UUID("00000000-0000-0000-0000-000000000001")
        expected = data_root / "phases" / f"batch_id={bid}"
        assert layout.phases_dir(bid) == expected

    def test_phases_file(self, data_root):
        from sporedb.storage.parquet_layout import ParquetLayout

        layout = ParquetLayout(data_root)
        bid = UUID("00000000-0000-0000-0000-000000000001")
        expected = data_root / "phases" / f"batch_id={bid}" / "data.parquet"
        assert layout.phases_file(bid) == expected
