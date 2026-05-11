"""Tests for InfluxDB connector with mocked clients.

All tests mock the influxdb and influxdb-client libraries to avoid
requiring a running InfluxDB instance.
"""

from __future__ import annotations

import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import MagicMock, patch

import pandas as pd
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
def v2_config() -> ConnectorConfig:
    return ConnectorConfig(
        connector_type="influxdb",
        host="http://localhost:8086",
        auth={"token": "my-test-token", "org": "my-org"},
        extra={"version": "2", "bucket": "bioprocess"},
    )


@pytest.fixture
def v1_config() -> ConnectorConfig:
    return ConnectorConfig(
        connector_type="influxdb",
        host="localhost",
        port=8086,
        auth={"username": "admin", "password": "secret"},
        extra={"version": "1", "database": "bioreactor"},
    )


@pytest.fixture
def auto_config() -> ConnectorConfig:
    return ConnectorConfig(
        connector_type="influxdb",
        host="http://localhost:8086",
        auth={"token": "my-test-token", "org": "my-org"},
        extra={"version": "auto", "bucket": "bioprocess"},
    )


@pytest.fixture
def mapping() -> SchemaMapping:
    return SchemaMapping(
        timestamp_field="_time",
        variable_mappings=[
            FieldMapping(source="DO", target="dissolved_oxygen", unit="mg/L"),
            FieldMapping(source="pH", target="ph"),
        ],
        metadata_mappings={},
        external_id_field=None,
    )


def _build_mock_v2_module() -> ModuleType:
    """Build a mock influxdb_client module."""
    mod = ModuleType("influxdb_client")
    mock_client_class = MagicMock()
    mod.InfluxDBClient = mock_client_class
    return mod


def _build_mock_v1_module() -> ModuleType:
    """Build a mock influxdb module."""
    mod = ModuleType("influxdb")
    mock_client_class = MagicMock()
    mod.InfluxDBClient = mock_client_class
    return mod


# ---------------------------------------------------------------------------
# Test: V2 connect path
# ---------------------------------------------------------------------------


class TestInfluxDBV2Connect:
    """Verify v2 connection using influxdb-client."""

    def test_v2_connect_creates_client(self, v2_config, engine):
        mock_v2 = _build_mock_v2_module()
        with patch.dict(sys.modules, {"influxdb_client": mock_v2}):
            from sporedb.connectors.influxdb import InfluxDBConnector

            conn = InfluxDBConnector(config=v2_config, engine=engine)
            conn.connect()

            assert conn._connected is True
            assert conn._version == "2"
            mock_v2.InfluxDBClient.assert_called_once_with(
                url="http://localhost:8086",
                token="my-test-token",
                org="my-org",
                timeout=30000,
                verify_ssl=True,
            )

    def test_v2_connect_with_port(self, engine):
        config = ConnectorConfig(
            connector_type="influxdb",
            host="http://influx.example.com",
            port=9999,
            auth={"token": "tok", "org": "org"},
            extra={"version": "2", "bucket": "b"},
        )
        mock_v2 = _build_mock_v2_module()
        with patch.dict(sys.modules, {"influxdb_client": mock_v2}):
            from sporedb.connectors.influxdb import InfluxDBConnector

            conn = InfluxDBConnector(config=config, engine=engine)
            conn.connect()

            # Port should be appended to host
            call_kwargs = mock_v2.InfluxDBClient.call_args[1]
            assert call_kwargs["url"] == "http://influx.example.com:9999"


# ---------------------------------------------------------------------------
# Test: V1 connect path
# ---------------------------------------------------------------------------


