"""Tests for LabVantage LIMS connector with mocked HTTP responses.

All tests use mocks -- no real LabVantage instance required.
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from types import ModuleType
from unittest.mock import MagicMock, patch

import pytest

from sporedb.connectors.config import (
    ConnectorConfig,
    FieldMapping,
    SchemaMapping,
)
from sporedb.connectors.result import PullResult
from sporedb.storage.engine import StorageEngine

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def engine(tmp_path) -> StorageEngine:
    return StorageEngine(data_root=tmp_path / "sporedb_data")


@pytest.fixture
def lv_config() -> ConnectorConfig:
    return ConnectorConfig(
        connector_type="labvantage",
        host="https://lims.example.com",
        auth={"username": "limsuser", "password": "limspass"},
        extra={"database_id": "PROD_LIMS"},
    )


@pytest.fixture
def mapping() -> SchemaMapping:
    return SchemaMapping(
        timestamp_field="resultdate",
        variable_mappings=[
            FieldMapping(source="glucose", target="glucose_g_l", unit="g/L"),
            FieldMapping(source="od600", target="optical_density"),
        ],
    )


def _build_mock_httpx() -> ModuleType:
    """Build a mock httpx module."""
    mod = ModuleType("httpx")
    mock_client_class = MagicMock()
    mod.Client = mock_client_class
    return mod


def _make_json_response(data: dict, status_code: int = 200) -> MagicMock:
    """Create a mock HTTP response."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = data
    resp.raise_for_status = MagicMock()
    if status_code >= 400:
        resp.raise_for_status.side_effect = Exception(f"HTTP {status_code}")
    return resp


# ---------------------------------------------------------------------------
# Test: Connect
# ---------------------------------------------------------------------------


class TestConnect:
    """Verify session-based authentication."""

    def test_connect_creates_session(self, lv_config, engine):
        mock_httpx = _build_mock_httpx()
        mock_client = MagicMock()
        mock_httpx.Client.return_value = mock_client

        # Mock successful auth response
        auth_resp = _make_json_response({"connectionid": "conn-12345-abcde"})
        mock_client.post.return_value = auth_resp

        with patch.dict(sys.modules, {"httpx": mock_httpx}):
            from sporedb.connectors.labvantage import (
                LabVantageLIMSConnector,
            )

            conn = LabVantageLIMSConnector(config=lv_config, engine=engine)
            conn.connect()

            assert conn._connected is True
            assert conn._connection_id == "conn-12345-abcde"

            # Verify auth request
            mock_client.post.assert_called_once_with(
                "/rest/connections",
                json={
                    "databaseid": "PROD_LIMS",
                    "username": "limsuser",
                    "password": "limspass",
                },
            )

    def test_connect_fails_without_connectionid(self, lv_config, engine):
        mock_httpx = _build_mock_httpx()
        mock_client = MagicMock()
        mock_httpx.Client.return_value = mock_client

        # Response without connectionid
        auth_resp = _make_json_response({"status": "ok"})
        mock_client.post.return_value = auth_resp

        with patch.dict(sys.modules, {"httpx": mock_httpx}):
            from sporedb.connectors.labvantage import (
                LabVantageLIMSConnector,
            )

            conn = LabVantageLIMSConnector(config=lv_config, engine=engine)
            with pytest.raises(ConnectionError, match="connectionid"):
                conn.connect()


# ---------------------------------------------------------------------------
# Test: Discover
# ---------------------------------------------------------------------------


