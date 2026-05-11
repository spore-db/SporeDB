"""Derived bioprocess metrics: growth rate, productivity, yield coefficients.

Provides functions for computing kinetic parameters from batch telemetry data:
- Specific growth rate (mu) via log-linear regression
- Volumetric productivity (Qp)
- Yield coefficients (Yx/s, Yp/s) with optional uncertainty propagation
- Orchestrated batch metrics computation for all phases
"""

from __future__ import annotations

import contextlib
from typing import Any
from uuid import UUID

import numpy as np
import pandas as pd
from scipy.stats import linregress

from sporedb.analytics.models import BatchMetrics, PhaseAnnotation, PhaseType


def compute_specific_growth_rate(
    time_hours: np.ndarray,
    biomass_values: np.ndarray,
) -> tuple[float, float, float]:
    """Compute specific growth rate mu (h^-1) via log-linear regression.

    mu = d(ln(X)) / dt, implemented as slope of linear regression on ln(X) vs time.

    Args:
        time_hours: Time array in hours (relative, starting from 0).
        biomass_values: Biomass concentration array (OD600, DCW, etc.). Must be > 0.

    Returns:
        Tuple of (mu, r_squared, std_error).

    Raises:
        ValueError: If biomass_values contains non-positive values.
    """
    if len(time_hours) < 2 or len(biomass_values) < 2:
        raise ValueError("Need at least 2 data points for growth rate computation")
    if np.any(biomass_values <= 0):
        raise ValueError("Biomass values must be positive for log transform")
    ln_x = np.log(biomass_values)
    result = linregress(time_hours, ln_x)
    return float(result.slope), float(result.rvalue**2), float(result.stderr)


def compute_volumetric_productivity(
    product_concentration: np.ndarray,
    time_hours: np.ndarray,
) -> float:
    """Compute volumetric productivity Qp (g/L/h).

    Qp = (P_final - P_initial) / (t_final - t_initial).
    Returns 0.0 if time delta is zero.
    """
    if len(product_concentration) < 2 or len(time_hours) < 2:
        raise ValueError("Need at least 2 data points for productivity computation")
    delta_p = float(product_concentration[-1] - product_concentration[0])
    delta_t = float(time_hours[-1] - time_hours[0])
    return delta_p / delta_t if delta_t > 0 else 0.0


def compute_yield_coefficient(
    consumed: np.ndarray | None = None,
    produced: np.ndarray | None = None,
    consumed_uncertain: list[Any] | None = None,
    produced_uncertain: list[Any] | None = None,
) -> float | tuple[float, float]:
    """Compute yield coefficient Y = delta_produced / delta_consumed.

    For Yx/s: produced = biomass, consumed = substrate.
    For Yp/s: produced = product, consumed = substrate.

    Note: substrate DECREASES, so delta_consumed = consumed[0] - consumed[-1].

    If consumed_uncertain/produced_uncertain are provided (lists of UncertainValue),
    uses uncertainties library for error propagation and returns (yield, uncertainty).
    Otherwise returns float.

    Returns 0.0 (or (0.0, 0.0)) when substrate consumption is near-zero.
    """
    if consumed_uncertain is not None and produced_uncertain is not None:
        # Uncertainty-aware computation
        delta_produced = (
            produced_uncertain[-1].to_ufloat() - produced_uncertain[0].to_ufloat()
        )
        delta_consumed = (
            consumed_uncertain[0].to_ufloat() - consumed_uncertain[-1].to_ufloat()
        )
        if abs(delta_consumed.nominal_value) < 1e-10:
            return (0.0, 0.0)
        y = delta_produced / delta_consumed
        return (float(y.nominal_value), float(y.std_dev))

    if consumed is not None and produced is not None:
        # Plain numpy computation
        delta_produced = float(produced[-1] - produced[0])
        delta_consumed = float(consumed[0] - consumed[-1])
        if abs(delta_consumed) < 1e-10:
            return 0.0
        return delta_produced / delta_consumed

    raise ValueError(
        "Must provide either (consumed, produced) arrays or "
        "(consumed_uncertain, produced_uncertain) lists"
    )


