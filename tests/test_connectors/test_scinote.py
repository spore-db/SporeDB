"""Tests for SciNote ELN connector with mocked OAuth2 and API responses.

All tests use mocks -- no real SciNote instance required.
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from types import ModuleType
from typing import Any
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
def scinote_config() -> ConnectorConfig:
    return ConnectorConfig(
        connector_type="scinote",
        host="https://scinote.example.com",
        auth={
            "client_id": "my_client_id",
            "client_secret": "my_client_secret",
            "access_token": "tok_abc123",
            "refresh_token": "ref_xyz789",
        },
        extra={
            "team_id": "42",
            "project_id": "10",
            "experiment_id": "5",
        },
    )


@pytest.fixture
def mapping() -> SchemaMapping:
    return SchemaMapping(
        timestamp_field="created_at",
        variable_mappings=[
            FieldMapping(
                source="glucose_concentration",
                target="glucose_g_l",
                unit="g/L",
            ),
            FieldMapping(
                source="cell_count",
                target="viable_cells",
                unit="cells/mL",
            ),
        ],
    )


def _build_mock_authlib() -> tuple[ModuleType, MagicMock]:
    """Build a mock authlib module and return (module, mock_oauth2client_class)."""
    # Create the nested module structure
    authlib_mod = ModuleType("authlib")
    integrations_mod = ModuleType("authlib.integrations")
    httpx_client_mod = ModuleType("authlib.integrations.httpx_client")

    mock_oauth2_client_class = MagicMock()
    httpx_client_mod.OAuth2Client = mock_oauth2_client_class

    authlib_mod.integrations = integrations_mod
    integrations_mod.httpx_client = httpx_client_mod

    return authlib_mod, mock_oauth2_client_class


def _make_json_api_response(data: Any, status_code: int = 200) -> MagicMock:
    """Create a mock HTTP response in JSON:API format."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = {"data": data}
    resp.raise_for_status = MagicMock()
    if status_code >= 400:
        resp.raise_for_status.side_effect = Exception(f"HTTP {status_code}")
    return resp


# ---------------------------------------------------------------------------
# Test: Connect
# ---------------------------------------------------------------------------


class TestConnect:
    """Verify OAuth2 token setup."""

    def test_connect_creates_oauth2_client(self, scinote_config, engine):
        authlib_mod, mock_class = _build_mock_authlib()
        with patch.dict(
            sys.modules,
            {
                "authlib": authlib_mod,
                "authlib.integrations": authlib_mod.integrations,
                "authlib.integrations.httpx_client": (
                    authlib_mod.integrations.httpx_client
                ),
            },
        ):
            from sporedb.connectors.scinote import SciNoteELNConnector

            conn = SciNoteELNConnector(config=scinote_config, engine=engine)
            conn.connect()

            assert conn._connected is True
            mock_class.assert_called_once_with(
                client_id="my_client_id",
                client_secret="my_client_secret",
                token_endpoint="https://scinote.example.com/oauth/token",
                token={
                    "access_token": "tok_abc123",
                    "refresh_token": "ref_xyz789",
                    "token_type": "Bearer",
                },
            )


# ---------------------------------------------------------------------------
# Test: Discover
# ---------------------------------------------------------------------------


