# Deploy SporeDB on Fly.io

Deploy SporeDB on Fly.io in under 5 minutes. Fly.io uses the `fly.toml` in this repo and provisions Postgres via the Fly CLI.

## Prerequisites

| Requirement | Details |
|-------------|---------|
| Fly.io account | [fly.io](https://fly.io) |
| flyctl CLI | `curl -L https://fly.io/install.sh \| sh` |
| GitHub repo | Clone [SporeDB](https://github.com/spore-db/SporeDB) |

## Quick Start

Fly.io does not have a one-click deploy button. Use the CLI to deploy:

```bash
# Authenticate with Fly.io
fly auth login

# Launch the app (uses fly.toml from the repo)
fly launch --copy-config --name sporedb

# Create and attach a Postgres database
fly postgres create --name sporedb-db
fly postgres attach sporedb-db

# Deploy the app
fly deploy
```

After deploy, configure secrets (see Configuration below).

## What Gets Provisioned

- **App Service:** SporeDB app on Fly.io (shared-cpu-1x, 512MB RAM)
- **Database:** Fly Postgres (shared instance)
- **Object Storage:** Not included by default -- use Fly Tigris for S3-compatible storage or provide an external endpoint

Fly Postgres is attached via CLI, not declared in `fly.toml`. Tigris (S3-compatible) can be provisioned with:

```bash
fly storage create
```

## Configuration

Set secrets via the Fly CLI:

```bash
fly secrets set SPOREDB_S3_ENDPOINT="https://your-s3-endpoint.com"
fly secrets set SPOREDB_S3_ACCESS_KEY="your-access-key"
fly secrets set SPOREDB_S3_SECRET_KEY="your-secret-key"
fly secrets set SPOREDB_S3_BUCKET="sporedb"
```

Non-secret values are set in `fly.toml` under `[env]`:

| Variable | Source | Description |
|----------|--------|-------------|
| `SPOREDB_DATABASE_URL` | Must set manually (see warning) | PostgreSQL connection string |
| `SPOREDB_MODE` | `selfhosted` (in fly.toml) | Deployment mode |
| `SPOREDB_SERVER_PORT` | `8000` (in fly.toml) | HTTP port |
| `SPOREDB_S3_ENDPOINT` | Set via `fly secrets set` | S3-compatible endpoint URL |
| `SPOREDB_S3_ACCESS_KEY` | Set via `fly secrets set` | S3 access key |
| `SPOREDB_S3_SECRET_KEY` | Set via `fly secrets set` | S3 secret key |
| `SPOREDB_S3_BUCKET` | Set via `fly secrets set` | S3 bucket name |
| `SPOREDB_ED25519_PRIVATE_KEY_B64` | Set via `fly secrets set` | Base64-encoded Ed25519 private key |
| `SPOREDB_ED25519_PUBLIC_KEY_B64` | Set via `fly secrets set` | Base64-encoded Ed25519 public key |

> **WARNING: Connection String Format**
>
> `fly postgres attach` injects `DATABASE_URL` in `postgres://user:pass@host:5432/db`
> format. SporeDB requires `postgresql+asyncpg://` format. The app does NOT auto-translate
> the prefix. You MUST override it:
>
> ```bash
> fly secrets set SPOREDB_DATABASE_URL='postgresql+asyncpg://user:pass@host:5432/sporedb'
> ```
>
> Get the connection details from `fly postgres connect sporedb-db` and change the prefix
> from `postgres://` to `postgresql+asyncpg://`.

> **Note on ports:** `fly.toml` explicitly sets `internal_port = 8000`. Fly.io defaults
> to port 8080, but SporeDB listens on 8000. Do not change this value.

## Ed25519 Key Setup

SporeDB requires Ed25519 keys for JWT authentication and audit trail signing. The app loads keys from file paths, so on Fly.io you must inject them as base64-encoded secrets that get decoded at startup.

**1. Generate key pair locally:**

```bash
openssl genpkey -algorithm ed25519 -out private.pem
openssl pkey -in private.pem -pubout -out public.pem
```

**2. Set as Fly.io secrets (base64-encoded):**

```bash
# Use openssl base64 -A to produce single-line output (portable across macOS/Linux):
fly secrets set SPOREDB_ED25519_PRIVATE_KEY_B64="$(openssl base64 -A -in private.pem)"
fly secrets set SPOREDB_ED25519_PUBLIC_KEY_B64="$(openssl base64 -A -in public.pem)"
```

**3. Override the start command** to decode keys at startup. You can either:

**Option A:** Set a custom start command in `fly.toml`:

Add to `fly.toml` under `[processes]` or override the Dockerfile `CMD`:

```toml
[processes]
  app = "sh -c 'mkdir -p /home/sporedb/app/keys && echo \"$SPOREDB_ED25519_PRIVATE_KEY_B64\" | base64 -d > /home/sporedb/app/keys/cloud_private.pem && echo \"$SPOREDB_ED25519_PUBLIC_KEY_B64\" | base64 -d > /home/sporedb/app/keys/cloud_public.pem && export SPOREDB_JWT_SECRET_KEY_PATH=/home/sporedb/app/keys/cloud_private.pem && export SPOREDB_JWT_PUBLIC_KEY_PATH=/home/sporedb/app/keys/cloud_public.pem && exec uvicorn sporedb.cloud.app:create_app --factory --host 0.0.0.0 --port 8000'"
```

**Option B:** Create an `entrypoint.sh` in your fork:

```bash
#!/bin/sh
mkdir -p /home/sporedb/app/keys
if [ -n "$SPOREDB_ED25519_PRIVATE_KEY_B64" ]; then
  echo "$SPOREDB_ED25519_PRIVATE_KEY_B64" | base64 -d > /home/sporedb/app/keys/cloud_private.pem
fi
if [ -n "$SPOREDB_ED25519_PUBLIC_KEY_B64" ]; then
  echo "$SPOREDB_ED25519_PUBLIC_KEY_B64" | base64 -d > /home/sporedb/app/keys/cloud_public.pem
fi
export SPOREDB_JWT_SECRET_KEY_PATH=/home/sporedb/app/keys/cloud_private.pem
export SPOREDB_JWT_PUBLIC_KEY_PATH=/home/sporedb/app/keys/cloud_public.pem
exec uvicorn sporedb.cloud.app:create_app --factory --host 0.0.0.0 --port 8000
```

Then update `Dockerfile` to use `ENTRYPOINT ["sh", "entrypoint.sh"]`.

## Cost Estimate

All prices are approximate monthly costs running 24/7.

| Workload | App | Database | Storage | Total/month |
|----------|-----|----------|---------|-------------|
| Small (10 batches) | ~$3.50/mo (shared-cpu-1x) | ~$3.50/mo (shared Postgres) | Tigris (pay per use) | ~$8/mo |
| Medium (50 batches) | ~$7/mo (shared-cpu-2x) | ~$7/mo | Tigris | ~$15/mo |
| Large (100+ batches) | ~$30/mo (performance-2x) | ~$30/mo | Tigris | ~$65/mo |

## Recommended Sizing

| Workload | VM Size | RAM | Postgres | Storage |
|----------|---------|-----|----------|---------|
| Small (10 batches) | shared-cpu-1x | 512MB | Shared | 1GB Tigris |
| Medium (50 batches) | shared-cpu-2x | 1GB | Shared | 10GB Tigris |
| Large (100+ batches) | performance-2x | 2GB | Dedicated | 50GB Tigris |

Scale by updating `fly.toml` and running `fly deploy`, or use `fly scale` commands:

```bash
fly scale vm shared-cpu-2x --memory 1024
```

## Troubleshooting

### Port mismatch / 502 errors

**Symptom:** Health check failures, 502 Bad Gateway errors.

**Fix:** Ensure `fly.toml` has `internal_port = 8000` in the `[http_service]` section. Fly.io defaults to 8080, but SporeDB listens on 8000.

### Postgres not attached

**Symptom:** Database connection errors on startup.

**Fix:** Fly Postgres is not declared in `fly.toml` -- it must be attached via CLI:

```bash
fly postgres create --name sporedb-db
fly postgres attach sporedb-db
```

Then set `SPOREDB_DATABASE_URL` with the correct prefix (see Configuration above).

### Machine keeps stopping

**Symptom:** App is not available after periods of inactivity.

**Fix:** This is intentional. `fly.toml` sets `auto_stop_machines = "stop"` and `min_machines_running = 0` to save costs. The machine restarts automatically on incoming requests. For always-on behavior:

```bash
fly scale count 1
```

Or edit `fly.toml` to set `min_machines_running = 1`.

### FileNotFoundError for keys

**Symptom:** `FileNotFoundError` for `keys/cloud_private.pem`, 500 errors on authenticated endpoints.

**Fix:** Ed25519 keys are not being decoded at startup. Verify:

1. Secrets are set: `fly secrets list` should show `SPOREDB_ED25519_PRIVATE_KEY_B64` and `SPOREDB_ED25519_PUBLIC_KEY_B64`
2. The start command override or `entrypoint.sh` is configured (see Ed25519 Key Setup)
3. Redeploy: `fly deploy`
