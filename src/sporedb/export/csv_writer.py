"""CSV export serialization for SporeDB batch data."""

from __future__ import annotations

import pandas as pd


def write_csv(df: pd.DataFrame) -> bytes:
    """Convert a DataFrame to UTF-8 encoded CSV bytes with header row."""
    return df.to_csv(index=False).encode("utf-8")
