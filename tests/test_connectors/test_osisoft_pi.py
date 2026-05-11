"""Tests for OSIsoft PI connector with mocked clients.

All tests use mocks -- no real PI server required.
Tests cover both pi-web-sdk and raw httpx fallback paths.
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from types import ModuleType, SimpleNamespace
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
def sdk_config() -> ConnectorConfig:
    """Config for pi-web-sdk backend (default)."""
    return ConnectorConfig(
        connector_type="osisoft_pi",
        host="https://pi.example.com",
        auth={"username": "piuser", "password": "pipass"},
        extra={"use_raw_httpx": "false"},
    )


@pytest.fixture
def httpx_config() -> ConnectorConfig:
    """Config for raw httpx fallback."""
    return ConnectorConfig(
        connector_type="osisoft_pi",
        host="https://pi.example.com",
        auth={"username": "piuser", "password": "pipass"},
        ssl_verify=False,
        timeout_seconds=60,
        extra={"use_raw_httpx": "true"},
    )


@pytest.fixture
def mapping() -> SchemaMapping:
    return SchemaMapping(
        timestamp_field="timestamp",
        variable_mappings=[
            FieldMapping(
                source="pi:\\\\SERVER\\sinusoid",
                target="dissolved_oxygen",
                unit="mg/L",
            ),
            FieldMapping(
                source="pi:\\\\SERVER\\cdt158",
                target="temperature",
                unit="degC",
            ),
        ],
    )


def _build_mock_pi_web_sdk() -> ModuleType:
    """Build a mock pi_web_sdk module."""
    mod = ModuleType("pi_web_sdk")

    # PIWebAPIConfig
    mock_config_class = MagicMock()
    mod.PIWebAPIConfig = mock_config_class

    # PIWebAPIClient
    mock_client_class = MagicMock()
    mod.PIWebAPIClient = mock_client_class

    return mod


def _build_mock_httpx() -> ModuleType:
    """Build a mock httpx module."""
    mod = ModuleType("httpx")
    mock_client_class = MagicMock()
    mod.Client = mock_client_class
    return mod


# ---------------------------------------------------------------------------
# Test: SDK connect
# ---------------------------------------------------------------------------


class TestSDKConnect:
    """Verify connect with pi-web-sdk."""

    def test_sdk_connect_creates_client(self, sdk_config, engine):
        mock_pi = _build_mock_pi_web_sdk()
        with patch.dict(sys.modules, {"pi_web_sdk": mock_pi}):
            from sporedb.connectors.osisoft_pi import OSIsoftPIConnector

            conn = OSIsoftPIConnector(config=sdk_config, engine=engine)
            conn.connect()

            assert conn._connected is True
            assert conn._use_raw_httpx is False
            mock_pi.PIWebAPIConfig.assert_called_once_with(
                base_url="https://pi.example.com",
                auth_type="basic",
                username="piuser",
                password="pipass",
                verify_ssl=True,
            )
            mock_pi.PIWebAPIClient.assert_called_once()


# ---------------------------------------------------------------------------
# Test: Httpx fallback connect
# ---------------------------------------------------------------------------


class TestHttpxConnect:
    """Verify connect with raw httpx fallback."""

    def test_httpx_connect_creates_client(self, httpx_config, engine):
        mock_httpx = _build_mock_httpx()
        with patch.dict(sys.modules, {"httpx": mock_httpx}):
            from sporedb.connectors.osisoft_pi import OSIsoftPIConnector

            conn = OSIsoftPIConnector(config=httpx_config, engine=engine)
            conn.connect()

            assert conn._connected is True
            assert conn._use_raw_httpx is True
            mock_httpx.Client.assert_called_once_with(
                base_url="https://pi.example.com",
                auth=("piuser", "pipass"),
                verify=False,
                timeout=60,
            )


# ---------------------------------------------------------------------------
# Test: Discover
# ---------------------------------------------------------------------------


class TestDiscover:
    """Test discover() for both SDK and httpx backends."""

    def test_discover_sdk(self, sdk_config, engine):
        mock_pi = _build_mock_pi_web_sdk()
        mock_client = MagicMock()
        mock_pi.PIWebAPIClient.return_value = mock_client

        # Mock data server
        mock_server = SimpleNamespace(web_id="server_wid_1")
        mock_client.dataserver.list.return_value = [mock_server]

        # Mock PI points
        mock_point_1 = SimpleNamespace(
            name="sinusoid",
            path="pi:\\\\SERVER\\sinusoid",
            engineering_units="mg/L",
        )
        mock_point_2 = SimpleNamespace(
            name="cdt158",
            path="pi:\\\\SERVER\\cdt158",
            engineering_units="degC",
        )
        mock_client.point.get_points.return_value = [
            mock_point_1,
            mock_point_2,
        ]

        with patch.dict(sys.modules, {"pi_web_sdk": mock_pi}):
            from sporedb.connectors.osisoft_pi import OSIsoftPIConnector

            conn = OSIsoftPIConnector(config=sdk_config, engine=engine)
            conn.connect()
            results = conn.discover()

            assert len(results) == 2
            assert results[0]["name"] == "sinusoid"
            assert results[0]["path"] == "pi:\\\\SERVER\\sinusoid"
            assert results[0]["type"] == "point"
            assert results[0]["engineering_units"] == "mg/L"
            assert results[1]["name"] == "cdt158"

    def test_discover_httpx(self, httpx_config, engine):
        mock_httpx = _build_mock_httpx()
        mock_client = MagicMock()
        mock_httpx.Client.return_value = mock_client

        # Mock data servers response
        servers_resp = MagicMock()
        servers_resp.json.return_value = {
            "Items": [{"WebId": "server_wid_1", "Name": "PISERVER"}]
        }
        servers_resp.raise_for_status = MagicMock()

        # Mock points response
        points_resp = MagicMock()
        points_resp.json.return_value = {
            "Items": [
                {
                    "Name": "sinusoid",
                    "Path": "pi:\\\\SERVER\\sinusoid",
                    "WebId": "point_wid_1",
                    "EngineeringUnits": "mg/L",
                },
                {
                    "Name": "cdt158",
                    "Path": "pi:\\\\SERVER\\cdt158",
                    "WebId": "point_wid_2",
                    "EngineeringUnits": "degC",
                },
            ]
        }
        points_resp.raise_for_status = MagicMock()

        def mock_get(url, **kwargs):
            if "dataservers" in url and "points" not in url:
                return servers_resp
            return points_resp

        mock_client.get.side_effect = mock_get

        with patch.dict(sys.modules, {"httpx": mock_httpx}):
            from sporedb.connectors.osisoft_pi import OSIsoftPIConnector

            conn = OSIsoftPIConnector(config=httpx_config, engine=engine)
            conn.connect()
            results = conn.discover()

            assert len(results) == 2
            assert results[0]["name"] == "sinusoid"
            assert results[0]["type"] == "point"


# ---------------------------------------------------------------------------
# Test: Pull
# ---------------------------------------------------------------------------


class TestPull:
    """Test pull() with mocked recorded values."""

    def test_pull_sdk_returns_pull_result(self, sdk_config, engine, mapping):
        mock_pi = _build_mock_pi_web_sdk()
        mock_client = MagicMock()
        mock_pi.PIWebAPIClient.return_value = mock_client

        # Mock point lookup
        mock_point = SimpleNamespace(web_id="point_wid_1")
        mock_client.point.get_by_path.return_value = mock_point

        # Mock recorded values
        now = datetime.now(UTC)
        mock_item_1 = SimpleNamespace(timestamp=now.isoformat(), value=7.1)
        mock_item_2 = SimpleNamespace(timestamp=now.isoformat(), value=6.8)
        mock_recorded = SimpleNamespace(items=[mock_item_1, mock_item_2])
        mock_client.stream.get_recorded.return_value = mock_recorded

        with patch.dict(sys.modules, {"pi_web_sdk": mock_pi}):
            from sporedb.connectors.osisoft_pi import OSIsoftPIConnector

            conn = OSIsoftPIConnector(config=sdk_config, engine=engine)
            conn.connect()
            result = conn.pull(
                "pi_test_batch",
                mapping,
                start_time="*-7d",
                end_time="*",
            )

            assert isinstance(result, PullResult)
            assert result.source_system == "osisoft_pi"
            # 2 points x 2 records each = 4 rows
            assert result.rows_imported == 4
            assert "pi_point_paths" in result.external_ids
            assert "pi:\\\\SERVER\\sinusoid" in result.external_ids["pi_point_paths"]

    def test_pull_httpx_returns_pull_result(self, httpx_config, engine, mapping):
        mock_httpx = _build_mock_httpx()
        mock_client = MagicMock()
        mock_httpx.Client.return_value = mock_client

        now = datetime.now(UTC)

        # Mock point lookup response
        point_resp = MagicMock()
        point_resp.json.return_value = {"WebId": "point_wid_1"}
        point_resp.raise_for_status = MagicMock()

        # Mock recorded values response
        stream_resp = MagicMock()
        stream_resp.json.return_value = {
            "Items": [
                {"Timestamp": now.isoformat(), "Value": 7.1},
                {"Timestamp": now.isoformat(), "Value": 6.8},
            ]
        }
        stream_resp.raise_for_status = MagicMock()

        def mock_get(url, **kwargs):
            if "streams" in url:
                return stream_resp
            return point_resp

        mock_client.get.side_effect = mock_get

        with patch.dict(sys.modules, {"httpx": mock_httpx}):
            from sporedb.connectors.osisoft_pi import OSIsoftPIConnector

            conn = OSIsoftPIConnector(config=httpx_config, engine=engine)
            conn.connect()
            result = conn.pull(
                "pi_test_batch_httpx",
                mapping,
                start_time="*-7d",
                end_time="*",
            )

            assert isinstance(result, PullResult)
            assert result.source_system == "osisoft_pi"
            assert result.rows_imported == 4

    def test_pull_empty_result(self, sdk_config, engine, mapping):
        mock_pi = _build_mock_pi_web_sdk()
        mock_client = MagicMock()
        mock_pi.PIWebAPIClient.return_value = mock_client

        # Mock point lookup
        mock_point = SimpleNamespace(web_id="point_wid_1")
        mock_client.point.get_by_path.return_value = mock_point

        # Mock empty recorded values
        mock_recorded = SimpleNamespace(items=[])
        mock_client.stream.get_recorded.return_value = mock_recorded

        with patch.dict(sys.modules, {"pi_web_sdk": mock_pi}):
            from sporedb.connectors.osisoft_pi import OSIsoftPIConnector

            conn = OSIsoftPIConnector(config=sdk_config, engine=engine)
            conn.connect()
            result = conn.pull("empty_batch", mapping)

            assert result.rows_imported == 0
            assert "No data retrieved from PI points" in result.warnings

    def test_pull_handles_point_failure(self, sdk_config, engine):
        mock_pi = _build_mock_pi_web_sdk()
        mock_client = MagicMock()
        mock_pi.PIWebAPIClient.return_value = mock_client

        # First point succeeds, second fails
        now = datetime.now(UTC)
        call_count = 0

        def mock_get_by_path(path):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return SimpleNamespace(web_id="wid_1")
            raise RuntimeError("Point not found")

        mock_client.point.get_by_path.side_effect = mock_get_by_path

        mock_recorded = SimpleNamespace(
            items=[SimpleNamespace(timestamp=now.isoformat(), value=7.0)]
        )
        mock_client.stream.get_recorded.return_value = mock_recorded

        single_mapping = SchemaMapping(
            timestamp_field="timestamp",
            variable_mappings=[
                FieldMapping(
                    source="pi:\\\\SERVER\\sinusoid",
                    target="dissolved_oxygen",
                    unit="mg/L",
                ),
                FieldMapping(
                    source="pi:\\\\SERVER\\broken_point",
                    target="bad_var",
                ),
            ],
        )

        with patch.dict(sys.modules, {"pi_web_sdk": mock_pi}):
            from sporedb.connectors.osisoft_pi import OSIsoftPIConnector

            conn = OSIsoftPIConnector(config=sdk_config, engine=engine)
            conn.connect()
            result = conn.pull("test_partial", single_mapping)

            # Only 1 point succeeded with 1 record
            assert result.rows_imported == 1
            assert any("Failed to pull PI point" in w for w in result.warnings)


# ---------------------------------------------------------------------------
# Test: Missing dependency
# ---------------------------------------------------------------------------


class TestMissingDependency:
    """Test that missing pi-web-sdk raises helpful errors."""

    def test_missing_pi_web_sdk(self, sdk_config, engine):
        with patch.dict(sys.modules, {"pi_web_sdk": None}):
            import importlib

            import sporedb.connectors.osisoft_pi as pi_mod

            importlib.reload(pi_mod)
            conn = pi_mod.OSIsoftPIConnector(config=sdk_config, engine=engine)

            with pytest.raises(ImportError, match="pi-web-sdk"):
                conn.connect()

    def test_missing_httpx_fallback(self, httpx_config, engine):
        with patch.dict(sys.modules, {"httpx": None}):
            import importlib

            import sporedb.connectors.osisoft_pi as pi_mod

            importlib.reload(pi_mod)
            conn = pi_mod.OSIsoftPIConnector(config=httpx_config, engine=engine)

            with pytest.raises(ImportError, match="httpx"):
                conn.connect()


# ---------------------------------------------------------------------------
# Test: Close
# ---------------------------------------------------------------------------


class TestClose:
    """Test connection cleanup."""

    def test_close_sdk_client(self, sdk_config, engine):
        mock_pi = _build_mock_pi_web_sdk()
        mock_client = MagicMock()
        mock_pi.PIWebAPIClient.return_value = mock_client

        with patch.dict(sys.modules, {"pi_web_sdk": mock_pi}):
            from sporedb.connectors.osisoft_pi import OSIsoftPIConnector

            conn = OSIsoftPIConnector(config=sdk_config, engine=engine)
            conn.connect()
            conn.close()

            mock_client.close.assert_called_once()
            assert conn._connected is False
            assert conn._client is None

    def test_close_httpx_client(self, httpx_config, engine):
        mock_httpx = _build_mock_httpx()
        mock_client = MagicMock()
        mock_httpx.Client.return_value = mock_client

        with patch.dict(sys.modules, {"httpx": mock_httpx}):
            from sporedb.connectors.osisoft_pi import OSIsoftPIConnector

            conn = OSIsoftPIConnector(config=httpx_config, engine=engine)
            conn.connect()
            conn.close()

            mock_client.close.assert_called_once()
            assert conn._connected is False

    def test_context_manager(self, sdk_config, engine):
        mock_pi = _build_mock_pi_web_sdk()
        mock_client = MagicMock()
        mock_pi.PIWebAPIClient.return_value = mock_client

        with patch.dict(sys.modules, {"pi_web_sdk": mock_pi}):
            from sporedb.connectors.osisoft_pi import OSIsoftPIConnector

            conn = OSIsoftPIConnector(config=sdk_config, engine=engine)
            with conn:
                assert conn._connected is True

            assert conn._connected is False
            mock_client.close.assert_called_once()
