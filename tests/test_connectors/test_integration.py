"""Integration tests for connector wiring.

Covers: registry, barrel exports, YAML mappings, CLI.
"""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest
from click.testing import CliRunner

from sporedb.cli import cli
from sporedb.connectors import (
    CONNECTOR_REGISTRY,
    BaseConnector,
    ConnectorConfig,
    FieldMapping,
    PullResult,
    SchemaMapping,
    load_mapping,
)
from sporedb.connectors.config import load_config

# ------------------------------------------------------------------ #
# CONNECTOR_REGISTRY tests
# ------------------------------------------------------------------ #


class TestConnectorRegistry:
    """Tests that CONNECTOR_REGISTRY is correctly populated."""

    def test_registry_is_dict(self):
        """CONNECTOR_REGISTRY is a dict."""
        assert isinstance(CONNECTOR_REGISTRY, dict)

    def test_registry_keys_are_strings(self):
        """All registry keys are connector type strings."""
        for key in CONNECTOR_REGISTRY:
            assert isinstance(key, str)

    def test_registry_values_are_base_connector_subclasses(self):
        """All registry values are BaseConnector subclasses."""
        for cls in CONNECTOR_REGISTRY.values():
            assert issubclass(cls, BaseConnector)

    def test_influxdb_in_registry(self):
        """InfluxDB connector is in the registry (dependencies available)."""
        # InfluxDBConnector only uses lazy imports inside methods,
        # so it should always be importable and registered
        assert "influxdb" in CONNECTOR_REGISTRY

    def test_osisoft_pi_in_registry(self):
        """OSIsoft PI connector is in the registry."""
        assert "osisoft_pi" in CONNECTOR_REGISTRY

    def test_labvantage_in_registry(self):
        """LabVantage connector is in the registry."""
        assert "labvantage" in CONNECTOR_REGISTRY

    def test_scinote_in_registry(self):
        """SciNote connector is in the registry."""
        assert "scinote" in CONNECTOR_REGISTRY

    def test_registry_dynamic_lookup(self):
        """Can dynamically instantiate connector from registry."""
        for _connector_type, cls in CONNECTOR_REGISTRY.items():
            assert callable(cls)
            # Verify it has the expected interface
            assert hasattr(cls, "connect")
            assert hasattr(cls, "discover")
            assert hasattr(cls, "pull")
            assert hasattr(cls, "map_schema")


# ------------------------------------------------------------------ #
# Barrel export tests
# ------------------------------------------------------------------ #


class TestBarrelExports:
    """Tests that all public names are importable from sporedb.connectors."""

    def test_base_connector_import(self):
        """BaseConnector is importable."""
        from sporedb.connectors import BaseConnector

        assert BaseConnector is not None

    def test_config_models_import(self):
        """ConnectorConfig, SchemaMapping, FieldMapping are importable."""
        from sporedb.connectors import ConnectorConfig, SchemaMapping

        assert ConnectorConfig is not None
        assert SchemaMapping is not None
        assert FieldMapping is not None

    def test_result_import(self):
        """PullResult is importable."""
        from sporedb.connectors import PullResult

        assert PullResult is not None

    def test_loaders_import(self):
        """load_mapping and load_config are importable."""
        from sporedb.connectors import load_config, load_mapping

        assert callable(load_mapping)
        assert callable(load_config)

    def test_registry_import(self):
        """CONNECTOR_REGISTRY is importable."""
        from sporedb.connectors import CONNECTOR_REGISTRY

        assert isinstance(CONNECTOR_REGISTRY, dict)


# ------------------------------------------------------------------ #
# Default YAML mapping files
# ------------------------------------------------------------------ #


_MAPPINGS_DIR = (
    Path(__file__).resolve().parent.parent.parent
    / "src"
    / "sporedb"
    / "connectors"
    / "mappings"
)


