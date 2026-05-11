"""Tests for sporedb demo CLI commands."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner

from sporedb.cli import cli


class TestDemoLoad:
    def test_demo_load(self, runner: CliRunner, tmp_path: Path):
        """demo load imports data and prints summary table."""
        demo_data = tmp_path / "demo_data"
        with (
            patch("sporedb.cli.demo.DEMO_DIR", tmp_path),
            patch("sporedb.cli.demo.DEMO_DATA", demo_data),
        ):
            result = runner.invoke(
                cli, ["--data-dir", str(tmp_path / "db"), "demo", "load"]
            )
            assert result.exit_code == 0, result.output
            assert "Demo Data Loaded" in result.output
            assert demo_data.exists()

    def test_demo_load_idempotent(self, runner: CliRunner, tmp_path: Path):
        """demo load skips if already loaded."""
        demo_data = tmp_path / "demo_data"
        demo_data.mkdir(parents=True)
        with (
            patch("sporedb.cli.demo.DEMO_DIR", tmp_path),
            patch("sporedb.cli.demo.DEMO_DATA", demo_data),
        ):
            result = runner.invoke(
                cli, ["--data-dir", str(tmp_path / "db"), "demo", "load"]
            )
            assert result.exit_code == 0
            assert "already loaded" in result.output

    def test_demo_load_force(self, runner: CliRunner, tmp_path: Path):
        """demo load --force reloads even if data exists."""
        demo_data = tmp_path / "demo_data"
        demo_data.mkdir(parents=True)
        with (
            patch("sporedb.cli.demo.DEMO_DIR", tmp_path),
            patch("sporedb.cli.demo.DEMO_DATA", demo_data),
        ):
            result = runner.invoke(
                cli,
                ["--data-dir", str(tmp_path / "db"), "demo", "load", "--force"],
            )
            assert result.exit_code == 0, result.output
            assert "Demo Data Loaded" in result.output


class TestDemoClean:
    def test_demo_clean(self, runner: CliRunner, tmp_path: Path):
        """demo clean removes demo data."""
        demo_data = tmp_path / "demo_data"
        demo_data.mkdir(parents=True)
        (demo_data / "test.db").touch()
        with (
            patch("sporedb.cli.demo.DEMO_DIR", tmp_path),
            patch("sporedb.cli.demo.DEMO_DATA", demo_data),
        ):
            result = runner.invoke(cli, ["demo", "clean"])
            assert result.exit_code == 0
            assert "removed" in result.output
            assert not demo_data.exists()

    def test_demo_clean_no_data(self, runner: CliRunner, tmp_path: Path):
        """demo clean when no data exists prints message."""
        demo_data = tmp_path / "demo_data"
        with (
            patch("sporedb.cli.demo.DEMO_DIR", tmp_path),
            patch("sporedb.cli.demo.DEMO_DATA", demo_data),
        ):
            result = runner.invoke(cli, ["demo", "clean"])
            assert result.exit_code == 0
            assert "No demo data" in result.output
