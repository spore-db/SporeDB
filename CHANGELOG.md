# Changelog

All notable changes to SporeDB will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-05-11

### Added

- **Batch Data Model** — first-class batch objects with canonical timestamps (inoculation, feed-start, induction, harvest), metadata, and lifecycle tracking
- **Data Ingestion** — CSV and Excel import with automatic column mapping, unit normalization, and timestamp detection
- **FDA 21 CFR Part 11 Compliance** — SHA-256 hash chain audit trail, Ed25519 digital signatures, Merkle tree integrity proofs, electronic signatures with meaning codes, RBAC access controls
- **Offline Phase Detection** — PELT (via ruptures) and BOCPD algorithms for automatic identification of lag, exponential, stationary, and decline phases
- **Cross-Run Alignment** — `align(runs, by='phase')` for multi-batch comparison anchored on phase boundaries
- **Golden Batch Analysis** — compute reference profiles from historical runs, score new runs against golden batch
- **Advanced Analytics** — batch metrics (specific growth rate, doubling time, yields), process analytical technology (PAT) integration
- **PromQL-style Query DSL** — domain-specific query language parsed by Lark, compiled to DuckDB SQL
- **Python SDK** — `SporeDB` client class with full API for batch management, ingestion, querying, and analysis
- **CLI** — Click-based command-line interface for batch operations, data import, and querying
- **Jupyter Visualization** — Plotly-based interactive charts: time-series overlay, phase markers, golden batch comparison, batch inspector widget
- **Cloud Tier** — FastAPI server with PostgreSQL metadata, S3-compatible object storage, JWT authentication, tenant isolation
- **Enterprise Connectors** — InfluxDB, OSIsoft PI Web API, LabVantage, SciNote data import
- **Deployment Guides** — Docker Compose, Fly.io, Railway, Render, AWS ECS/Fargate, DigitalOcean, air-gapped environments
- **Data Lineage** — unit operation tracking with parent-child batch relationships

[0.1.0]: https://github.com/spore-db/SporeDB/releases/tag/v0.1.0
