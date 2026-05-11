"""Golden batch profiling and scoring via Dynamic Time Warping.

Provides functions to:
- Create a reference trajectory (golden batch profile) from the top-N
  best batches (aligned by elapsed time)
- Score any batch against a golden profile using fastdtw normalized distance
- Convert DTW distance to a 0-100 similarity score
"""

from __future__ import annotations

from uuid import UUID

import numpy as np
import pandas as pd
from fastdtw import fastdtw
from scipy.spatial.distance import euclidean

from sporedb.analytics.models import BatchScore, GoldenBatchProfile


def create_golden_profile(
    aligned_df: pd.DataFrame,
    batch_names: list[str],
    variables: list[str],
    metadata: dict[str, object] | None = None,
) -> GoldenBatchProfile:
    """Create a golden batch profile from aligned batch DataFrames.

    The aligned_df is the output of align() with elapsed_hours as index
    and columns like 'batch_A__OD600', 'batch_A__pH', etc.

    Computes mean and std trajectory across batches for each variable.

    Args:
        aligned_df: Output of align(), indexed by elapsed_hours.
        batch_names: Names of batches that contributed (must match column prefixes).
        variables: Variable names to include in profile (e.g., ["OD600", "pH"]).
        metadata: Optional metadata dict (strain, media, scale for documentation).

    Returns:
        GoldenBatchProfile with mean/std trajectories.

    Raises:
        ValueError: If aligned_df is empty, batch_names is empty, or variables is empty.
    """
    if aligned_df.empty or not batch_names or not variables:
        raise ValueError(
            "aligned_df must be non-empty and batch_names/variables must be provided"
        )

    n_timepoints = len(aligned_df)
    n_variables = len(variables)

    # Build mean and std arrays: (n_timepoints, n_variables)
    mean_arr = np.zeros((n_timepoints, n_variables))
    std_arr = np.zeros((n_timepoints, n_variables))

    for v_idx, var in enumerate(variables):
        # Gather all batch columns for this variable
        cols = [f"{bn}__{var}" for bn in batch_names]
        missing = [c for c in cols if c not in aligned_df.columns]
        if missing:
            raise ValueError(f"Missing columns for variable '{var}': {missing}")
        var_data = aligned_df[cols].to_numpy(dtype=float)  # (n_timepoints, n_batches)
        mean_arr[:, v_idx] = np.nanmean(var_data, axis=1)
        std_arr[:, v_idx] = np.nanstd(var_data, axis=1)

    # Extract elapsed_hours from index
    elapsed = aligned_df.index.to_numpy(dtype=float).tolist()

    return GoldenBatchProfile(
        variables=variables,
        mean_trajectory=mean_arr.tolist(),
        std_trajectory=std_arr.tolist(),
        elapsed_hours=elapsed,
        source_batch_ids=batch_names,
        metadata=metadata or {},
    )


def score_against_profile(
    profile: GoldenBatchProfile,
    batch_trajectory: np.ndarray,
    batch_id: UUID,
    max_distance: float = 2.0,
) -> BatchScore:
    """Score a batch against a golden batch profile.

    1. Validate that trajectory has same number of variables as profile
    2. Z-score normalize both profile mean and batch trajectory per variable
    3. Compute multivariate DTW distance with Sakoe-Chiba window
    4. Convert normalized distance to 0-100 score (100 = identical)

    Args:
        profile: Golden batch reference profile.
        batch_trajectory: Batch data as (timepoints, variables) array.
        batch_id: UUID of the batch being scored.
        max_distance: Normalization ceiling for score conversion (configurable).

    Returns:
        BatchScore with 0-100 score and DTW normalized distance.

    Raises:
        ValueError: If trajectory has different number of variables than profile.
    """
    n_profile_vars = len(profile.variables)
    if batch_trajectory.ndim == 1:
        batch_trajectory = batch_trajectory.reshape(-1, 1)

    if batch_trajectory.shape[1] != n_profile_vars:
        raise ValueError(
            f"Trajectory has {batch_trajectory.shape[1]} variables but profile "
            f"expects {n_profile_vars} variables ({profile.variables})"
        )

    # Convert profile mean trajectory to numpy
    ref = np.array(profile.mean_trajectory, dtype=float)  # (n_timepoints, n_vars)

    # Z-score normalize both per variable (column-wise)
    ref_norm = _zscore_columns(ref)
    batch_norm = _zscore_columns(batch_trajectory)

    # fastdtw radius approximates Sakoe-Chiba window constraint
    radius = max(len(batch_trajectory) // 5, 10)
    distance, _path = fastdtw(batch_norm, ref_norm, radius=radius, dist=euclidean)
    # Normalize by alignment path length (matches dtw-python normalizedDistance)
    n_points = max(len(batch_norm), len(ref_norm))
    norm_dist = float(distance) / n_points if n_points > 0 else 0.0

    # Convert to 0-100 score
    score = max(0.0, 100.0 * (1.0 - norm_dist / max_distance))
    score = min(score, 100.0)

    return BatchScore(
        batch_id=batch_id,
        profile_id=profile.profile_id,
        score=round(score, 2),
        variables=profile.variables,
        dtw_normalized_distance=round(norm_dist, 6),
        metadata={},
    )


def extract_batch_trajectory(
    telemetry_df: pd.DataFrame,
    variables: list[str],
) -> np.ndarray:
    """Extract a (timepoints, variables) array from a telemetry DataFrame.

    Helper to convert a standard telemetry DataFrame (ts, variable, value columns)
    into the numpy array format expected by score_against_profile().

    Pivots the long-format DataFrame to wide format, sorted by timestamp.
    """
    pivoted = pd.pivot_table(
        telemetry_df, index="ts", columns="variable", values="value"
    )
    pivoted = pivoted.sort_index()
    return pivoted[variables].to_numpy(dtype=float)


def _zscore_columns(arr: np.ndarray) -> np.ndarray:
    """Z-score normalize each column of a 2D array.

    Handles constant columns (std=0) by leaving them as zeros.
    """
    result = np.zeros_like(arr, dtype=float)
    for col in range(arr.shape[1]):
        col_data = arr[:, col]
        mean = np.nanmean(col_data)
        std = np.nanstd(col_data)
        if std > 1e-10:
            result[:, col] = (col_data - mean) / std
        else:
            result[:, col] = 0.0
    return result
