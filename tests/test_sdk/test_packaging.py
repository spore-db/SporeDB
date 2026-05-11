"""Tests for package metadata and public API exports."""

from __future__ import annotations

import tomllib
from pathlib import Path


def test_version_defined():
    import sporedb

    assert hasattr(sporedb, "__version__")
    assert sporedb.__version__ == "0.1.0"


def test_sporedb_class_exported():
    from sporedb import SporeDB

    assert callable(SporeDB)


def test_public_api_exports():
    from sporedb import (
        Batch,
        ImportResult,
        PhaseAnnotation,
        SporeDB,
    )

    # All names should be importable without error
    assert SporeDB is not None
    assert Batch is not None
    assert ImportResult is not None
    assert PhaseAnnotation is not None


def test_license_is_apache():
    """Verify pyproject.toml declares Apache-2.0."""
    pyproject = Path(__file__).parent.parent.parent / "pyproject.toml"
    with open(pyproject, "rb") as f:
        data = tomllib.load(f)
    assert data["project"]["license"] == "Apache-2.0"


def test_console_scripts_entry_point():
    """Verify pyproject.toml declares sporedb console script."""
    pyproject = Path(__file__).parent.parent.parent / "pyproject.toml"
    with open(pyproject, "rb") as f:
        data = tomllib.load(f)
    assert "sporedb" in data["project"]["scripts"]
    assert data["project"]["scripts"]["sporedb"] == "sporedb.cli:cli"


def test_classifiers_include_apache():
    """Verify pyproject.toml has Apache classifier."""
    pyproject = Path(__file__).parent.parent.parent / "pyproject.toml"
    with open(pyproject, "rb") as f:
        data = tomllib.load(f)
    classifiers = data["project"]["classifiers"]
    assert any("Apache" in c for c in classifiers)


def test_project_urls():
    """Verify pyproject.toml has homepage and repository URLs."""
    pyproject = Path(__file__).parent.parent.parent / "pyproject.toml"
    with open(pyproject, "rb") as f:
        data = tomllib.load(f)
    urls = data["project"]["urls"]
    assert "Homepage" in urls
    assert "Repository" in urls
