"""Tests for BaseConnector abstract class."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest

from sporedb.connectors.base import BaseConnector
from sporedb.connectors.config import ConnectorConfig, SchemaMapping
from sporedb.connectors.result import PullResult
from sporedb.storage.engine import StorageEngine


class ConcreteConnector(BaseConnector):
    """Minimal concrete connector for testing the abstract base class."""

    def __init__(self, config: ConnectorConfig, engine: StorageEngine) -> None:
        super().__init__(config, engine)
        self.connect_called = False
        self.close_called = False

    def connect(self) -> None:
        self._connected = True
        self.connect_called = True

    def discover(self) -> list[dict[str, Any]]:
        return [{"name": "test_measurement", "type": "measurement"}]

    def pull(
        self,
        batch_name: str,
        mapping: SchemaMapping,
        **kwargs: Any,
    ) -> PullResult:
        return PullResult(
            batch_id=uuid4(),
            source_system="test",
            source_identifier="test_measurement",
            rows_imported=10,
            columns_mapped={"col_a": "variable_a"},
            external_ids={},
            warnings=[],
            elapsed_seconds=0.5,
        )

    def map_schema(self, mapping: SchemaMapping) -> SchemaMapping:
        return mapping

    def close(self) -> None:
        self.close_called = True
        super().close()


@pytest.fixture
def config() -> ConnectorConfig:
    return ConnectorConfig(
        connector_type="test",
        host="localhost",
        port=8086,
        auth={"token": "test-token"},
    )


@pytest.fixture
def engine(tmp_path) -> StorageEngine:
    return StorageEngine(data_root=tmp_path / "sporedb_data")


@pytest.fixture
def connector(config, engine) -> ConcreteConnector:
    return ConcreteConnector(config=config, engine=engine)


class TestBaseConnectorAbstract:
    """Verify that BaseConnector cannot be instantiated directly."""

    def test_cannot_instantiate_base_connector(self, config, engine):
        with pytest.raises(TypeError, match="abstract method"):
            BaseConnector(config=config, engine=engine)

    def test_abstract_methods_exist(self):
        abstract_methods = BaseConnector.__abstractmethods__
        assert "connect" in abstract_methods
        assert "discover" in abstract_methods
        assert "pull" in abstract_methods
        assert "map_schema" in abstract_methods


class TestConcreteConnector:
    """Verify that a concrete subclass works correctly."""

    def test_initial_state(self, connector):
        assert connector._connected is False
        assert connector.connect_called is False

    def test_connect_sets_connected(self, connector):
        connector.connect()
        assert connector._connected is True
        assert connector.connect_called is True

    def test_close_sets_disconnected(self, connector):
        connector.connect()
        assert connector._connected is True
        connector.close()
        assert connector._connected is False
        assert connector.close_called is True

    def test_discover_returns_list(self, connector):
        result = connector.discover()
        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]["name"] == "test_measurement"

    def test_pull_returns_pull_result(self, connector):
        mapping = SchemaMapping(timestamp_field="_time")
        result = connector.pull("test_batch", mapping)
        assert isinstance(result, PullResult)
        assert result.rows_imported == 10
        assert result.source_system == "test"

    def test_config_stored(self, connector, config):
        assert connector.config is config

    def test_engine_stored(self, connector, engine):
        assert connector.engine is engine


class TestContextManagerProtocol:
    """Verify that BaseConnector supports context manager usage."""

    def test_enter_calls_connect(self, connector):
        with connector as ctx:
            assert ctx is connector
            assert connector._connected is True
            assert connector.connect_called is True
        # __exit__ calls close
        assert connector._connected is False
        assert connector.close_called is True

    def test_exit_calls_close_on_exception(self, config, engine):
        class FailingConnector(ConcreteConnector):
            def discover(self) -> list[dict[str, Any]]:
                raise RuntimeError("discovery failed")

        conn = FailingConnector(config=config, engine=engine)
        with pytest.raises(RuntimeError, match="discovery failed"), conn:
            conn.discover()

        # close should still have been called
        assert conn._connected is False
        assert conn.close_called is True
