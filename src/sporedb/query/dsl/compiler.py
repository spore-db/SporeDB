"""Compile bioprocess DSL AST to parameterized DuckDB SQL.

Walks the typed AST from BioprocessDSLTransformer and emits:
- DuckDB SQL string with ? placeholders
- Parameter list (positional, matching ? order)

Domain functions (phase_duration, growth_rate, etc.) expand to
SQL subqueries or JOINs. Standard aggregates pass through.
User values are NEVER interpolated into SQL strings.
"""

from __future__ import annotations

import re
from typing import Any

from sporedb.query.dsl.ast_nodes import (
    AliasNode,
    AndNode,
    ComparisonNode,
    FieldRefNode,
    FuncCallNode,
    NotNode,
    OrNode,
    QueryNode,
    SelectNode,
    SourceNode,
)
from sporedb.query.dsl.functions import DOMAIN_FUNCTIONS, SQL_AGGREGATES

# Valid SQL identifier pattern: letters/underscore start, alphanumeric/underscore body.
_SAFE_IDENTIFIER = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")

# Allowlist of valid comparison operators (must match grammar COMP_OP rule).
_VALID_OPS = frozenset({"=", "!=", "<", ">", "<=", ">=", "LIKE"})


class DuckDBCompiler:
    """Compile DSL AST to parameterized DuckDB SQL."""

    def compile(self, query: QueryNode) -> tuple[str, list[object]]:
        """Compile a QueryNode to (sql_string, parameters).

        Returns:
            Tuple of (SQL string with ? placeholders, list of parameter values).
        """
        params: list[object] = []
        joins: list[str] = []

        select_sql = self._compile_select(query.select, params, joins)
        from_sql, source_where = self._compile_source(query.source, params)

        # Build JOIN clause from domain function requirements
        join_sql = ""
        seen_joins: set[str] = set()
        for j in joins:
            if j not in seen_joins:
                join_sql += f" LEFT JOIN {j}"
                seen_joins.add(j)

        # Combine source-level filter (e.g. batch_id = ?) with user WHERE
        where_parts: list[str] = []
        if source_where:
            where_parts.append(source_where)
        if query.where is not None:
            where_parts.append(self._compile_condition(query.where, params, joins))
        where_sql = ""
        if where_parts:
            where_sql = f" WHERE {' AND '.join(where_parts)}"

        group_sql = ""
        if query.group_by:
            fields = ", ".join(
                self._compile_expr(f, params, joins) for f in query.group_by
            )
            group_sql = f" GROUP BY {fields}"

        order_sql = ""
        if query.order_by:
            if query.order_by.direction not in ("ASC", "DESC"):
                raise ValueError(
                    f"Invalid ORDER BY direction: {query.order_by.direction!r}"
                )
            field = self._compile_expr(query.order_by.field, params, joins)
            order_sql = f" ORDER BY {field} {query.order_by.direction}"

        limit_sql = ""
        if query.limit is not None:
            limit_sql = " LIMIT ?"
            params.append(query.limit)

        sql = (
            f"SELECT {select_sql} FROM "
            f"{from_sql}{join_sql}{where_sql}{group_sql}{order_sql}{limit_sql}"
        )
        return sql, params

    def _compile_select(
        self, select: SelectNode, params: list[Any], joins: list[Any]
    ) -> str:
        """Compile SELECT clause expressions."""
        parts: list[str] = []
        for expr in select.expressions:
            parts.append(self._compile_expr(expr, params, joins))
        return ", ".join(parts)

    def _compile_source(self, source: SourceNode, params: list[Any]) -> tuple[str, str]:
        """Compile FROM clause source.

        Returns (from_fragment, source_where_fragment). The caller must
        AND-combine the source_where_fragment with any user WHERE clause.
        """
        if source.kind == "all_batches":
            return "batch_catalog b", ""
        elif source.kind == "single_batch":
            if source.batch_id is not None:
                params.append(source.batch_id)
                return "batch_catalog b", "b.batch_id = ?"
            return "batch_catalog b", ""
        elif source.kind == "golden_ref":
            if source.profile_id is not None:
                params.append(source.profile_id)
                return "golden_profiles g", "g.profile_id = ?"
            return "golden_profiles g", ""
        else:
            return "batch_catalog b", ""

    def _compile_expr(self, expr: object, params: list[Any], joins: list[Any]) -> str:
        """Compile an expression node to SQL fragment."""
        if isinstance(expr, FuncCallNode):
            return self._compile_func(expr, params, joins)
        elif isinstance(expr, FieldRefNode):
            # MD-05: Validate and quote all SQL identifiers
            for p in expr.parts:
                if not _SAFE_IDENTIFIER.match(p):
                    raise ValueError(f"Invalid SQL identifier: {p!r}")
            return ".".join(f'"{p}"' for p in expr.parts)
        elif isinstance(expr, AliasNode):
            inner = self._compile_expr(expr.expr, params, joins)
            if not _SAFE_IDENTIFIER.match(expr.alias):
                raise ValueError(f"Invalid SQL identifier for alias: {expr.alias!r}")
            return f'{inner} AS "{expr.alias}"'
        elif isinstance(expr, str):
            # String literal in expression context -- parameterize
            params.append(expr)
            return "?"
        elif isinstance(expr, (int, float)):
            params.append(expr)
            return "?"
        else:
            raise TypeError(
                f"Cannot compile expression of type {type(expr).__name__}: {expr!r}"
            )

    def _compile_func(
        self, func: FuncCallNode, params: list[Any], joins: list[Any]
    ) -> str:
        """Compile a function call to SQL.

        Domain functions expand to their SQL template with JOINs.
        Standard aggregates pass through as SQL function calls.
        """
        name_lower = func.name.lower()

        # Check domain functions first
        if name_lower in DOMAIN_FUNCTIONS:
            domain_fn = DOMAIN_FUNCTIONS[name_lower]

            # Add required JOIN if any
            if domain_fn.requires_join:
                join_clause = domain_fn.requires_join
                # If the JOIN clause has a ?, add the function's first arg as param
                if "?" in join_clause and func.args:
                    arg = func.args[0]
                    if isinstance(arg, (str, int, float)):
                        params.append(arg)
                joins.append(join_clause)

            return domain_fn.sql_template

        # Standard SQL aggregates pass through
        if name_lower in SQL_AGGREGATES:
            if func.args:
                inner_parts = [self._compile_expr(a, params, joins) for a in func.args]
                inner = ", ".join(inner_parts)
                return f"{name_lower.upper()}({inner})"
            else:
                return f"{name_lower.upper()}(*)"

        raise ValueError(f"Unknown function: {func.name}")

    def _compile_condition(
        self,
        cond: object,
        params: list[Any],
        joins: list[Any] | None = None,
        depth: int = 0,
    ) -> str:
        """Compile a condition node to SQL WHERE fragment."""
        if depth > 50:
            raise ValueError("Query condition nesting exceeds maximum depth of 50")
        if joins is None:
            joins = []
        if isinstance(cond, ComparisonNode):
            if cond.op not in _VALID_OPS:
                raise ValueError(f"Invalid comparison operator: {cond.op!r}")
            left = self._compile_condition_operand(cond.left, params, joins)
            right = self._compile_condition_operand(cond.right, params, joins)
            return f"{left} {cond.op} {right}"
        elif isinstance(cond, AndNode):
            left = self._compile_condition(cond.left, params, joins, depth + 1)
            right = self._compile_condition(cond.right, params, joins, depth + 1)
            return f"({left} AND {right})"
        elif isinstance(cond, OrNode):
            left = self._compile_condition(cond.left, params, joins, depth + 1)
            right = self._compile_condition(cond.right, params, joins, depth + 1)
            return f"({left} OR {right})"
        elif isinstance(cond, NotNode):
            inner = self._compile_condition(cond.operand, params, joins, depth + 1)
            return f"NOT ({inner})"
        else:
            raise TypeError(
                f"Cannot compile condition of type {type(cond).__name__}: {cond!r}"
            )

    def _compile_condition_operand(
        self, operand: object, params: list[Any], joins: list[Any]
    ) -> str:
        """Compile an operand within a condition (field ref or literal)."""
        if isinstance(operand, FieldRefNode):
            # MD-05: Validate and quote all SQL identifiers
            for p in operand.parts:
                if not _SAFE_IDENTIFIER.match(p):
                    raise ValueError(f"Invalid SQL identifier: {p!r}")
            return ".".join(f'"{p}"' for p in operand.parts)
        elif isinstance(operand, FuncCallNode):
            return self._compile_func(operand, params, joins)
        elif isinstance(operand, (str, int, float)):
            params.append(operand)
            return "?"
        else:
            raise TypeError(
                f"Cannot compile operand of type {type(operand).__name__}: {operand!r}"
            )