class TestInfluxDBV1Connect:
    """Verify v1 connection using influxdb."""

    def test_v1_connect_creates_client(self, v1_config, engine):
        mock_v1 = _build_mock_v1_module()
        with patch.dict(sys.modules, {"influxdb": mock_v1}):
            from sporedb.connectors.influxdb import InfluxDBConnector

            conn = InfluxDBConnector(config=v1_config, engine=engine)
            conn.connect()

            assert conn._connected is True
            assert conn._version == "1"
            mock_v1.InfluxDBClient.assert_called_once_with(
                host="localhost",
                port=8086,
                username="admin",
                password="secret",
                database="bioreactor",
                ssl=False,
                verify_ssl=True,
                timeout=30,
            )

    def test_v1_strips_protocol_prefix(self, engine):
        config = ConnectorConfig(
            connector_type="influxdb",
            host="http://myhost",
            port=8086,
            auth={"username": "u", "password": "p"},
            extra={"version": "1", "database": "db"},
        )
        mock_v1 = _build_mock_v1_module()
        with patch.dict(sys.modules, {"influxdb": mock_v1}):
            from sporedb.connectors.influxdb import InfluxDBConnector

            conn = InfluxDBConnector(config=config, engine=engine)
            conn.connect()

            call_kwargs = mock_v1.InfluxDBClient.call_args[1]
            assert call_kwargs["host"] == "myhost"


# ---------------------------------------------------------------------------
# Test: Auto-detect logic
# ---------------------------------------------------------------------------


class TestAutoDetect:
    """Test auto-detect: v2 health check -> fallback to v1."""

    def test_auto_detect_v2_success(self, auto_config, engine):
        mock_v2 = _build_mock_v2_module()
        # Configure health check to pass
        mock_client = MagicMock()
        health_result = SimpleNamespace(status="pass")
        mock_client.health.return_value = health_result
        mock_v2.InfluxDBClient.return_value = mock_client

        with patch.dict(sys.modules, {"influxdb_client": mock_v2}):
            from sporedb.connectors.influxdb import InfluxDBConnector

            conn = InfluxDBConnector(config=auto_config, engine=engine)
            conn.connect()

            assert conn._version == "2"
            assert conn._connected is True

    def test_auto_detect_fallback_to_v1(self, auto_config, engine):
        mock_v2 = _build_mock_v2_module()
        mock_v1 = _build_mock_v1_module()

        # Configure v2 health check to fail
        mock_v2_client = MagicMock()
        mock_v2_client.health.side_effect = ConnectionError("v2 unavailable")
        mock_v2.InfluxDBClient.return_value = mock_v2_client

        with patch.dict(
            sys.modules,
            {"influxdb_client": mock_v2, "influxdb": mock_v1},
        ):
            from sporedb.connectors.influxdb import InfluxDBConnector

            conn = InfluxDBConnector(config=auto_config, engine=engine)
            conn.connect()

            assert conn._version == "1"
            assert conn._connected is True
            # v2 client should have been closed after failure
            mock_v2_client.close.assert_called_once()

    def test_auto_detect_v2_health_not_pass(self, auto_config, engine):
        mock_v2 = _build_mock_v2_module()
        mock_v1 = _build_mock_v1_module()

        # Configure v2 health check to return non-pass status
        mock_v2_client = MagicMock()
        health_result = SimpleNamespace(status="fail")
        mock_v2_client.health.return_value = health_result
        mock_v2.InfluxDBClient.return_value = mock_v2_client

        with patch.dict(
            sys.modules,
            {"influxdb_client": mock_v2, "influxdb": mock_v1},
        ):
            from sporedb.connectors.influxdb import InfluxDBConnector

            conn = InfluxDBConnector(config=auto_config, engine=engine)
            conn.connect()

            # Should fall back to v1
            assert conn._version == "1"


# ---------------------------------------------------------------------------
# Test: Discover
# ---------------------------------------------------------------------------


