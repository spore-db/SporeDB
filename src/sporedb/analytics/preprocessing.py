"""Signal preprocessing utilities for changepoint detection.

Functions for cleaning, interpolating, smoothing, and downsampling
bioprocess time-series signals before analysis.
"""

from __future__ import annotations

import numpy as np


def validate_signal(values: np.ndarray) -> np.ndarray:
    """Validate and clean a signal array for changepoint detection.

    Replaces Inf with NaN. Raises ValueError if empty or all-NaN.
    Returns a copy of the array with Inf replaced.
    """
    if values.size == 0:
        raise ValueError("Signal array is empty")
    result = values.copy().astype(float)
    result[np.isinf(result)] = np.nan
    if np.all(np.isnan(result)):
        raise ValueError("Signal array is all NaN after cleaning")
    return result


def interpolate_nans(values: np.ndarray, limit: int = 5) -> np.ndarray:
    """Interpolate NaN values using linear interpolation.

    Only fills gaps of ``limit`` or fewer consecutive NaN values.
    Larger gaps are left as NaN. Edge NaNs (at start/end with no
    anchor on one side) are also left as NaN.
    """
    result = values.copy().astype(float)
    nan_mask = np.isnan(result)

    if not np.any(nan_mask):
        return result

    # Identify NaN run lengths and positions
    # We need to find each contiguous run of NaNs and check its length
    valid_mask = ~nan_mask

    if not np.any(valid_mask):
        return result  # all NaN, nothing to interpolate

    # Find contiguous NaN runs
    changes = np.diff(nan_mask.astype(int))
    run_starts = np.where(changes == 1)[0] + 1  # NaN run starts
    run_ends = np.where(changes == -1)[0] + 1  # NaN run ends

    # Handle edge cases: starts with NaN
    if nan_mask[0]:
        run_starts = np.concatenate([[0], run_starts])
    # Ends with NaN
    if nan_mask[-1]:
        run_ends = np.concatenate([run_ends, [len(result)]])

    # For each NaN run, interpolate only if length <= limit and bounded by valid values
    for start, end in zip(run_starts, run_ends, strict=True):
        run_len = end - start
        if run_len > limit:
            continue  # skip large gaps
        # Need valid anchors on both sides
        if start == 0 or end == len(result):
            continue  # edge NaN, no anchor on one side

        # Linear interpolation between the valid values bracketing this gap
        left_val = result[start - 1]
        right_val = result[end]
        n = run_len + 1  # number of intervals
        for i in range(run_len):
            result[start + i] = left_val + (right_val - left_val) * (i + 1) / n

    return result


def smooth_signal(values: np.ndarray, window: int = 5) -> np.ndarray:
    """Smooth signal using scipy uniform_filter1d.

    Window=1 returns input unchanged. Preserves array length.
    Uses scipy.ndimage.uniform_filter1d with mode='nearest' for edge handling.
    """
    if window <= 1:
        return values.copy()
    from scipy.ndimage import uniform_filter1d

    return uniform_filter1d(values.astype(float), size=window, mode="nearest")  # type: ignore[no-any-return]


def downsample_signal(values: np.ndarray, max_samples: int = 10000) -> np.ndarray:
    """Downsample signal if it exceeds max_samples by taking evenly spaced points.

    Returns input unchanged if length <= max_samples.
    """
    if len(values) <= max_samples:
        return values
    indices = np.linspace(0, len(values) - 1, max_samples, dtype=int)
    return values[indices]
