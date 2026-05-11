"""Additional preprocessing tests to cover edge-case branches.

Covers lines 45, 54, 57, 66 in analytics/preprocessing.py:
- Line 45: interpolate_nans with all-NaN input returns unchanged
- Line 54: interpolate_nans with leading NaN (no left anchor -> skip)
- Line 57: interpolate_nans with trailing NaN (no right anchor -> skip)
- Line 66: downsample_signal main indexing path with large array
"""

from __future__ import annotations

import numpy as np
import pytest

from sporedb.analytics.preprocessing import (
    downsample_signal,
    interpolate_nans,
)


class TestInterpolateNansEdgeCases:
    def test_all_nan_returns_unchanged(self) -> None:
        """All-NaN array has no valid values; returns unchanged (line 45)."""
        arr = np.array([np.nan, np.nan, np.nan, np.nan])
        result = interpolate_nans(arr)
        assert np.all(np.isnan(result))
        # Should be a copy, not the same object
        assert result is not arr

    def test_leading_nan_not_filled(self) -> None:
        """Leading NaN has no left anchor, so it is not interpolated (line 54)."""
        # [NaN, 1.0, 2.0, 3.0] -> leading NaN left as NaN (no left anchor)
        arr = np.array([np.nan, 1.0, 2.0, 3.0])
        result = interpolate_nans(arr, limit=5)
        assert np.isnan(result[0]), "Leading NaN should remain NaN (no left anchor)"
        np.testing.assert_array_equal(result[1:], [1.0, 2.0, 3.0])

    def test_trailing_nan_not_filled(self) -> None:
        """Trailing NaN has no right anchor, so it is not interpolated (line 57)."""
        # [1.0, 2.0, 3.0, NaN] -> trailing NaN left as NaN (no right anchor)
        arr = np.array([1.0, 2.0, 3.0, np.nan])
        result = interpolate_nans(arr, limit=5)
        np.testing.assert_array_equal(result[:3], [1.0, 2.0, 3.0])
        assert np.isnan(result[3]), "Trailing NaN should remain NaN (no right anchor)"

    def test_multiple_leading_nans_not_filled(self) -> None:
        """Multiple leading NaNs, all remain unfilled."""
        arr = np.array([np.nan, np.nan, 5.0, 10.0])
        result = interpolate_nans(arr, limit=5)
        assert np.isnan(result[0])
        assert np.isnan(result[1])
        assert result[2] == 5.0

    def test_interior_gap_filled_but_edges_not(self) -> None:
        """Interior gap filled, edge NaNs not filled."""
        arr = np.array([np.nan, 2.0, np.nan, 4.0, np.nan])
        result = interpolate_nans(arr, limit=5)
        # leading NaN stays
        assert np.isnan(result[0])
        # interior NaN at index 2 is filled (between 2.0 and 4.0)
        assert result[2] == pytest.approx(3.0)
        # trailing NaN stays
        assert np.isnan(result[4])

    def test_no_nans_returns_unchanged(self) -> None:
        """Array with no NaN values is returned unchanged."""
        arr = np.array([1.0, 2.0, 3.0, 4.0])
        result = interpolate_nans(arr)
        np.testing.assert_array_equal(result, arr)


class TestDownsampleSignalCoverage:
    def test_downsample_selects_evenly_spaced_points(self) -> None:
        """Downsampling uses linspace to pick evenly spaced indices (line 66)."""
        arr = np.arange(500, dtype=float)
        result = downsample_signal(arr, max_samples=50)
        assert len(result) == 50
        # First and last elements should be preserved
        assert result[0] == 0.0
        assert result[-1] == 499.0

    def test_downsample_200_to_100(self) -> None:
        """200-element array downsampled to 100 has correct shape (line 66)."""
        arr = np.arange(200, dtype=float)
        result = downsample_signal(arr, max_samples=100)
        assert len(result) == 100

    def test_downsample_exact_boundary_not_downsampled(self) -> None:
        """Array with exactly max_samples elements is returned unchanged."""
        arr = np.arange(100, dtype=float)
        result = downsample_signal(arr, max_samples=100)
        np.testing.assert_array_equal(result, arr)