class TestDiscover:
    """Test discover() with JSON:API parsing."""

    def test_discover_lists_projects_and_experiments(self, scinote_config, engine):
        authlib_mod, mock_class = _build_mock_authlib()
        mock_client = MagicMock()
        mock_class.return_value = mock_client

        # Mock projects response (JSON:API format)
        projects_data = [
            {
                "id": "10",
                "type": "projects",
                "attributes": {"name": "Fermentation Study Alpha"},
            },
            {
                "id": "11",
                "type": "projects",
                "attributes": {"name": "Cell Culture Beta"},
            },
        ]

        # Mock experiments responses
        exp_data_10 = [
            {
                "id": "5",
                "type": "experiments",
                "attributes": {"name": "Run 001"},
            },
            {
                "id": "6",
                "type": "experiments",
                "attributes": {"name": "Run 002"},
            },
        ]
        exp_data_11 = [
            {
                "id": "7",
                "type": "experiments",
                "attributes": {"name": "Culture 001"},
            },
        ]

        def mock_get(url, **kwargs):
            if "/projects" in url and "/experiments" not in url:
                return _make_json_api_response(projects_data)
            elif "projects/10/experiments" in url:
                return _make_json_api_response(exp_data_10)
            elif "projects/11/experiments" in url:
                return _make_json_api_response(exp_data_11)
            return _make_json_api_response([])

        mock_client.get.side_effect = mock_get

        with patch.dict(
            sys.modules,
            {
                "authlib": authlib_mod,
                "authlib.integrations": authlib_mod.integrations,
                "authlib.integrations.httpx_client": (
                    authlib_mod.integrations.httpx_client
                ),
            },
        ):
            from sporedb.connectors.scinote import SciNoteELNConnector

            conn = SciNoteELNConnector(config=scinote_config, engine=engine)
            conn.connect()
            results = conn.discover()

            assert len(results) == 2
            assert results[0]["project_id"] == "10"
            assert results[0]["project_name"] == "Fermentation Study Alpha"
            assert len(results[0]["experiments"]) == 2
            assert results[0]["experiments"][0]["name"] == "Run 001"
            assert results[1]["project_id"] == "11"
            assert len(results[1]["experiments"]) == 1

    def test_discover_requires_team_id(self, engine):
        config_no_team = ConnectorConfig(
            connector_type="scinote",
            host="https://scinote.example.com",
            auth={
                "client_id": "cid",
                "client_secret": "csec",
                "access_token": "tok",
                "refresh_token": "ref",
            },
            extra={},  # No team_id
        )

        authlib_mod, mock_class = _build_mock_authlib()
        with patch.dict(
            sys.modules,
            {
                "authlib": authlib_mod,
                "authlib.integrations": authlib_mod.integrations,
                "authlib.integrations.httpx_client": (
                    authlib_mod.integrations.httpx_client
                ),
            },
        ):
            from sporedb.connectors.scinote import SciNoteELNConnector

            conn = SciNoteELNConnector(config=config_no_team, engine=engine)
            conn.connect()

            with pytest.raises(ValueError, match="team_id"):
                conn.discover()


# ---------------------------------------------------------------------------
# Test: Pull
# ---------------------------------------------------------------------------


