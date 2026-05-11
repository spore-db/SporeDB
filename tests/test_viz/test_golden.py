"""Tests for golden batch dashboard widget (IFACE-04)."""

from __future__ import annotations

from uuid import UUID

import ipywidgets as widgets
import plotly.graph_objects as go
import pytest

from sporedb.viz._golden import golden_batch_dashboard


class TestGoldenLayout:
    """golden_batch_dashboard returns correct widget structure."""

    def test_returns_vbox(self, mock_db, batch_ids) -> None:
        w = golden_batch_dashboard(mock_db, batch_ids)
        assert isinstance(w, widgets.VBox)

    def test_vbox_has_three_children(self, mock_db, batch_ids) -> None:
        w = golden_batch_dashboard(mock_db, batch_ids)
        # children: IntSlider, FigureWidget, HTML
        assert len(w.children) == 3

    def test_first_child_is_int_slider(self, mock_db, batch_ids) -> None:
        w = golden_batch_dashboard(mock_db, batch_ids)
        assert isinstance(w.children[0], widgets.IntSlider)

    def test_slider_max_equals_batch_count(self, mock_db, batch_ids) -> None:
        w = golden_batch_dashboard(mock_db, batch_ids)
        slider = w.children[0]
        assert slider.max == len(batch_ids)
        assert slider.min == 2

    def test_slider_default_value(self, mock_db, batch_ids) -> None:
        w = golden_batch_dashboard(mock_db, batch_ids)
        slider = w.children[0]
        assert slider.value == min(3, len(batch_ids))

    def test_second_child_is_figure_widget(self, mock_db, batch_ids) -> None:
        w = golden_batch_dashboard(mock_db, batch_ids)
        assert isinstance(w.children[1], go.FigureWidget)

    def test_third_child_is_html(self, mock_db, batch_ids) -> None:
        w = golden_batch_dashboard(mock_db, batch_ids)
        assert isinstance(w.children[2], widgets.HTML)


class TestGoldenInitialRender:
    """Initial render creates golden profile visualization."""

    def test_initial_render_creates_traces(self, mock_db, batch_ids) -> None:
        w = golden_batch_dashboard(mock_db, batch_ids)
        fig = w.children[1]
        # Should have traces: upper bound, lower bound (fill), mean, batch traces
        assert len(fig.data) >= 3

    def test_initial_render_calls_align(self, mock_db, batch_ids) -> None:
        golden_batch_dashboard(mock_db, batch_ids)
        mock_db.align.assert_called()

    def test_mean_trace_has_blue_line(self, mock_db, batch_ids) -> None:
        w = golden_batch_dashboard(mock_db, batch_ids)
        fig = w.children[1]
        # Find the golden mean trace
        mean_traces = [t for t in fig.data if "Golden Mean" in (t.name or "")]
        assert len(mean_traces) >= 1
        assert mean_traces[0].line.color == "blue"

    def test_envelope_trace_has_fill(self, mock_db, batch_ids) -> None:
        w = golden_batch_dashboard(mock_db, batch_ids)
        fig = w.children[1]
        fill_traces = [t for t in fig.data if t.fill == "tonexty"]
        assert len(fill_traces) >= 1

    def test_all_batches_used_shows_no_score(self, mock_db, batch_ids) -> None:
        """When slider == len(batch_ids), no batches remain for scoring."""
        w = golden_batch_dashboard(mock_db, batch_ids)
        # Default slider value is min(3, 3) = 3, using all batches
        html = w.children[2]
        assert "All batches" in html.value or "none to score" in html.value

    def test_individual_batch_traces_dotted(self, mock_db, batch_ids) -> None:
        w = golden_batch_dashboard(mock_db, batch_ids)
        fig = w.children[1]
        dot_traces = [t for t in fig.data if t.line and t.line.dash == "dot"]
        assert len(dot_traces) >= 1


class TestGoldenScoring:
    """Scoring of remaining batches against golden profile."""

    def test_scoring_with_remaining_batches(self, mock_db, batch_ids) -> None:
        """Set slider to 2 so 1 batch remains for scoring."""
        w = golden_batch_dashboard(mock_db, batch_ids)
        slider = w.children[0]
        slider.value = 2
        html = w.children[2]
        # Should show a score for the remaining batch
        assert "score=" in html.value or "could not score" in html.value


class TestGoldenValidation:
    """Input validation."""

    def test_single_batch_raises(self, mock_db) -> None:
        with pytest.raises(ValueError, match="At least 2"):
            golden_batch_dashboard(
                mock_db, [UUID("00000000-0000-0000-0000-000000000001")]
            )

    def test_empty_batch_ids_raises(self, mock_db) -> None:
        with pytest.raises(ValueError, match="At least 2"):
            golden_batch_dashboard(mock_db, [])
