#!/usr/bin/env python3
"""Generate docs/configuration.md from CloudSettings model fields.

Run: python scripts/generate_env_docs.py > docs/configuration.md
"""

from __future__ import annotations

import sys
from pathlib import Path

# Add src to path for import
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from sporedb.cloud.config import CloudSettings  # noqa: E402

SECTIONS: dict[str, list[str]] = {
    "Server": ["mode", "server_host", "server_port", "server_workers"],
    "Database": ["database_url"],
    "Storage": [
        "s3_endpoint",
        "s3_access_key",
        "s3_secret_key",
        "s3_bucket",
        "s3_region",
    ],
    "Authentication": [
        "jwt_secret_key_path",
        "jwt_public_key_path",
        "jwt_algorithm",
        "jwt_access_token_expire_minutes",
        "jwt_refresh_token_expire_days",
    ],
    "Compliance": [
        "compliance_audit_trail",
        "compliance_require_signatures",
        "compliance_rbac_enabled",
    ],
    "Application": ["app_title", "app_version", "cors_origins", "debug"],
}

PROVIDER_EXAMPLES: dict[str, dict[str, str]] = {
    "s3_endpoint": {
        "AWS": "https://s3.us-east-1.amazonaws.com",
        "GCP": "https://storage.googleapis.com",
        "Azure": "https://<account>.blob.core.windows.net",
        "MinIO": "http://localhost:9000",
        "Hetzner": "https://fsn1.your-objectstorage.com",
    },
    "s3_region": {
        "AWS": "us-east-1",
        "GCP": "auto",
        "Azure": "n/a (use endpoint)",
        "MinIO": "us-east-1",
        "Hetzner": "fsn1",
    },
    "database_url": {
        "AWS RDS": "postgresql+asyncpg://user:pass@mydb.xxx.us-east-1.rds.amazonaws.com:5432/sporedb",
        "GCP Cloud SQL": "postgresql+asyncpg://user:pass@/sporedb?host=/cloudsql/project:region:instance",
        "Azure": "postgresql+asyncpg://user:pass@myserver.postgres.database.azure.com:5432/sporedb",
        "Local/Docker": "postgresql+asyncpg://sporedb:sporedb@localhost:5432/sporedb",
        "Hetzner": "postgresql+asyncpg://user:pass@hetzner-db.example.com:5432/sporedb",
    },
}

FIELD_DESCRIPTIONS: dict[str, str] = {
    "mode": "Deployment mode",
    "server_host": "Host address to bind the API server",
    "server_port": "Port for the API server",
    "server_workers": "Number of uvicorn worker processes",
    "database_url": "PostgreSQL connection string (asyncpg driver required)",
    "s3_endpoint": "S3-compatible storage endpoint URL",
    "s3_access_key": "S3 access key ID",
    "s3_secret_key": "S3 secret access key",
    "s3_bucket": "S3 bucket name for Parquet data files",
    "s3_region": "S3 region (used for signature calculation)",
    "jwt_secret_key_path": "Path to Ed25519 private key for signing tokens",
    "jwt_public_key_path": "Path to Ed25519 public key for verifying tokens",
    "jwt_algorithm": "JWT signing algorithm",
    "jwt_access_token_expire_minutes": "Access token lifetime in minutes",
    "jwt_refresh_token_expire_days": "Refresh token lifetime in days",
    "compliance_audit_trail": "Enable tamper-evident audit trail",
    "compliance_require_signatures": "Require cryptographic signatures on mutations",
    "compliance_rbac_enabled": "Enable role-based access control",
    "app_title": "Application title shown in OpenAPI docs",
    "app_version": "Application version string",
    "cors_origins": "Allowed CORS origins (JSON array format)",
    "debug": "Enable debug mode (disable in production)",
}

# Fields that have no default (required)
REQUIRED_FIELDS = {"database_url", "s3_access_key", "s3_secret_key"}


def _format_default(field_name: str) -> str:
    """Return a display string for the field's default value."""
    info = CloudSettings.model_fields[field_name]
    default = info.default
    if field_name in REQUIRED_FIELDS:
        return "(none)"
    if isinstance(default, list):
        return "`[]`"
    if isinstance(default, bool):
        return f"`{str(default).lower()}`"
    if isinstance(default, (int, float)):
        return f"`{default}`"
    if isinstance(default, str):
        return f"`{default}`" if default else "(empty)"
    return str(default)


def _is_required(field_name: str) -> str:
    return "Yes" if field_name in REQUIRED_FIELDS else "No"


def generate() -> str:
    """Generate the full configuration reference markdown."""
    lines: list[str] = []
    lines.append("# Configuration Reference")
    lines.append("")
    lines.append(
        "All SporeDB cloud tier settings use the `SPOREDB_` environment variable prefix. "
        "Configuration sources are applied in this priority order:"
    )
    lines.append("")
    lines.append("1. **Environment variables** with `SPOREDB_` prefix (highest priority)")
    lines.append("2. **sporedb.yml** config file (if present)")
    lines.append("3. **Default values** (lowest priority)")
    lines.append("")
    lines.append(
        "!!! warning \"Production deployments\"\n"
        "    Always set unique credentials for `SPOREDB_DATABASE_URL`, "
        "`SPOREDB_S3_ACCESS_KEY`, and `SPOREDB_S3_SECRET_KEY` in production. "
        "Never use the default development values from docker-compose.yml."
    )
    lines.append("")

    for section_name, field_names in SECTIONS.items():
        lines.append(f"## {section_name}")
        lines.append("")
        lines.append("| Variable | Default | Required | Description |")
        lines.append("|----------|---------|----------|-------------|")

        for name in field_names:
            env_name = f"SPOREDB_{name.upper()}"
            default = _format_default(name)
            required = _is_required(name)
            desc = FIELD_DESCRIPTIONS.get(name, "")
            lines.append(f"| `{env_name}` | {default} | {required} | {desc} |")

        lines.append("")

        # Add provider examples after Storage and Database sections
        section_examples = [
            f for f in field_names if f in PROVIDER_EXAMPLES
        ]
        if section_examples:
            lines.append(f"### {section_name} Provider Examples")
            lines.append("")
            for field_name in section_examples:
                env_name = f"SPOREDB_{field_name.upper()}"
                lines.append(f"**{env_name}:**")
                lines.append("")
                lines.append("| Provider | Example Value |")
                lines.append("|----------|---------------|")
                for provider, value in PROVIDER_EXAMPLES[field_name].items():
                    lines.append(f"| {provider} | `{value}` |")
                lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("See also: [Self-Hosted Guide](deployment/selfhosted.md)")
    lines.append("")

    return "\n".join(lines)


if __name__ == "__main__":
    print(generate())
