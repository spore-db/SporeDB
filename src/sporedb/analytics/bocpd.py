"""Bayesian Online Changepoint Detection (BOCPD) for real-time phase monitoring.

Implements Adams and MacKay (2007) with a Normal-Inverse-Gamma conjugate model
for univariate observations. Designed for streaming bioprocess telemetry where
phase transitions need to be detected as new data arrives.
"""

from __future__ import annotations

from datetime import UTC
from uuid import UUID

import numpy as np
import pandas as pd
from scipy.stats import t as student_t

from sporedb.analytics.models import BOCPDConfig, PhaseAnnotation, PhaseType
from sporedb.analytics.preprocessing import validate_signal

_REQUIRED_COLUMNS = {"ts", "variable", "value"}


class BOCPDDetector:
    """Bayesian Online Changepoint Detection for real-time phase monitoring.

    Maintains run length posterior R[t, r] = P(r_t = r | x_{1:t}).
    Changepoint detected when R[t, 0] exceeds threshold.
    Uses Normal-Inverse-Gamma conjugate model for univariate observations.

    Parameters
    ----------
    config : BOCPDConfig | None
        Detection parameters. Defaults to ``BOCPDConfig()``.
    """

    _t: int
    _run_length_probs: np.ndarray[tuple[int], np.dtype[np.float64]]
    _mu_params: np.ndarray[tuple[int], np.dtype[np.float64]]
    _kappa_params: np.ndarray[tuple[int], np.dtype[np.float64]]
    _alpha_params: np.ndarray[tuple[int], np.dtype[np.float64]]
    _beta_params: np.ndarray[tuple[int], np.dtype[np.float64]]

    def __init__(self, config: BOCPDConfig | None = None) -> None:
        self._config = config or BOCPDConfig()
        self._reset_state()

    @property
    def config(self) -> BOCPDConfig:
        return self._config

    @property
    def run_length_probs(self) -> np.ndarray:
        """Current run length posterior distribution."""
        return self._run_length_probs

    @property
    def t(self) -> int:
        """Number of observations processed."""
        return self._t

    def update(self, x: float) -> tuple[bool, float]:
        """Process one data point. Returns (changepoint_detected, cp_probability).

        Implements the Adams-MacKay (2007) algorithm:
        1. Compute predictive probability (Student-t posterior predictive)
        2. Compute growth probabilities (no changepoint)
        3. Compute changepoint probability (sum over all run lengths * hazard)
        4. Update run length distribution
        5. Normalize
        6. Update NIG sufficient statistics
        7. Truncate if exceeding max_run_length

        Detection criterion: the cumulative probability mass on short run
        lengths (0..threshold_window) exceeds ``threshold``. This captures
        the posterior's shift toward short run lengths after a regime change.
        """
        # Check for NaN/Inf input (T-05-03 mitigation)
        if not np.isfinite(x):
            # Treat non-finite as no-information update
            return False, 0.0

        hazard = self._config.hazard_rate

        # Step 1: Predictive probabilities under each run length
        pred_probs = self._predictive(x)

        # Step 2: Growth probabilities (existing run length continues)
        growth_probs = self._run_length_probs * pred_probs * (1.0 - hazard)

        # Step 3: Changepoint probability (new run starts)
        cp_prob = float(np.sum(self._run_length_probs * pred_probs * hazard))

        # Step 4: Update run length distribution
        new_rl = np.empty(len(growth_probs) + 1)
        new_rl[0] = cp_prob
        new_rl[1:] = growth_probs

        # Step 5: Normalize
        evidence = np.sum(new_rl)
        if evidence > 0:
            new_rl /= evidence
        else:
            # Fallback: reset to prior
            new_rl = np.array([1.0])

        self._run_length_probs = new_rl

        # Step 6: Update NIG sufficient statistics
        self._update_params(x)

        # Step 7: Truncate if needed
        self._truncate()

        self._t += 1

        # Detect changepoint: MAP run length dropped significantly
        # A changepoint is signaled when the MAP (most probable) run length
        # drops to a small value, indicating the posterior has shifted to
        # believe a new regime started recently.
        map_rl = int(np.argmax(new_rl))
        # Use a short-run-length window: sum probability in first few run lengths
        short_window = min(10, len(new_rl))
        short_mass = float(np.sum(new_rl[:short_window]))

        # Changepoint detected when either:
        # 1. MAP run length is very short (< 5) AND we've seen enough data, OR
        # 2. Short run length mass exceeds threshold
        # Need some burn-in before detecting changes
        detected = self._t > 10 and map_rl < 5 and short_mass > self._config.threshold

        return detected, short_mass

    def reset(self) -> None:
        """Reset to initial state (clear all posteriors)."""
        self._reset_state()

    def detect_batch(
        self, telemetry_df: pd.DataFrame, batch_id: UUID
    ) -> list[PhaseAnnotation]:
        """Run BOCPD over a complete telemetry DataFrame and return detected phases.

        Convenience method that iterates update() over all data points and
        converts detected changepoints to PhaseAnnotation objects.

        Parameters
        ----------
        telemetry_df : pd.DataFrame
            Must contain columns: ``ts``, ``variable``, ``value``.
        batch_id : UUID
            Batch identifier for the resulting phase annotations.

        Returns
        -------
        list[PhaseAnnotation]
            Detected phases with timestamps and labels.

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

        # Validate signal (T-05-03: NaN/Inf handling)
        values = validate_signal(values)

        # Reset detector state for fresh batch processing
        self.reset()

        # Run BOCPD over all data points
        changepoint_indices: list[int] = []
        for i, x in enumerate(values):
            detected, _ = self.update(float(x))
            if detected and i > 0:  # Skip index 0 (trivial changepoint)
                changepoint_indices.append(i)

        # Convert changepoints to PhaseAnnotation objects
        return self._build_annotations(
            changepoint_indices, timestamps, values, batch_id
        )

    def _predictive(self, x: float) -> np.ndarray:
        """Student-t posterior predictive for each run length.

        Under the Normal-Inverse-Gamma model, the posterior predictive is
        Student-t with parameters derived from the sufficient statistics.
        """
        # Degrees of freedom
        df = 2.0 * self._alpha_params
        # Location
        loc = self._mu_params
        # Scale
        scale = np.sqrt(
            self._beta_params
            * (self._kappa_params + 1.0)
            / (self._alpha_params * self._kappa_params)
        )

        # Compute Student-t PDF for each run length
        probs = student_t.pdf(x, df=df, loc=loc, scale=scale)

        # Guard against numerical issues
        probs = np.maximum(probs, 1e-300)

        return probs  # type: ignore[no-any-return]

    def _update_params(self, x: float) -> None:
        """Update Normal-Inverse-Gamma sufficient statistics.

        Appends prior parameters at position 0 (for new run length = 0)
        and updates existing parameters for run lengths that grew.
        """
        mu_old = self._mu_params
        kappa_old = self._kappa_params
        alpha_old = self._alpha_params
        beta_old = self._beta_params

        # New kappa, alpha
        kappa_new = kappa_old + 1.0
        alpha_new = alpha_old + 0.5

        # New mu
        mu_new = (kappa_old * mu_old + x) / kappa_new

        # New beta
        beta_new = beta_old + 0.5 * kappa_old * (x - mu_old) ** 2 / kappa_new

        # Prepend prior values for run length 0 (new segment starts)
        self._mu_params = np.concatenate([[self._config.mu0], mu_new])
        self._kappa_params = np.concatenate([[self._config.kappa0], kappa_new])
        self._alpha_params = np.concatenate([[self._config.alpha0], alpha_new])
        self._beta_params = np.concatenate([[self._config.beta0], beta_new])

    def _truncate(self) -> None:
        """Truncate run length posterior to max_run_length.

        Merges probability mass beyond max_run_length into R[0]
        (changepoint), then slices all parameter arrays.
        """
        max_rl = self._config.max_run_length
        if len(self._run_length_probs) > max_rl + 1:
            # Merge truncated mass into changepoint probability
            overflow_mass = np.sum(self._run_length_probs[max_rl + 1 :])
            self._run_length_probs = self._run_length_probs[: max_rl + 1]
            self._run_length_probs[0] += overflow_mass

            # Re-normalize
            total = np.sum(self._run_length_probs)
            if total > 0:
                self._run_length_probs /= total

            # Slice parameter arrays
            self._mu_params = self._mu_params[: max_rl + 1]
            self._kappa_params = self._kappa_params[: max_rl + 1]
            self._alpha_params = self._alpha_params[: max_rl + 1]
            self._beta_params = self._beta_params[: max_rl + 1]

    def _reset_state(self) -> None:
        """Initialize/reset sufficient statistics to prior."""
        self._t = 0
        self._run_length_probs = np.array([1.0])
        self._mu_params = np.array([self._config.mu0])
        self._kappa_params = np.array([self._config.kappa0])
        self._alpha_params = np.array([self._config.alpha0])
        self._beta_params = np.array([self._config.beta0])

    def _build_annotations(
        self,
        changepoint_indices: list[int],
        timestamps: np.ndarray,
        values: np.ndarray,
        batch_id: UUID,
    ) -> list[PhaseAnnotation]:
        """Convert changepoint indices to PhaseAnnotation objects.

        Labels phases using growth-rate heuristic consistent with PhaseDetector.
        """
        n = len(values)
        if n == 0:
            return []

        # Build segment boundaries
        boundaries = [0] + changepoint_indices + [n]
        segments: list[tuple[int, int]] = []
        for i in range(len(boundaries) - 1):
            s, e = boundaries[i], boundaries[i + 1]
            if e > s:
                segments.append((s, e))

        if not segments:
            return []

        # Compute growth rates for labeling
        growth_rates: list[float] = []
        for s, e in segments:
            seg_len = e - s
            if seg_len <= 1:
                growth_rates.append(0.0)
            else:
                rate = (values[min(e - 1, n - 1)] - values[s]) / seg_len
                growth_rates.append(float(rate))

        # Label using growth-rate heuristic
        labels = self._label_segments(growth_rates)

        # Build PhaseAnnotation objects
        annotations: list[PhaseAnnotation] = []
        for i, (s, e) in enumerate(segments):
            end_idx = min(e - 1, n - 1)
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
                    metadata={
                        "growth_rate": growth_rates[i],
                        "detection_method": "bocpd",
                    },
                )
            )

        return annotations

    @staticmethod
    def _label_segments(growth_rates: list[float]) -> list[PhaseType]:
        """Label segments by growth-rate classification.

        Same heuristic as PhaseDetector._label_phases for consistency.
        """
        n_segments = len(growth_rates)
        if n_segments == 0:
            return []

        max_rate = max(growth_rates)
        exp_idx = growth_rates.index(max_rate) if max_rate > 0 else -1

        abs_rates = [abs(r) for r in growth_rates]
        max_abs_rate = max(abs_rates) if abs_rates else 1.0
        threshold = 0.10 * max_abs_rate

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

        return labels
