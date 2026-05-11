"""SporeDB export layer: batch data to CSV, Parquet, and Arrow formats."""

from __future__ import annotations

import sys
from pathlib import Path
from uuid import UUID

import pandas as pd
import pyarrow.parquet as pq

from sporedb.export.arrow_writer import write_arrow
from sporedb.export.csv_writer import write_csv
from sporedb.export.parquet_writer import write_parquet
from sporedb.storage.engine import StorageEngine
from sporedb.storage.ts_store import TimeSeriesStore

__all__ = ["export_batch", "write_csv", "write_parquet", "write_arrow"]

_SUPPORTED_FORMATS = {"csv", "parquet", "arrow"}

_WRITERS = {
    "csv": write_csv,
    "parquet": write_parquet,
    "arrow": write_arrow,
}


def _read_original_data(data_root: Path, batch_id: UUID) -> pd.DataFrame | None:
    """Read pre-conversion data from the original sidecar Parquet file.

    Returns DataFrame if the sidecar exists, None otherwise.
    """
    path = data_root / "original" / str(batch_id) / "telemetry.parquet"
    if not path.exists():
        return None
    return pq.read_table(path).to_pandas()  # type: ignore[no-untyped-call, no-any-return]


def export_batch(
    batch_id: UUID,
    engine: StorageEngine,
    format: str = "csv",
    form: str = "aligned",
    output_path: Path | str | None = None,
    include_assay: bool = True,
    allowed_export_root: Path | None = None,
) -> bytes | None:
    """Export batch telemetry data in the specified format.

    Args:
        batch_id: The batch to export.
        engine: StorageEngine instance providing data access.
        format: Output format - "csv", "parquet", or "arrow".
        form: Data form - "aligned" (canonical units) or "original" (pre-conversion).
        output_path: If provided, write to this file and return None.
            Otherwise return bytes.
        include_assay: If True and form="aligned", include assay data.
        allowed_export_root: If provided, validates that the resolved output_path
            is within this directory. Prevents path traversal attacks (21 CFR Part 11).

    Returns:
        Bytes of the exported data, or None if output_path was provided.

    Raises:
        ValueError: If format is unsupported, no data exists, or output_path
            is outside allowed_export_root.
    """
    if format not in _SUPPORTED_FORMATS:
        raise ValueError(
            f"Unsupported format '{format}'. "
            f"Must be one of: {sorted(_SUPPORTED_FORMATS)}"
        )

    ts_store = TimeSeriesStore(engine)

    if form == "original":
        df = _read_original_data(engine.data_root, batch_id)
        if df is None:
            # Fall back to aligned with warning
            print(
                f"WARNING: No original data found for batch {batch_id}, "
                "falling back to aligned form.",
                file=sys.stderr,
            )
            df = ts_store.get_telemetry(batch_id)
    else:
        # aligned (default)
        df = ts_store.get_telemetry(batch_id)
        if include_assay:
            assay_df = ts_store.get_assay(batch_id)
            if not assay_df.empty:
                df = pd.concat([df, assay_df], ignore_index=True)

    if df.empty:
        raise ValueError(f"No data found for batch {batch_id}")

    # Serialize using the appropriate writer
    data = _WRITERS[format](df)

    if output_path is not None:
        # T-02-10 mitigation: resolve path to prevent traversal
        resolved = Path(output_path).resolve()
        if allowed_export_root is not None:
            root_resolved = allowed_export_root.resolve()
            if not resolved.is_relative_to(root_resolved):
                raise ValueError(
                    f"Output path '{resolved}' is outside allowed "
                    f"export directory '{root_resolved}'"
                )
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_bytes(data)
        return None

    return data
