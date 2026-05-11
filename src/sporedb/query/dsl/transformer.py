"""Transform Lark parse tree to typed AST nodes for the bioprocess DSL."""

from __future__ import annotations

from typing import Any

from lark import Token, Transformer, v_args

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

# Domain function names that are recognized as reserved keywords.
# These are distinguished from field references during transformation.
DOMAIN_FUNCTIONS = frozenset(
    {
        "phase_duration",
        "growth_rate",
        "yield_coefficient",
        "golden_score",
        "compare",
        "align",
        "avg",
        "min",
        "max",
        "sum",
        "count",
    }
)


class BioprocessDSLTransformer(Transformer[Any, QueryNode]):
    """Transform Lark parse tree to typed AST nodes."""

    def start(self, items: list[Any]) -> QueryNode:
        return items[0]  # type: ignore[no-any-return]

    def query(self, items: list[Any]) -> QueryNode:
        """Build QueryNode from parsed clauses.

        Items order: select_clause, from_clause, then optional
        where/group/order/limit in parse order.
        """
        select = items[0]
        source = items[1]
        where = None
        group_by = None
        order_by = None
        limit = None
        for item in items[2:]:
            if isinstance(item, (ComparisonNode, AndNode, OrNode, NotNode)):
                where = item
            elif isinstance(item, list) and item and isinstance(item[0], FieldRefNode):
                group_by = item
            elif isinstance(item, OrderByNode):
                order_by = item
            elif isinstance(item, int):
                limit = item
        return QueryNode(
            select=select,
            source=source,
            where=where,
            group_by=group_by,
            order_by=order_by,
            limit=limit,
        )

    def select_clause(self, items: list[Any]) -> SelectNode:
        return SelectNode(expressions=list(items))

    def from_clause(self, items: list[Any]) -> SourceNode:
        return items[0]  # type: ignore[no-any-return]

    def all_batches(self, items: list[Any]) -> SourceNode:
        filter_expr = items[0] if items else None
        return SourceNode(kind="all_batches", filter_expr=filter_expr)

    def single_batch(self, items: list[Any]) -> SourceNode:
        batch_id = str(items[0])[1:-1]  # strip quotes from ESCAPED_STRING
        return SourceNode(kind="single_batch", batch_id=batch_id)

    def golden_ref(self, items: list[Any]) -> SourceNode:
        profile_id = str(items[0])[1:-1]
        return SourceNode(kind="golden_ref", profile_id=profile_id)

    def filter_expr(self, items: list[Any]) -> object:
        return items[0]

    def where_clause(self, items: list[Any]) -> object:
        return items[0]

    def group_clause(self, items: list[Any]) -> list[FieldRefNode]:
        return list(items)

    def order_clause(self, items: list[Any]) -> OrderByNode:
        field_node = items[0]
        direction = "ASC"
        if len(items) > 1:
            direction = str(items[1]).upper()
        return OrderByNode(field=field_node, direction=direction)

    def direction(self, items: list[Any]) -> str:
        return str(items[0]).upper()

    def limit_clause(self, items: list[Any]) -> int:
        return int(items[0])

    def func_call(self, items: list[Any]) -> FuncCallNode:
        name = str(items[0])
        args = items[1] if len(items) > 1 else []
        return FuncCallNode(name=name, args=args)

    def args(self, items: list[Any]) -> list[Any]:
        return list(items)

    def field_ref(self, items: list[Any]) -> FieldRefNode:
        return FieldRefNode(parts=[str(i) for i in items])

    def alias_expr(self, items: list[Any]) -> AliasNode:
        return AliasNode(expr=items[0], alias=str(items[1]))

    def comparison(self, items: list[Any]) -> ComparisonNode:
        return ComparisonNode(left=items[0], op=str(items[1]), right=items[2])

    def and_cond(self, items: list[Any]) -> AndNode:
        return AndNode(left=items[0], right=items[1])

    def or_cond(self, items: list[Any]) -> OrNode:
        return OrNode(left=items[0], right=items[1])

    def not_cond(self, items: list[Any]) -> NotNode:
        return NotNode(operand=items[0])

    @v_args(inline=True)
    def number(self, n: Token) -> float:
        return float(n)

    @v_args(inline=True)
    def string(self, s: Token) -> str:
        return str(s)[1:-1]
