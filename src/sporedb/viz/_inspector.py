"""Interactive phase inspection widget for Jupyter notebooks."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

import ipywidgets as widgets
import plotly.graph_objects as go

from sporedb.analytics.models import PhaseAnnotation
from sporedb.viz._phase_markers import PHASE_COLORS

if TYPE_CHECKING:
    from sporedb.client import SporeDB


def phase_inspector(
    db: SporeDB,
    batch_ids: list[UUID],
    signals: list[str] | None = None,
) -> widgets.VBox:
    """Interactive widget for inspecting phases across batches.

    Provides dropdown controls for batch and signal selection.
    Displays the time-series with phase boundary shading and
    a summary panel showing phase type, start, and end times.

    Args:
        db: SporeDB client instance.
        batch_ids: List of batch UUIDs available for inspection.
        signals: Available signal names for the dropdown
            (default: ["OD600", "pH", "DO", "temperature"]).

    Returns:
        ipywidgets.VBox containing controls, FigureWidget, and info panel.

    Raises:
        ValueError: If batch_ids is empty.
    """
    if not batch_ids:
        raise ValueError("batch_ids must be non-empty")
    if signals is None:
        signals = ["OD600", "pH", "DO", "temperature"]

    batch_dropdown = widgets.Dropdown(
        options=[(str(bid)[:12] + "..", bid) for bid in batch_ids],
        value=batch_ids[0],
        description="Batch:",
    )
    signal_dropdown = widgets.Dropdown(
        options=signals,
        value=signals[0],
        description="Signal:",
    )
    show_phases_cb = widgets.Checkbox(
        value=True,
        description="Show phases",
    )

    fig = go.FigureWidget()
    fig.update_layout(
        height=450,
        template="plotly_white",
        hovermode="x unified",
    )

    phase_info = widgets.HTML(value="<i>Select a batch to inspect phases</i>")

    def _update(change: object = None) -> None:
        bid = batch_dropdown.value
        signal = signal_dropdown.value

        # Fetch telemetry and filter to selected signal
        df = db.get_telemetry(bid)
        sig_df = df[df["variable"] == signal].sort_values("ts")

        with fig.batch_update():
            fig.data = []
            if not sig_df.empty:
                fig.add_scatter(
                    x=sig_df["ts"].tolist(),
                    y=sig_df["value"].tolist(),
                    name=signal,
                    mode="lines",
                    line=dict(color="#1f77b4"),
                )

            # Clear existing shapes
            fig.layout.shapes = ()

            if show_phases_cb.value:
                phases: list[PhaseAnnotation] = db.detect_phases(bid, signal=signal)
                for ann in phases:
                    fig.add_shape(
                        type="rect",
                        x0=ann.start_ts,
                        x1=ann.end_ts,
                        y0=0,
                        y1=1,
                        yref="y domain",
                        fillcolor=PHASE_COLORS.get(
                            ann.phase_type.value, "rgba(128,128,128,0.1)"
                        ),
                        layer="below",
                        line_width=0,
                    )
                # Build info panel HTML
                rows = [
                    f"<b>{p.phase_type.value}</b>: "
                    f"{p.start_ts:%H:%M} - {p.end_ts:%H:%M} "
                    f"(conf: {p.confidence:.2f})"
                    for p in phases
                ]
                phase_info.value = (
                    "<br>".join(rows) if rows else "<i>No phases detected</i>"
                )
            else:
                phase_info.value = "<i>Phase display disabled</i>"

        fig.update_layout(
            title=f"{signal} - Batch {str(bid)[:12]}",
            xaxis_title="Timestamp",
            yaxis_title=signal,
        )

    batch_dropdown.observe(_update, names="value")
    signal_dropdown.observe(_update, names="value")
    show_phases_cb.observe(_update, names="value")
    _update()  # Initial render

    return widgets.VBox(
        [
            widgets.HBox([batch_dropdown, signal_dropdown, show_phases_cb]),
            fig,
            phase_info,
        ]
    )
