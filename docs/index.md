<!-- This page mirrors README.md. Keep both in sync. -->

# SporeDB

[![CI](https://github.com/spore-db/SporeDB/actions/workflows/ci.yml/badge.svg)](https://github.com/spore-db/SporeDB/actions/workflows/ci.yml)
[![PyPI version](https://img.shields.io/pypi/v/sporedb)](https://pypi.org/project/sporedb/)
[![Python versions](https://img.shields.io/pypi/pyversions/sporedb)](https://pypi.org/project/sporedb/)
[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)

Bioprocess-native time-series database for fermentation scientists, cell culture engineers, and biologics developers.

Built on Apache Arrow, Parquet, and DuckDB -- SporeDB provides first-class primitives for batch management, automatic phase detection, cross-run alignment, and regulatory-compliant audit trails (FDA 21 CFR Part 11).

## Features

- **Batch Management** -- create, track, and compare fermentation runs with full metadata
- **Automatic Phase Detection** -- PELT + BOCPD algorithms identify lag, exponential, stationary, and decline phases
- **Cross-Run Alignment** -- `align(runs, by='phase')` for multi-batch comparison
- **FDA 21 CFR Part 11 Compliance** -- cryptographic audit trails, electronic signatures, access controls
- **PromQL-style Query Language** -- domain-specific DSL compiled to DuckDB SQL
- **Columnar Storage** -- Apache Arrow + Parquet + DuckDB for fast analytical queries
- **Industrial Connectors** -- InfluxDB, OSIsoft PI Web API import/export
- **Interactive Visualization** -- Plotly-based charts for Jupyter notebooks

## Installation

```bash
pip install sporedb
```

### Optional extras

```bash
pip install sporedb[cloud]       # FastAPI server, SQLAlchemy, Alembic
pip install sporedb[viz]         # Plotly interactive visualizations
pip install sporedb[connectors]  # InfluxDB, PI Web API connectors
pip install sporedb[all]         # Everything
```

## Quick Start

```python
from sporedb import SporeDB

# Connect to a local SporeDB instance
with SporeDB("./my_data") as db:
    # Create a batch
    batch = db.create_batch("CHO-Run-001", strain="CHO-K1")
    print(batch)

    # Import telemetry from CSV
    result = db.import_csv("telemetry.csv", "CHO-Run-001")
    print(f"Imported {result.rows_imported} rows in {result.elapsed_seconds:.2f}s")

    # Detect phases automatically
    phases = db.detect_phases(result.batch_id)
    for phase in phases:
        print(f"  {phase.phase_type.value}: {phase.start_ts} - {phase.end_ts}")

    # Retrieve telemetry as a Pandas DataFrame
    df = db.get_telemetry(result.batch_id)
    print(df.head())
```

Expected output:

```
Batch CHO-Run-001 created (id=019...)
Imported 2847 rows in 0.42s
Detected 4 phases:
  lag: 2024-01-01T00:00 - 2024-01-01T06:00
  exponential: 2024-01-01T06:00 - 2024-01-02T12:00
  stationary: 2024-01-02T12:00 - 2024-01-03T18:00
  decline: 2024-01-03T18:00 - 2024-01-04T00:00
```

## Architecture

SporeDB is a **library-first** database that embeds directly in your Python process:

- **Storage**: Apache Arrow in-memory + Parquet on-disk + DuckDB for SQL analytics
- **Phase Detection**: PELT (offline) and BOCPD (online) changepoint algorithms via `ruptures`
- **Query Language**: PromQL-style DSL parsed by Lark, compiled to DuckDB SQL
- **Compliance**: SHA-256 hash chains + Ed25519 signatures for tamper-evident audit trails
- **Cloud Tier**: Optional FastAPI server with PostgreSQL metadata + S3-compatible object storage

## Deploy

Run SporeDB on your own infrastructure:

```bash
# Quick start with Docker Compose
git clone https://github.com/spore-db/SporeDB.git
cd SporeDB && make generate-keys && make build && make up
```

See the full [Self-Hosted Deployment Guide](deployment/selfhosted.md) for production setup with PostgreSQL and S3-compatible storage.

## Contributing

We welcome contributions! See [Contributing](contributing.md) for development setup, testing, and PR guidelines.

## License

Apache-2.0 -- see [LICENSE](https://github.com/spore-db/SporeDB/blob/main/LICENSE) for details.