class TestDiscover:
    """Test discover() for both v1 and v2."""

    def test_discover_v2(self, v2_config, engine):
        mock_v2 = _build_mock_v2_module()
        mock_client = MagicMock()
        mock_v2.InfluxDBClient.return_value = mock_client

        # Mock query_api response
        mock_record = MagicMock()
        mock_record.get_value.return_value = "bioreactor_data"
        mock_table = MagicMock()
        mock_table.records = [mock_record]
        mock_client.query_api.return_value.query.return_value = [mock_table]

        with patch.dict(sys.modules, {"influxdb_client": mock_v2}):
            from sporedb.connectors.influxdb import InfluxDBConnector

            conn = InfluxDBConnector(config=v2_config, engine=engine)
            conn.connect()
            results = conn.discover()

            assert len(results) == 1
            assert results[0]["name"] == "bioreactor_data"
            assert results[0]["type"] == "measurement"

    def test_discover_v1(self, v1_config, engine):
        mock_v1 = _build_mock_v1_module()
        mock_client = MagicMock()
        mock_v1.InfluxDBClient.return_value = mock_client

        # Mock SHOW MEASUREMENTS response
        meas_result = MagicMock()
        meas_result.get_points.return_value = [{"name": "reactor_1"}]

        # Mock SHOW FIELD KEYS response
        field_result = MagicMock()
        field_result.get_points.return_value = [
            {"fieldKey": "DO", "fieldType": "float"},
            {"fieldKey": "pH", "fieldType": "float"},
        ]

        # Mock SHOW TAG KEYS response
        tag_result = MagicMock()
        tag_result.get_points.return_value = [
            {"tagKey": "reactor_id"},
        ]

        def mock_query(q):
            if "SHOW MEASUREMENTS" in q:
                return meas_result
            elif "SHOW FIELD KEYS" in q:
                return field_result
            elif "SHOW TAG KEYS" in q:
                return tag_result
            return MagicMock(get_points=lambda: [])

        mock_client.query.side_effect = mock_query

        with patch.dict(sys.modules, {"influxdb": mock_v1}):
            from sporedb.connectors.influxdb import InfluxDBConnector

            conn = InfluxDBConnector(config=v1_config, engine=engine)
            conn.connect()
            results = conn.discover()

            # 1 measurement + 2 fields + 1 tag = 4
            assert len(results) == 4
            measurement_names = [
                r["name"] for r in results if r["type"] == "measurement"
            ]
            assert "reactor_1" in measurement_names
            field_names = [r["name"] for r in results if r["type"] == "field"]
            assert "reactor_1.DO" in field_names
            assert "reactor_1.pH" in field_names


# ---------------------------------------------------------------------------
# Test: Pull
# ---------------------------------------------------------------------------


