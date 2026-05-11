"""Phase boundary rendering as vertical shaded rectangles on Plotly charts."""

from __future__ import annotations

from sporedb.analytics.models import PhaseAnnotation, PhaseType

# Semi-transparent fill colors per phase type
PHASE_COLORS: dict[str, str] = {
    PhaseType.LAG.value: "rgba(200,200,200,0.2)",
    PhaseType.EXPONENTIAL.value: "rgba(0,200,0,0.15)",
    PhaseType.STATIONARY.value: "rgba(0,0,200,0.15)",
    PhaseType.DECLINE.value: "rgba(200,0,0,0.15)",
    PhaseType.UNKNOWN.value: "rgba(128,128,128,0.1)",
}


def add_phase_markers(
    fig: object,
    annotations: list[PhaseAnnotation],
) -> None:
    """Add vertical shaded rectangles for each phase boundary to a FigureWidget.

    Each PhaseAnnotation produces a vrect shape from start_ts to end_ts
    with a color determined by the phase type.

    Args:
        fig: A plotly go.FigureWidget instance.
        annotations: List of PhaseAnnotation objects from detect_phases().

    Raises:
        ValueError: If annotations is empty.
    """
    if not annotations:
        raise ValueError("annotations must be non-empty")
    for ann in annotations:
        fig.add_vrect(  # type: ignore[attr-defined]
            x0=ann.start_ts,
            x1=ann.end_ts,
            fillcolor=PHASE_COLORS.get(ann.phase_type.value, "rgba(128,128,128,0.1)"),
            layer="below",
            line_width=0,
            annotation_text=ann.phase_type.value,
            annotation_position="top left",
        )