class TestDiscover:
    """Test endpoint discovery."""

    def test_discover_probes_endpoints(self, lv_config, engine):
        mock_httpx = _build_mock_httpx()
        mock_client = MagicMock()
        mock_httpx.Client.return_value = mock_client

        # Auth response
        auth_resp = _make_json_response({"connectionid": "conn-abc"})
        mock_client.post.return_value = auth_resp

        # Endpoint probing: sample=200, result=200, test=404
        def mock_get(url, **kwargs):
            if "/rest/sample" in url or "/rest/result" in url:
                return _make_json_response({"data": []}, 200)
            elif "/rest/test" in url:
                resp = MagicMock()
                resp.status_code = 404
                return resp
            return _make_json_response({}, 200)

        mock_client.get.side_effect = mock_get

        with patch.dict(sys.modules, {"httpx": mock_httpx}):
            from sporedb.connectors.labvantage import (
                LabVantageLIMSConnector,
            )

            conn = LabVantageLIMSConnector(config=lv_config, engine=engine)
            conn.connect()
            results = conn.discover()

            assert len(results) == 3
            sample_ep = next(r for r in results if r["type"] == "samples")
            assert sample_ep["available"] is True

            result_ep = next(r for r in results if r["type"] == "results")
            assert result_ep["available"] is True

            test_ep = next(r for r in results if r["type"] == "tests")
            assert test_ep["available"] is False

    def test_discover_handles_connection_error(self, lv_config, engine):
        mock_httpx = _build_mock_httpx()
        mock_client = MagicMock()
        mock_httpx.Client.return_value = mock_client

        # Auth response
        auth_resp = _make_json_response({"connectionid": "conn-abc"})
        mock_client.post.return_value = auth_resp

        # All endpoints fail
        mock_client.get.side_effect = ConnectionError("Network error")

        with patch.dict(sys.modules, {"httpx": mock_httpx}):
            from sporedb.connectors.labvantage import (
                LabVantageLIMSConnector,
            )

            conn = LabVantageLIMSConnector(config=lv_config, engine=engine)
            conn.connect()
            results = conn.discover()

            assert len(results) == 3
            assert all(r["available"] is False for r in results)


# ---------------------------------------------------------------------------
# Test: Pull
# ---------------------------------------------------------------------------


class TestPull:
    """Test pull with mocked sample/result data."""

    def test_pull_with_sample_and_results(self, lv_config, engine, mapping):
        mock_httpx = _build_mock_httpx()
        mock_client = MagicMock()
        mock_httpx.Client.return_value = mock_client

        # Auth response
        auth_resp = _make_json_response({"connectionid": "conn-abc"})
        mock_client.post.return_value = auth_resp

        now = datetime.now(UTC)

        # Mock sample and result responses
        sample_data = {
            "data": [
                {"keyid1": "SAMPLE-001", "status": "complete"},
                {"keyid1": "SAMPLE-002", "status": "complete"},
            ]
        }
        result_data = {
            "data": [
                {
                    "resultdate": now.isoformat(),
                    "glucose": "12.5",
                    "od600": "0.85",
                    "unit": "g/L",
                    "testmethod": "HPLC",
                },
            ]
        }

        def mock_get(url, **kwargs):
            if "/rest/sample" in url:
                return _make_json_response(sample_data)
            elif "/rest/result" in url:
                return _make_json_response(result_data)
            return _make_json_response({"data": []})

        mock_client.get.side_effect = mock_get

        with patch.dict(sys.modules, {"httpx": mock_httpx}):
            from sporedb.connectors.labvantage import (
                LabVantageLIMSConnector,
            )

            conn = LabVantageLIMSConnector(config=lv_config, engine=engine)
            conn.connect()
            result = conn.pull("lims_batch_001", mapping)

            assert isinstance(result, PullResult)
            assert result.source_system == "labvantage"
            assert result.source_identifier == "https://lims.example.com"
            # 2 samples x 1 result each x 2 mapped fields = 4
            assert result.rows_imported == 4
            assert result.columns_mapped == {
                "glucose": "glucose_g_l",
                "od600": "optical_density",
            }
            assert "lims_sample_ids" in result.external_ids
            assert "SAMPLE-001" in result.external_ids["lims_sample_ids"]

    def test_pull_creates_batch_before_assay(self, lv_config, engine, mapping):
        """Verify pull creates batch via BatchStore BEFORE AssayMeasurement objects."""
        mock_httpx = _build_mock_httpx()
        mock_client = MagicMock()
        mock_httpx.Client.return_value = mock_client

        auth_resp = _make_json_response({"connectionid": "conn-abc"})
        mock_client.post.return_value = auth_resp

        now = datetime.now(UTC)
        sample_data = {"data": [{"keyid1": "S-001"}]}
        result_data = {
            "data": [
                {
                    "resultdate": now.isoformat(),
                    "glucose": "10.0",
                    "od600": "0.5",
                }
            ]
        }

        def mock_get(url, **kwargs):
            if "/rest/sample" in url:
                return _make_json_response(sample_data)
            elif "/rest/result" in url:
                return _make_json_response(result_data)
            return _make_json_response({"data": []})

        mock_client.get.side_effect = mock_get

        with patch.dict(sys.modules, {"httpx": mock_httpx}):
            from sporedb.connectors.labvantage import (
                LabVantageLIMSConnector,
            )

            conn = LabVantageLIMSConnector(config=lv_config, engine=engine)
            conn.connect()
            result = conn.pull("batch_order_test", mapping)

            # Verify batch exists (was created before assays)
            from sporedb.storage.batch_store import BatchStore

            batch_store = BatchStore(engine)
            batch = batch_store.get_batch(result.batch_id)
            assert batch is not None
            assert batch.name == "batch_order_test"

            # Verify assay data was persisted with correct batch_id
            from sporedb.storage.ts_store import TimeSeriesStore

            ts_store = TimeSeriesStore(engine)
            assay_df = ts_store.get_assay(result.batch_id)
            assert not assay_df.empty
            assert all(
                str(bid) == str(result.batch_id) for bid in assay_df["batch_id"].values
            )

    def test_pull_with_sample_ids_filter(self, lv_config, engine, mapping):
        mock_httpx = _build_mock_httpx()
        mock_client = MagicMock()
        mock_httpx.Client.return_value = mock_client

        auth_resp = _make_json_response({"connectionid": "conn-abc"})
        mock_client.post.return_value = auth_resp

        now = datetime.now(UTC)
        sample_data = {"data": [{"keyid1": "SAMPLE-005"}]}
        result_data = {
            "data": [
                {
                    "resultdate": now.isoformat(),
                    "glucose": "15.0",
                    "od600": "1.2",
                }
            ]
        }

        def mock_get(url, **kwargs):
            if "/rest/sample" in url:
                # Verify keyid1 param was passed
                params = kwargs.get("params", {})
                assert params.get("keyid1") == "SAMPLE-005"
                return _make_json_response(sample_data)
            elif "/rest/result" in url:
                return _make_json_response(result_data)
            return _make_json_response({"data": []})

        mock_client.get.side_effect = mock_get

        with patch.dict(sys.modules, {"httpx": mock_httpx}):
            from sporedb.connectors.labvantage import (
                LabVantageLIMSConnector,
            )

            conn = LabVantageLIMSConnector(config=lv_config, engine=engine)
            conn.connect()
            result = conn.pull(
                "filtered_batch",
                mapping,
                sample_ids=["SAMPLE-005"],
            )

            assert result.rows_imported == 2  # 1 sample x 2 fields
            assert "SAMPLE-005" in result.external_ids["lims_sample_ids"]

    def test_pull_empty_results(self, lv_config, engine, mapping):
        mock_httpx = _build_mock_httpx()
        mock_client = MagicMock()
        mock_httpx.Client.return_value = mock_client

        auth_resp = _make_json_response({"connectionid": "conn-abc"})
        mock_client.post.return_value = auth_resp

        # No samples returned
        def mock_get(url, **kwargs):
            return _make_json_response({"data": []})

        mock_client.get.side_effect = mock_get

        with patch.dict(sys.modules, {"httpx": mock_httpx}):
            from sporedb.connectors.labvantage import (
                LabVantageLIMSConnector,
            )

            conn = LabVantageLIMSConnector(config=lv_config, engine=engine)
            conn.connect()
            result = conn.pull("empty_batch", mapping)

            assert result.rows_imported == 0
            assert result.batch_id is not None  # Batch still created