class TestPull:
    """Test pull() with mocked query responses."""

    def test_pull_v2_returns_pull_result(self, v2_config, engine, mapping):
        mock_v2 = _build_mock_v2_module()
        mock_client = MagicMock()
        mock_v2.InfluxDBClient.return_value = mock_client

        # Create mock DataFrame response
        df = pd.DataFrame(
            {
                "_time": pd.to_datetime(
                    [
                        "2025-01-01T00:00:00Z",
                        "2025-01-01T01:00:00Z",
                        "2025-01-01T02:00:00Z",
                    ]
                ),
                "DO": [7.1, 6.8, 6.5],
                "pH": [7.0, 6.9, 6.8],
            }
        )
        mock_client.query_api.return_value.query_data_frame.return_value = df

        with patch.dict(sys.modules, {"influxdb_client": mock_v2}):
            from sporedb.connectors.influxdb import InfluxDBConnector

            conn = InfluxDBConnector(config=v2_config, engine=engine)
            conn.connect()
            result = conn.pull("test_batch", mapping, measurement="bioreactor_data")

            assert isinstance(result, PullResult)
            assert result.source_system == "influxdb"
            assert result.source_identifier == "bioreactor_data"
            # 3 rows x 2 variables = 6 telemetry records
            assert result.rows_imported == 6
            assert result.columns_mapped == {
                "DO": "dissolved_oxygen",
                "pH": "ph",
            }

    def test_pull_v1_returns_pull_result(self, v1_config, engine, mapping):
        mock_v1 = _build_mock_v1_module()
        mock_client = MagicMock()
        mock_v1.InfluxDBClient.return_value = mock_client

        # Create mock InfluxQL response
        mock_result = MagicMock()
        mock_result.get_points.return_value = [
            {"time": "2025-01-01T00:00:00Z", "DO": 7.1, "pH": 7.0},
            {"time": "2025-01-01T01:00:00Z", "DO": 6.8, "pH": 6.9},
        ]
        mock_client.query.return_value = mock_result

        # Change mapping timestamp_field to match v1's "time" column
        v1_mapping = SchemaMapping(
            timestamp_field="time",
            variable_mappings=[
                FieldMapping(source="DO", target="dissolved_oxygen", unit="mg/L"),
                FieldMapping(source="pH", target="ph"),
            ],
        )

        with patch.dict(sys.modules, {"influxdb": mock_v1}):
            from sporedb.connectors.influxdb import InfluxDBConnector

            conn = InfluxDBConnector(config=v1_config, engine=engine)
            conn.connect()
            result = conn.pull(
                "test_batch_v1", v1_mapping, measurement="bioreactor_data"
            )

            assert isinstance(result, PullResult)
            assert result.source_system == "influxdb"
            # 2 rows x 2 variables = 4
            assert result.rows_imported == 4

    def test_pull_empty_result(self, v2_config, engine, mapping):
        mock_v2 = _build_mock_v2_module()
        mock_client = MagicMock()
        mock_v2.InfluxDBClient.return_value = mock_client

        # Return empty DataFrame
        mock_client.query_api.return_value.query_data_frame.return_value = (
            pd.DataFrame()
        )

        with patch.dict(sys.modules, {"influxdb_client": mock_v2}):
            from sporedb.connectors.influxdb import InfluxDBConnector

            conn = InfluxDBConnector(config=v2_config, engine=engine)
            conn.connect()
            result = conn.pull("empty_batch", mapping, measurement="no_data")

            assert result.rows_imported == 0
            assert "Query returned no data" in result.warnings

    def test_pull_missing_source_field(self, v2_config, engine):
        mock_v2 = _build_mock_v2_module()
        mock_client = MagicMock()
        mock_v2.InfluxDBClient.return_value = mock_client

        # DataFrame missing one of the mapped fields
        df = pd.DataFrame(
            {
                "_time": pd.to_datetime(["2025-01-01T00:00:00Z"]),
                "DO": [7.1],
                # "pH" is missing
            }
        )
        mock_client.query_api.return_value.query_data_frame.return_value = df

        mapping_with_missing = SchemaMapping(
            timestamp_field="_time",
            variable_mappings=[
                FieldMapping(source="DO", target="dissolved_oxygen"),
                FieldMapping(source="pH", target="ph"),
            ],
        )

        with patch.dict(sys.modules, {"influxdb_client": mock_v2}):
            from sporedb.connectors.influxdb import InfluxDBConnector

            conn = InfluxDBConnector(config=v2_config, engine=engine)
            conn.connect()
            result = conn.pull("test", mapping_with_missing, measurement="test_meas")

            assert "Source field 'pH' not found in query results" in result.warnings
            assert result.columns_mapped == {"DO": "dissolved_oxygen"}

    def test_pull_requires_measurement(self, v2_config, engine, mapping):
        mock_v2 = _build_mock_v2_module()
        mock_client = MagicMock()
        mock_v2.InfluxDBClient.return_value = mock_client

        with patch.dict(sys.modules, {"influxdb_client": mock_v2}):
            from sporedb.connectors.influxdb import InfluxDBConnector

            conn = InfluxDBConnector(config=v2_config, engine=engine)
            conn.connect()

            with pytest.raises(ValueError, match="measurement"):
                conn.pull("test", mapping)