class TestDefaultMappings:
    """Tests that all default YAML mapping files load and validate."""

    @pytest.mark.parametrize(
        "filename,expected_ts_field",
        [
            ("influxdb_default.yml", "_time"),
            ("pi_default.yml", "timestamp"),
            ("labvantage_default.yml", "analysis_date"),
            ("scinote_default.yml", "created_at"),
        ],
    )
    def test_mapping_loads_and_validates(self, filename, expected_ts_field):
        """Default YAML mapping loads as a valid SchemaMapping."""
        mapping = load_mapping(_MAPPINGS_DIR / filename)
        assert isinstance(mapping, SchemaMapping)
        assert mapping.timestamp_field == expected_ts_field
        assert len(mapping.variable_mappings) > 0

    @pytest.mark.parametrize(
        "filename",
        [
            "influxdb_default.yml",
            "pi_default.yml",
            "labvantage_default.yml",
            "scinote_default.yml",
        ],
    )
    def test_mapping_variable_mappings_have_source_and_target(self, filename):
        """Each variable mapping has source and target fields."""
        mapping = load_mapping(_MAPPINGS_DIR / filename)
        for vm in mapping.variable_mappings:
            assert vm.source, f"Missing source in {filename}"
            assert vm.target, f"Missing target in {filename}"

    def test_labvantage_has_external_id_field(self):
        """labvantage_default.yml has external_id_field set."""
        mapping = load_mapping(_MAPPINGS_DIR / "labvantage_default.yml")
        assert mapping.external_id_field == "sample_id"

    def test_scinote_has_external_id_field(self):
        """scinote_default.yml has external_id_field set."""
        mapping = load_mapping(_MAPPINGS_DIR / "scinote_default.yml")
        assert mapping.external_id_field == "experiment_id"


# ------------------------------------------------------------------ #
# Config round-trip test
# ------------------------------------------------------------------ #


class TestConfigRoundTrip:
    """Tests config model creation and validation round-trip."""

    def test_connector_config_from_dict(self):
        """ConnectorConfig can be created from a dict."""
        data = {
            "connector_type": "influxdb",
            "host": "http://localhost:8086",
            "port": 8086,
            "auth": {"token": "my-token", "org": "my-org"},
            "extra": {"bucket": "bioreactor", "version": "2"},
        }
        config = ConnectorConfig.model_validate(data)
        assert config.connector_type == "influxdb"
        assert config.host == "http://localhost:8086"
        assert config.auth["token"] == "my-token"
        assert config.extra["bucket"] == "bioreactor"

    def test_schema_mapping_from_dict(self):
        """SchemaMapping can be created from a dict (mimicking YAML load)."""
        data = {
            "timestamp_field": "_time",
            "variable_mappings": [
                {"source": "DO", "target": "dissolved_oxygen", "unit": "%"},
                {"source": "PH", "target": "ph"},
            ],
            "metadata_mappings": {"reactor_id": "bioreactor_id"},
        }
        mapping = SchemaMapping.model_validate(data)
        assert mapping.timestamp_field == "_time"
        assert len(mapping.variable_mappings) == 2
        assert mapping.variable_mappings[0].unit == "%"

    def test_pull_result_creation(self):
        """PullResult can be created with typical connector output."""
        result = PullResult(
            batch_id=uuid4(),
            source_system="influxdb",
            source_identifier="bioreactor_data",
            rows_imported=100,
            columns_mapped={"DO": "dissolved_oxygen", "PH": "ph"},
            external_ids={"reactor_id": "R-001"},
            warnings=["Field 'unused_field' not found"],
            elapsed_seconds=2.5,
        )
        assert result.rows_imported == 100
        assert result.source_system == "influxdb"
        assert len(result.warnings) == 1

    def test_config_to_yaml_roundtrip(self, tmp_path):
        """ConnectorConfig can be saved and loaded via YAML."""
        import yaml

        config = ConnectorConfig(
            connector_type="osisoft_pi",
            host="https://pi.example.com",
            auth={"username": "admin", "password": "secret"},
            ssl_verify=True,
        )

        yaml_path = tmp_path / "config.yml"
        with open(yaml_path, "w") as f:
            yaml.dump(config.model_dump(), f)

        loaded = load_config(yaml_path)
        assert loaded.connector_type == "osisoft_pi"
        assert loaded.host == "https://pi.example.com"
        assert loaded.auth["username"] == "admin"


