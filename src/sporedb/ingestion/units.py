from __future__ import annotations

from collections.abc import Callable

from pydantic import BaseModel

CANONICAL_UNITS: dict[str, str | None] = {
    "concentration": "g/L",
    "temperature": "C",
    "dissolved_oxygen": "%",
    "time": "h",
    "volume": "L",
    "ph": None,
}

VARIABLE_CATEGORY: dict[str, str] = {
    "dissolved_oxygen": "dissolved_oxygen",
    "ph": "ph",
    "temperature": "temperature",
    "biomass": "concentration",
    "glucose": "concentration",
    "volume": "volume",
    "lactate": "concentration",
    "ammonia": "concentration",
    "glutamine": "concentration",
    "glutamate": "concentration",
    "product_titer": "concentration",
}

CONVERSIONS: dict[tuple[str, str], Callable[[float], float] | None] = {
    ("mg/mL", "g/L"): lambda x: x,
    ("mg/L", "g/L"): lambda x: x / 1000,
    ("g/mL", "g/L"): lambda x: x * 1000,
    ("ug/mL", "g/L"): lambda x: x / 1000,
    ("mol/L", "g/L"): None,  # needs molecular weight
    ("K", "C"): lambda x: x - 273.15,
    ("F", "C"): lambda x: (x - 32) * 5 / 9,
    ("min", "h"): lambda x: x / 60,
    ("s", "h"): lambda x: x / 3600,
    ("mL", "L"): lambda x: x / 1000,
}

# Known unit strings for header parsing and unit row detection
_KNOWN_UNITS: set[str] = {
    "g/L",
    "mg/mL",
    "mg/L",
    "g/mL",
    "ug/mL",
    "mol/L",
    "K",
    "C",
    "F",
    "min",
    "h",
    "s",
    "mL",
    "L",
    "%",
    "pct",
    "rpm",
}

# Header suffix to unit mapping (split on underscores)
_HEADER_SUFFIX_MAP: dict[str, str] = {
    "g_L": "g/L",
    "mg_mL": "mg/mL",
    "mg_L": "mg/L",
    "g_mL": "g/mL",
    "ug_mL": "ug/mL",
    "K": "K",
    "C": "C",
    "F": "F",
    "min": "min",
    "h": "h",
    "s": "s",
    "mL": "mL",
    "L": "L",
    "pct": "%",
}


class UnitConversionLog(BaseModel):
    """Log entry for a unit conversion applied during import."""

    column: str
    from_unit: str
    to_unit: str
    rows_converted: int


def convert_unit(
    from_unit: str,
    to_unit: str,
    value: float,
) -> tuple[float | None, str | None]:
    """Convert a value from one unit to another.

    Returns:
        Tuple of (converted_value, None) on success,
        or (None, warning_message) on failure.
    """
    import math

    if math.isnan(value) or math.isinf(value):
        return (None, f"Cannot convert non-finite value {value}")

    if from_unit == to_unit:
        return (value, None)

    key = (from_unit, to_unit)
    if key not in CONVERSIONS:
        return (None, f"No conversion from {from_unit} to {to_unit}")

    converter = CONVERSIONS[key]
    if converter is None:
        return (
            None,
            f"Conversion from {from_unit} to {to_unit} requires "
            "additional parameters (e.g., molecular weight)",
        )

    return (converter(value), None)


def detect_unit_from_header(header: str) -> str | None:
    """Parse unit suffix from a column header name.

    Checks for known unit patterns in the trailing segments of the header
    when split by underscore.

    Returns:
        Detected unit string, or None if no unit found.
    """
    parts = header.strip().split("_")
    if len(parts) < 2:
        return None

    # Try two-part suffix first (e.g., "mg_mL" from "glucose_mg_mL")
    if len(parts) >= 3:
        two_part = f"{parts[-2]}_{parts[-1]}"
        if two_part in _HEADER_SUFFIX_MAP:
            return _HEADER_SUFFIX_MAP[two_part]

    # Try single-part suffix
    last = parts[-1]
    if last in _HEADER_SUFFIX_MAP:
        return _HEADER_SUFFIX_MAP[last]

    return None


def is_unit_row(row: list[str]) -> bool:
    """Check if a row appears to contain unit labels rather than data.

    Returns True if all non-empty values match known unit patterns.
    """
    non_empty = [v.strip() for v in row if v.strip()]
    if not non_empty:
        return False

    return all(value in _KNOWN_UNITS for value in non_empty)


def detect_unit_by_range(
    variable: str,
    values: list[float],
) -> str | None:
    """Heuristic: guess the unit of a variable based on value ranges.

    Args:
        variable: The canonical variable name (e.g., "temperature", "glucose").
        values: Sample numeric values for the variable.

    Returns:
        Guessed unit string, or None if no heuristic applies.
    """
    if not values:
        return None

    mean_val = sum(values) / len(values)
    category = VARIABLE_CATEGORY.get(variable)

    if variable == "temperature" or category == "temperature":
        if mean_val > 200:
            return "K"
        return "C"

    if category == "concentration":
        if mean_val > 500:
            return "mg/L"  # values in hundreds suggest mg/L
        if mean_val >= 0.1:
            return "g/L"  # mid-range values are likely g/L
        # Very small values are ambiguous (g/mL vs g/L) -- do not guess
        return None

    return None
