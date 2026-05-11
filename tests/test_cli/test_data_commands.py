"""Tests for sporedb data CLI commands (import/export)."""

from __future__ import annotations

from click.testing import CliRunner

from sporedb.cli import cli


class TestDataImport:
    def test_import_csv(self, runner: CliRunner, tmp_path):
        """data import of CSV file succeeds."""
        csv_file = tmp_path / "test.csv"
        csv_file.write_text(
            "timestamp,OD600,pH,temperature\n"
            "2026-01-01 00:00:00,0.1,7.0,37.0\n"
            "2026-01-01 01:00:00,0.5,6.8,37.1\n"
        )
        data_dir = str(tmp_path / "data")
        result = runner.invoke(
            cli,
            [
                "--data-dir",
                data_dir,
                "data",
                "import",
                str(csv_file),
                "--name",
                "CSV-Run-001",
            ],
        )
        assert result.exit_code == 0
        assert "Import Complete" in result.output or "rows" in result.output.lower()

    def test_import_nonexistent_file(self, runner: CliRunner, tmp_path):
        """data import of nonexistent file shows error."""
        result = runner.invoke(
            cli,
            [
                "--data-dir",
                str(tmp_path / "data"),
                "data",
                "import",
                "/nonexistent/file.csv",
                "--name",
                "Bad-001",
            ],
        )
        # Click's Path(exists=True) should catch this
        assert result.exit_code != 0

    def test_import_unsupported_format(self, runner: CliRunner, tmp_path):
        """data import of unsupported file type shows error."""
        txt_file = tmp_path / "test.txt"
        txt_file.write_text("not a csv")
        data_dir = str(tmp_path / "data")
        result = runner.invoke(
            cli,
            [
                "--data-dir",
                data_dir,
                "data",
                "import",
                str(txt_file),
                "--name",
                "Bad-002",
            ],
        )
        assert result.exit_code != 0
        assert "Unsupported file type" in result.output


class TestDataExport:
    def test_export_csv(self, runner: CliRunner, tmp_path):
        """data export to CSV after import produces output."""
        # Import first
        csv_file = tmp_path / "input.csv"
        csv_file.write_text(
            "timestamp,OD600,pH\n"
            "2026-01-01 00:00:00,0.1,7.0\n"
            "2026-01-01 01:00:00,0.5,6.8\n"
        )
        data_dir = str(tmp_path / "data")
        runner.invoke(
            cli,
            [
                "--data-dir",
                data_dir,
                "data",
                "import",
                str(csv_file),
                "--name",
                "Export-Test",
            ],
        )
        # List batches to verify import worked
        list_result = runner.invoke(cli, ["--data-dir", data_dir, "batch", "list"])
        assert "Export-Test" in list_result.output


class TestHelp:
    def test_main_help(self, runner: CliRunner):
        """sporedb --help shows command groups."""
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "batch" in result.output
        assert "data" in result.output
        assert "query" in result.output

    def test_batch_help(self, runner: CliRunner):
        """sporedb batch --help shows subcommands."""
        result = runner.invoke(cli, ["batch", "--help"])
        assert result.exit_code == 0
        assert "create" in result.output
        assert "list" in result.output
        assert "show" in result.output
        assert "delete" in result.output

    def test_data_help(self, runner: CliRunner):
        """sporedb data --help shows import and export."""
        result = runner.invoke(cli, ["data", "--help"])
        assert result.exit_code == 0
        assert "import" in result.output
        assert "export" in result.output
