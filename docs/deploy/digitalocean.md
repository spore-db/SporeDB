# Deploy SporeDB on DigitalOcean

Deploy SporeDB on DigitalOcean App Platform with managed PostgreSQL and
Spaces (S3-compatible storage). Estimated time: 10 minutes.

## Prerequisites

| Requirement | Details |
|-------------|---------|
| DigitalOcean account | With billing enabled |
| `doctl` CLI | Installed and authenticated (`doctl auth init`) |
| GitHub repo | SporeDB repo forked to your account or connected as a source in App Platform |

## Quick Start

Go to **cloud.digitalocean.com > App Platform > Create App**, select your
SporeDB GitHub repo, and follow the wizard. Or use the CLI:

```bash
doctl apps create --spec .do/app-spec.yaml
```

> Note: SporeDB does not ship a `.do/app-spec.yaml` file. This guide focuses
> on the console walkthrough. See the step-by-step instructions below.

## Step-by-Step Setup

### 1. Connect Your GitHub Repository

1. Go to **cloud.digitalocean.com > App Platform > Create App**
2. Select **GitHub** as the source
3. Authorize DigitalOcean to access your GitHub account (if not already done)
4. Select the **SporeDB** repository and the `main` branch

### 2. Configure the App Component

1. Set the component name to `sporedb`
2. Set the type to **Web Service**
3. Set the Dockerfile path to `Dockerfile`
4. Set the HTTP port to `8000`

### 3. Add a Managed PostgreSQL Database

1. Click **Add Resource > Database**
2. Select **PostgreSQL**
3. Choose the **Development** plan ($7/mo, single node)
4. Name the database `sporedb-db`

### 4. Create a Spaces Bucket (S3-Compatible Storage)

Spaces is created separately from App Platform:

1. Go to **cloud.digitalocean.com > Spaces Object Storage > Create a Space**
2. Choose a region (e.g., `nyc3`)
3. Name the Space `sporedb`
4. Note the endpoint URL (e.g., `https://nyc3.digitaloceanspaces.com`)
5. Go to **API > Spaces Keys > Generate New Key**
6. Save the access key and secret key

### 5. Generate Ed25519 Signing Keys

SporeDB uses Ed25519 key pairs for JWT authentication and audit trail signing.
Generate them locally:

```bash
openssl genpkey -algorithm ed25519 -out private.pem
openssl pkey -in private.pem -pubout -out public.pem
```

Base64-encode for upload as environment variables:

```bash
# Cross-platform single-line base64 (works on both macOS and Linux):
openssl base64 -A -in private.pem   # Set as SPOREDB_ED25519_PRIVATE_KEY_B64
openssl base64 -A -in public.pem    # Set as SPOREDB_ED25519_PUBLIC_KEY_B64
```

### 6. Set Environment Variables

In the App Platform settings, add the following environment variables:

| Variable | Value | Secret? |
|----------|-------|---------|
| `SPOREDB_MODE` | `selfhosted` | No |
| `SPOREDB_SERVER_PORT` | `8000` | No |
| `SPOREDB_DATABASE_URL` | `postgresql+asyncpg://user:pass@host:25060/db?sslmode=require` | Yes |
| `SPOREDB_S3_ENDPOINT` | `https://nyc3.digitaloceanspaces.com` | No |
| `SPOREDB_S3_ACCESS_KEY` | (your Spaces API key) | Yes |
| `SPOREDB_S3_SECRET_KEY` | (your Spaces API secret) | Yes |
| `SPOREDB_S3_BUCKET` | `sporedb` | No |
| `SPOREDB_ED25519_PRIVATE_KEY_B64` | (base64-encoded private key) | Yes |
| `SPOREDB_ED25519_PUBLIC_KEY_B64` | (base64-encoded public key) | Yes |

> **WARNING:** Do NOT use the auto-injected `${db.DATABASE_URL}` variable
> directly. DigitalOcean injects it in `postgresql://` format, but SporeDB
> requires `postgresql+asyncpg://` format. You MUST set `SPOREDB_DATABASE_URL`
> manually with the correct prefix.
>
> To construct the URL: go to the database component in App Platform, copy the
> connection details (host, port, username, password, database name), and
> assemble them as:
> `postgresql+asyncpg://username:password@host:25060/dbname?sslmode=require`

### 7. Override the Docker Command

SporeDB loads Ed25519 keys from file paths only. On App Platform, container
filesystems are ephemeral. Override the Docker command to decode base64-encoded
keys at startup.

In the app component settings, set the **Run Command** to:

```bash
sh -c 'mkdir -p /home/sporedb/app/keys && echo "$SPOREDB_ED25519_PRIVATE_KEY_B64" | base64 -d > /home/sporedb/app/keys/cloud_private.pem && echo "$SPOREDB_ED25519_PUBLIC_KEY_B64" | base64 -d > /home/sporedb/app/keys/cloud_public.pem && export SPOREDB_JWT_SECRET_KEY_PATH=/home/sporedb/app/keys/cloud_private.pem && export SPOREDB_JWT_PUBLIC_KEY_PATH=/home/sporedb/app/keys/cloud_public.pem && exec uvicorn sporedb.cloud.app:create_app --factory --host 0.0.0.0 --port 8000'
```

This command:

1. Creates the keys directory
2. Decodes the base64-encoded Ed25519 keys to PEM files
3. Sets the key file path environment variables
4. Launches the SporeDB server

### 8. Deploy

Click **Create Resources** and wait for the build and deployment to complete.
App Platform will build the Docker image from the repository and start the
service.

