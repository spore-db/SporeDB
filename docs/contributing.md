<!-- This page mirrors CONTRIBUTING.md at the repo root. Keep both in sync. -->

# Contributing to SporeDB

Thank you for your interest in contributing to SporeDB! This guide will help you
get set up for development and submit your first pull request.

## Development Setup

### Prerequisites

- Python 3.11 or later
- Git
- [Hatch](https://hatch.pypa.io/) (Python project manager)

### Getting Started

```bash
# 1. Clone the repository
git clone https://github.com/spore-db/SporeDB.git
cd SporeDB

# 2. Create the development environment
hatch env create

# 3. Run the test suite to verify everything works
hatch run test
```

## Running Tests

```bash
# Quick test run (stops on first failure)
hatch run test

# Or use pytest directly
pytest tests/ -x -q --tb=short

# Run with coverage
pytest tests/ --cov=src/sporedb --cov-report=term-missing

# Run a specific test file
pytest tests/test_batch.py -x -q
```

The project has 775+ tests. A full run takes about 2 minutes.

## Code Style

SporeDB uses [ruff](https://docs.astral.sh/ruff/) for linting and formatting:

```bash
# Check for lint issues
ruff check src/ tests/

# Auto-fix lint issues
ruff check --fix src/ tests/

# Check formatting
ruff format --check src/ tests/

# Auto-format
ruff format src/ tests/
```

Configuration is in `pyproject.toml`:
- Line length: 88
- Target Python: 3.11
- Rules: E, F, I, UP, B, SIM

**No pre-commit hooks** -- CI catches all issues. We prefer a frictionless
development experience for scientists and engineers.

## Type Checking

SporeDB uses strict mypy type checking:

```bash
mypy src/sporedb/
```

Configuration in `pyproject.toml`: `strict = true` with `pydantic.mypy` plugin.

All public API functions and classes must have complete type annotations.

## Submitting a Pull Request

1. Create a branch from `main`:
   ```bash
   git checkout -b my-feature
   ```

2. Make your changes and add tests for new functionality.

3. Verify all checks pass locally:
   ```bash
   ruff check src/ tests/
   ruff format --check src/ tests/
   mypy src/sporedb/
   pytest tests/ -x -q
   ```

4. Push and open a PR against `main`. Fill in the PR template.

5. CI will run lint, type check, tests (Python 3.11-3.13), and build.

## Project Structure

```
SporeDB/
  src/sporedb/          # Main package
    analytics/          # Phase detection, alignment, golden batch
    cloud/              # FastAPI cloud tier
    cli/                # Click CLI
    compliance/         # Audit trails, signatures, RBAC
    connectors/         # InfluxDB, PI Web API
    export/             # CSV, Parquet, Arrow export
    ingestion/          # CSV, Excel import
    models/             # Pydantic data models
    query/              # PromQL-style DSL (Lark parser)
    storage/            # DuckDB + Parquet storage engine
    viz/                # Plotly charts
    client.py           # SporeDB main entry point
  tests/                # pytest test suite
  docs/                 # Documentation
```

## Questions?

Open an issue with the [Feature Request](https://github.com/spore-db/SporeDB/issues/new?template=feature-request.yml) template or start a discussion.
