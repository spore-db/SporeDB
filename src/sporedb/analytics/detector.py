"""PELT-based changepoint detection with growth-rate phase labeling.

Uses ruptures KernelCPD (C-optimized PELT with RBF kernel) to detect
changepoints in bioprocess signals, then classifies each segment by
its growth rate to assign biologically meaningful phase labels.
"""

from __future__ import annotations

from datetime import UTC
from uuid import UUID

import numpy as np
import pandas as pd
import ruptures as rpt

from sporedb.analytics.models import DetectionConfig, PhaseAnnotation, PhaseType
from sporedb.analytics.preprocessing import (
    downsample_signal,
    interpolate_nans,
    smooth_signal,
    validate_signal,
)

_REQUIRED_COLUMNS = {"ts", "variable", "value"}


class PhaseDetector:
    """Detect bioprocess phases using PELT changepoint detection.

    Wraps ``ruptures.KernelCPD`` with RBF kernel for changepoint
    detection, then labels each segment by growth-rate classification
    (not positional ordering).

    Parameters
    ----------
    config : DetectionConfig | None
        Detection parameters. Defaults to ``DetectionConfig()`` which
        uses OD600, RBF kernel, min_size=10, auto-BIC penalty, and
        smoothing_window=5.
    """

    def __init__(self, config: DetectionConfig | None = None) -> None:
        self._config = config or DetectionConfig()

    @property
    def config(self) -> DetectionConfig:
        return self._config

    def detect(
        self, telemetry_df: pd.DataFrame, batch_id: UUID
    ) -> list[PhaseAnnotation]:
        """Detect phases in a telemetry DataFrame.

        Parameters
        ----------
        telemetry_df : pd.DataFrame
            Must contain columns: ``ts``, ``variable``, ``value``.
        batch_id : UUID
            Batch identifier for the resulting phase annotations.

        Returns
        -------
        list[PhaseAnnotation]
            Ordered list of detected phases with timestamps and labels.

        Raises
        ------
        ValueError
            If required columns are missing, DataFrame is empty, or
            the configured signal variable has no data.
        """
        # Validate required columns
        missing = _REQUIRED_COLUMNS - set(telemetry_df.columns)
        if missing:
            raise ValueError(f"DataFrame missing required columns: {sorted(missing)}")

        # Filter to configured signal variable
        signal_df = telemetry_df[
            telemetry_df["variable"] == self._config.signal_variable
        ].copy()

        if signal_df.empty:
            raise ValueError(
                f"No data for signal variable '{self._config.signal_variable}'"
            )

        # Sort by timestamp and extract arrays
        signal_df = signal_df.sort_values("ts").reset_index(drop=True)
        values = signal_df["value"].to_numpy(dtype=float)
        timestamps = signal_df["ts"].to_numpy()

        # Preprocess pipeline: validate -> interpolate -> smooth -> downsample
        processed = validate_signal(values)
        processed = interpolate_nans(processed)
        processed = smooth_signal(processed, window=self._config.smoothing_window)
        processed = downsample_signal(processed)

        # Fit PELT with KernelCPD (C-optimized)
        algo = rpt.KernelCPD(
            kernel=self._config.kernel,
            min_size=self._config.min_size,
        ).fit(processed.reshape(-1, 1))

        # Determine penalty
        if self._config.penalty is None:
            pen = self._auto_penalty(processed)
        else:
            pen = self._config.penalty

        # Detect breakpoints
        bkps = algo.predict(pen=pen)

        # Map breakpoint indices back to original array size if downsampled
        if len(processed) < len(values):
            scale = len(values) / len(processed)
            bkps = [min(round(b * scale), len(values)) for b in bkps]
            # Ensure last breakpoint is exactly n_original
            if bkps and bkps[-1] != len(values):
                bkps[-1] = len(values)

        return self._label_phases(bkps, timestamps, values, batch_id)

    def _auto_penalty(self, values: np.ndarray) -> float:
        """Compute BIC auto-penalty: log(n) * variance(signal).

        This is the standard BIC penalty used in changepoint detection
        to balance model complexity against fit quality.

        For constant or near-constant signals, a variance floor of 1.0
        is used to prevent a zero penalty (which would cause ruptures
        to return the maximum number of breakpoints).
        """
        variance = float(np.var(values))
        if variance < 1e-10:
            # Constant signal: use variance floor to suppress spurious breakpoints
            variance = 1.0
        return float(np.log(len(values)) * variance)

    def _label_phases(
        self,
        bkps: list[int],
        timestamps: np.ndarray,
        values: np.ndarray,
        batch_id: UUID,
    ) -> list[PhaseAnnotation]:
        """Label segments by growth-rate classification.

        Labels are assigned based on growth rate, NOT positional ordering:
        - Highest positive growth rate -> EXPONENTIAL
        - Near-zero rate before exponential -> LAG
        - Near-zero rate after exponential -> STATIONARY
        - Negative rate after peak value -> DECLINE
        - Anything else -> UNKNOWN
        """
        # Build segment boundaries
        starts = [0] + bkps[:-1]
        ends = bkps

        # Compute growth rate for each segment
        growth_rates: list[float] = []
        for s, e in zip(starts, ends, strict=True):
            seg_len = e - s
            if seg_len <= 1:
                growth_rates.append(0.0)
            else:
                rate = (values[min(e - 1, len(values) - 1)] - values[s]) / seg_len
                growth_rates.append(float(rate))

        n_segments = len(growth_rates)
        if n_segments == 0:
            return []

        # Find the segment with the highest positive growth rate -> EXPONENTIAL
        max_rate = max(growth_rates)
        exp_idx = growth_rates.index(max_rate) if max_rate > 0 else -1

        # Threshold for "near-zero" growth rate
        abs_rates = [abs(r) for r in growth_rates]
        max_abs_rate = max(abs_rates) if abs_rates else 1.0
        threshold = 0.10 * max_abs_rate  # 10% of max absolute rate

        # Classify each segment
        labels: list[PhaseType] = []
        for i, rate in enumerate(growth_rates):
            if i == exp_idx:
                labels.append(PhaseType.EXPONENTIAL)
            elif rate < 0 and i > exp_idx and exp_idx >= 0:
                labels.append(PhaseType.DECLINE)
            elif abs(rate) < threshold and i < exp_idx and exp_idx >= 0:
                labels.append(PhaseType.LAG)
            elif abs(rate) < threshold and i > exp_idx and exp_idx >= 0:
                labels.append(PhaseType.STATIONARY)
            else:
                labels.append(PhaseType.UNKNOWN)

        # Build PhaseAnnotation objects
        annotations: list[PhaseAnnotation] = []
        for i, (s, e) in enumerate(zip(starts, ends, strict=True)):
            end_idx = min(e, len(timestamps) - 1)
            start_ts = pd.Timestamp(timestamps[s]).to_pydatetime()
            end_ts = pd.Timestamp(timestamps[end_idx]).to_pydatetime()

            # Ensure timezone-aware
            if start_ts.tzinfo is None:
                start_ts = start_ts.replace(tzinfo=UTC)
                end_ts = end_ts.replace(tzinfo=UTC)

            annotations.append(
                PhaseAnnotation(
                    batch_id=batch_id,
                    phase_type=labels[i],
                    start_ts=start_ts,
                    end_ts=end_ts,
                    signal_variable=self._config.signal_variable,
                    confidence=1.0,
                    metadata={"growth_rate": growth_rates[i]},
                )
            )

        return annotations