### 9. Verify

Once deployed, check the app URL:

```bash
curl -f https://your-app-name.ondigitalocean.app/health
```

The health endpoint should return HTTP 200.

## What Gets Provisioned

| Resource | Specification |
|----------|--------------|
| App container | Basic instance, 512 MB RAM |
| Managed PostgreSQL | Basic (256 MB), single node |
| Spaces bucket | User-created separately |

## Configuration

| Variable | Source | Description |
|----------|--------|-------------|
| `SPOREDB_MODE` | App env var | `selfhosted` |
| `SPOREDB_SERVER_PORT` | App env var | `8000` |
| `SPOREDB_S3_ENDPOINT` | App env var | Spaces endpoint URL |
| `SPOREDB_S3_BUCKET` | App env var | `sporedb` |
| `SPOREDB_DATABASE_URL` | App env var (encrypted) | `postgresql+asyncpg://...` (manual, not auto-injected) |
| `SPOREDB_S3_ACCESS_KEY` | App env var (encrypted) | Spaces API key |
| `SPOREDB_S3_SECRET_KEY` | App env var (encrypted) | Spaces API secret |
| `SPOREDB_ED25519_PRIVATE_KEY_B64` | App env var (encrypted) | Base64-encoded Ed25519 private key |
| `SPOREDB_ED25519_PUBLIC_KEY_B64` | App env var (encrypted) | Base64-encoded Ed25519 public key |

### Connection String Format

> **WARNING:** DigitalOcean's auto-injected `${db.DATABASE_URL}` uses
> `postgresql://` format. SporeDB requires `postgresql+asyncpg://` format.
> You MUST set `SPOREDB_DATABASE_URL` manually with the correct prefix.
>
> **Correct:** `postgresql+asyncpg://user:pass@host:25060/db?sslmode=require`
> **Wrong:** `postgresql://user:pass@host:25060/db?sslmode=require`

## Ed25519 Key Setup

SporeDB loads Ed25519 signing keys from file paths only. On DigitalOcean App
Platform, container filesystems are ephemeral -- key files do not persist
across deploys. The Docker command override handles this by:

1. Reading `SPOREDB_ED25519_PRIVATE_KEY_B64` and `SPOREDB_ED25519_PUBLIC_KEY_B64`
   from encrypted environment variables
2. Decoding the base64 values to PEM files at `/home/sporedb/app/keys/`
3. Setting `SPOREDB_JWT_SECRET_KEY_PATH` and `SPOREDB_JWT_PUBLIC_KEY_PATH`
4. Launching uvicorn

Do NOT set `SPOREDB_JWT_SECRET_KEY_PATH` or `SPOREDB_JWT_PUBLIC_KEY_PATH` to
local file paths in environment variables -- the files will not exist on the
ephemeral container filesystem. Use the base64 startup script pattern instead.

## Cost Estimate

All prices are approximate monthly costs for DigitalOcean.

| Workload | App | Managed Postgres | Spaces | Total/month |
|----------|-----|-----------------|--------|-------------|
| Small (10 batches) | $5/mo (basic, 512 MB) | $7/mo (basic-256mb) | $5/mo (250 GB included) | ~$17/mo |
| Medium (50 batches) | $10/mo (basic, 1 GB) | $15/mo (basic-1gb) | $5/mo | ~$30/mo |
| Large (100+ batches) | $22/mo (pro, 1 GB) | $50/mo (basic-4gb) | $5/mo | ~$77/mo |

## Recommended Sizing

| Workload | CPU | RAM | DB Plan | Spaces Storage |
|----------|-----|-----|---------|---------------|
| Small (10 batches) | 1 vCPU | 512 MB | basic-256mb | 10 GB |
| Medium (50 batches) | 1 vCPU | 1 GB | basic-1gb | 50 GB |
| Large (100+ batches) | 2 vCPU | 2 GB | basic-4gb | 100 GB |

To change app sizing, update the instance type in App Platform settings.
To upgrade the database, modify the plan via the database component settings.

## Troubleshooting

### Build fails

- Verify the Dockerfile is at the repository root and the correct branch is
  selected
- Check the build logs in App Platform for specific errors
- Ensure the repository is connected and DigitalOcean has read access

### Database connection refused / rfc1738 error

- Verify `SPOREDB_DATABASE_URL` has the `postgresql+asyncpg://` prefix
- Do NOT use the auto-injected `${db.DATABASE_URL}` -- it uses `postgresql://`
  format which SporeDB does not auto-translate
- Confirm the database is in the same region as the app and the trusted sources
  include the app component
- Ensure `?sslmode=require` is appended to the connection string (DigitalOcean
  managed databases require SSL)

### Spaces access denied

- Verify the Spaces API key has read/write permissions
- Ensure the bucket region matches the endpoint URL (e.g., `nyc3` bucket uses
  `https://nyc3.digitaloceanspaces.com`)
- Check that the bucket name in `SPOREDB_S3_BUCKET` matches exactly

### 500 on auth endpoints / FileNotFoundError for keys

- Verify `SPOREDB_ED25519_PRIVATE_KEY_B64` and `SPOREDB_ED25519_PUBLIC_KEY_B64`
  are set as encrypted environment variables
- Confirm the Docker command override is in place (see Step 7)
- Check the app runtime logs for specific error messages
- Ensure the base64 encoding is correct:
  ```bash
  # Verify locally
  echo "YOUR_B64_VALUE" | base64 -d | head -1
  # Should output: -----BEGIN PRIVATE KEY-----
  ```