# ------------------------------------------------------------------ #
# CLI-to-connector wiring
# ------------------------------------------------------------------ #


class TestCLIToConnectorWiring:
    """Tests that CLI pull commands wire through to connectors correctly."""

    def test_pull_influxdb_invokable(self):
        """sporedb pull influxdb is a registered CLI command."""
        runner = CliRunner()
        result = runner.invoke(cli, ["pull", "influxdb", "--help"])
        assert result.exit_code == 0
        assert "InfluxDB" in result.output

    def test_pull_pi_invokable(self):
        """sporedb pull pi is a registered CLI command."""
        runner = CliRunner()
        result = runner.invoke(cli, ["pull", "pi", "--help"])
        assert result.exit_code == 0
        assert "OSIsoft" in result.output or "PI" in result.output

    def test_pull_labvantage_invokable(self):
        """sporedb pull labvantage is a registered CLI command."""
        runner = CliRunner()
        result = runner.invoke(cli, ["pull", "labvantage", "--help"])
        assert result.exit_code == 0
        assert "LabVantage" in result.output

    def test_pull_scinote_invokable(self):
        """sporedb pull scinote is a registered CLI command."""
        runner = CliRunner()
        result = runner.invoke(cli, ["pull", "scinote", "--help"])
        assert result.exit_code == 0
        assert "SciNote" in result.output

    def test_all_pull_subcommands_in_group(self):
        """All four connector subcommands appear in pull group help."""
        runner = CliRunner()
        result = runner.invoke(cli, ["pull", "--help"])
        assert result.exit_code == 0
        for name in ["influxdb", "pi", "labvantage", "scinote"]:
            assert name in result.output


# ------------------------------------------------------------------ #
# Pyproject.toml extras verification
# ------------------------------------------------------------------ #


class TestPyprojectExtras:
    """Tests that pyproject.toml has the correct [connectors] extra."""

    def test_connectors_extra_exists(self):
        """pyproject.toml has [connectors] optional dependency group."""
        import tomllib

        pyproject_path = (
            Path(__file__).resolve().parent.parent.parent / "pyproject.toml"
        )
        with open(pyproject_path, "rb") as f:
            data = tomllib.load(f)
        optional_deps = data["project"]["optional-dependencies"]
        assert "connectors" in optional_deps

    def test_connectors_extra_has_required_packages(self):
        """[connectors] extra includes required packages (pi-web-sdk -> [osisoft])."""
        import tomllib

        pyproject_path = (
            Path(__file__).resolve().parent.parent.parent / "pyproject.toml"
        )
        with open(pyproject_path, "rb") as f:
            data = tomllib.load(f)
        connectors_deps = data["project"]["optional-dependencies"]["connectors"]
        deps_str = " ".join(connectors_deps).lower()
        assert "influxdb-client" in deps_str
        assert "influxdb>" in deps_str  # influxdb>=5.3.0
        assert "pyyaml" in deps_str
        assert "authlib" in deps_str
        assert "httpx" in deps_str
        # pi-web-sdk is proprietary — isolated in [osisoft] extra
        osisoft_deps = data["project"]["optional-dependencies"].get("osisoft", [])
        osisoft_str = " ".join(osisoft_deps).lower()
        assert "pi-web-sdk" in osisoft_str

    def test_all_extra_exists(self):
        """pyproject.toml has [all] convenience extra."""
        import tomllib

        pyproject_path = (
            Path(__file__).resolve().parent.parent.parent / "pyproject.toml"
        )
        with open(pyproject_path, "rb") as f:
            data = tomllib.load(f)
        optional_deps = data["project"]["optional-dependencies"]
        assert "all" in optional_deps
        all_deps = " ".join(optional_deps["all"]).lower()
        assert "connectors" in all_deps
        assert "cloud" in all_deps
        assert "viz" in all_deps
        assert "dev" in all_deps
