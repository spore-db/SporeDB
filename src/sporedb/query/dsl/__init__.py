"""SporeDB bioprocess DSL: PromQL-style query language for batch analytics.

Public API:
- parse_query(query_string) -> QueryNode AST
- DuckDBCompiler: AST-to-SQL compiler
"""

from __future__ import annotations

from pathlib import Path

from lark import Lark

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

_GRAMMAR_PATH = Path(__file__).parent / "grammar.lark"


def _build_parser() -> Lark:
    """Build the Lark LALR(1) parser from the grammar file."""
    return Lark(
        _GRAMMAR_PATH.read_text(),
        start="start",
        parser="lalr",
    )


# Lazy initialization: parser and transformer are built on first use
# to avoid import errors before transformer.py exists (Task 2).
_PARSER: Lark | None = None
_TRANSFORMER = None


def parse_query(query: str) -> QueryNode:
    """Parse a bioprocess DSL query string into a typed AST.

    Raises lark.exceptions.UnexpectedInput on malformed queries.
    """
    global _PARSER, _TRANSFORMER
    if _PARSER is None:
        _PARSER = _build_parser()
    if _TRANSFORMER is None:
        from sporedb.query.dsl.transformer import BioprocessDSLTransformer

        _TRANSFORMER = BioprocessDSLTransformer()
    tree = _PARSER.parse(query)
    return _TRANSFORMER.transform(tree)


from sporedb.query.dsl.compiler import DuckDBCompiler  # noqa: E402

__all__ = [
    "AliasNode",
    "AndNode",
    "ComparisonNode",
    "DuckDBCompiler",
    "FieldRefNode",
    "FuncCallNode",
    "NotNode",
    "OrNode",
    "OrderByNode",
    "QueryNode",
    "SelectNode",
    "SourceNode",
    "parse_query",
]
