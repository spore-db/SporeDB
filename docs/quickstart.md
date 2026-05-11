# Quick Start

Get started with SporeDB in under 5 minutes.

## Installation

```bash
pip install sporedb
```

For cloud tier features (FastAPI server, PostgreSQL metadata):

```bash
pip install sporedb[cloud]
```

For visualization (Plotly charts in Jupyter):

```bash
pip install sporedb[viz]
```

For everything:

```bash
pip install sporedb[all]
```

## Create Your First Batch

```python
from sporedb import SporeDB

with SporeDB("./my_data") as db:
    # Create a fermentation batch
    batch = db.create_batch("CHO-Run-001", strain="CHO-K1")
    print(batch)
```

## Import Telemetry Data

```python
    # Import time-series telemetry from CSV
    result = db.import_csv("telemetry.csv", "CHO-Run-001")
    print(f"Imported {result.rows_imported} rows in {result.elapsed_seconds:.2f}s")
```

Your CSV should have a timestamp column and one or more measurement columns
(e.g., `dissolved_oxygen`, `ph`, `temperature`, `optical_density`).

## Detect Phases

```python
    # Automatically detect fermentation phases
    phases = db.detect_phases(result.batch_id)
    for phase in phases:
        print(f"  {phase.phase_type.value}: {phase.start_ts} - {phase.end_ts}")
```

SporeDB uses the PELT algorithm (via `ruptures`) to detect changepoints
in the telemetry signal and classify phases as lag, exponential, stationary,
or decline.

## Retrieve and Analyze

```python
    # Get telemetry as a Pandas DataFrame
    df = db.get_telemetry(result.batch_id)
    print(df.head())
```

## Next Steps

- [Self-Hosted Deployment](deployment/selfhosted.md) -- run SporeDB on your infrastructure
- [API Reference](reference/index.md) -- full API documentation
- [Contributing](contributing.md) -- help improve SporeDB
