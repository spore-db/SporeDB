"""Additional model tests to cover remaining uncovered lines.

Covers:
- sporedb/__init__.py lines 55-59: lazy CloudClient __getattr__
- models/assay.py lines 25, 66, 73: UncertainValue.to_ufloat(), timezone validators
- models/timeseries.py lines 35, 42: tz-aware validator, finite value validator
- models/lineage.py line 54: timezone-aware validator for UnitOperation
- models/batch.py lines 48, 73: CanonicalTimestamps tz validator, BatchMetadata finite
- query/filters.py lines 43-44, 52-58: name_contains + lifecycle filters
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import pytest

# ---------------------------------------------------------------------------
# sporedb.__init__ lazy CloudClient
# ---------------------------------------------------------------------------


class TestSporeDBModuleLazyImport:
    def test_cloudclient_accessible_via_getattr(self) -> None:
        """sporedb.CloudClient should be importable via lazy __getattr__."""
        import sporedb

        # Should not raise -- triggers the __getattr__ path (lines 55-58)
        CloudClient = sporedb.CloudClient  # noqa: N806
        assert CloudClient is not None

    def test_unknown_attribute_raises_attribute_error(self) -> None:
        """Accessing non-existent attribute raises AttributeError (line 59)."""
        import sporedb

        with pytest.raises(AttributeError):
            _ = sporedb.this_attribute_does_not_exist  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# models/assay.py
# ---------------------------------------------------------------------------


class TestUncertainValueToUfloat:
    def test_to_ufloat_returns_ufloat_object(self) -> None:
        """UncertainValue.to_ufloat() returns an uncertainties.ufloat."""
        from sporedb.models.assay import UncertainValue

        uv = UncertainValue(value=5.0, uncertainty=0.1, unit="g/L")
        result = uv.to_ufloat()
        # uncertainties.UFloat has nominal_value and std_dev
        assert hasattr(result, "nominal_value")
        assert result.nominal_value == pytest.approx(5.0)
        assert result.std_dev == pytest.approx(0.1)

    def test_uncertain_value_finite_validator_raises_on_inf(self) -> None:
        """UncertainValue.must_be_finite raises on inf value."""
        from sporedb.models.assay import UncertainValue

        with pytest.raises(ValueError, match="finite"):
            UncertainValue(value=float("inf"))

    def test_uncertain_value_finite_validator_raises_on_nan(self) -> None:
        """UncertainValue.must_be_finite raises on NaN value."""
        from sporedb.models.assay import UncertainValue

        with pytest.raises(ValueError, match="finite"):
            UncertainValue(value=float("nan"))

    def test_uncertain_value_finite_validator_raises_on_inf_uncertainty(self) -> None:
        """UncertainValue.must_be_finite raises on inf uncertainty."""
        from sporedb.models.assay import UncertainValue

        with pytest.raises(ValueError):
            UncertainValue(value=1.0, uncertainty=float("inf"))


class TestAssayMeasurementValidators:
    def test_naive_timestamp_raises(self) -> None:
        """ts without tzinfo raises ValueError (line 66 - ts_must_be_aware)."""
        from sporedb.models.assay import AssayMeasurement

        with pytest.raises(ValueError, match="timezone-aware"):
            AssayMeasurement(
                batch_id=UUID("00000000-0000-0000-0000-000000000001"),
                ts=datetime(2026, 1, 1),  # naive - no tzinfo
                variable="glucose",
                value=10.0,
            )

    def test_infinite_value_raises(self) -> None:
        """Infinite value raises ValueError (line 73 - must_be_finite)."""
        from sporedb.models.assay import AssayMeasurement

        with pytest.raises(ValueError, match="finite"):
            AssayMeasurement(
                batch_id=UUID("00000000-0000-0000-0000-000000000001"),
                ts=datetime(2026, 1, 1, tzinfo=UTC),
                variable="glucose",
                value=float("inf"),
            )

    def test_nan_value_raises(self) -> None:
        """NaN value raises ValueError."""
        from sporedb.models.assay import AssayMeasurement

        with pytest.raises(ValueError, match="finite"):
            AssayMeasurement(
                batch_id=UUID("00000000-0000-0000-0000-000000000001"),
                ts=datetime(2026, 1, 1, tzinfo=UTC),
                variable="glucose",
                value=float("nan"),
            )


# ---------------------------------------------------------------------------
# models/timeseries.py
# ---------------------------------------------------------------------------


class TestTelemetryRecordValidators:
    def test_naive_ts_raises(self) -> None:
        """ts without tzinfo raises ValueError (line 35)."""
        from sporedb.models.timeseries import TelemetryRecord

        with pytest.raises(ValueError, match="timezone-aware"):
            TelemetryRecord(
                batch_id=UUID("00000000-0000-0000-0000-000000000001"),
                ts=datetime(2026, 1, 1),  # naive
                variable="OD600",
                value=1.5,
            )

    def test_infinite_value_raises(self) -> None:
        """Infinite value raises ValueError (line 42)."""
        from sporedb.models.timeseries import TelemetryRecord

        with pytest.raises(ValueError, match="finite"):
            TelemetryRecord(
                batch_id=UUID("00000000-0000-0000-0000-000000000001"),
                ts=datetime(2026, 1, 1, tzinfo=UTC),
                variable="OD600",
                value=float("inf"),
            )


# ---------------------------------------------------------------------------
# models/lineage.py
# ---------------------------------------------------------------------------


class TestUnitOperationValidators:
    def test_naive_started_at_raises(self) -> None:
        """started_at without tzinfo raises ValueError (line 54)."""
        from sporedb.models.lineage import UnitOperation

        with pytest.raises(ValueError, match="timezone-aware"):
            UnitOperation(
                batch_id=UUID("00000000-0000-0000-0000-000000000001"),
                name="seed_train",
                operation_type="upstream",
                started_at=datetime(2026, 1, 1),  # naive
            )


# ---------------------------------------------------------------------------
# models/batch.py
# ---------------------------------------------------------------------------


class TestCanonicalTimestampsValidator:
    def test_naive_inoculation_raises(self) -> None:
        """Naive inoculation datetime raises ValueError (line 48)."""
        from sporedb.models.batch import CanonicalTimestamps

        with pytest.raises(ValueError, match="timezone-aware"):
            CanonicalTimestamps(
                inoculation=datetime(2026, 1, 1),  # naive
            )


class TestBatchMetadataValidator:
    def test_infinite_scale_liters_raises(self) -> None:
        """Infinite scale_liters raises ValueError (line 73)."""
        from sporedb.models.batch import BatchMetadata

        with pytest.raises(ValueError, match="finite"):
            BatchMetadata(scale_liters=float("inf"))


# ---------------------------------------------------------------------------
# query/filters.py
# ---------------------------------------------------------------------------


class TestBatchFilterToSqlClauses:
    def test_lifecycle_filter_generates_clause(self) -> None:
        """lifecycle filter produces a SQL lifecycle clause."""
        from sporedb.models.batch import BatchLifecycle
        from sporedb.query.filters import BatchFilter

        bf = BatchFilter(lifecycle=BatchLifecycle.RUNNING)
        clauses, params = bf.to_sql_clauses()
        assert any("lifecycle" in c for c in clauses)
        assert BatchLifecycle.RUNNING.value in params

    def test_name_contains_filter_escapes_special_chars(self) -> None:
        """name_contains escapes %, _, \\ and produces ILIKE clause (lines 52-58)."""
        from sporedb.query.filters import BatchFilter

        # Test with special characters that need escaping
        bf = BatchFilter(name_contains="50% yield_test\\batch")
        clauses, params = bf.to_sql_clauses()

        assert any("ILIKE" in c for c in clauses)
        # The param should be wrapped in % and have escaping applied
        param = next(
            p
            for p in params
            if isinstance(p, str) and "ILIKE" not in p and "%" in str(p)
        )
        assert "\\%" in param  # % was escaped
        assert "\\_" in param  # _ was escaped

    def test_name_contains_plain_string_generates_like_clause(self) -> None:
        """Plain name_contains (no special chars) produces correct ILIKE clause."""
        from sporedb.query.filters import BatchFilter

        bf = BatchFilter(name_contains="CHO-Run")
        clauses, params = bf.to_sql_clauses()

        assert any("ILIKE" in c for c in clauses)
        assert any("%CHO-Run%" in str(p) for p in params)

    def test_all_filters_combined(self) -> None:
        """All filter fields set produces correct number of clauses."""
        from datetime import timedelta

        from sporedb.models.batch import BatchLifecycle
        from sporedb.query.filters import BatchFilter

        now = datetime.now(UTC)
        bf = BatchFilter(
            strain="CHO-K1",
            media="CD-CHO",
            operator="Dr. Smith",
            lifecycle=BatchLifecycle.RUNNING,
            tags=["pilot", "glucose"],
            inoculation_after=now - timedelta(days=30),
            inoculation_before=now,
            name_contains="Run",
        )
        clauses, params = bf.to_sql_clauses()

        # 7 field filters (strain, media, operator, lifecycle, name_contains,
        # inoculation_after, inoculation_before) + 2 tags = 9 clauses total
        assert len(clauses) == 9
        assert len(params) == 9