class TestPull:
    """Test pull with mocked experiment/task/result data."""

    def test_pull_with_quantitative_results(self, scinote_config, engine, mapping):
        authlib_mod, mock_class = _build_mock_authlib()
        mock_client = MagicMock()
        mock_class.return_value = mock_client

        now = datetime.now(UTC)

        # Mock tasks response
        tasks_data = [
            {
                "id": "100",
                "type": "tasks",
                "attributes": {"name": "Measurement Protocol"},
            },
        ]

        # Mock results response
        results_data = [
            {
                "id": "200",
                "type": "results",
                "attributes": {
                    "name": "glucose_concentration",
                    "value": "12.5",
                    "created_at": now.isoformat(),
                    "unit": "g/L",
                },
                "_task_name": "Measurement Protocol",
            },
            {
                "id": "201",
                "type": "results",
                "attributes": {
                    "name": "cell_count",
                    "value": "1500000",
                    "created_at": now.isoformat(),
                    "unit": "cells/mL",
                },
                "_task_name": "Measurement Protocol",
            },
        ]

        # Mock experiment details
        exp_detail = {
            "id": "5",
            "type": "experiments",
            "attributes": {"name": "Run 001"},
        }

        def mock_get(url, **kwargs):
            if "/tasks" in url and "/results" in url:
                return _make_json_api_response(results_data)
            elif "/tasks" in url:
                return _make_json_api_response(tasks_data)
            elif "/experiments/5" in url and "/tasks" not in url:
                return _make_json_api_response(exp_detail)
            return _make_json_api_response([])

        mock_client.get.side_effect = mock_get

        with patch.dict(
            sys.modules,
            {
                "authlib": authlib_mod,
                "authlib.integrations": authlib_mod.integrations,
                "authlib.integrations.httpx_client": (
                    authlib_mod.integrations.httpx_client
                ),
            },
        ):
            from sporedb.connectors.scinote import SciNoteELNConnector

            conn = SciNoteELNConnector(config=scinote_config, engine=engine)
            conn.connect()
            result = conn.pull("eln_batch_001", mapping)

            assert isinstance(result, PullResult)
            assert result.source_system == "scinote"
            assert result.rows_imported == 2
            assert result.columns_mapped == {
                "glucose_concentration": "glucose_g_l",
                "cell_count": "viable_cells",
            }
            assert result.external_ids["eln_experiment_id"] == "5"
            assert result.external_ids["eln_project_id"] == "10"

    def test_pull_creates_batch_before_assay(self, scinote_config, engine, mapping):
        """Verify pull creates batch via BatchStore BEFORE AssayMeasurement objects."""
        authlib_mod, mock_class = _build_mock_authlib()
        mock_client = MagicMock()
        mock_class.return_value = mock_client

        now = datetime.now(UTC)

        tasks_data = [
            {
                "id": "100",
                "type": "tasks",
                "attributes": {"name": "Protocol 1"},
            },
        ]
        results_data = [
            {
                "id": "200",
                "type": "results",
                "attributes": {
                    "name": "glucose_concentration",
                    "value": "10.0",
                    "created_at": now.isoformat(),
                },
            },
        ]
        exp_detail = {
            "id": "5",
            "type": "experiments",
            "attributes": {"name": "Test Exp"},
        }

        def mock_get(url, **kwargs):
            if "/tasks" in url and "/results" in url:
                return _make_json_api_response(results_data)
            elif "/tasks" in url:
                return _make_json_api_response(tasks_data)
            elif "/experiments/5" in url and "/tasks" not in url:
                return _make_json_api_response(exp_detail)
            return _make_json_api_response([])

        mock_client.get.side_effect = mock_get

        with patch.dict(
            sys.modules,
            {
                "authlib": authlib_mod,
                "authlib.integrations": authlib_mod.integrations,
                "authlib.integrations.httpx_client": (
                    authlib_mod.integrations.httpx_client
                ),
            },
        ):
            from sporedb.connectors.scinote import SciNoteELNConnector

            conn = SciNoteELNConnector(config=scinote_config, engine=engine)
            conn.connect()
            result = conn.pull("batch_order_test", mapping)

            # Verify batch exists
            from sporedb.storage.batch_store import BatchStore

            batch_store = BatchStore(engine)
            batch = batch_store.get_batch(result.batch_id)
            assert batch is not None
            assert batch.name == "batch_order_test"

            # Verify assay data has correct batch_id
            from sporedb.storage.ts_store import TimeSeriesStore

            ts_store = TimeSeriesStore(engine)
            assay_df = ts_store.get_assay(result.batch_id)
            assert not assay_df.empty
            assert all(
                str(bid) == str(result.batch_id) for bid in assay_df["batch_id"].values
            )

    def test_pull_with_text_observations(self, scinote_config, engine, mapping):
        """Test that non-numeric results are stored as batch metadata."""
        authlib_mod, mock_class = _build_mock_authlib()
        mock_client = MagicMock()
        mock_class.return_value = mock_client

        now = datetime.now(UTC)

        tasks_data = [
            {
                "id": "100",
                "type": "tasks",
                "attributes": {"name": "Observation"},
            },
        ]
        results_data = [
            {
                "id": "200",
                "type": "results",
                "attributes": {
                    "name": "glucose_concentration",
                    "value": "12.5",
                    "created_at": now.isoformat(),
                },
            },
            {
                "id": "201",
                "type": "results",
                "attributes": {
                    "name": "color_observation",
                    "value": "light yellow, turbid",
                    "created_at": now.isoformat(),
                },
            },
        ]
        exp_detail = {
            "id": "5",
            "type": "experiments",
            "attributes": {"name": "Experiment"},
        }

        def mock_get(url, **kwargs):
            if "/tasks" in url and "/results" in url:
                return _make_json_api_response(results_data)
            elif "/tasks" in url:
                return _make_json_api_response(tasks_data)
            elif "/experiments/5" in url and "/tasks" not in url:
                return _make_json_api_response(exp_detail)
            return _make_json_api_response([])

        mock_client.get.side_effect = mock_get

        with patch.dict(
            sys.modules,
            {
                "authlib": authlib_mod,
                "authlib.integrations": authlib_mod.integrations,
                "authlib.integrations.httpx_client": (
                    authlib_mod.integrations.httpx_client
                ),
            },
        ):
            from sporedb.connectors.scinote import SciNoteELNConnector

            conn = SciNoteELNConnector(config=scinote_config, engine=engine)
            conn.connect()
            result = conn.pull("text_obs_batch", mapping)

            # Numeric result mapped
            assert result.rows_imported == 1
            assert "glucose_concentration" in result.columns_mapped

            # Text observation stored in batch metadata
            from sporedb.storage.batch_store import BatchStore

            batch_store = BatchStore(engine)
            batch = batch_store.get_batch(result.batch_id)
            assert batch is not None
            assert (
                batch.metadata.extra.get("color_observation") == "light yellow, turbid"
            )

    def test_pull_requires_ids(self, engine):
        config_no_ids = ConnectorConfig(
            connector_type="scinote",
            host="https://scinote.example.com",
            auth={
                "client_id": "cid",
                "client_secret": "csec",
                "access_token": "tok",
                "refresh_token": "ref",
            },
            extra={},  # No team/project/experiment IDs
        )
        authlib_mod, mock_class = _build_mock_authlib()

        with patch.dict(
            sys.modules,
            {
                "authlib": authlib_mod,
                "authlib.integrations": authlib_mod.integrations,
                "authlib.integrations.httpx_client": (
                    authlib_mod.integrations.httpx_client
                ),
            },
        ):
            from sporedb.connectors.scinote import SciNoteELNConnector

            conn = SciNoteELNConnector(config=config_no_ids, engine=engine)
            conn.connect()

            with pytest.raises(
                ValueError, match="team_id, project_id, and experiment_id"
            ):
                conn.pull("test", mapping)

    def test_pull_empty_experiment(self, scinote_config, engine, mapping):
        authlib_mod, mock_class = _build_mock_authlib()
        mock_client = MagicMock()
        mock_class.return_value = mock_client

        # No tasks or results
        exp_detail = {
            "id": "5",
            "type": "experiments",
            "attributes": {"name": "Empty Exp"},
        }

        def mock_get(url, **kwargs):
            if "/experiments/5" in url and "/tasks" not in url:
                return _make_json_api_response(exp_detail)
            return _make_json_api_response([])

        mock_client.get.side_effect = mock_get

        with patch.dict(
            sys.modules,
            {
                "authlib": authlib_mod,
                "authlib.integrations": authlib_mod.integrations,
                "authlib.integrations.httpx_client": (
                    authlib_mod.integrations.httpx_client
                ),
            },
        ):
            from sporedb.connectors.scinote import SciNoteELNConnector

            conn = SciNoteELNConnector(config=scinote_config, engine=engine)
            conn.connect()
            result = conn.pull("empty_eln_batch", mapping)

            assert result.rows_imported == 0
            assert result.batch_id is not None


