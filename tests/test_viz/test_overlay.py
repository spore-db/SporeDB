"""Tests for multi-run overlay chart (ANLYT-04)."""

from __future__ import annotations

from uuid import UUID

import plotly.graph_objects as go
import pytest

from sporedb.viz._overlay import overlay_runs


class TestOverlayReturnType:
    """overlay_runs must return FigureWidget for Jupyter interactivity."""

    def test_returns_figure_widget(self, mock_db, batch_ids) -> None:
        fig = overlay_runs(mock_db, batch_ids)
        assert isinstance(fig, go.FigureWidget)

    def test_not_plain_figure(self, mock_db, batch_ids) -> None:
        fig = overlay_runs(mock_db, batch_ids)
        # FigureWidget is a subclass of Figure, but we need the widget subclass
        assert type(fig).__name__ == "FigureWidget"


class TestOverlayTraceCount:
    """Correct number of traces for given batches and variables."""

    def test_single_variable_three_batches(self, mock_db, batch_ids) -> None:
        fig = overlay_runs(mock_db, batch_ids, variables=["OD600"])
        # 3 batches x 1 variable = 3 scatter traces
        scatter_traces = [t for t in fig.data if isinstance(t, go.Scatter)]
        assert len(scatter_traces) == 3

    def test_two_variables_two_batches(self, mock_db, batch_ids) -> None:
        two_ids = batch_ids[:2]
        fig = overlay_runs(mock_db, two_ids, variables=["OD600", "pH"])
        # 2 batches x 2 variables = 4 scatter traces
        scatter_traces = [t for t in fig.data if isinstance(t, go.Scatter)]
        assert len(scatter_traces) == 4

    def test_default_variable_is_od600(self, mock_db, batch_ids) -> None:
        overlay_runs(mock_db, batch_ids)
        # Should use OD600 as default, so align called with signal="OD600"
        mock_db.align.assert_called()
        call_args = mock_db.align.call_args
        assert call_args[1].get("signal") == "OD600"


class TestOverlayPhaseMarkers:
    """Phase boundary markers controlled by show_phases flag."""

    def test_phase_markers_added_when_show_phases_true(
        self, mock_db, batch_ids
    ) -> None:
        fig = overlay_runs(mock_db, batch_ids, show_phases=True)
        # detect_phases should be called for first batch
        mock_db.detect_phases.assert_called_once()
        # vrect shapes should exist in layout
        shapes = fig.layout.shapes
        assert len(shapes) > 0

    def test_no_phase_markers_when_show_phases_false(self, mock_db, batch_ids) -> None:
        fig = overlay_runs(mock_db, batch_ids, show_phases=False)
        mock_db.detect_phases.assert_not_called()
        shapes = fig.layout.shapes
        assert len(shapes) == 0


class TestOverlayColors:
    """Each batch gets a distinct color."""

    def test_distinct_colors_per_batch(self, mock_db, batch_ids) -> None:
        fig = overlay_runs(mock_db, batch_ids, variables=["OD600"])
        colors = [t.line.color for t in fig.data if hasattr(t, "line") and t.line.color]
        # All 3 should be different
        assert len(set(colors)) == 3


class TestOverlayLayout:
    """Layout configuration checks."""

    def test_plotly_white_template(self, mock_db, batch_ids) -> None:
        fig = overlay_runs(mock_db, batch_ids)
        # plotly_white sets a white plot background
        bg = fig.layout.template.layout.plot_bgcolor
        assert bg == "white" or bg == "#fff" or bg == "#ffffff"

    def test_height_scales_with_variables(self, mock_db, batch_ids) -> None:
        fig1 = overlay_runs(mock_db, batch_ids, variables=["OD600"])
        fig2 = overlay_runs(mock_db, batch_ids, variables=["OD600", "pH"])
        assert fig1.layout.height == 300
        assert fig2.layout.height == 600

    def test_hovermode_x_unified(self, mock_db, batch_ids) -> None:
        fig = overlay_runs(mock_db, batch_ids)
        assert fig.layout.hovermode == "x unified"


class TestOverlayValidation:
    """Input validation."""

    def test_empty_batch_ids_raises(self, mock_db) -> None:
        with pytest.raises(ValueError, match="non-empty"):
            overlay_runs(mock_db, [])

    def test_more_than_10_batches_raises(self, mock_db) -> None:
        ids = [UUID(f"00000000-0000-0000-0000-{i:012d}") for i in range(11)]
        with pytest.raises(ValueError, match="Maximum 10"):
            overlay_runs(mock_db, ids)
