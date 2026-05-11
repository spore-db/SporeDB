"""Multi-run overlay chart for comparing batch fermentation runs."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

import plotly.graph_objects as go
from plotly.subplots import make_subplots

from sporedb.viz._colors import get_batch_colors
from sporedb.viz._phase_markers import add_phase_markers
from sporedb.viz._utils import configure_time_axis, format_trace_name

if TYPE_CHECKING:
    from sporedb.client import SporeDB


def overlay_runs(
    db: SporeDB,
    batch_ids: list[UUID],
    variables: list[str] | None = None,
    show_phases: bool = True,
) -> go.FigureWidget:
    """Overlay 2-10 batch runs on an interactive chart with phase boundaries.

    Creates a Plotly FigureWidget with one subplot row per variable,
    each containing scatter traces for every selected batch. Phase
    boundaries from the first batch are shown as shaded vertical regions.

    Args:
        db: SporeDB client instance.
        batch_ids: List of batch UUIDs to overlay (2-10).
        variables: Variable names to plot (default: ["OD600"]).
            Each variable gets its own subplot row.
        show_phases: Whether to render phase boundary markers.

    Returns:
        Interactive go.FigureWidget with pan/zoom support.

    Raises:
        ValueError: If batch_ids is empty or exceeds 10 entries.
    """
    if not batch_ids:
        raise ValueError("batch_ids must be non-empty")
    if len(batch_ids) > 10:
        raise ValueError(
            f"Maximum 10 batches supported for overlay, got {len(batch_ids)}"
        )
    if variables is None:
        variables = ["OD600"]

    batch_names = [str(bid) for bid in batch_ids]
    colors = get_batch_colors(batch_names)

    # Create subplots: one row per variable, shared x-axis
    fig = make_subplots(
        rows=len(variables),
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.05,
        subplot_titles=variables,
    )
    fig = go.FigureWidget(fig)

    # For each variable, align and add traces
    for v_idx, var in enumerate(variables, 1):
        aligned_df = db.align(batch_ids, signal=var)

        for bname in batch_names:
            col = f"{bname}__{var}"
            if col in aligned_df.columns:
                fig.add_scatter(
                    x=aligned_df.index.tolist(),
                    y=aligned_df[col].tolist(),
                    name=format_trace_name(bname, var),
                    mode="lines",
                    line=dict(color=colors[bname]),
                    row=v_idx,
                    col=1,
                )

    # Phase boundary markers from first batch
    if show_phases and batch_ids:
        phases = db.detect_phases(batch_ids[0], signal=variables[0])
        if phases:
            add_phase_markers(fig, phases)

    fig.update_layout(
        height=300 * len(variables),
        template="plotly_white",
        hovermode="x unified",
    )
    configure_time_axis(fig)

    return fig
