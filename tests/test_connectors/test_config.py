"""Tests for connector config and schema mapping models."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from sporedb.connectors.config import (
    ConnectorConfig,
    FieldMapping,
    SchemaMapping,
    load_config,
    load_mapping,
)


class TestFieldMapping:
    """Validate FieldMapping model."""

    def test_basic_field_mapping(self):
        fm = FieldMapping(source="dissolved_oxygen", target="do")
        assert fm.source == "dissolved_oxygen"
        assert fm.target == "do"
        assert fm.unit is None
        assert fm.transform is None

    def test_field_mapping_with_unit_and_transform(self):
        fm = FieldMapping(
            source="temp_f",
            target="temperature",
            unit="fahrenheit",
            transform="offset:-32,multiply:0.5556",
        )
        assert fm.unit == "fahrenheit"
        assert fm.transform == "offset:-32,multiply:0.5556"

    def test_field_mapping_requires_source_and_target(self):
        with pytest.raises(ValidationError):
            FieldMapping(source="do")  # missing target


class TestSchemaMapping:
    """Validate SchemaMapping model."""

    def test_minimal_schema_mapping(self):
        sm = SchemaMapping(timestamp_field="_time")
        assert sm.timestamp_field == "_time"
        assert sm.variable_mappings == []
        assert sm.metadata_mappings == {}
        assert sm.external_id_field is None

    def test_full_schema_mapping(self):
        sm = SchemaMapping(
            timestamp_field="_time",
            variable_mappings=[
                FieldMapping(source="DO", target="dissolved_oxygen", unit="mg/L"),
                FieldMapping(source="pH", target="ph"),
            ],
            metadata_mappings={"reactor_id": "reactor_name", "strain": "strain"},
            external_id_field="sample_id",
        )
        assert len(sm.variable_mappings) == 2
        assert sm.variable_mappings[0].source == "DO"
        assert sm.metadata_mappings["reactor_id"] == "reactor_name"
        assert sm.external_id_field == "sample_id"

    def test_schema_mapping_requires_timestamp_field(self):
        with pytest.raises(ValidationError):
            SchemaMapping()  # missing timestamp_field


class TestConnectorConfig:
    """Validate ConnectorConfig model."""

    def test_minimal_config(self):
        cc = ConnectorConfig(
            connector_type="influxdb",
            host="localhost",
        )
        assert cc.connector_type == "influxdb"
        assert cc.host == "localhost"
        assert cc.port is None
        assert cc.auth == {}
        assert cc.ssl_verify is True
        assert cc.timeout_seconds == 30
        assert cc.extra == {}

    def test_full_config(self):
        cc = ConnectorConfig(
            connector_type="influxdb",
            host="influx.example.com",
            port=8086,
            auth={"token": "my-token", "org": "my-org"},
            ssl_verify=False,
            timeout_seconds=60,
            extra={"version": "2", "bucket": "bioprocess"},
        )
        assert cc.port == 8086
        assert cc.auth["token"] == "my-token"
        assert cc.ssl_verify is False
        assert cc.timeout_seconds == 60
        assert cc.extra["bucket"] == "bioprocess"

    def test_config_requires_connector_type_and_host(self):
        with pytest.raises(ValidationError):
            ConnectorConfig(connector_type="influxdb")  # missing host

        with pytest.raises(ValidationError):
            ConnectorConfig(host="localhost")  # missing connector_type


class TestLoadMapping:
    """Test YAML loading for schema mappings."""

    def test_load_mapping_from_yaml(self, tmp_path):
        yaml_content = """
timestamp_field: _time
variable_mappings:
  - source: DO
    target: dissolved_oxygen
    unit: mg/L
  - source: pH
    target: ph
metadata_mappings:
  reactor_id: reactor_name
external_id_field: sample_id
"""
        yaml_file = tmp_path / "mapping.yml"
        yaml_file.write_text(yaml_content)

        mapping = load_mapping(yaml_file)
        assert mapping.timestamp_field == "_time"
        assert len(mapping.variable_mappings) == 2
        assert mapping.variable_mappings[0].source == "DO"
        assert mapping.variable_mappings[0].unit == "mg/L"
        assert mapping.metadata_mappings["reactor_id"] == "reactor_name"
        assert mapping.external_id_field == "sample_id"

    def test_load_mapping_file_not_found(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_mapping(tmp_path / "nonexistent.yml")

    def test_load_mapping_invalid_yaml(self, tmp_path):
        yaml_file = tmp_path / "bad.yml"
        yaml_file.write_text("not_a_valid_mapping: true\n")
        with pytest.raises(ValidationError):
            load_mapping(yaml_file)

    def test_load_mapping_minimal(self, tmp_path):
        yaml_content = "timestamp_field: time\n"
        yaml_file = tmp_path / "minimal.yml"
        yaml_file.write_text(yaml_content)

        mapping = load_mapping(yaml_file)
        assert mapping.timestamp_field == "time"
        assert mapping.variable_mappings == []


class TestLoadConfig:
    """Test YAML loading for connector configs."""

    def test_load_config_from_yaml(self, tmp_path):
        yaml_content = """
connector_type: influxdb
host: influx.example.com
port: 8086
auth:
  token: my-secret-token
  org: my-org
ssl_verify: true
timeout_seconds: 45
extra:
  version: "2"
  bucket: bioprocess
"""
        yaml_file = tmp_path / "config.yml"
        yaml_file.write_text(yaml_content)

        config = load_config(yaml_file)
        assert config.connector_type == "influxdb"
        assert config.host == "influx.example.com"
        assert config.port == 8086
        assert config.auth["token"] == "my-secret-token"
        assert config.timeout_seconds == 45
        assert config.extra["bucket"] == "bioprocess"

    def test_load_config_file_not_found(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_config(tmp_path / "nonexistent.yml")