# ---------------------------------------------------------------------------
# Test: Missing dependency
# ---------------------------------------------------------------------------


class TestMissingDependency:
    """Test that missing influxdb libraries raise helpful errors."""

    def test_missing_v2_dependency(self, v2_config, engine):
        # Temporarily remove influxdb_client from modules
        with patch.dict(
            sys.modules,
            {"influxdb_client": None},
        ):
            # Force re-import by clearing module from cache
            import importlib

            import sporedb.connectors.influxdb as influx_mod

            importlib.reload(influx_mod)
            conn = influx_mod.InfluxDBConnector(config=v2_config, engine=engine)

            with pytest.raises(ImportError, match="influxdb-client"):
                conn.connect()

    def test_missing_v1_dependency(self, v1_config, engine):
        with patch.dict(sys.modules, {"influxdb": None}):
            import importlib

            import sporedb.connectors.influxdb as influx_mod

            importlib.reload(influx_mod)
            conn = influx_mod.InfluxDBConnector(config=v1_config, engine=engine)

            with pytest.raises(ImportError, match="influxdb"):
                conn.connect()


# ---------------------------------------------------------------------------
# Test: Close
# ---------------------------------------------------------------------------


class TestClose:
    """Test connection cleanup."""

    def test_close_calls_client_close(self, v2_config, engine):
        mock_v2 = _build_mock_v2_module()
        mock_client = MagicMock()
        mock_v2.InfluxDBClient.return_value = mock_client

        with patch.dict(sys.modules, {"influxdb_client": mock_v2}):
            from sporedb.connectors.influxdb import InfluxDBConnector

            conn = InfluxDBConnector(config=v2_config, engine=engine)
            conn.connect()
            conn.close()

            mock_client.close.assert_called_once()
            assert conn._connected is False
            assert conn._client is None

    def test_close_without_connect(self, v2_config, engine):
        mock_v2 = _build_mock_v2_module()
        with patch.dict(sys.modules, {"influxdb_client": mock_v2}):
            from sporedb.connectors.influxdb import InfluxDBConnector

            conn = InfluxDBConnector(config=v2_config, engine=engine)
            # Should not raise
            conn.close()
            assert conn._connected is False

    def test_context_manager(self, v2_config, engine):
        mock_v2 = _build_mock_v2_module()
        mock_client = MagicMock()
        mock_v2.InfluxDBClient.return_value = mock_client

        with patch.dict(sys.modules, {"influxdb_client": mock_v2}):
            from sporedb.connectors.influxdb import InfluxDBConnector

            conn = InfluxDBConnector(config=v2_config, engine=engine)
            with conn:
                assert conn._connected is True

            assert conn._connected is False
            mock_client.close.assert_called_once()


# ---------------------------------------------------------------------------
# Test: Flux / InfluxQL injection prevention (CR-01, CR-02)
# ---------------------------------------------------------------------------


