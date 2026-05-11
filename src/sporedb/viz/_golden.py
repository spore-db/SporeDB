"""Golden batch dashboard widget for Jupyter notebooks."""

from __future__ import annotations

import html as html_mod
from typing import TYPE_CHECKING
from uuid import UUID

import ipywidgets as widgets
import numpy as np
import plotly.graph_objects as go

from sporedb.analytics.golden_batch import (
    create_golden_profile,
    extract_batch_trajectory,
    score_against_profile,
)
from sporedb.viz._colors import get_batch_colors
from sporedb.viz._utils import configure_time_axis

if TYPE_CHECKING:
    from sporedb.client import SporeDB


def golden_batch_dashboard(
    db: SporeDB,
    batch_ids: list[UUID],
    variables: list[str] | None = None,
) -> widgets.VBox:
    """Dashboard for golden batch creation, visualization, and scoring.

    Provides a top-N slider to select how many batches form the golden
    profile. Displays the golden mean trajectory with +/- 1 std envelope.
    Scores remaining batches against the profile and shows scores.

    Args:
        db: SporeDB client instance.
        batch_ids: List of batch UUIDs to include (minimum 2).
        variables: Variables for the golden profile (default: ["OD600"]).

    Returns:
        ipywidgets.VBox containing slider, FigureWidget, and score panel.

    Raises:
        ValueError: If fewer than 2 batch_ids provided.
    """
    if len(batch_ids) < 2:
        raise ValueError("At least 2 batch_ids required for golden batch comparison")
    if variables is None:
        variables = ["OD600"]

    top_n_slider = widgets.IntSlider(
        value=min(3, len(batch_ids)),
        min=2,
        max=len(batch_ids),
        step=1,
        description="Top N:",
    )

    fig = go.FigureWidget()
    fig.update_layout(
        height=450,
        template="plotly_white",
        hovermode="x unified",
        title="Golden Batch Profile",
    )

    score_output = widgets.HTML(value="<i>Adjust slider to build golden profile</i>")

    batch_names = [str(bid) for bid in batch_ids]
    colors = get_batch_colors(batch_names)

    def _update(change: object = None) -> None:
        n = top_n_slider.value
        selected_ids = batch_ids[:n]
        selected_names = [str(bid) for bid in selected_ids]

        # Align selected batches
        aligned_df = db.align(selected_ids, signal=variables[0])

        # Create golden profile
        profile = create_golden_profile(aligned_df, selected_names, variables)

        # Extract numpy arrays
        mean = np.array(profile.mean_trajectory, dtype=float)  # (timepoints, vars)
        if mean.ndim == 1:
            mean = mean.reshape(-1, 1)
        std = np.array(profile.std_trajectory, dtype=float)
        if std.ndim == 1:
            std = std.reshape(-1, 1)
        hours = profile.elapsed_hours

        with fig.batch_update():
            fig.data = []

            # For each variable (column), plot mean +/- std envelope
            for v_idx, var in enumerate(variables):
                m = mean[:, v_idx]
                s = std[:, v_idx]

                # Upper bound (no legend)
                fig.add_scatter(
                    x=hours,
                    y=(m + s).tolist(),
                    mode="lines",
                    line=dict(width=0),
                    showlegend=False,
                    hoverinfo="skip",
                )
                # Lower bound with fill to previous trace
                fig.add_scatter(
                    x=hours,
                    y=(m - s).tolist(),
                    mode="lines",
                    line=dict(width=0),
                    fill="tonexty",
                    fillcolor="rgba(0,100,200,0.2)",
                    name=f"Golden +/- 1 std ({var})",
                )
                # Mean line
                fig.add_scatter(
                    x=hours,
                    y=m.tolist(),
                    mode="lines",
                    line=dict(color="blue", width=2),
                    name=f"Golden Mean ({var})",
                )

                # Overlay individual batch traces
                for bname in selected_names:
                    col = f"{bname}__{var}"
                    if col in aligned_df.columns:
                        fig.add_scatter(
                            x=aligned_df.index.tolist(),
                            y=aligned_df[col].tolist(),
                            mode="lines",
                            line=dict(color=colors[bname], width=1, dash="dot"),
                            name=f"{bname[:8]}.. {var}",
                            opacity=0.5,
                        )

        configure_time_axis(fig)
        fig.update_layout(title=f"Golden Batch Profile (top {n})")

        # Score remaining batches against profile
        remaining_ids = batch_ids[n:]
        if remaining_ids:
            score_rows = []
            for bid in remaining_ids:
                bname = str(bid)
                # Get telemetry for this batch and extract trajectory
                telemetry_df = db.get_telemetry(bid)
                try:
                    traj = extract_batch_trajectory(telemetry_df, variables)
                    result = score_against_profile(profile, traj, bid)
                    name_esc = html_mod.escape(bname[:12])
                    score_rows.append(
                        f"<b>{name_esc}..</b>: score={result.score:.1f}/100 "
                        f"(dist={result.dtw_normalized_distance:.3f})"
                    )
                except (ValueError, KeyError) as exc:
                    import logging

                    logging.getLogger("sporedb.viz").warning(
                        "Could not score batch %s: %s", bname[:12], exc
                    )
                    score_rows.append(
                        f"<b>{html_mod.escape(bname[:12])}..</b>: could not score"
                    )
            score_output.value = "<br>".join(score_rows)
        else:
            score_output.value = "<i>All batches used in profile -- none to score</i>"

    top_n_slider.observe(_update, names="value")
    _update()  # Initial render

    return widgets.VBox([top_n_slider, fig, score_output])
