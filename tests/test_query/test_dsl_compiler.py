"""Tests for DSL-to-DuckDB SQL compiler and domain function registry."""

from __future__ import annotations

from sporedb.query.dsl.ast_nodes import (
    AndNode,
    ComparisonNode,
    FieldRefNode,
    FuncCallNode,
    OrderByNode,
    QueryNode,
    SelectNode,
    SourceNode,
)
from sporedb.query.dsl.compiler import DuckDBCompiler
from sporedb.query.dsl.functions import DOMAIN_FUNCTIONS, SQL_AGGREGATES

# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _make_query(
    select_exprs: list,
    source_kind: str = "all_batches",
    where=None,
    group_by=None,
    order_by=None,
    limit=None,
    batch_id=None,
    profile_id=None,
) -> QueryNode:
    return QueryNode(
        select=SelectNode(expressions=select_exprs),
        source=SourceNode(
            kind=source_kind,
            batch_id=batch_id,
            profile_id=profile_id,
        ),
        where=where,
        group_by=group_by,
        order_by=order_by,
        limit=limit,
    )


class TestDomainFunctions:
    """Tests for individual domain function SQL expansion."""

    def test_phase_duration_sql(self) -> None:
        compiler = DuckDBCompiler()
        q = _make_query([FuncCallNode("phase_duration", ["exponential"])])
        sql, params = compiler.compile(q)

        assert "p.end_ts" in sql or "phase" in sql.lower()
        assert "exponential" in params

    def test_growth_rate_sql(self) -> None:
        compiler = DuckDBCompiler()
        q = _make_query([FuncCallNode("growth_rate", [])])
        sql, params = compiler.compile(q)

        assert "m.mu" in sql or "mu" in sql

    def test_yield_coefficient_sql(self) -> None:
        compiler = DuckDBCompiler()
        q = _make_query([FuncCallNode("yield_coefficient", [])])
        sql, params = compiler.compile(q)

        assert "yx_s" in sql


class TestCompilation:
    """Tests for full query compilation."""

    def test_basic_select_compile(self) -> None:
        compiler = DuckDBCompiler()
        q = _make_query([FuncCallNode("growth_rate", [])])
        sql, params = compiler.compile(q)

        assert sql.startswith("SELECT")
        assert "FROM" in sql

    def test_where_clause_compile(self) -> None:
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

        assert "WHERE" in sql
        assert "?" in sql
        assert "CHO-K1" in params

    def test_all_batches_source(self) -> None:
        compiler = DuckDBCompiler()
        q = _make_query([FieldRefNode(["strain"])])
        sql, params = compiler.compile(q)

        assert "batch_catalog" in sql

    def test_single_batch_source(self) -> None:
        compiler = DuckDBCompiler()
        q = _make_query(
            [FieldRefNode(["strain"])],
            source_kind="single_batch",
            batch_id="B001",
        )
        sql, params = compiler.compile(q)

        assert "batch_catalog" in sql
        assert "B001" in params


class TestClauses:
    """Tests for GROUP BY, ORDER BY, LIMIT clauses."""

    def test_group_by_compile(self) -> None:
        compiler = DuckDBCompiler()
        q = _make_query(
            [FieldRefNode(["strain"]), FuncCallNode("count", [])],
            group_by=[FieldRefNode(["strain"])],
        )
        sql, params = compiler.compile(q)

        assert "GROUP BY" in sql

    def test_order_by_compile(self) -> None:
        compiler = DuckDBCompiler()
        q = _make_query(
            [FieldRefNode(["strain"])],
            order_by=OrderByNode(field=FieldRefNode(["strain"]), direction="DESC"),
        )
        sql, params = compiler.compile(q)

        assert "ORDER BY" in sql
        assert "DESC" in sql

    def test_limit_compile(self) -> None:
        compiler = DuckDBCompiler()
        q = _make_query(
            [FieldRefNode(["strain"])],
            limit=10,
        )
        sql, params = compiler.compile(q)

        assert "LIMIT ?" in sql
        assert 10 in params

    def test_aggregate_passthrough(self) -> None:
        compiler = DuckDBCompiler()
        q = _make_query(
            [
                FuncCallNode("avg", [FuncCallNode("growth_rate", [])]),
            ]
        )
        sql, params = compiler.compile(q)

        assert "avg(" in sql.lower() or "AVG(" in sql


class TestSecurity:
    """SQL injection prevention tests."""

    def test_no_string_interpolation(self) -> None:
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

        # User value must NOT appear in SQL string
        assert "CHO-K1" not in sql, f"User value leaked into SQL: {sql}"
        # User value MUST appear in params
        assert "CHO-K1" in params, f"User value not in params: {params}"

    def test_parameterized_where(self) -> None:
        compiler = DuckDBCompiler()
        q = _make_query(
            [FieldRefNode(["strain"])],
            where=AndNode(
                left=ComparisonNode(
                    left=FieldRefNode(["strain"]),
                    op="=",
                    right="CHO",
                ),
                right=ComparisonNode(
                    left=FieldRefNode(["scale"]),
                    op=">",
                    right=100.0,
                ),
            ),
        )
        sql, params = compiler.compile(q)

        assert "CHO" not in sql
        assert 100.0 not in sql.split()  # not as literal text
        assert "CHO" in params
        assert 100.0 in params


class TestEndToEnd:
    """End-to-end: parse_query -> compile -> verify SQL and params."""

    def test_end_to_end(self) -> None:
        from sporedb.query.dsl import parse_query

        ast = parse_query("SELECT growth_rate() FROM batches")
        compiler = DuckDBCompiler()
        sql, params = compiler.compile(ast)

        assert isinstance(sql, str)
        assert isinstance(params, list)
        assert "SELECT" in sql
        assert "FROM" in sql

    def test_end_to_end_where(self) -> None:
        from sporedb.query.dsl import parse_query

        ast = parse_query('SELECT strain FROM batches WHERE strain = "CHO-K1"')
        compiler = DuckDBCompiler()
        sql, params = compiler.compile(ast)

        assert "CHO-K1" not in sql
        assert "CHO-K1" in params
        assert "?" in sql


class TestFunctionRegistry:
    """Tests for the function registry itself."""

    def test_domain_functions_keys(self) -> None:
        assert "phase_duration" in DOMAIN_FUNCTIONS
        assert "growth_rate" in DOMAIN_FUNCTIONS
        assert "yield_coefficient" in DOMAIN_FUNCTIONS
        assert "golden_score" in DOMAIN_FUNCTIONS

    def test_sql_aggregates(self) -> None:
        assert "avg" in SQL_AGGREGATES
        assert "count" in SQL_AGGREGATES
        assert "min" in SQL_AGGREGATES
        assert "max" in SQL_AGGREGATES
        assert "sum" in SQL_AGGREGATES
