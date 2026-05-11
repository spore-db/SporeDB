"""Tests for the SporeDB facade client."""

from __future__ import annotations

from datetime import UTC
from unittest.mock import MagicMock, patch
from uuid import UUID

import pandas as pd
import pytest
from uuid_utils import uuid7

from sporedb.client import SporeDB


class TestSporeDBInit:
    def test_create_client_with_default_path(self, tmp_path):
        """SporeDB(tmp_path) creates engine and stores."""
        db = SporeDB(tmp_path / "data")
        assert db is not None
        db.close()

    def test_context_manager(self, tmp_path):
        """with SporeDB(...) as db: works and closes cleanly."""
        with SporeDB(tmp_path / "data") as db:
            assert db is not None


class TestSporeDBBatchCRUD:
    def test_create_and_list_batch(self, tmp_path):
        """Create a batch, list_batches returns it."""
        with SporeDB(tmp_path / "data") as db:
            batch = db.create_batch("CHO-Run-001", strain="CHO-K1", media="CD-CHO")
            assert batch.name == "CHO-Run-001"
            assert batch.metadata.strain == "CHO-K1"
            batches = db.list_batches()
            assert len(batches) == 1
            assert batches[0].batch_id == batch.batch_id

    def test_get_batch_by_id(self, tmp_path):
        """get_batch returns the created batch."""
        with SporeDB(tmp_path / "data") as db:
            batch = db.create_batch("Test-001")
            retrieved = db.get_batch(batch.batch_id)
            assert retrieved is not None
            assert retrieved.name == "Test-001"

    def test_get_batch_not_found(self, tmp_path):
        """get_batch returns None for nonexistent ID."""
        with SporeDB(tmp_path / "data") as db:
            assert db.get_batch(uuid7()) is None

    def test_delete_batch(self, tmp_path):
        """delete_batch removes the batch."""
        with SporeDB(tmp_path / "data") as db:
            batch = db.create_batch("Del-001")
            assert db.delete_batch(batch.batch_id) is True
            assert db.get_batch(batch.batch_id) is None

    def test_create_batch_with_all_kwargs(self, tmp_path):
        """Create a batch with all optional keyword arguments."""
        from datetime import datetime

        inoc = datetime(2026, 1, 1, 8, 0, tzinfo=UTC)
        with SporeDB(tmp_path / "data") as db:
            batch = db.create_batch(
                "Full-001",
                strain="E. coli BL21",
                media="LB",
                scale_liters=2.0,
                operator="Dr. Test",
                tags=["test", "demo"],
                inoculation=inoc,
            )
            assert batch.metadata.strain == "E. coli BL21"
            assert batch.metadata.media == "LB"
            assert batch.metadata.scale_liters == 2.0
            assert batch.metadata.operator == "Dr. Test"
            assert batch.tags == ["test", "demo"]
            assert batch.timestamps.inoculation == inoc


class TestSporeDBImport:
    def test_import_csv(self, tmp_path):
        """import_csv returns ImportResult with rows_imported > 0."""
        csv_content = (
            "timestamp,OD600,pH,temperature\n"
            "2026-01-01 00:00:00,0.1,7.0,37.0\n"
            "2026-01-01 01:00:00,0.5,6.8,37.1\n"
        )
        csv_file = tmp_path / "test.csv"
        csv_file.write_text(csv_content)
        with SporeDB(tmp_path / "data") as db:
            result = db.import_csv(csv_file, "CSV-Run-001")
            assert result.rows_imported > 0
            assert isinstance(result.batch_id, UUID)


class TestSporeDBCloudModeGuards:
    """Cloud-mode clients must raise NotImplementedError for local-only methods."""

    @pytest.fixture
    def cloud_db(self):
        """Create a SporeDB client in cloud mode with a mock CloudClient."""
        with patch("sporedb.cloud_client.CloudClient") as MockCloudClient:
            mock_cloud = MagicMock()
            MockCloudClient.return_value = mock_cloud
            db = SporeDB(endpoint="https://cloud.sporedb.io", api_key="test-key")
            yield db
            db.close()

    def test_get_unified_view_raises(self, cloud_db):
        """get_unified_view raises NotImplementedError in cloud mode."""
        with pytest.raises(NotImplementedError, match="Unified view"):
            cloud_db.get_unified_view(uuid7())

    def test_import_csv_raises(self, cloud_db, tmp_path):
        """import_csv raises NotImplementedError in cloud mode."""
        csv_file = tmp_path / "test.csv"
        csv_file.write_text("ts,val\n2026-01-01,1.0\n")
        with pytest.raises(NotImplementedError, match="CSV import"):
            cloud_db.import_csv(csv_file, "test")

    def test_import_excel_raises(self, cloud_db, tmp_path):
        """import_excel raises NotImplementedError in cloud mode."""
        xls_file = tmp_path / "test.xlsx"
        xls_file.write_bytes(b"fake")
        with pytest.raises(NotImplementedError, match="Excel import"):
            cloud_db.import_excel(xls_file, "test")

    def test_export_raises(self, cloud_db):
        """export raises NotImplementedError in cloud mode."""
        with pytest.raises(NotImplementedError, match="Export"):
            cloud_db.export(uuid7())


class TestSporeDBTelemetry:
    def test_get_telemetry_returns_dataframe(self, tmp_path):
        """get_telemetry returns pd.DataFrame after import."""
        csv_file = tmp_path / "tel.csv"
        csv_file.write_text(
            "timestamp,OD600,pH\n"
            "2026-01-01 00:00:00,0.1,7.0\n"
            "2026-01-01 01:00:00,0.5,6.8\n"
        )
        with SporeDB(tmp_path / "data") as db:
            result = db.import_csv(csv_file, "Tel-001")
            df = db.get_telemetry(result.batch_id)
            assert isinstance(df, pd.DataFrame)
            assert len(df) > 0

    def test_get_telemetry_empty_for_new_batch(self, tmp_path):
        """get_telemetry returns empty DataFrame for a batch with no data."""
        with SporeDB(tmp_path / "data") as db:
            batch = db.create_batch("Empty-001")
            df = db.get_telemetry(batch.batch_id)
            assert isinstance(df, pd.DataFrame)
            assert len(df) == 0
