"""Security tests for DSL-to-DuckDB SQL compiler.

Verifies MD-05: SQL identifier quoting and injection prevention.
"""

from __future__ import annotations

import pytest

from sporedb.query.dsl.ast_nodes import (
    ComparisonNode,
    FieldRefNode,
    QueryNode,
    SelectNode,
    SourceNode,
)
from sporedb.query.dsl.compiler import DuckDBCompiler


def _make_query(select_exprs, where=None):
    return QueryNode(
        select=SelectNode(expressions=select_exprs),
        source=SourceNode(kind="all_batches"),
        where=where,
        group_by=None,
        order_by=None,
        limit=None,
    )


class TestFieldRefQuoting:
    """MD-05: FieldRefNode must produce quoted identifiers."""

    def test_single_part_quoted(self) -> None:
        compiler = DuckDBCompiler()
        q = _make_query([FieldRefNode(["batch_id"])])
        sql, _params = compiler.compile(q)

        assert '"batch_id"' in sql

    def test_dotted_parts_quoted(self) -> None:
        compiler = DuckDBCompiler()
        q = _make_query([FieldRefNode(["b", "batch_id"])])
        sql, _params = compiler.compile(q)

        assert '"b"."batch_id"' in sql

    def test_where_field_refs_quoted(self) -> None:
        compiler = DuckDBCompiler()
        q = _make_query(
            [FieldRefNode(["strain"])],
            where=ComparisonNode(
                left=FieldRefNode(["strain"]),
                op="=",
                right="CHO-K1",
            ),
        )
        sql, params = compiler.compile(q)

        # Field ref in WHERE should be quoted
        assert '"strain"' in sql
        # User value should NOT be in SQL (parameterized)
        assert "CHO-K1" not in sql
        assert "CHO-K1" in params


class TestIdentifierInjection:
    """MD-05: Invalid identifier characters raise ValueError."""

    def test_sql_injection_in_identifier_rejected(self) -> None:
        compiler = DuckDBCompiler()
        q = _make_query([FieldRefNode(["; DROP TABLE batches"])])

        with pytest.raises(ValueError, match="Invalid SQL identifier"):
            compiler.compile(q)

    def test_quote_in_identifier_rejected(self) -> None:
        compiler = DuckDBCompiler()
        q = _make_query([FieldRefNode(['batch"id'])])

        with pytest.raises(ValueError, match="Invalid SQL identifier"):
            compiler.compile(q)

    def test_space_in_identifier_rejected(self) -> None:
        compiler = DuckDBCompiler()
        q = _make_query([FieldRefNode(["batch id"])])

        with pytest.raises(ValueError, match="Invalid SQL identifier"):
            compiler.compile(q)

    def test_dash_in_identifier_rejected(self) -> None:
        compiler = DuckDBCompiler()
        q = _make_query([FieldRefNode(["batch-id"])])

        with pytest.raises(ValueError, match="Invalid SQL identifier"):
            compiler.compile(q)

    def test_valid_identifiers_pass(self) -> None:
        compiler = DuckDBCompiler()
        q = _make_query([FieldRefNode(["batch_id"])])

        # Should not raise
        sql, _params = compiler.compile(q)
        assert '"batch_id"' in sql

    def test_where_injection_rejected(self) -> None:
        compiler = DuckDBCompiler()
        q = _make_query(
            [FieldRefNode(["strain"])],
            where=ComparisonNode(
                left=FieldRefNode(["1; DROP TABLE batches--"]),
                op="=",
                right="x",
            ),
        )

        with pytest.raises(ValueError, match="Invalid SQL identifier"):
            compiler.compile(q)
