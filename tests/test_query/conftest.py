"""Shared fixtures for DSL query tests."""

from __future__ import annotations

import pytest


@pytest.fixture
def sample_queries() -> dict[str, str]:
    """Sample DSL query strings for testing."""
    return {
        "basic_select": "SELECT growth_rate() FROM batches",
        "with_where": (
            'SELECT phase_duration("exponential") FROM batches WHERE strain = "CHO-K1"'
        ),
        "single_batch": 'SELECT growth_rate() FROM batch("B001")',
        "multi_select": "SELECT growth_rate(), yield_coefficient() FROM batches",
        "with_alias": "SELECT growth_rate() AS mu FROM batches",
        "with_and": (
            "SELECT growth_rate() FROM batches "
            'WHERE strain = "CHO-K1" AND media = "CD-CHO"'
        ),
        "case_insensitive": "select growth_rate() from batches",
        "with_comment": "SELECT growth_rate() FROM batches -- this is a comment",
        "with_group_by": (
            "SELECT strain, avg(growth_rate()) FROM batches GROUP BY strain"
        ),
        "with_order_by": "SELECT growth_rate() FROM batches ORDER BY batch.name DESC",
        "with_limit": "SELECT growth_rate() FROM batches LIMIT 10",
    }
