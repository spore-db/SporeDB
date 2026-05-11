from __future__ import annotations

from thefuzz import fuzz, process

from sporedb.ingestion.result import ColumnMapping
from sporedb.ingestion.vocabulary import get_vocabulary

# Column names that indicate a timestamp/time column
_TIMESTAMP_INDICATORS: set[str] = {
    "time",
    "timestamp",
    "datetime",
    "elapsed",
    "hours",
    "t",
    "time_h",
    "time_min",
    "elapsed_h",
    "elapsed_min",
}


def _clean_column_name(col_name: str) -> str:
    """Strip whitespace and leading/trailing underscores."""
    return col_name.strip().strip("_")


def match_column(
    col_name: str,
    vocabulary: dict[str, list[str]],
    threshold: int = 70,
) -> tuple[str | None, float]:
    """Match a column name against the bioprocess vocabulary.

    First attempts exact case-insensitive match, then falls back to
    fuzzy matching using token_sort_ratio.

    Returns:
        Tuple of (variable_name, confidence) or (None, 0.0) if no match.
    """
    cleaned = _clean_column_name(col_name)
    if not cleaned:
        return (None, 0.0)

    cleaned_lower = cleaned.lower()

    # Build reverse lookup: alias -> variable_name
    alias_to_var: dict[str, str] = {}
    all_aliases: list[str] = []
    for var_name, aliases in vocabulary.items():
        for alias in aliases:
            alias_to_var[alias.lower()] = var_name
            all_aliases.append(alias)

    # Exact match (case-insensitive)
    if cleaned_lower in alias_to_var:
        return (alias_to_var[cleaned_lower], 1.0)

    # Fuzzy match
    if not all_aliases:
        return (None, 0.0)

    result = process.extractOne(
        cleaned,
        all_aliases,
        scorer=fuzz.token_sort_ratio,
        score_cutoff=threshold,
    )

    if result is None:
        return (None, 0.0)

    best_alias, score = result[0], result[1]
    var_name = alias_to_var[best_alias.lower()]
    confidence = score / 100.0
    return (var_name, confidence)


def detect_columns(
    headers: list[str],
    data_rows: list[list[str]],
    vocabulary: dict[str, list[str]] | None = None,
    custom_vocab: dict[str, list[str]] | None = None,
) -> ColumnMapping:
    """Detect column mappings from raw CSV/Excel headers and data rows.

    Args:
        headers: List of column header strings.
        data_rows: First few rows of data as string lists.
        vocabulary: Override the default vocabulary entirely.
        custom_vocab: Merge additional entries into the default vocabulary.

    Returns:
        ColumnMapping with all fields populated.
    """
    vocab = get_vocabulary(custom_vocab) if vocabulary is None else vocabulary

    timestamp_col: str = ""
    variable_mappings: dict[str, str] = {}
    unit_mappings: dict[str, str] = {}
    unmapped_cols: list[str] = []
    confidence: dict[str, float] = {}

    for header in headers:
        cleaned = _clean_column_name(header)
        cleaned_lower = cleaned.lower()

        # Check if this is a timestamp column
        if cleaned_lower in _TIMESTAMP_INDICATORS and not timestamp_col:
            timestamp_col = header
            continue

        # Try matching against vocabulary
        var_name, conf = match_column(header, vocab)
        if var_name is not None:
            variable_mappings[header] = var_name
            confidence[header] = conf
        else:
            unmapped_cols.append(header)

    return ColumnMapping(
        timestamp_col=timestamp_col,
        variable_mappings=variable_mappings,
        unit_mappings=unit_mappings,
        unmapped_cols=unmapped_cols,
        confidence=confidence,
    )