class TestFluxInjection:
    """CR-01: Flux query injection prevention."""

    def test_measurement_with_quote_rejected(self, v2_config, engine, mapping):
        """Measurement containing double-quote is rejected."""
        mock_v2 = _build_mock_v2_module()
        mock_client = MagicMock()
        mock_v2.InfluxDBClient.return_value = mock_client

        with patch.dict(sys.modules, {"influxdb_client": mock_v2}):
            from sporedb.connectors.influxdb import InfluxDBConnector

            conn = InfluxDBConnector(config=v2_config, engine=engine)
            conn.connect()

            with pytest.raises(ValueError, match="Unsafe characters in measurement"):
                conn.pull(
                    "test",
                    mapping,
                    measurement='") |> drop(fn: (r) => true) //',
                )

    def test_measurement_with_pipe_rejected(self, v2_config, engine, mapping):
        """Measurement containing |> is rejected."""
        mock_v2 = _build_mock_v2_module()
        mock_client = MagicMock()
        mock_v2.InfluxDBClient.return_value = mock_client

        with patch.dict(sys.modules, {"influxdb_client": mock_v2}):
            from sporedb.connectors.influxdb import InfluxDBConnector

            conn = InfluxDBConnector(config=v2_config, engine=engine)
            conn.connect()

            with pytest.raises(ValueError, match="Unsafe characters in measurement"):
                conn.pull(
                    "test",
                    mapping,
                    measurement="foo |> evil",
                )

    def test_valid_measurement_passes(self, v2_config, engine, mapping):
        """Valid measurement name passes through to query."""
        mock_v2 = _build_mock_v2_module()
        mock_client = MagicMock()
        mock_v2.InfluxDBClient.return_value = mock_client
        mock_client.query_api.return_value.query_data_frame.return_value = (
            pd.DataFrame()
        )

        with patch.dict(sys.modules, {"influxdb_client": mock_v2}):
            from sporedb.connectors.influxdb import InfluxDBConnector

            conn = InfluxDBConnector(config=v2_config, engine=engine)
            conn.connect()

            # Should not raise
            result = conn.pull("test", mapping, measurement="temperature")
            assert result.rows_imported == 0


class TestInfluxQLInjection:
    """CR-02: InfluxQL query injection prevention."""

    def test_time_range_injection_rejected(self, v1_config, engine, mapping):
        """time_range with SQL injection payload is rejected."""
        mock_v1 = _build_mock_v1_module()
        mock_client = MagicMock()
        mock_v1.InfluxDBClient.return_value = mock_client

        with patch.dict(sys.modules, {"influxdb": mock_v1}):
            from sporedb.connectors.influxdb import InfluxDBConnector

            conn = InfluxDBConnector(config=v1_config, engine=engine)
            conn.connect()

            with pytest.raises(ValueError, match="Invalid time range format"):
                conn.pull(
                    "test",
                    mapping,
                    measurement="temperature",
                    start="30d; DROP MEASUREMENT foo",
                )

    def test_valid_time_range_passes(self, v1_config, engine):
        """Valid time ranges pass through."""
        mock_v1 = _build_mock_v1_module()
        mock_client = MagicMock()
        mock_v1.InfluxDBClient.return_value = mock_client

        # Return empty result
        mock_result = MagicMock()
        mock_result.get_points.return_value = []
        mock_client.query.return_value = mock_result

        v1_mapping = SchemaMapping(
            timestamp_field="time",
            variable_mappings=[
                FieldMapping(source="DO", target="dissolved_oxygen", unit="mg/L"),
            ],
        )

        with patch.dict(sys.modules, {"influxdb": mock_v1}):
            from sporedb.connectors.influxdb import InfluxDBConnector

            conn = InfluxDBConnector(config=v1_config, engine=engine)
            conn.connect()

            # Should not raise for valid durations
            result = conn.pull(
                "test", v1_mapping, measurement="temperature", start="30d"
            )
            assert result.rows_imported == 0

    def test_valid_time_range_hours(self, v1_config, engine):
        """time_range with hours passes."""
        mock_v1 = _build_mock_v1_module()
        mock_client = MagicMock()
        mock_v1.InfluxDBClient.return_value = mock_client

        mock_result = MagicMock()
        mock_result.get_points.return_value = []
        mock_client.query.return_value = mock_result

        v1_mapping = SchemaMapping(
            timestamp_field="time",
            variable_mappings=[
                FieldMapping(source="DO", target="dissolved_oxygen", unit="mg/L"),
            ],
        )

        with patch.dict(sys.modules, {"influxdb": mock_v1}):
            from sporedb.connectors.influxdb import InfluxDBConnector

            conn = InfluxDBConnector(config=v1_config, engine=engine)
            conn.connect()

            result = conn.pull(
                "test", v1_mapping, measurement="temperature", start="12h"
            )
            assert result.rows_imported == 0
