"""Shared CLI test fixtures."""

from __future__ import annotations

import pytest
from click.testing import CliRunner


@pytest.fixture
def runner() -> CliRunner:
    """Click CliRunner for invoking CLI commands in tests."""
    return CliRunner()