# ---------------------------------------------------------------------------
# Test: Close
# ---------------------------------------------------------------------------


class TestClose:
    """Test connection cleanup."""

    def test_close_cleans_up(self, lv_config, engine):
        mock_httpx = _build_mock_httpx()
        mock_client = MagicMock()
        mock_httpx.Client.return_value = mock_client

        auth_resp = _make_json_response({"connectionid": "conn-abc"})
        mock_client.post.return_value = auth_resp

        with patch.dict(sys.modules, {"httpx": mock_httpx}):
            from sporedb.connectors.labvantage import (
                LabVantageLIMSConnector,
            )

            conn = LabVantageLIMSConnector(config=lv_config, engine=engine)
            conn.connect()
            conn.close()

            mock_client.close.assert_called_once()
            assert conn._connected is False
            assert conn._connection_id == ""
            assert conn._client is None

    def test_context_manager(self, lv_config, engine):
        mock_httpx = _build_mock_httpx()
        mock_client = MagicMock()
        mock_httpx.Client.return_value = mock_client

        auth_resp = _make_json_response({"connectionid": "conn-abc"})
        mock_client.post.return_value = auth_resp

        with patch.dict(sys.modules, {"httpx": mock_httpx}):
            from sporedb.connectors.labvantage import (
                LabVantageLIMSConnector,
            )

            conn = LabVantageLIMSConnector(config=lv_config, engine=engine)
            with conn:
                assert conn._connected is True

            assert conn._connected is False