def compute_batch_metrics(
    telemetry_df: pd.DataFrame,
    phases: list[PhaseAnnotation],
    batch_id: UUID,
    biomass_variable: str = "OD600",
    product_variable: str | None = None,
    substrate_variable: str | None = None,
) -> list[BatchMetrics]:
    """Compute all available metrics for each detected phase.

    Computes mu for exponential phase, Qp if product_variable given,
    Yx/s and Yp/s if both product and substrate variables given.

    Args:
        telemetry_df: DataFrame with columns ts, variable, value.
        phases: List of PhaseAnnotation for the batch.
        batch_id: Batch identifier.
        biomass_variable: Name of biomass signal (default: "OD600").
        product_variable: Name of product signal, if available.
        substrate_variable: Name of substrate signal, if available.

    Returns:
        List of BatchMetrics, one per phase that has computable metrics.
    """
    results: list[BatchMetrics] = []

    for phase in phases:
        # Extract time-series segment for this phase
        mask = (telemetry_df["ts"] >= phase.start_ts) & (
            telemetry_df["ts"] <= phase.end_ts
        )
        phase_df = telemetry_df[mask].copy()

        if phase_df.empty:
            continue

        mu = None
        r_squared = None
        qp = None
        yx_s = None
        yp_s = None

        # Extract biomass data for this phase
        biomass_df = phase_df[phase_df["variable"] == biomass_variable].sort_values(
            "ts"
        )

        if not biomass_df.empty and len(biomass_df) >= 2:
            biomass_values = biomass_df["value"].to_numpy(dtype=float)
            # Compute time in hours relative to phase start
            time_hours = (
                pd.to_datetime(biomass_df["ts"]) - pd.Timestamp(phase.start_ts)
            ).dt.total_seconds().to_numpy() / 3600.0

            # Compute mu for exponential phase
            if phase.phase_type == PhaseType.EXPONENTIAL and np.all(biomass_values > 0):
                with contextlib.suppress(ValueError, Exception):
                    mu, r_squared, _ = compute_specific_growth_rate(
                        time_hours, biomass_values
                    )

            # Compute Qp if product variable is available
            if product_variable is not None:
                product_df = phase_df[
                    phase_df["variable"] == product_variable
                ].sort_values("ts")
                if not product_df.empty and len(product_df) >= 2:
                    product_values = product_df["value"].to_numpy(dtype=float)
                    product_time = (
                        pd.to_datetime(product_df["ts"]) - pd.Timestamp(phase.start_ts)
                    ).dt.total_seconds().to_numpy() / 3600.0
                    qp = compute_volumetric_productivity(product_values, product_time)

            # Compute yield coefficients if substrate variable is available
            if substrate_variable is not None:
                substrate_df = phase_df[
                    phase_df["variable"] == substrate_variable
                ].sort_values("ts")
                if not substrate_df.empty and len(substrate_df) >= 2:
                    # Align biomass and substrate by common time range
                    common_start = max(
                        pd.Timestamp(biomass_df["ts"].min()),
                        pd.Timestamp(substrate_df["ts"].min()),
                    )
                    common_end = min(
                        pd.Timestamp(biomass_df["ts"].max()),
                        pd.Timestamp(substrate_df["ts"].max()),
                    )
                    # Use first/last values at common time boundaries
                    bio_common = biomass_df[
                        (biomass_df["ts"] >= common_start)
                        & (biomass_df["ts"] <= common_end)
                    ].sort_values("ts")
                    sub_common = substrate_df[
                        (substrate_df["ts"] >= common_start)
                        & (substrate_df["ts"] <= common_end)
                    ].sort_values("ts")

                    if len(bio_common) >= 2 and len(sub_common) >= 2:
                        bio_vals = bio_common["value"].to_numpy(dtype=float)
                        substrate_values = sub_common["value"].to_numpy(dtype=float)
                    else:
                        substrate_values = substrate_df["value"].to_numpy(dtype=float)
                        bio_vals = biomass_values

                    # Yx/s = biomass yield on substrate
                    yx_s_val = compute_yield_coefficient(
                        consumed=substrate_values,
                        produced=bio_vals,
                    )
                    yx_s = (
                        float(yx_s_val) if isinstance(yx_s_val, (int, float)) else None
                    )

                    # Yp/s = product yield on substrate (if product available)
                    if product_variable is not None:
                        product_df = phase_df[
                            phase_df["variable"] == product_variable
                        ].sort_values("ts")
                        if not product_df.empty and len(product_df) >= 2:
                            product_values = product_df["value"].to_numpy(dtype=float)
                            yp_s_val = compute_yield_coefficient(
                                consumed=substrate_values,
                                produced=product_values,
                            )
                            yp_s = (
                                float(yp_s_val)
                                if isinstance(yp_s_val, (int, float))
                                else None
                            )

        # Only create metrics if we computed something
        if any(v is not None for v in [mu, qp, yx_s, yp_s]):
            results.append(
                BatchMetrics(
                    batch_id=batch_id,
                    phase_type=phase.phase_type,
                    mu=mu,
                    qp=qp,
                    yx_s=yx_s,
                    yp_s=yp_s,
                    r_squared=r_squared,
                    signal_variable=biomass_variable,
                )
            )

    return results
