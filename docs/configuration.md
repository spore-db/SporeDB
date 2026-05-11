# Configuration Reference

All SporeDB cloud tier settings use the `SPOREDB_` environment variable prefix. Configuration sources are applied in this priority order:

1. **Environment variables** with `SPOREDB_` prefix (highest priority)
2. **sporedb.yml** config file (if present)
3. **Default values** (lowest priority)

!!! warning "Production deployments"
    Always set unique credentials for `SPOREDB_DATABASE_URL`, `SPOREDB_S3_ACCESS_KEY`, and `SPOREDB_S3_SECRET_KEY` in production. Never use the default development values from docker-compose.yml.

## Server

| Variable | Default | Required | Description |
|----------|---------|----------|-------------|
| `SPOREDB_MODE` | `cloud` | No | Deployment mode |
| `SPOREDB_SERVER_HOST` | `0.0.0.0` | No | Host address to bind the API server |
| `SPOREDB_SERVER_PORT` | `8000` | No | Port for the API server |
| `SPOREDB_SERVER_WORKERS` | `4` | No | Number of uvicorn worker processes |

## Database

| Variable | Default | Required | Description |
|----------|---------|----------|-------------|
| `SPOREDB_DATABASE_URL` | (none) | Yes | PostgreSQL connection string (asyncpg driver required) |

### Database Provider Examples

**SPOREDB_DATABASE_URL:**

| Provider | Example Value |
|----------|---------------|
| AWS RDS | `postgresql+asyncpg://user:pass@mydb.xxx.us-east-1.rds.amazonaws.com:5432/sporedb` |
| GCP Cloud SQL | `postgresql+asyncpg://user:pass@/sporedb?host=/cloudsql/project:region:instance` |
| Azure | `postgresql+asyncpg://user:pass@myserver.postgres.database.azure.com:5432/sporedb` |
| Local/Docker | `postgresql+asyncpg://sporedb:sporedb@localhost:5432/sporedb` |
| Hetzner | `postgresql+asyncpg://user:pass@hetzner-db.example.com:5432/sporedb` |

## Storage

| Variable | Default | Required | Description |
|----------|---------|----------|-------------|
| `SPOREDB_S3_ENDPOINT` | `http://localhost:9000` | No | S3-compatible storage endpoint URL |
| `SPOREDB_S3_ACCESS_KEY` | (none) | Yes | S3 access key ID |
| `SPOREDB_S3_SECRET_KEY` | (none) | Yes | S3 secret access key |
| `SPOREDB_S3_BUCKET` | `sporedb` | No | S3 bucket name for Parquet data files |
| `SPOREDB_S3_REGION` | `us-east-1` | No | S3 region (used for signature calculation) |

### Storage Provider Examples

**SPOREDB_S3_ENDPOINT:**

| Provider | Example Value |
|----------|---------------|
| AWS | `https://s3.us-east-1.amazonaws.com` |
| GCP | `https://storage.googleapis.com` |
| Azure | `https://<account>.blob.core.windows.net` |
| MinIO | `http://localhost:9000` |
| Hetzner | `https://fsn1.your-objectstorage.com` |

**SPOREDB_S3_REGION:**

| Provider | Example Value |
|----------|---------------|
| AWS | `us-east-1` |
| GCP | `auto` |
| Azure | `n/a (use endpoint)` |
| MinIO | `us-east-1` |
| Hetzner | `fsn1` |

## Authentication

| Variable | Default | Required | Description |
|----------|---------|----------|-------------|
| `SPOREDB_JWT_SECRET_KEY_PATH` | `keys/cloud_private.pem` | No | Path to Ed25519 private key for signing tokens |
| `SPOREDB_JWT_PUBLIC_KEY_PATH` | `keys/cloud_public.pem` | No | Path to Ed25519 public key for verifying tokens |
| `SPOREDB_JWT_ALGORITHM` | `EdDSA` | No | JWT signing algorithm |
| `SPOREDB_JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | `15` | No | Access token lifetime in minutes |
| `SPOREDB_JWT_REFRESH_TOKEN_EXPIRE_DAYS` | `7` | No | Refresh token lifetime in days |

## Compliance

| Variable | Default | Required | Description |
|----------|---------|----------|-------------|
| `SPOREDB_COMPLIANCE_AUDIT_TRAIL` | `true` | No | Enable tamper-evident audit trail |
| `SPOREDB_COMPLIANCE_REQUIRE_SIGNATURES` | `true` | No | Require cryptographic signatures on mutations |
| `SPOREDB_COMPLIANCE_RBAC_ENABLED` | `true` | No | Enable role-based access control |

## Application

| Variable | Default | Required | Description |
|----------|---------|----------|-------------|
| `SPOREDB_APP_TITLE` | `SporeDB Cloud` | No | Application title shown in OpenAPI docs |
| `SPOREDB_APP_VERSION` | `0.1.0` | No | Application version string |
| `SPOREDB_CORS_ORIGINS` | `[]` | No | Allowed CORS origins (JSON array format) |
| `SPOREDB_DEBUG` | `false` | No | Enable debug mode (disable in production) |

---

See also: [Self-Hosted Guide](deployment/selfhosted.md)

