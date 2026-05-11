"""Parquet export serialization for SporeDB batch data."""

from __future__ import annotations

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq


def write_parquet(df: pd.DataFrame) -> bytes:
    """Convert a DataFrame to Parquet bytes."""
    table = pa.Table.from_pandas(df)
    buf = pa.BufferOutputStream()
    pq.write_table(table, buf)  # type: ignore[no-untyped-call]
    return buf.getvalue().to_pybytes()  # type: ignore[no-any-return]
