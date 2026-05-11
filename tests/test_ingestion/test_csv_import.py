"""Tests for CSV reader with encoding detection and two-pass import."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pyarrow.parquet as pq
import pytest

from sporedb.ingestion.csv_reader import import_csv, read_csv_safe
from sporedb.ingestion.result import ColumnMapping
from sporedb.storage.engine import StorageEngine
from sporedb.storage.ts_store import TimeSeriesStore

FIXTURES = Path(__file__).parent.parent / "fixtures"


@pytest.fixture
def engine(data_root):
    return StorageEngine(data_root)


class TestReadCsvSafe:
    """Test raw CSV reading with encoding detection."""

    def test_reads_headers_and_data(self):
        headers, rows, encoding = read_csv_safe(FIXTURES / "sample_telemetry.csv")
        assert headers == ["timestamp", "pH", "DO_%", "temp_C", "OD600", "glucose_g_L"]
        assert len(rows) == 5
        assert rows[0][0] == "2026-04-20 08:00:00"

    def test_detects_utf8_encoding(self):
        _, _, encoding = read_csv_safe(FIXTURES / "sample_telemetry.csv")
        assert encoding.lower().replace("-", "") in ("utf8", "ascii")


class TestImportCsv:
    """Test full CSV import pipeline."""

    def test_import_absolute_timestamps(self, engine):
        result = import_csv(
            FIXTURES / "sample_telemetry.csv",
            "Run-042",
            engine=engine,
        )
        assert result.rows_imported > 0
        assert isinstance(result.batch_id, UUID)
        assert result.elapsed_seconds >= 0

    def test_import_elapsed_with_inoculation_ts(self, engine):
        inoc_ts = datetime(2026, 4, 20, 8, 0, 0, tzinfo=UTC)
        result = import_csv(
            FIXTURES / "sample_elapsed.csv",
            "Run-Elapsed",
            engine=engine,
            inoculation_ts=inoc_ts,
        )
        assert result.rows_imported == 20  # 5 rows × 4 variables = 20 records
        # Verify timestamps were converted to absolute
        ts_store = TimeSeriesStore(engine)
        df = ts_store.get_telemetry(result.batch_id)
        assert not df.empty

    def test_import_with_unit_conversion(self, engine):
        """temp_K should be converted to C, biomass_mg_L to g/L."""
        inoc_ts = datetime(2026, 4, 20, 8, 0, 0, tzinfo=UTC)
        result = import_csv(
            FIXTURES / "sample_elapsed.csv",
            "Run-Units",
            engine=engine,
            inoculation_ts=inoc_ts,
        )
        # Should have unit conversions recorded
        assert len(result.units_converted) > 0

    def test_two_pass_flow_with_provided_mapping(self, engine):
        """When ColumnMapping is provided, use it instead of auto-detecting."""
        mapping = ColumnMapping(
            timestamp_col="timestamp",
            variable_mappings={
                "pH": "ph",
                "DO_%": "dissolved_oxygen",
                "temp_C": "temperature",
            },
            unit_mappings={},
            unmapped_cols=["OD600", "glucose_g_L"],
            confidence={"pH": 1.0, "DO_%": 1.0, "temp_C": 1.0},
        )
        result = import_csv(
            FIXTURES / "sample_telemetry.csv",
            "Run-TwoPass",
            engine=engine,
            mapping=mapping,
        )
        # Only 3 variables should be mapped (pH, DO, temp)
        assert "ph" in result.columns_mapped.values() or "pH" in result.columns_mapped

    def test_persists_telemetry_records(self, engine):
        result = import_csv(
            FIXTURES / "sample_telemetry.csv",
            "Run-Persist",
            engine=engine,
        )
        ts_store = TimeSeriesStore(engine)
        df = ts_store.get_telemetry(result.batch_id)
        assert not df.empty
        assert len(df) > 0

    def test_original_values_stored_in_sidecar_parquet(self, engine):
        result = import_csv(
            FIXTURES / "sample_telemetry.csv",
            "Run-Original",
            engine=engine,
        )
        sidecar_path = (
            engine.data_root / "original" / str(result.batch_id) / "telemetry.parquet"
        )
        assert sidecar_path.exists()
        table = pq.read_table(sidecar_path)
        assert table.num_rows == 5


class TestImportCsvEdgeCases:
    """Test edge cases and validation."""

    def test_empty_csv_raises_valueerror(self, engine, tmp_path):
        empty_csv = tmp_path / "empty.csv"
        empty_csv.write_text("")
        with pytest.raises(ValueError):
            import_csv(empty_csv, "Empty", engine=engine)

    def test_questionable_values_produce_warnings(self, engine, tmp_path):
        """Negative OD and pH > 14 should warn but not reject."""
        csv_content = "timestamp,pH,OD600\n2026-04-20 08:00:00,15.0,-0.5\n"
        bad_csv = tmp_path / "bad_values.csv"
        bad_csv.write_text(csv_content)
        result = import_csv(bad_csv, "Run-Bad", engine=engine)
        assert len(result.warnings) > 0
        assert result.rows_imported == 2  # 1 row × 2 variables = 2 records

    def test_elapsed_without_inoculation_ts_raises(self, engine):
        with pytest.raises(ValueError, match="inoculation"):
            import_csv(
                FIXTURES / "sample_elapsed.csv",
                "Run-NoInoc",
                engine=engine,
            )
