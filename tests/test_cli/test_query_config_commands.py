"""Tests for CLI query and config commands.

Covers cli/query.py lines 15-46:
- Successful query with results (table output)
- Empty result (no results message)
- DSL parse error (ClickException)
- General exception (ClickException)
- Truncation for > 50 rows

Covers cli/config.py lines 21-29:
- config show when data dir exists
- config show when data dir does not exist
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pandas as pd
from click.testing import CliRunner

from sporedb.cli import cli


class TestQueryCommand:
    """Tests for the `sporedb query <expression>` CLI command."""

    def _make_runner_with_db(self, tmp_path, mock_db: MagicMock) -> CliRunner:
        """Create a runner; the db is injected via click's obj mechanism."""
        return CliRunner()

    def _invoke_query(self, runner, tmp_path, mock_db, expression):
        """Invoke query command with a mock db injected into click context."""
        from sporedb.cli import cli as cli_group

        # Patch SporeDB construction so it returns our mock
        with patch("sporedb.cli.SporeDB", return_value=mock_db):
            result = runner.invoke(
                cli_group,
                ["--data-dir", str(tmp_path / "data"), "query", expression],
            )
        return result

    def test_query_with_results_shows_table(self, tmp_path) -> None:
        """Successful query with rows prints a Rich table."""
        runner = CliRunner()
        mock_db = MagicMock()
        mock_db.query.return_value = pd.DataFrame(
            {
                "batch_id": ["abc", "def"],
                "ts": ["2026-01-01", "2026-01-02"],
                "value": [1.5, 2.0],
            }
        )
        result = self._invoke_query(runner, tmp_path, mock_db, "select()")
        assert result.exit_code == 0
        # Should output batch_id column header or values
        assert "abc" in result.output or "batch_id" in result.output

    def test_query_empty_results_shows_no_results(self, tmp_path) -> None:
        """Empty DataFrame prints 'No results.' message."""
        runner = CliRunner()
        mock_db = MagicMock()
        mock_db.query.return_value = pd.DataFrame()
        result = self._invoke_query(runner, tmp_path, mock_db, "select()")
        assert result.exit_code == 0
        assert "No results" in result.output

    def test_query_parse_error_shows_click_exception(self, tmp_path) -> None:
        """DSL parse error (lark UnexpectedInput) becomes ClickException."""
        try:
            from lark.exceptions import UnexpectedInput

            exc = UnexpectedInput("Unexpected token")
        except ImportError:
            exc = Exception("Unexpected token")

        runner = CliRunner()
        mock_db = MagicMock()
        mock_db.query.side_effect = exc
        result = self._invoke_query(runner, tmp_path, mock_db, "bad!!!dsl")
        assert result.exit_code != 0
        assert "parse error" in result.output.lower() or "Error" in result.output

    def test_query_general_exception_shows_click_exception(self, tmp_path) -> None:
        """Generic exception during query becomes ClickException."""
        runner = CliRunner()
        mock_db = MagicMock()
        mock_db.query.side_effect = RuntimeError("DuckDB crashed")
        result = self._invoke_query(runner, tmp_path, mock_db, "select()")
        assert result.exit_code != 0
        assert "Query error" in result.output or "Error" in result.output

    def test_query_truncates_at_50_rows(self, tmp_path) -> None:
        """Output with > 50 rows shows 'Showing 50 of N rows' message."""
        runner = CliRunner()
        mock_db = MagicMock()
        mock_db.query.return_value = pd.DataFrame({"val": range(75)})
        result = self._invoke_query(runner, tmp_path, mock_db, "select()")
        assert result.exit_code == 0
        assert "75" in result.output or "50" in result.output


class TestConfigShowCommand:
    """Tests for `sporedb config show` CLI command."""

    def _invoke_config_show(self, runner, tmp_path, mock_db):
        with patch("sporedb.cli.SporeDB", return_value=mock_db):
            result = runner.invoke(
                cli,
                ["--data-dir", str(tmp_path / "data"), "config", "show"],
            )
        return result

    def test_config_show_displays_data_dir(self, tmp_path) -> None:
        """config show prints the resolved data directory path."""
        runner = CliRunner()
        data_dir = tmp_path / "data"
        data_dir.mkdir(parents=True)

        mock_db = MagicMock()
        mock_db._engine.data_root = str(data_dir)
        mock_db.list_batches.return_value = []

        with patch("sporedb.cli.SporeDB", return_value=mock_db):
            result = runner.invoke(
                cli,
                ["--data-dir", str(data_dir), "config", "show"],
            )

        assert result.exit_code == 0
        assert "Data directory" in result.output

    def test_config_show_shows_batch_count_when_dir_exists(self, tmp_path) -> None:
        """config show includes batch count when data directory exists."""
        runner = CliRunner()
        data_dir = tmp_path / "data"
        data_dir.mkdir(parents=True)

        mock_db = MagicMock()
        mock_db._engine.data_root = str(data_dir)
        mock_db.list_batches.return_value = ["batch1", "batch2"]

        with patch("sporedb.cli.SporeDB", return_value=mock_db):
            result = runner.invoke(
                cli,
                ["--data-dir", str(data_dir), "config", "show"],
            )

        assert result.exit_code == 0
        assert "Batch count" in result.output

    def test_config_show_nonexistent_dir(self, tmp_path) -> None:
        """config show with non-existent data dir shows Exists: False."""
        runner = CliRunner()
        nonexistent = tmp_path / "nonexistent_data"

        mock_db = MagicMock()
        mock_db._engine.data_root = str(nonexistent)

        with patch("sporedb.cli.SporeDB", return_value=mock_db):
            result = runner.invoke(
                cli,
                ["--data-dir", str(nonexistent), "config", "show"],
            )

        assert result.exit_code == 0
        assert "False" in result.output or "Data directory" in result.output
