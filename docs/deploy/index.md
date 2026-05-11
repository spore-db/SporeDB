# Deploy SporeDB

Choose your platform to deploy SporeDB. Each guide includes prerequisites, step-by-step instructions, configuration, cost estimates, and recommended sizing for bioprocess workloads.

## One-Click Platforms

Deploy with a single click or a few CLI commands:

| Platform | Guide | Time | Starting Cost |
|----------|-------|------|---------------|
| Railway | [Deploy on Railway](railway.md) | ~3 min | ~$5/mo |
| Render | [Deploy on Render](render.md) | ~5 min | ~$14/mo |
| Fly.io | [Deploy on Fly.io](fly-io.md) | ~5 min | ~$8/mo |

## Step-by-Step Guides

For full control over your infrastructure:

| Platform | Guide | Time | Starting Cost |
|----------|-------|------|---------------|
| AWS (ECS/Fargate) | [Deploy on AWS](aws.md) | ~20 min | ~$26/mo |
| DigitalOcean | [Deploy on DigitalOcean](digitalocean.md) | ~10 min | ~$17/mo |
| Self-Hosted (Docker) | [Self-Hosted Guide](../deployment/selfhosted.md) | ~5 min | Infrastructure only |

## Requirements

All deployment options require:

- **PostgreSQL 16+** for metadata storage
- **S3-compatible object storage** for Parquet files (batch data)
- **Ed25519 key pair** for JWT authentication and audit trail signing

Each guide covers how to provision these on the target platform.

## Configuration

SporeDB uses the `SPOREDB_*` environment variable namespace for all configuration. Platform-managed services (Postgres, S3) inject connection details via environment variables. See each guide's Configuration section for platform-specific mapping.

For the full environment variable reference, see the [Configuration Guide](../configuration.md).
