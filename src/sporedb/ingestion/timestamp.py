from __future__ import annotations

import warnings
from datetime import UTC, datetime, timedelta

from dateutil import parser as dateutil_parser

TIMESTAMP_COLUMN_NAMES: set[str] = {
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

# Maximum rows to sample for timestamp detection (T-02-04 mitigation)
_MAX_DETECTION_ROWS: int = 5


def _looks_like_elapsed(values: list[str]) -> bool:
    """Check if values look like elapsed time.

    Criteria: numeric, starting near 0, monotonically non-decreasing.
    """
    try:
        floats = [float(v) for v in values if v.strip()]
    except (ValueError, TypeError):
        return False

    if not floats:
        return False

    # Must start near zero
    if min(floats) >= 1.0:
        return False

    # Must be monotonically non-decreasing (time should increase)
    return all(floats[i] >= floats[i - 1] for i in range(1, len(floats)))


def _looks_like_datetime(values: list[str]) -> bool:
    """Check if values look like parseable datetime strings.

    Limits parsing to first 5 values for safety (T-02-04).
    """
    sample = [v for v in values if v.strip()][:_MAX_DETECTION_ROWS]
    if len(sample) < 1:
        return False

    parsed_count = 0
    for v in sample[:5]:
        # Skip pure numeric strings -- they are data values, not datetimes
        stripped = v.strip()
        try:
            float(stripped)
            continue  # numeric values are not datetimes
        except ValueError:
            pass

        try:
            dateutil_parser.parse(stripped)
            parsed_count += 1
        except (ValueError, OverflowError):
            pass

    threshold = min(3, len(sample))
    return parsed_count >= threshold


def detect_elapsed_unit(column_name: str) -> str:
    """Detect the elapsed time unit from a column name suffix.

    Checks for common suffixes like '_min', '_h', '_s'.
    Defaults to 'h' (hours) if no recognizable suffix is found.

    Args:
        column_name: The timestamp column header name.

    Returns:
        One of 'h', 'min', or 's'.
    """
    lower = column_name.strip().lower()
    if (
        lower.endswith("_min")
        or lower.endswith("_mins")
        or lower == "elapsed_min"
        or lower == "time_min"
    ):
        return "min"
    if lower.endswith("_s") or lower.endswith("_sec") or lower.endswith("_seconds"):
        return "s"
    if lower.endswith("_h") or lower.endswith("_hr") or lower.endswith("_hours"):
        return "h"
    # Check if the name itself indicates minutes or seconds
    if lower in ("minutes", "min"):
        return "min"
    if lower in ("seconds", "sec", "s"):
        return "s"
    # Default to hours
    return "h"


def detect_timestamp_column(
    headers: list[str],
    first_rows: list[list[str]],
) -> tuple[str, bool]:
    """Detect which column contains timestamp data.

    Priority 1: Match column names against TIMESTAMP_COLUMN_NAMES.
    Priority 2: Scan columns for datetime-parseable values.

    Args:
        headers: Column header names.
        first_rows: First few data rows as string lists.

    Returns:
        Tuple of (column_name, is_elapsed).
        is_elapsed=True when values are numeric and start near 0.

    Raises:
        ValueError: If no timestamp column can be identified.
    """
    # Priority 1: match by column name
    for i, header in enumerate(headers):
        cleaned = header.strip().lower().strip("_")
        if cleaned in TIMESTAMP_COLUMN_NAMES:
            # Determine if elapsed or absolute
            col_values = [row[i] for row in first_rows if i < len(row)]
            is_elapsed = _looks_like_elapsed(col_values)
            return (header, is_elapsed)

    # Priority 2: scan for datetime-like columns
    for i, header in enumerate(headers):
        col_values = [row[i] for row in first_rows if i < len(row)]
        if _looks_like_datetime(col_values):
            return (header, False)

    raise ValueError("No timestamp column found in headers")


def elapsed_to_absolute(
    elapsed_values: list[float],
    elapsed_unit: str,
    reference_ts: datetime,
) -> list[datetime]:
    """Convert elapsed time values to absolute UTC datetimes.

    Args:
        elapsed_values: Numeric elapsed time values.
        elapsed_unit: Unit of elapsed time ("h", "min", "s").
        reference_ts: Reference timestamp (e.g., inoculation time).

    Returns:
        List of UTC-aware datetime objects.
    """
    # Convert elapsed unit to hours
    if elapsed_unit == "h":
        multiplier = 1.0
    elif elapsed_unit == "min":
        multiplier = 1.0 / 60.0
    elif elapsed_unit == "s":
        multiplier = 1.0 / 3600.0
    else:
        raise ValueError(
            f"Unsupported elapsed time unit: '{elapsed_unit}'. "
            "Must be 'h', 'min', or 's'."
        )

    result: list[datetime] = []
    for val in elapsed_values:
        hours = val * multiplier
        dt = reference_ts + timedelta(hours=hours)
        # Ensure UTC
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        result.append(dt)

    return result


def parse_timestamps(
    values: list[str],
    is_elapsed: bool,
    reference_ts: datetime | None = None,
    elapsed_unit: str = "h",
) -> list[datetime]:
    """Parse timestamp strings into UTC-aware datetime objects.

    Args:
        values: Raw string values from the timestamp column.
        is_elapsed: Whether values represent elapsed time.
        reference_ts: Required if is_elapsed=True. The reference point
            for elapsed time conversion.
        elapsed_unit: Unit for elapsed time values ('h', 'min', or 's').
            Defaults to 'h'. Use detect_elapsed_unit() to infer from column name.

    Returns:
        List of UTC-aware datetime objects.

    Raises:
        ValueError: If is_elapsed=True and reference_ts is None.
    """
    if is_elapsed:
        if reference_ts is None:
            raise ValueError("reference_ts is required for elapsed time parsing")

        float_values = [float(v) for v in values]
        return elapsed_to_absolute(float_values, elapsed_unit, reference_ts)

    # Absolute timestamps
    result: list[datetime] = []
    for v in values:
        dt = dateutil_parser.parse(v)
        if dt.tzinfo is None:
            warnings.warn(
                f"Naive timestamp '{v}' has no timezone info and will be "
                "assumed UTC. Pass timezone-aware timestamps to avoid "
                "potential time offset errors.",
                UserWarning,
                stacklevel=2,
            )
            dt = dt.replace(tzinfo=UTC)
        result.append(dt)

    return result
