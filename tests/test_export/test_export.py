"""Tests for SporeDB export layer: CSV, Parquet, and Arrow IPC formats."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from sporedb.export import export_batch, write_arrow, write_csv, write_parquet
from sporedb.models.batch import Batch, BatchMetadata, CanonicalTimestamps
from sporedb.models.timeseries import TelemetryRecord
from sporedb.storage.batch_store import BatchStore
from sporedb.storage.engine import StorageEngine
from sporedb.storage.ts_store import TimeSeriesStore


@pytest.fixture
def populated_engine(tmp_path: Path):
    """Create an engine with a batch and 5 telemetry records."""
    engine = StorageEngine(tmp_path / "data")
    batch = Batch(
        name="Test-Run-001",
        timestamps=CanonicalTimestamps(),
        metadata=BatchMetadata(),
    )
    BatchStore(engine).create_batch(batch)
    ts_store = TimeSeriesStore(engine)

    records = [
        TelemetryRecord(
            batch_id=batch.batch_id,
            ts=datetime(2024, 1, 1, i, 0, 0, tzinfo=UTC),
            variable="temperature",
            value=37.0 + i * 0.1,
            unit="celsius",
        )
        for i in range(5)
    ]
    ts_store.append_telemetry(records)
    return engine, batch.batch_id


@pytest.fixture
def populated_engine_with_original(populated_engine):
    """Same as populated_engine but with an original sidecar Parquet file."""
    engine, batch_id = populated_engine

    # Write original data (temperature in Kelvin) to sidecar location
    original_dir = engine.data_root / "original" / str(batch_id)
    original_dir.mkdir(parents=True, exist_ok=True)

    df = pd.DataFrame(
        {
            "batch_id": [str(batch_id)] * 5,
            "ts": [datetime(2024, 1, 1, i, 0, 0, tzinfo=UTC) for i in range(5)],
            "variable": ["temperature"] * 5,
            "value": [310.0 + i * 0.1 for i in range(5)],  # Kelvin
            "unit": ["kelvin"] * 5,
        }
    )
    table = pa.Table.from_pandas(df)
    pq.write_table(table, original_dir / "telemetry.parquet")

    return engine, batch_id


class TestWriteCSV:
    def test_returns_bytes(self):
        df = pd.DataFrame({"a": [1, 2], "b": [3.0, 4.0]})
        result = write_csv(df)
        assert isinstance(result, bytes)

    def test_valid_csv_content(self):
        df = pd.DataFrame({"col1": [1, 2, 3], "col2": ["x", "y", "z"]})
        result = write_csv(df)
        lines = result.decode("utf-8").strip().split("\n")
        assert lines[0] == "col1,col2"  # header
        assert len(lines) == 4  # header + 3 rows


class TestWriteParquet:
    def test_returns_bytes(self):
        df = pd.DataFrame({"a": [1, 2], "b": [3.0, 4.0]})
        result = write_parquet(df)
        assert isinstance(result, bytes)

    def test_readable_as_parquet(self):
        df = pd.DataFrame({"x": [10, 20, 30], "y": [1.1, 2.2, 3.3]})
        result = write_parquet(df)
        table = pq.read_table(pa.BufferReader(result))
        assert table.num_rows == 3
        assert table.column_names == ["x", "y"]


class TestWriteArrow:
    def test_returns_bytes(self):
        df = pd.DataFrame({"a": [1, 2], "b": [3.0, 4.0]})
        result = write_arrow(df)
        assert isinstance(result, bytes)

    def test_readable_as_arrow_ipc(self):
        df = pd.DataFrame({"x": [10, 20, 30], "y": [1.1, 2.2, 3.3]})
        result = write_arrow(df)
        reader = pa.ipc.open_file(pa.BufferReader(result))
        table = reader.read_all()
        assert table.num_rows == 3
        assert table.column_names == ["x", "y"]


class TestExportBatch:
    def test_csv_export(self, populated_engine):
        engine, batch_id = populated_engine
        result = export_batch(batch_id, engine, format="csv")
        assert isinstance(result, bytes)
        text = result.decode("utf-8")
        assert "temperature" in text
        assert "37.0" in text

    def test_parquet_export(self, populated_engine):
        engine, batch_id = populated_engine
        result = export_batch(batch_id, engine, format="parquet")
        table = pq.read_table(pa.BufferReader(result))
        assert table.num_rows == 5

    def test_arrow_export(self, populated_engine):
        engine, batch_id = populated_engine
        result = export_batch(batch_id, engine, format="arrow")
        reader = pa.ipc.open_file(pa.BufferReader(result))
        table = reader.read_all()
        assert table.num_rows == 5

    def test_output_path_writes_file(self, populated_engine, tmp_path):
        engine, batch_id = populated_engine
        out_file = tmp_path / "output.csv"
        result = export_batch(batch_id, engine, format="csv", output_path=out_file)
        assert result is None
        assert out_file.exists()
        content = out_file.read_text()
        assert "temperature" in content

    def test_form_original(self, populated_engine_with_original):
        engine, batch_id = populated_engine_with_original
        result = export_batch(batch_id, engine, format="csv", form="original")
        text = result.decode("utf-8")
        assert "310.0" in text  # Kelvin values from original sidecar

    def test_form_aligned(self, populated_engine):
        engine, batch_id = populated_engine
        result = export_batch(batch_id, engine, format="csv", form="aligned")
        text = result.decode("utf-8")
        assert "37.0" in text  # Celsius values from main storage

    def test_nonexistent_batch_raises(self, populated_engine):
        engine, _ = populated_engine
        fake_id = uuid4()
        with pytest.raises(ValueError, match="No data found"):
            export_batch(fake_id, engine, format="csv")

    def test_unsupported_format_raises(self, populated_engine):
        engine, batch_id = populated_engine
        with pytest.raises(ValueError, match="Unsupported format"):
            export_batch(batch_id, engine, format="excel")

    def test_includes_assay_data(self, populated_engine):
        engine, batch_id = populated_engine
        # Add assay data
        from sporedb.models.assay import AssayMeasurement

        ts_store = TimeSeriesStore(engine)
        assay_records = [
            AssayMeasurement(
                batch_id=batch_id,
                ts=datetime(2024, 1, 1, 2, 0, 0, tzinfo=UTC),
                variable="glucose",
                value=5.0,
                uncertainty=0.1,
                unit="g/L",
                method="HPLC",
            )
        ]
        ts_store.append_assay(assay_records)

        result = export_batch(batch_id, engine, format="csv", include_assay=True)
        text = result.decode("utf-8")
        assert "glucose" in text
        assert "temperature" in text
