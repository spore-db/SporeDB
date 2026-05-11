"""Compound filter for batch search queries."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from sporedb.models.batch import BatchLifecycle


@dataclass
class BatchFilter:
    """Compound filter for batch search queries.

    All set fields are combined with AND semantics.
    Filter values are always passed as parameterized query parameters
    to prevent SQL injection.
    """

    strain: str | None = None
    media: str | None = None
    operator: str | None = None
    lifecycle: BatchLifecycle | None = None
    tags: list[str] = field(default_factory=list)
    inoculation_after: datetime | None = None
    inoculation_before: datetime | None = None
    name_contains: str | None = None

    def to_sql_clauses(self) -> tuple[list[str], list[object]]:
        """Convert to SQL WHERE clauses and parameters.

        Returns (clauses, params) where clauses are SQL fragments like
        "meta_strain = ?" and params are the corresponding values.
        NEVER interpolates user values into SQL strings.
        """
        clauses: list[str] = []
        params: list[object] = []

        if self.strain is not None:
            clauses.append("meta_strain = ?")
            params.append(self.strain)
        if self.media is not None:
            clauses.append("meta_media = ?")
            params.append(self.media)
        if self.operator is not None:
            clauses.append("meta_operator = ?")
            params.append(self.operator)
        if self.lifecycle is not None:
            clauses.append("lifecycle = ?")
            params.append(self.lifecycle.value)
        if self.name_contains is not None:
            escaped = (
                self.name_contains.replace("\\", "\\\\")
                .replace("%", "\\%")
                .replace("_", "\\_")
            )
            clauses.append("name ILIKE ? ESCAPE '\\'")
            params.append(f"%{escaped}%")
        if self.inoculation_after is not None:
            clauses.append("ts_inoculation >= ?")
            params.append(self.inoculation_after.isoformat())
        if self.inoculation_before is not None:
            clauses.append("ts_inoculation < ?")
            params.append(self.inoculation_before.isoformat())
        # Tags: each tag must be present (AND semantics).
        # Use DuckDB list_contains for reliable JSON array membership testing.
        for tag in self.tags:
            clauses.append(
                "list_contains(CAST(json_extract(tags, '$') AS VARCHAR[]), ?)"
            )
            params.append(tag)

        return clauses, params
