"""Tests for signal preprocessing utilities."""

from __future__ import annotations

import numpy as np
import pytest

from sporedb.analytics.preprocessing import (
    downsample_signal,
    interpolate_nans,
    smooth_signal,
    validate_signal,
)


class TestValidateSignal:
    def test_raises_on_empty_array(self):
        with pytest.raises(ValueError, match="empty"):
            validate_signal(np.array([]))

    def test_raises_on_all_nan_array(self):
        with pytest.raises(ValueError, match="all NaN"):
            validate_signal(np.array([np.nan, np.nan, np.nan]))

    def test_replaces_inf_with_nan(self):
        arr = np.array([1.0, np.inf, 3.0, -np.inf, 5.0])
        result = validate_signal(arr)
        assert np.isnan(result[1])
        assert np.isnan(result[3])
        # Non-inf values preserved
        np.testing.assert_array_equal(result[0], 1.0)
        np.testing.assert_array_equal(result[2], 3.0)
        np.testing.assert_array_equal(result[4], 5.0)

    def test_clean_array_passes_through(self):
        arr = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        result = validate_signal(arr)
        np.testing.assert_array_equal(result, arr)
        # Should be a copy, not the same object
        assert result is not arr


class TestInterpolateNans:
    def test_fills_interior_gaps_within_limit(self):
        # Gap of 2 NaNs (within default limit=5)
        arr = np.array([1.0, np.nan, np.nan, 4.0, 5.0])
        result = interpolate_nans(arr, limit=5)
        # Interior NaNs should be linearly interpolated
        np.testing.assert_allclose(result[1], 2.0, atol=0.01)
        np.testing.assert_allclose(result[2], 3.0, atol=0.01)

    def test_does_not_fill_gaps_larger_than_limit(self):
        # Gap of 6 NaNs (exceeds limit=5)
        arr = np.array([1.0, np.nan, np.nan, np.nan, np.nan, np.nan, np.nan, 8.0])
        result = interpolate_nans(arr, limit=5)
        # All 6 NaNs should remain as NaN
        assert np.all(np.isnan(result[1:7]))


class TestSmoothSignal:
    def test_window_one_returns_input_unchanged(self):
        arr = np.array([1.0, 5.0, 2.0, 8.0, 3.0])
        result = smooth_signal(arr, window=1)
        np.testing.assert_array_equal(result, arr)

    def test_window_five_reduces_variance(self):
        rng = np.random.default_rng(42)
        noisy = 5.0 + rng.normal(0, 1.0, 100)
        smoothed = smooth_signal(noisy, window=5)
        assert np.var(smoothed) < np.var(noisy)

    def test_preserves_array_length(self):
        arr = np.array([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0])
        result = smooth_signal(arr, window=3)
        assert len(result) == len(arr)


class TestDownsampleSignal:
    def test_reduces_to_max_samples(self):
        arr = np.arange(1000, dtype=float)
        result = downsample_signal(arr, max_samples=100)
        assert len(result) == 100

    def test_returns_unchanged_when_under_max(self):
        arr = np.array([1.0, 2.0, 3.0])
        result = downsample_signal(arr, max_samples=100)
        np.testing.assert_array_equal(result, arr)