# ---------------------------------------------------------------------------
# Test: Missing dependency
# ---------------------------------------------------------------------------


class TestMissingDependency:
    """Test that missing authlib raises helpful errors."""

    def test_missing_authlib(self, scinote_config, engine):
        with patch.dict(
            sys.modules,
            {
                "authlib": None,
                "authlib.integrations": None,
                "authlib.integrations.httpx_client": None,
            },
        ):
            import importlib

            import sporedb.connectors.scinote as scinote_mod

            importlib.reload(scinote_mod)
            conn = scinote_mod.SciNoteELNConnector(config=scinote_config, engine=engine)

            with pytest.raises(ImportError, match="authlib"):
                conn.connect()


# ---------------------------------------------------------------------------
# Test: Close
# ---------------------------------------------------------------------------


class TestClose:
    """Test connection cleanup."""

    def test_close_oauth2_client(self, scinote_config, engine):
        authlib_mod, mock_class = _build_mock_authlib()
        mock_client = MagicMock()
        mock_class.return_value = mock_client

        with patch.dict(
            sys.modules,
            {
                "authlib": authlib_mod,
                "authlib.integrations": authlib_mod.integrations,
                "authlib.integrations.httpx_client": (
                    authlib_mod.integrations.httpx_client
                ),
            },
        ):
            from sporedb.connectors.scinote import SciNoteELNConnector

            conn = SciNoteELNConnector(config=scinote_config, engine=engine)
            conn.connect()
            conn.close()

            mock_client.close.assert_called_once()
            assert conn._connected is False
            assert conn._client is None

    def test_context_manager(self, scinote_config, engine):
        authlib_mod, mock_class = _build_mock_authlib()
        mock_client = MagicMock()
        mock_class.return_value = mock_client

        with patch.dict(
            sys.modules,
            {
                "authlib": authlib_mod,
                "authlib.integrations": authlib_mod.integrations,
                "authlib.integrations.httpx_client": (
                    authlib_mod.integrations.httpx_client
                ),
            },
        ):
            from sporedb.connectors.scinote import SciNoteELNConnector

            conn = SciNoteELNConnector(config=scinote_config, engine=engine)
            with conn:
                assert conn._connected is True

            assert conn._connected is False
            mock_client.close.assert_called_once()
