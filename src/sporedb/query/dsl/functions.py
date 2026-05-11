"""Domain function registry for bioprocess DSL SQL compilation.

Maps domain-specific function names to SQL expansion templates.
Each template uses ? placeholders for parameters.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class DomainFunction:
    """SQL expansion template for a domain function."""

    name: str
    sql_template: str  # SQL fragment with {arg0}, {arg1} for positional args
    requires_join: str | None = None  # JOIN clause needed in FROM
    is_post_process: bool = False  # True if cannot be pure SQL (e.g., golden_score)


DOMAIN_FUNCTIONS: dict[str, DomainFunction] = {
    "phase_duration": DomainFunction(
        name="phase_duration",
        sql_template="(EXTRACT(EPOCH FROM (p.end_ts - p.start_ts)) / 3600.0)",
        requires_join="phases p ON p.batch_id = b.batch_id AND p.phase_type = ?",
    ),
    "growth_rate": DomainFunction(
        name="growth_rate",
        sql_template="m.mu",
        requires_join=(
            "batch_metrics m ON m.batch_id = b.batch_id "
            "AND m.phase_type = 'exponential'"
        ),
    ),
    "yield_coefficient": DomainFunction(
        name="yield_coefficient",
        sql_template="m.yx_s",
        requires_join="batch_metrics m ON m.batch_id = b.batch_id",
    ),
    "golden_score": DomainFunction(
        name="golden_score",
        sql_template="NULL",  # Computed post-query in Python
        is_post_process=True,
    ),
}

# Standard SQL aggregates: pass through without expansion
SQL_AGGREGATES: set[str] = {"avg", "min", "max", "sum", "count"}
