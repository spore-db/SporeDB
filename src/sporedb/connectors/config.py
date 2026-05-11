"""Pydantic models for connector configuration and YAML schema mapping."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

import yaml
from pydantic import BaseModel, Field, field_validator


class FieldMapping(BaseModel):
    """Maps one external field to a SporeDB variable."""

    source: str  # External field name (tag, point, column)
    target: str  # SporeDB variable name (e.g., "dissolved_oxygen")
    unit: str | None = None  # Source unit (for conversion)
    transform: str | None = None  # Optional: "multiply:1000", "offset:-273.15"


class SchemaMapping(BaseModel):
    """Complete mapping from external system to SporeDB batch schema."""

    timestamp_field: str  # External timestamp field
    variable_mappings: list[FieldMapping] = Field(default_factory=list)
    metadata_mappings: dict[str, str] = Field(
        default_factory=dict
    )  # e.g. {"reactor_id": "strain"}
    external_id_field: str | None = None  # Field for lims_sample_id / eln_experiment_id


class ConnectorConfig(BaseModel):
    """Base configuration for any connector."""

    connector_type: str  # "influxdb", "osisoft_pi", "labvantage", "scinote"
    host: str
    port: int | None = None

    @field_validator("host")
    @classmethod
    def validate_host_scheme(cls, v: str) -> str:
        parsed = urlparse(v)
        if parsed.scheme and parsed.scheme not in ("http", "https"):
            raise ValueError(f"Unsupported URL scheme: {parsed.scheme}")
        return v

    auth: dict[str, str] = Field(default_factory=dict, repr=False)
    ssl_verify: bool = True
    timeout_seconds: int = 30
    extra: dict[str, str] = Field(default_factory=dict)


def load_mapping(path: Path) -> SchemaMapping:
    """Load and validate a YAML schema mapping file.

    Args:
        path: Path to the YAML mapping file.

    Returns:
        Validated SchemaMapping instance.

    Raises:
        FileNotFoundError: If the YAML file does not exist.
        pydantic.ValidationError: If the YAML content is invalid.
    """
    with open(path) as f:
        data = yaml.safe_load(f)
    return SchemaMapping.model_validate(data)


def load_config(path: Path) -> ConnectorConfig:
    """Load and validate a connector configuration from YAML.

    Args:
        path: Path to the YAML config file.

    Returns:
        Validated ConnectorConfig instance.

    Raises:
        FileNotFoundError: If the YAML file does not exist.
        pydantic.ValidationError: If the YAML content is invalid.
    """
    with open(path) as f:
        data = yaml.safe_load(f)
    return ConnectorConfig.model_validate(data)
