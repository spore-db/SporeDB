"""Cloud tier configuration loaded from environment variables.

Supports three configuration sources (in priority order):
1. Environment variables with SPOREDB_ prefix (highest priority)
2. sporedb.yml config file (if present)
3. Default values (lowest priority)
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _load_yaml_settings(yaml_path: str = "sporedb.yml") -> dict[str, Any]:
    """Load settings from a YAML config file if it exists.

    Returns a flat dict with keys matching CloudSettings field names.
    Nested YAML keys are flattened (e.g., ``database.url`` becomes
    ``database_url``).
    """
    path = Path(yaml_path)
    if not path.exists():
        return {}

    try:
        import yaml
    except ImportError:
        return {}

    with open(path) as f:
        data = yaml.safe_load(f)

    if not isinstance(data, dict):
        return {}

    flat: dict[str, Any] = {}

    # Top-level mode
    if "mode" in data:
        flat["mode"] = data["mode"]

    # Server section
    server = data.get("server", {})
    if isinstance(server, dict):
        if "host" in server:
            flat["server_host"] = server["host"]
        if "port" in server:
            flat["server_port"] = server["port"]
        if "workers" in server:
            flat["server_workers"] = server["workers"]

    # Database section
    db = data.get("database", {})
    if isinstance(db, dict) and "url" in db:
        flat["database_url"] = db["url"]

    # Storage section
    storage = data.get("storage", {})
    if isinstance(storage, dict):
        if "endpoint" in storage:
            flat["s3_endpoint"] = storage["endpoint"]
        if "access_key" in storage:
            flat["s3_access_key"] = storage["access_key"]
        if "secret_key" in storage:
            flat["s3_secret_key"] = storage["secret_key"]
        if "bucket" in storage:
            flat["s3_bucket"] = storage["bucket"]
        if "region" in storage:
            flat["s3_region"] = storage["region"]

    # Auth section
    auth = data.get("auth", {})
    if isinstance(auth, dict):
        if "jwt_private_key_path" in auth:
            flat["jwt_secret_key_path"] = auth["jwt_private_key_path"]
        if "jwt_public_key_path" in auth:
            flat["jwt_public_key_path"] = auth["jwt_public_key_path"]
        if "jwt_algorithm" in auth:
            flat["jwt_algorithm"] = auth["jwt_algorithm"]
        if "access_token_expire_minutes" in auth:
            flat["jwt_access_token_expire_minutes"] = auth[
                "access_token_expire_minutes"
            ]
        if "refresh_token_expire_days" in auth:
            flat["jwt_refresh_token_expire_days"] = auth["refresh_token_expire_days"]

    # Compliance section
    compliance = data.get("compliance", {})
    if isinstance(compliance, dict):
        if "audit_trail" in compliance:
            flat["compliance_audit_trail"] = compliance["audit_trail"]
        if "require_signatures" in compliance:
            flat["compliance_require_signatures"] = compliance["require_signatures"]
        if "rbac_enabled" in compliance:
            flat["compliance_rbac_enabled"] = compliance["rbac_enabled"]

    # CORS section
    cors = data.get("cors", {})
    if isinstance(cors, dict) and "origins" in cors:
        flat["cors_origins"] = cors["origins"]

    return flat


class CloudSettings(BaseSettings):
    """Configuration for SporeDB cloud tier.

    All fields can be overridden via environment variables with
    the ``SPOREDB_`` prefix (e.g. ``SPOREDB_DATABASE_URL``).

    If a ``sporedb.yml`` file exists in the working directory, its
    values are loaded as defaults. Environment variables always take
    precedence over YAML values.
    """

    model_config = SettingsConfigDict(env_prefix="SPOREDB_")

    # Deployment mode: "cloud", "selfhosted", or "local"
    mode: str = "cloud"

    # Server
    server_host: str = "0.0.0.0"
    server_port: int = 8000
    server_workers: int = 4

    # Database (required — no default credentials)
    database_url: str = ""

    # S3-compatible object storage (required — no default credentials)
    s3_endpoint: str = "http://localhost:9000"
    s3_access_key: str = ""
    s3_secret_key: str = ""
    s3_bucket: str = "sporedb"
    s3_region: str = "us-east-1"

    # JWT authentication
    jwt_secret_key_path: str = "keys/cloud_private.pem"
    jwt_public_key_path: str = "keys/cloud_public.pem"
    jwt_algorithm: str = "EdDSA"
    jwt_access_token_expire_minutes: int = 15
    jwt_refresh_token_expire_days: int = 7

    # Compliance
    compliance_audit_trail: bool = True
    compliance_require_signatures: bool = True
    compliance_rbac_enabled: bool = True

    # Application
    app_title: str = "SporeDB Cloud"
    app_version: str = "0.1.0"
    cors_origins: list[str] = []
    debug: bool = False

    @model_validator(mode="after")
    def _check_required_secrets(self) -> CloudSettings:
        """Fail fast if required credentials are not configured."""
        if not self.database_url:
            raise ValueError(
                "SPOREDB_DATABASE_URL must be set (no default credentials)"
            )
        if not self.s3_access_key or not self.s3_secret_key:
            raise ValueError(
                "SPOREDB_S3_ACCESS_KEY and SPOREDB_S3_SECRET_KEY must be set"
            )
        return self

    @classmethod
    def from_yaml(
        cls,
        yaml_path: str = "sporedb.yml",
        **overrides: Any,
    ) -> CloudSettings:
        """Create settings by merging YAML config, env vars, and overrides.

        Priority (highest first):
        1. Keyword argument overrides
        2. Environment variables (SPOREDB_ prefix)
        3. YAML file values
        4. Field defaults

        Parameters
        ----------
        yaml_path:
            Path to the YAML configuration file.
        **overrides:
            Explicit field overrides (highest priority).
        """
        yaml_values = _load_yaml_settings(yaml_path)
        # Merge: YAML values serve as init defaults; env vars and
        # explicit overrides take precedence via pydantic-settings.
        merged = {**yaml_values, **overrides}
        return cls(**merged)
