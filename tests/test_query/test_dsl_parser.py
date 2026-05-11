"""Tests for the bioprocess DSL parser and transformer."""

from __future__ import annotations

import pytest
from lark.exceptions import UnexpectedInput

from sporedb.query.dsl import parse_query
from sporedb.query.dsl.ast_nodes import (
    AliasNode,
    AndNode,
    ComparisonNode,
    FieldRefNode,
    FuncCallNode,
    NotNode,
    OrderByNode,
    OrNode,
    QueryNode,
    SelectNode,
    SourceNode,
)


class TestBasicParsing:
    """Test basic SELECT/FROM parsing."""

    def test_basic_select(self) -> None:
        ast = parse_query("SELECT growth_rate() FROM batches")
        assert isinstance(ast, QueryNode)
        assert isinstance(ast.select, SelectNode)
        assert len(ast.select.expressions) == 1
        expr = ast.select.expressions[0]
        assert isinstance(expr, FuncCallNode)
        assert expr.name == "growth_rate"

    def test_select_with_where(self) -> None:
        ast = parse_query(
            'SELECT phase_duration("exponential") FROM batches WHERE strain = "CHO-K1"'
        )
        assert isinstance(ast, QueryNode)
        assert isinstance(ast.where, ComparisonNode)
        assert ast.where.op == "="

    def test_single_batch_source(self) -> None:
        ast = parse_query('SELECT growth_rate() FROM batch("B001")')
        assert isinstance(ast.source, SourceNode)
        assert ast.source.kind == "single_batch"
        assert ast.source.batch_id == "B001"

    def test_multiple_select_exprs(self) -> None:
        ast = parse_query("SELECT growth_rate(), yield_coefficient() FROM batches")
        assert len(ast.select.expressions) == 2
        assert all(isinstance(e, FuncCallNode) for e in ast.select.expressions)

    def test_all_batches_source(self) -> None:
        ast = parse_query("SELECT growth_rate() FROM batches")
        assert isinstance(ast.source, SourceNode)
        assert ast.source.kind == "all_batches"

    def test_golden_ref_source(self) -> None:
        ast = parse_query('SELECT golden_score() FROM golden_profile("profile_1")')
        assert ast.source.kind == "golden_ref"
        assert ast.source.profile_id == "profile_1"


class TestExpressions:
    """Test expression parsing: field refs, aliases, function calls."""

    def test_field_ref(self) -> None:
        ast = parse_query("SELECT batch.strain FROM batches")
        expr = ast.select.expressions[0]
        assert isinstance(expr, FieldRefNode)
        assert expr.parts == ["batch", "strain"]

    def test_alias_expr(self) -> None:
        ast = parse_query("SELECT growth_rate() AS mu FROM batches")
        expr = ast.select.expressions[0]
        assert isinstance(expr, AliasNode)
        assert expr.alias == "mu"
        assert isinstance(expr.expr, FuncCallNode)

    def test_func_call_with_args(self) -> None:
        ast = parse_query('SELECT phase_duration("exponential") FROM batches')
        func = ast.select.expressions[0]
        assert isinstance(func, FuncCallNode)
        assert func.name == "phase_duration"
        assert len(func.args) == 1
        assert func.args[0] == "exponential"

    def test_func_call_no_args(self) -> None:
        ast = parse_query("SELECT count() FROM batches")
        func = ast.select.expressions[0]
        assert isinstance(func, FuncCallNode)
        assert func.name == "count"
        assert func.args == []

    def test_nested_func_call(self) -> None:
        ast = parse_query("SELECT avg(growth_rate()) FROM batches")
        outer = ast.select.expressions[0]
        assert isinstance(outer, FuncCallNode)
        assert outer.name == "avg"
        assert len(outer.args) == 1
        inner = outer.args[0]
        assert isinstance(inner, FuncCallNode)
        assert inner.name == "growth_rate"


class TestConditions:
    """Test WHERE clause condition parsing."""

    def test_and_condition(self) -> None:
        ast = parse_query(
            "SELECT growth_rate() FROM batches "
            'WHERE strain = "CHO-K1" AND media = "CD-CHO"'
        )
        assert isinstance(ast.where, AndNode)
        assert isinstance(ast.where.left, ComparisonNode)
        assert isinstance(ast.where.right, ComparisonNode)

    def test_or_condition(self) -> None:
        ast = parse_query(
            "SELECT growth_rate() FROM batches "
            'WHERE strain = "CHO-K1" OR strain = "HEK293"'
        )
        assert isinstance(ast.where, OrNode)

    def test_not_condition(self) -> None:
        ast = parse_query(
            'SELECT growth_rate() FROM batches WHERE NOT strain = "CHO-K1"'
        )
        assert isinstance(ast.where, NotNode)
        assert isinstance(ast.where.operand, ComparisonNode)

    def test_comparison_operators(self) -> None:
        for op in ["=", "!=", "<", ">", "<=", ">="]:
            ast = parse_query(f"SELECT growth_rate() FROM batches WHERE value {op} 10")
            assert isinstance(ast.where, ComparisonNode)
            assert ast.where.op == op


class TestClauses:
    """Test GROUP BY, ORDER BY, and LIMIT clauses."""

    def test_group_by(self) -> None:
        ast = parse_query(
            "SELECT strain, avg(growth_rate()) FROM batches GROUP BY strain"
        )
        assert ast.group_by is not None
        assert len(ast.group_by) == 1
        assert isinstance(ast.group_by[0], FieldRefNode)

    def test_order_by(self) -> None:
        ast = parse_query("SELECT growth_rate() FROM batches ORDER BY batch.name DESC")
        assert ast.order_by is not None
        assert isinstance(ast.order_by, OrderByNode)
        assert ast.order_by.direction == "DESC"

    def test_order_by_default_asc(self) -> None:
        ast = parse_query("SELECT growth_rate() FROM batches ORDER BY batch.name")
        assert ast.order_by is not None
        assert ast.order_by.direction == "ASC"

    def test_limit(self) -> None:
        ast = parse_query("SELECT growth_rate() FROM batches LIMIT 10")
        assert ast.limit == 10


class TestEdgeCases:
    """Test edge cases: case insensitivity, comments, errors."""

    def test_case_insensitive(self) -> None:
        ast = parse_query("select growth_rate() from batches")
        assert isinstance(ast, QueryNode)
        assert isinstance(ast.select.expressions[0], FuncCallNode)

    def test_comment_ignored(self) -> None:
        ast = parse_query("SELECT growth_rate() FROM batches -- this is a comment")
        assert isinstance(ast, QueryNode)

    def test_malformed_query_raises(self) -> None:
        with pytest.raises(UnexpectedInput):
            parse_query("INVALID GARBAGE")

    def test_incomplete_query_raises(self) -> None:
        with pytest.raises(UnexpectedInput):
            parse_query("SELECT FROM")

    def test_mixed_case_keywords(self) -> None:
        ast = parse_query('Select growth_rate() From batches Where strain = "CHO"')
        assert isinstance(ast, QueryNode)
        assert isinstance(ast.where, ComparisonNode)
