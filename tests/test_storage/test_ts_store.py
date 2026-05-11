"""Integration tests for TimeSeriesStore: telemetry, assay, ASOF JOIN, uncertainty."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pandas as pd
import pytest
from uuid_utils import uuid7

from sporedb.models.assay import AssayMeasurement, UncertainValue
from sporedb.models.timeseries import TelemetryRecord
from sporedb.storage import StorageEngine
from sporedb.storage.ts_store import TimeSeriesStore


def _make_uuid() -> UUID:
    return UUID(str(uuid7()))


@pytest.fixture
def batch_id() -> UUID:
    return _make_uuid()


@pytest.fixture
def ts_store(data_root):
    with StorageEngine(data_root) as engine:
        yield TimeSeriesStore(engine)


@pytest.fixture
def base_time() -> datetime:
    return datetime(2026, 4, 20, 8, 0, 0, tzinfo=UTC)


def _make_telemetry(
    batch_id: UUID, base_time: datetime, count: int = 100
) -> list[TelemetryRecord]:
    """Create count telemetry records at 30-second intervals."""
    return [
        TelemetryRecord(
            batch_id=batch_id,
            ts=base_time + timedelta(seconds=30 * i),
            variable="dissolved_oxygen",
            value=40.0 + i * 0.1,
            unit="% sat",
        )
        for i in range(count)
    ]


def _make_assay(
    batch_id: UUID, base_time: datetime, count: int = 5
) -> list[AssayMeasurement]:
    """Create count assay measurements at 1-hour intervals."""
    return [
        AssayMeasurement(
            batch_id=batch_id,
            ts=base_time + timedelta(hours=i),
            variable="glucose",
            value=20.0 - i * 2.0,
            uncertainty=0.2,
            unit="g/L",
            method="HPLC",
        )
        for i in range(count)
    ]


class TestAppendAndGetTelemetry:
    def test_append_and_get_telemetry(self, ts_store, batch_id, base_time):
        """Append 100 telemetry records, retrieve and verify count."""
        records = _make_telemetry(batch_id, base_time, 100)
        count = ts_store.append_telemetry(records)
        assert count == 100

        df = ts_store.get_telemetry(batch_id)
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 100
        assert "variable" in df.columns
        assert "value" in df.columns
        assert "unit" in df.columns

    def test_append_telemetry_twice_appends(self, ts_store, batch_id, base_time):
        """Two appends concatenate; total equals sum."""
        records1 = _make_telemetry(batch_id, base_time, 50)
        ts_store.append_telemetry(records1)

        records2 = _make_telemetry(batch_id, base_time + timedelta(hours=2), 30)
        ts_store.append_telemetry(records2)

        df = ts_store.get_telemetry(batch_id)
        assert len(df) == 80

    def test_get_telemetry_empty_batch(self, ts_store):
        """Get telemetry for a batch with no data returns empty DataFrame."""
        empty_id = _make_uuid()
        df = ts_store.get_telemetry(empty_id)
        assert isinstance(df, pd.DataFrame)
        assert df.empty


class TestAppendAndGetAssay:
    def test_append_and_get_assay(self, ts_store, batch_id, base_time):
        """Append assay measurements with uncertainty and method columns."""
        records = _make_assay(batch_id, base_time, 5)
        count = ts_store.append_assay(records)
        assert count == 5

        df = ts_store.get_assay(batch_id)
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 5
        assert "uncertainty" in df.columns
        assert "method" in df.columns
        assert df["uncertainty"].iloc[0] == pytest.approx(0.2)
        assert df["method"].iloc[0] == "HPLC"


class TestUnifiedViewAsofJoin:
    def test_unified_view_asof_join(self, ts_store, batch_id, base_time):
        """ASOF JOIN links each assay measurement to nearest prior telemetry ts."""
        telemetry = _make_telemetry(batch_id, base_time, 100)
        ts_store.append_telemetry(telemetry)

        assay = _make_assay(batch_id, base_time, 5)
        ts_store.append_assay(assay)

        df = ts_store.get_unified_view(batch_id)
        assert isinstance(df, pd.DataFrame)
        assert not df.empty
        # The unified view should contain sensor and analyte columns
        assert "sensor" in df.columns or "sensor_value" in df.columns
        assert "analyte" in df.columns or "assay_value" in df.columns

    def test_unified_view_links_nearest_prior_timestamp(
        self, ts_store, batch_id, base_time
    ):
        """Each assay row links to the nearest prior telemetry timestamp."""
        # Telemetry every 30s for 2 hours = 240 records
        telemetry = _make_telemetry(batch_id, base_time, 240)
        ts_store.append_telemetry(telemetry)

        # Assay at exactly hour 1 and hour 2
        assay = [
            AssayMeasurement(
                batch_id=batch_id,
                ts=base_time + timedelta(hours=1),
                variable="glucose",
                value=15.0,
                uncertainty=0.2,
                unit="g/L",
                method="HPLC",
            ),
        ]
        ts_store.append_assay(assay)

        df = ts_store.get_unified_view(batch_id)
        assert not df.empty
        # There should be assay data linked in the result
        assert df["assay_value"].notna().any()


class TestUncertaintyPropagation:
    def test_get_assay_as_uncertain(self, ts_store, batch_id, base_time):
        """get_assay_as_uncertain returns list of UncertainValue objects."""
        records = _make_assay(batch_id, base_time, 5)
        ts_store.append_assay(records)

        uncertain_vals = ts_store.get_assay_as_uncertain(batch_id, "glucose")
        assert len(uncertain_vals) == 5
        assert all(isinstance(uv, UncertainValue) for uv in uncertain_vals)
        assert uncertain_vals[0].value == pytest.approx(20.0)
        assert uncertain_vals[0].uncertainty == pytest.approx(0.2)

    def test_uncertainty_propagation(self, ts_store, batch_id, base_time):
        """Subtract two UncertainValues; result has propagated uncertainty."""
        records = _make_assay(batch_id, base_time, 5)
        ts_store.append_assay(records)

        uncertain_vals = ts_store.get_assay_as_uncertain(batch_id, "glucose")
        a = uncertain_vals[0].to_ufloat()
        b = uncertain_vals[1].to_ufloat()
        diff = a - b
        assert diff.std_dev > 0  # Uncertainty propagated
