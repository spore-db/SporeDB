# Deploy SporeDB on Railway

Deploy SporeDB on Railway in under 3 minutes. Railway auto-builds from your Dockerfile and provisions managed PostgreSQL.

## Prerequisites

| Requirement | Details |
|-------------|---------|
| Railway account | [railway.com](https://railway.com) (free tier available) |
| Railway CLI | `npm i -g @railway/cli` |
| GitHub repo | Fork or clone [SporeDB](https://github.com/spore-db/SporeDB) |

## Quick Start

### Option 1: One-Click Deploy (Railway Template)

If a Railway Template has been published:

<!-- Uncomment when Railway Template is published:
[![Deploy on Railway](https://railway.com/button.svg)](https://railway.com/template/REAL_TEMPLATE_ID)
-->

> **Note:** A one-click Railway deploy button will be added once the Railway Template is published.
> Use the CLI deploy method below in the meantime.
>
> To create a one-click button, publish a Railway Template at [railway.com/templates](https://railway.com/templates)
> that bundles the app service, Postgres plugin, and environment variables.

### Option 2: CLI Deploy

```bash
railway login
railway init
railway add --plugin postgresql
railway up
```

After deploy, configure environment variables (see Configuration below).

## What Gets Provisioned

- **App Service:** SporeDB container built from `Dockerfile` (512MB RAM, 0.5 CPU default)
- **Database:** Railway Postgres plugin (managed PostgreSQL)
- **Object Storage:** Not included -- you must provide an external S3-compatible endpoint or use a Railway volume for development

> **Note:** `railway.json` only controls build and deploy settings. It cannot declare
> Postgres plugins or environment variables. Database and env vars are managed via the
> Railway dashboard or CLI.

## Configuration

Set environment variables via CLI or dashboard:

```bash
railway variables set SPOREDB_MODE=selfhosted
railway variables set SPOREDB_SERVER_PORT=8000
railway variables set SPOREDB_S3_ENDPOINT="https://your-s3-endpoint.com"
railway variables set SPOREDB_S3_ACCESS_KEY="your-access-key"
railway variables set SPOREDB_S3_SECRET_KEY="your-secret-key"
railway variables set SPOREDB_S3_BUCKET="sporedb"
```

| Variable | Value | Description |
|----------|-------|-------------|
| `SPOREDB_DATABASE_URL` | Must set manually (see warning) | PostgreSQL connection string |
| `SPOREDB_MODE` | `selfhosted` | Deployment mode |
| `SPOREDB_SERVER_PORT` | `8000` | HTTP port |
| `SPOREDB_S3_ENDPOINT` | Your S3 endpoint | S3-compatible endpoint URL |
| `SPOREDB_S3_ACCESS_KEY` | Your access key | S3 access key |
| `SPOREDB_S3_SECRET_KEY` | Your secret key | S3 secret key |
| `SPOREDB_S3_BUCKET` | `sporedb` | S3 bucket name |
| `SPOREDB_ED25519_PRIVATE_KEY_B64` | Base64-encoded key | Ed25519 private key (see Key Setup) |
| `SPOREDB_ED25519_PUBLIC_KEY_B64` | Base64-encoded key | Ed25519 public key (see Key Setup) |

> **WARNING: Connection String Format**
>
> Railway's Postgres plugin injects `DATABASE_URL` in `postgres://user:pass@host:5432/db`
> format. SporeDB requires `postgresql+asyncpg://` format. The app does NOT auto-translate
> the prefix. You MUST set `SPOREDB_DATABASE_URL` manually:
>
> ```bash
> # Get the Railway-injected DATABASE_URL, then set with correct prefix:
> railway variables set SPOREDB_DATABASE_URL='postgresql+asyncpg://user:pass@host:5432/railway'
> ```
>
> Replace `user`, `pass`, `host`, and `railway` with values from your Railway Postgres plugin.

## Ed25519 Key Setup

SporeDB requires Ed25519 keys for JWT authentication and audit trail signing. The app loads keys from file paths, so on Railway you must inject them as base64-encoded environment variables that get decoded at startup.

**1. Generate key pair locally:**

```bash
openssl genpkey -algorithm ed25519 -out private.pem
openssl pkey -in private.pem -pubout -out public.pem
```

**2. Base64-encode for platform injection:**

```bash
# Cross-platform single-line base64 (works on both macOS and Linux):
openssl base64 -A -in private.pem    # Copy this value
openssl base64 -A -in public.pem     # Copy this value
```

**3. Set as Railway secrets:**

```bash
railway variables set SPOREDB_ED25519_PRIVATE_KEY_B64="<base64-private-key>"
railway variables set SPOREDB_ED25519_PUBLIC_KEY_B64="<base64-public-key>"
```

**4. Override the start command** to decode keys at startup. In your `railway.json`, the deploy section can include a `startCommand`, or set it via the Railway dashboard:

```bash
sh -c 'mkdir -p /home/sporedb/app/keys && echo "$SPOREDB_ED25519_PRIVATE_KEY_B64" | base64 -d > /home/sporedb/app/keys/cloud_private.pem && echo "$SPOREDB_ED25519_PUBLIC_KEY_B64" | base64 -d > /home/sporedb/app/keys/cloud_public.pem && export SPOREDB_JWT_SECRET_KEY_PATH=/home/sporedb/app/keys/cloud_private.pem && export SPOREDB_JWT_PUBLIC_KEY_PATH=/home/sporedb/app/keys/cloud_public.pem && exec uvicorn sporedb.cloud.app:create_app --factory --host 0.0.0.0 --port 8000'
```

Set this as the start command in your Railway service settings (Settings > Deploy > Custom Start Command).

## Cost Estimate

All prices are approximate monthly costs running 24/7.

| Workload | App | Database | Storage | Total/month |
|----------|-----|----------|---------|-------------|
| Small (10 batches) | ~$5 (Hobby credit) | Included | BYO S3 | ~$5/mo |
| Medium (50 batches) | ~$10-15 | Included | BYO S3 | ~$10-15/mo |
| Large (100+ batches) | ~$20+ | Included | BYO S3 | ~$20+/mo |

> Railway uses usage-based pricing. The Hobby plan includes $5/mo credit. The Pro plan
> includes $20/mo credit with usage-based billing after.

## Recommended Sizing

| Workload | CPU | RAM | DB Plan | Storage |
|----------|-----|-----|---------|---------|
| Small (10 batches) | 0.5 | 512MB | Plugin default | 1GB S3 |
| Medium (50 batches) | 1 | 1GB | Plugin default | 10GB S3 |
| Large (100+ batches) | 2 | 2GB | Plugin default | 50GB S3 |

Scale via the Railway dashboard under your service's Settings > Resources.

## Troubleshooting

### App cannot connect to Postgres

**Symptom:** Connection refused or timeout errors on startup.

**Fix:** Ensure the Postgres plugin is added to your project:

```bash
railway add --plugin postgresql
```

Then set `SPOREDB_DATABASE_URL` with the correct `postgresql+asyncpg://` prefix (see Configuration above).

### Health check failing

**Symptom:** Railway marks the service as unhealthy and restarts it repeatedly.

**Fix:** Verify `SPOREDB_SERVER_PORT` is set to `8000`. The `railway.json` health check expects the app at `/health` on the configured port.

### Storage errors when writing batch data

**Symptom:** "Bucket not found" or S3 connection errors.

**Fix:** Railway does not provision S3-compatible storage automatically. Set all `SPOREDB_S3_*` environment variables pointing to your external S3 endpoint (AWS S3, MinIO, Cloudflare R2, etc.).

### Auth errors / 500 on login

**Symptom:** 500 Internal Server Error on authenticated endpoints, or `FileNotFoundError` for `keys/cloud_private.pem`.

**Fix:** Ed25519 keys are not being decoded at startup. Verify:

1. `SPOREDB_ED25519_PRIVATE_KEY_B64` and `SPOREDB_ED25519_PUBLIC_KEY_B64` are set
2. The custom start command (see Ed25519 Key Setup) is configured in your service settings
3. The start command runs before uvicorn starts (decodes base64 keys to `/home/sporedb/app/keys/`)
