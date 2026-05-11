"""Shared helpers for SporeDB visualization."""

from __future__ import annotations


def format_trace_name(batch_name: str, variable: str, max_len: int = 20) -> str:
    """Format a trace name for chart legends.

    Truncates long batch names to keep legends readable.

    Args:
        batch_name: Full batch name or UUID string.
        variable: Variable name (e.g., "OD600").
        max_len: Max chars for the batch portion.

    Returns:
        Formatted string like "CHO-Run-042.. OD600".
    """
    if len(batch_name) > max_len:
        batch_name = batch_name[: max_len - 2] + ".."
    return f"{batch_name} {variable}"


def configure_time_axis(fig: object, title: str = "Elapsed Hours") -> None:
    """Configure the x-axis of a FigureWidget for elapsed time display.

    Args:
        fig: A plotly FigureWidget instance.
        title: X-axis title text.
    """
    fig.update_xaxes(title_text=title, tickformat=".1f", hoverformat=".2f")  # type: ignore[attr-defined]
