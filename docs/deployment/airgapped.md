# SporeDB Air-Gapped Deployment Guide

Deploy SporeDB on servers with no internet access. This guide covers
building a portable image bundle on an internet-connected machine and
loading it on the air-gapped target.

## Overview

Air-gapped deployment uses `docker save` / `docker load` to transfer
pre-built Docker images as a single tar archive. No package downloads
or registry access is needed on the target server.

## Prerequisites

### Build machine (internet-connected)

- Docker Engine >= 24.0
- Docker Compose >= 2.20
- Internet access (to pull base images and build)

### Target server (air-gapped)

- Docker Engine >= 24.0
- Docker Compose >= 2.20
- Approved file transfer mechanism (USB drive, secure file transfer)

## Step 1: Build on Internet-Connected Machine

```bash
# Clone the repository
git clone https://github.com/spore-db/SporeDB.git
cd SporeDB

# Build Docker images and save the air-gapped bundle
make save-airgap
```

This produces `sporedb-airgap-0.1.0.tar` containing:

- `sporedb:0.1.0` -- SporeDB application
- `postgres:16-alpine` -- PostgreSQL 16
- `minio/minio:latest` -- MinIO object storage

To build a specific version:

```bash
make save-airgap IMAGE_TAG=0.2.0
```

## Step 2: Prepare Configuration Files

Copy these files alongside the tar archive for transfer:

```
sporedb-airgap-0.1.0.tar    # Docker image bundle
docker-compose.yml            # Base compose file
docker-compose.selfhosted.yml # Self-hosted overlay
sporedb.yml                   # Configuration (edit for target env)
scripts/generate-keys.sh      # Key generation script
Makefile                       # Deployment targets
```

Edit `sporedb.yml` for the target environment before transfer:

- Set database password
- Configure storage paths
- Set CORS origins for the target network

## Step 3: Generate Signing Keys

Generate keys on a secure machine before transfer:

```bash
make generate-keys
```

This creates `keys/cloud_private.pem` and `keys/cloud_public.pem`.
Include the `keys/` directory in the transfer bundle.

## Step 4: Transfer to Air-Gapped Server

Transfer all files via your approved mechanism:

```
sporedb-airgap-0.1.0.tar
docker-compose.yml
docker-compose.selfhosted.yml
sporedb.yml
Makefile
scripts/generate-keys.sh
keys/
  cloud_private.pem
  cloud_public.pem
```

## Step 5: Load and Start on Air-Gapped Server

```bash
# Load Docker images from the tar archive
make load-airgap

# Start all services
make up

# Verify services are running
make status
```

## Step 6: Verify Deployment

```bash
# Check all containers are healthy
docker compose -f docker-compose.yml -f docker-compose.selfhosted.yml ps

# Check the health endpoint
curl -f http://localhost:8000/health

# Run compliance validation
make validate-compliance
```

## Upgrading in Air-Gapped Environments

1. On the internet-connected build machine, pull the new version and rebuild:

   ```bash
   git pull origin main
   make save-airgap IMAGE_TAG=0.2.0
   ```

2. Transfer the new `sporedb-airgap-0.2.0.tar` to the air-gapped server.

3. On the air-gapped server:

   ```bash
   make down
   make load-airgap IMAGE_TAG=0.2.0
   make up
   make validate-compliance
   ```

## Bundle Size

Approximate sizes for the air-gapped tar:

| Image             | Compressed Size |
|-------------------|-----------------|
| sporedb:0.1.0     | ~250 MB         |
| postgres:16-alpine| ~100 MB         |
| minio/minio:latest| ~150 MB         |
| **Total**         | **~500 MB**     |

Actual sizes depend on the SporeDB image build and base image versions.

## Security Considerations

- Transfer the tar archive via approved media only
- Verify tar integrity with checksums:
  ```bash
  # On build machine
  sha256sum sporedb-airgap-0.1.0.tar > sporedb-airgap-0.1.0.tar.sha256

  # On air-gapped server
  sha256sum -c sporedb-airgap-0.1.0.tar.sha256
  ```
- Store signing keys separately from the image bundle
- Change all default passwords in `sporedb.yml` before deployment
