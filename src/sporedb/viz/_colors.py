"""Consistent color palette assignment for batch runs."""

from __future__ import annotations

# 10 perceptually distinct colors from Plotly D3 palette
_D3_PALETTE = [
    "#1f77b4",
    "#ff7f0e",
    "#2ca02c",
    "#d62728",
    "#9467bd",
    "#8c564b",
    "#e377c2",
    "#7f7f7f",
    "#bcbd22",
    "#17becf",
]


def get_batch_colors(batch_names: list[str]) -> dict[str, str]:
    """Assign a consistent color to each batch name.

    Uses Plotly D3 qualitative palette (10 colors, cycles for >10 batches).

    Args:
        batch_names: List of batch name strings.

    Returns:
        Dict mapping each batch name to a hex color string.

    Raises:
        ValueError: If batch_names is empty.
    """
    if not batch_names:
        raise ValueError("batch_names must be non-empty")
    return {
        name: _D3_PALETTE[i % len(_D3_PALETTE)] for i, name in enumerate(batch_names)
    }
