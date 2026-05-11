"""Typed AST nodes for the bioprocess DSL parse tree."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class QueryNode:
    """Root AST node representing a complete DSL query."""

    select: SelectNode
    source: SourceNode
    where: Any | None = None
    group_by: list[FieldRefNode] | None = None
    order_by: OrderByNode | None = None
    limit: int | None = None


@dataclass
class SelectNode:
    """SELECT clause with list of expressions."""

    expressions: list[Any]


@dataclass
class FuncCallNode:
    """Domain or aggregate function call: name(args...)."""

    name: str
    args: list[Any] = field(default_factory=list)


@dataclass
class FieldRefNode:
    """Dotted field reference: e.g. batch.strain, or plain name: e.g. strain."""

    parts: list[str]


@dataclass
class AliasNode:
    """Expression with an alias: expr AS name."""

    expr: Any
    alias: str


@dataclass
class ComparisonNode:
    """Binary comparison: left op right."""

    left: Any
    op: str
    right: Any


@dataclass
class AndNode:
    """Logical AND of two conditions."""

    left: Any
    right: Any


@dataclass
class OrNode:
    """Logical OR of two conditions."""

    left: Any
    right: Any


@dataclass
class NotNode:
    """Logical NOT of a condition."""

    operand: Any


@dataclass
class SourceNode:
    """FROM clause source specification."""

    kind: str  # "all_batches", "single_batch", "golden_ref"
    filter_expr: Any | None = None
    batch_id: str | None = None
    profile_id: str | None = None


@dataclass
class OrderByNode:
    """ORDER BY clause."""

    field: FieldRefNode
    direction: str = "ASC"
