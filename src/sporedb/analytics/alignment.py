"""Cross-run alignment by elapsed time from a phase boundary.

Enables scientists to compare multiple bioprocess runs by re-indexing
all batches to elapsed hours from a common phase boundary (e.g. start
of exponential phase). The resulting DataFrame has columns namespaced
as ``batch_name__variable`` and a shared ``elapsed_hours`` index that
includes negative values for data before the anchor phase.
"""

from __future__ import annotations

from datetime import datetime

import numpy as np
import pandas as pd

from sporedb.analytics.models import PhaseAnnotation, PhaseType


def _find_phase_start(
    annotations: list[PhaseAnnotation],
    phase_type: PhaseType,
) -> datetime:
    """Find the start timestamp of the specified phase type.

    Raises ValueError if the phase type is not found in annotations.
    """
    for ann in annotations:
        if ann.phase_type == phase_type:
            return ann.start_ts
    raise ValueError(
        f"Phase {phase_type.value} not found in annotations. "
        f"Available phases: {[a.phase_type.value for a in annotations]}"
    )


def align(
    batches: dict[str, pd.DataFrame],
    phase_annotations: dict[str, list[PhaseAnnotation]],
    anchor_phase: PhaseType = PhaseType.EXPONENTIAL,
    variables: list[str] | None = None,
    resolution_minutes: float | None = None,
) -> pd.DataFrame:
    """Align multiple batch runs by elapsed time from a phase boundary.

    Args:
        batches: Mapping of batch_name -> telemetry DataFrame.
            Each DataFrame must have columns: ``ts``, ``variable``, ``value``.
        phase_annotations: Mapping of batch_name -> list of PhaseAnnotation.
        anchor_phase: Phase boundary to anchor alignment on
            (default: EXPONENTIAL start).
        variables: Optional list of variables to include. None = all variables.
        resolution_minutes: If set, resample to uniform grid at this resolution.

    Returns:
        DataFrame with ``elapsed_hours`` as index and columns named
        ``batch_name__variable``. Negative elapsed_hours indicate data
        before the anchor phase.

    Raises:
        ValueError: If a batch has no annotations for the anchor phase,
            or if a batch_name in ``batches`` is not in ``phase_annotations``.
    """
    aligned_frames: list[pd.DataFrame] = []

    for batch_name, df in batches.items():
        if batch_name not in phase_annotations:
            raise ValueError(f"Batch '{batch_name}' not found in phase_annotations")

        # Find anchor time for this batch
        anchor_time = _find_phase_start(phase_annotations[batch_name], anchor_phase)

        # Work on a copy
        batch_df = df.copy()

        # Filter to requested variables if specified
        if variables is not None:
            batch_df = batch_df[batch_df["variable"].isin(variables)]

        if batch_df.empty:
            continue

        # Compute elapsed hours from anchor time
        batch_df["elapsed_hours"] = (
            pd.to_datetime(batch_df["ts"]) - pd.Timestamp(anchor_time)
        ).dt.total_seconds() / 3600.0

        # Pivot: one column per variable, elapsed_hours as index
        pivoted = batch_df.pivot_table(
            index="elapsed_hours",
            columns="variable",
            values="value",
            aggfunc="mean",
        )

        # Rename columns to batch_name__variable
        pivoted.columns = [f"{batch_name}__{col}" for col in pivoted.columns]

        aligned_frames.append(pivoted)

    if not aligned_frames:
        return pd.DataFrame()

    # Concatenate all on elapsed_hours axis
    result = pd.concat(aligned_frames, axis=1).sort_index()
    result.index.name = "elapsed_hours"

    # Apply uniform time grid if requested
    if resolution_minutes is not None:
        step_hours = resolution_minutes / 60.0
        min_h = result.index.min()
        max_h = result.index.max()
        new_index = np.arange(min_h, max_h + step_hours / 2, step_hours)
        # Reindex to uniform grid, interpolating values
        result = result.reindex(result.index.union(new_index.tolist())).interpolate(
            method="index"
        )
        result = result.reindex(new_index)
        result.index.name = "elapsed_hours"

    return result
