# Deploy SporeDB on Render

Deploy SporeDB on Render in under 5 minutes. Render reads the `render.yaml` Blueprint to provision your app and managed PostgreSQL automatically.

## Prerequisites

| Requirement | Details |
|-------------|---------|
| Render account | [render.com](https://render.com) |
| GitHub repo | Fork or clone [SporeDB](https://github.com/spore-db/SporeDB) and connect to Render |

No CLI installation required -- Render reads `render.yaml` from your repo root.

## Quick Start

Click the button below to deploy using Render's Blueprint:

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/spore-db/SporeDB)

Render will:

1. Detect `render.yaml` in your repo root
2. Create a web service (SporeDB) and a managed PostgreSQL database
3. Build the Docker image from `Dockerfile`
4. Start the app with auto-injected environment variables

After deploy, configure the remaining secrets in the Render dashboard (see Configuration below).

## What Gets Provisioned

- **App Service:** SporeDB web service on Render's starter plan (512MB RAM, 0.5 CPU)
- **Database:** Managed PostgreSQL 16 (basic-256mb plan)
- **Object Storage:** Not included -- you must provide an external S3-compatible endpoint

The `render.yaml` Blueprint declares both the web service and the database. Secrets marked `sync: false` must be set manually in the dashboard.

## Configuration

After deploying, set the following secrets in the Render dashboard (Environment tab):

| Variable | Source | Description |
|----------|--------|-------------|
| `SPOREDB_DATABASE_URL` | Must override manually (see warning) | PostgreSQL connection string |
| `SPOREDB_MODE` | `selfhosted` (auto-set) | Deployment mode |
| `SPOREDB_SERVER_PORT` | `8000` (auto-set) | HTTP port |
| `SPOREDB_S3_ENDPOINT` | Set in dashboard | S3-compatible endpoint URL |
| `SPOREDB_S3_ACCESS_KEY` | Set in dashboard | S3 access key |
| `SPOREDB_S3_SECRET_KEY` | Set in dashboard | S3 secret key |
| `SPOREDB_S3_BUCKET` | `sporedb` (auto-set) | S3 bucket name |
| `SPOREDB_ED25519_PRIVATE_KEY_B64` | Set in dashboard | Base64-encoded Ed25519 private key |
| `SPOREDB_ED25519_PUBLIC_KEY_B64` | Set in dashboard | Base64-encoded Ed25519 public key |

> **WARNING: Connection String Format**
>
> Render auto-injects `SPOREDB_DATABASE_URL` via the `fromDatabase` block in `render.yaml`
> using `postgres://user:pass@host:5432/db` format. SporeDB requires `postgresql+asyncpg://`
> format. The app does NOT auto-translate the prefix.
>
> After deploy, go to your web service's Environment tab and **override** `SPOREDB_DATABASE_URL`
> with the correct prefix:
>
> ```
> postgresql+asyncpg://user:pass@host:5432/sporedb
> ```
>
> Copy the connection details from your Render PostgreSQL dashboard and change the prefix
> from `postgres://` to `postgresql+asyncpg://`.

## Ed25519 Key Setup

SporeDB requires Ed25519 keys for JWT authentication and audit trail signing. The app loads keys from file paths, so on Render you must inject them as base64-encoded environment variables that get decoded at startup.

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

**3. Set as Render secrets:**

In the Render dashboard, go to your web service > Environment and add:

- `SPOREDB_ED25519_PRIVATE_KEY_B64` = `<base64-private-key>` (mark as Secret)
- `SPOREDB_ED25519_PUBLIC_KEY_B64` = `<base64-public-key>` (mark as Secret)

**4. Override the Docker command** to decode keys at startup. In the Render dashboard, go to your web service > Settings > Docker Command and set:

```bash
sh -c 'mkdir -p /home/sporedb/app/keys && echo "$SPOREDB_ED25519_PRIVATE_KEY_B64" | base64 -d > /home/sporedb/app/keys/cloud_private.pem && echo "$SPOREDB_ED25519_PUBLIC_KEY_B64" | base64 -d > /home/sporedb/app/keys/cloud_public.pem && export SPOREDB_JWT_SECRET_KEY_PATH=/home/sporedb/app/keys/cloud_private.pem && export SPOREDB_JWT_PUBLIC_KEY_PATH=/home/sporedb/app/keys/cloud_public.pem && exec uvicorn sporedb.cloud.app:create_app --factory --host 0.0.0.0 --port 8000'
```

## Cost Estimate

All prices are approximate monthly costs running 24/7.

| Workload | App | Database | Storage | Total/month |
|----------|-----|----------|---------|-------------|
| Small (10 batches) | $7/mo (Starter) | $7/mo (basic-256mb) | BYO S3 | ~$14/mo |
| Medium (50 batches) | $25/mo (Standard) | $15/mo (basic-1gb) | BYO S3 | ~$40/mo |
| Large (100+ batches) | $85/mo (Standard Plus) | $45/mo (basic-4gb) | BYO S3 | ~$130/mo |

## Recommended Sizing

| Workload | Plan | RAM | DB Plan | Storage |
|----------|------|-----|---------|---------|
| Small (10 batches) | Starter | 512MB | basic-256mb | 1GB S3 |
| Medium (50 batches) | Standard | 1GB | basic-1gb | 10GB S3 |
| Large (100+ batches) | Standard Plus | 2GB | basic-4gb | 50GB S3 |

Scale via the Render dashboard under your web service's Settings.

## Troubleshooting

### render.yaml not detected

**Symptom:** Render does not create the Blueprint services.

**Fix:** The file must be at the repo root and named exactly `render.yaml` (not `render.yml` or in a subdirectory). Verify the file is committed and pushed to the branch Render is tracking.

### Database connection refused / rfc1738 error

**Symptom:** App crashes on startup with "Could not parse rfc1738 URL" or database connection errors.

**Fix:** Check that `SPOREDB_DATABASE_URL` has the `postgresql+asyncpg://` prefix. Render's auto-injected connection string uses `postgres://` format which SporeDB cannot parse. Override it manually in the dashboard (see Configuration above).

### Storage not configured

**Symptom:** Errors when writing batch data, "bucket not found" messages.

**Fix:** Render does not provision S3-compatible storage automatically. Set `SPOREDB_S3_ENDPOINT`, `SPOREDB_S3_ACCESS_KEY`, and `SPOREDB_S3_SECRET_KEY` in the dashboard pointing to your external S3 endpoint.

### 500 on auth endpoints

**Symptom:** 500 Internal Server Error on login or authenticated endpoints, `FileNotFoundError` for `keys/cloud_private.pem`.

**Fix:** Ed25519 keys are not configured. Verify:

1. `SPOREDB_ED25519_PRIVATE_KEY_B64` and `SPOREDB_ED25519_PUBLIC_KEY_B64` are set in the Environment tab
2. The Docker Command override is set to decode keys at startup (see Ed25519 Key Setup)
3. Redeploy the service after making changes
