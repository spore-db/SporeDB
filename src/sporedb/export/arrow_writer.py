"""Arrow IPC export serialization for SporeDB batch data."""

from __future__ import annotations

import pandas as pd
import pyarrow as pa


def write_arrow(df: pd.DataFrame) -> bytes:
    """Convert a DataFrame to Arrow IPC (file format) bytes."""
    table = pa.Table.from_pandas(df)
    buf = pa.BufferOutputStream()
    writer = pa.ipc.new_file(buf, table.schema)
    writer.write_table(table)
    writer.close()
    return buf.getvalue().to_pybytes()  # type: ignore[no-any-return]
