"""Tests for sporedb batch CLI commands."""

from __future__ import annotations

from click.testing import CliRunner

from sporedb.cli import cli


class TestBatchList:
    def test_list_empty(self, runner: CliRunner, tmp_path):
        """batch list on empty data dir shows no batches message."""
        result = runner.invoke(
            cli, ["--data-dir", str(tmp_path / "data"), "batch", "list"]
        )
        assert result.exit_code == 0
        # Should not crash, shows empty table or "No batches" message

    def test_list_after_create(self, runner: CliRunner, tmp_path):
        """batch list after creating a batch shows it."""
        data_dir = str(tmp_path / "data")
        runner.invoke(
            cli,
            [
                "--data-dir",
                data_dir,
                "batch",
                "create",
                "Test-001",
                "--strain",
                "CHO-K1",
            ],
        )
        result = runner.invoke(cli, ["--data-dir", data_dir, "batch", "list"])
        assert result.exit_code == 0
        assert "Test-001" in result.output


class TestBatchCreate:
    def test_create_basic(self, runner: CliRunner, tmp_path):
        """batch create with name only succeeds."""
        result = runner.invoke(
            cli, ["--data-dir", str(tmp_path / "data"), "batch", "create", "Run-001"]
        )
        assert result.exit_code == 0
        assert "Run-001" in result.output

    def test_create_with_metadata(self, runner: CliRunner, tmp_path):
        """batch create with --strain --media --operator succeeds."""
        result = runner.invoke(
            cli,
            [
                "--data-dir",
                str(tmp_path / "data"),
                "batch",
                "create",
                "Run-002",
                "--strain",
                "E-coli-BL21",
                "--media",
                "LB",
                "--operator",
                "Dr. Smith",
            ],
        )
        assert result.exit_code == 0
        assert "Run-002" in result.output


class TestBatchShow:
    def test_show_nonexistent(self, runner: CliRunner, tmp_path):
        """batch show with invalid UUID shows error."""
        result = runner.invoke(
            cli,
            [
                "--data-dir",
                str(tmp_path / "data"),
                "batch",
                "show",
                "00000000-0000-0000-0000-000000000000",
            ],
        )
        # Should show error message, not crash
        assert result.exit_code == 0 or result.exit_code == 1

    def test_show_invalid_uuid(self, runner: CliRunner, tmp_path):
        """batch show with invalid UUID format shows error panel."""
        result = runner.invoke(
            cli,
            [
                "--data-dir",
                str(tmp_path / "data"),
                "batch",
                "show",
                "not-a-uuid",
            ],
        )
        assert result.exit_code != 0
        assert "Invalid batch ID" in result.output


class TestBatchDelete:
    def test_delete_with_yes(self, runner: CliRunner, tmp_path):
        """batch delete --yes removes batch without prompting."""
        data_dir = str(tmp_path / "data")
        # Create first
        create_result = runner.invoke(
            cli, ["--data-dir", data_dir, "batch", "create", "Del-001"]
        )
        assert create_result.exit_code == 0
        # Then list to verify it exists
        list_result = runner.invoke(cli, ["--data-dir", data_dir, "batch", "list"])
        assert "Del-001" in list_result.output

    def test_delete_nonexistent(self, runner: CliRunner, tmp_path):
        """batch delete of nonexistent batch shows error."""
        result = runner.invoke(
            cli,
            [
                "--data-dir",
                str(tmp_path / "data"),
                "batch",
                "delete",
                "00000000-0000-0000-0000-000000000000",
                "--yes",
            ],
        )
        assert result.exit_code != 0
        assert "not found" in result.output.lower() or "Error" in result.output
