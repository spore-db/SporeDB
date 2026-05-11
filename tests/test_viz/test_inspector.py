"""Tests for phase inspector widget (IFACE-04)."""

from __future__ import annotations

import ipywidgets as widgets
import plotly.graph_objects as go
import pytest

from sporedb.viz._inspector import phase_inspector


class TestInspectorLayout:
    """phase_inspector returns correct widget structure."""

    def test_returns_vbox(self, mock_db, batch_ids) -> None:
        w = phase_inspector(mock_db, batch_ids)
        assert isinstance(w, widgets.VBox)

    def test_vbox_has_three_children(self, mock_db, batch_ids) -> None:
        w = phase_inspector(mock_db, batch_ids)
        # children: HBox(controls), FigureWidget, HTML
        assert len(w.children) == 3

    def test_first_child_is_hbox_with_controls(self, mock_db, batch_ids) -> None:
        w = phase_inspector(mock_db, batch_ids)
        controls = w.children[0]
        assert isinstance(controls, widgets.HBox)
        # Should contain batch dropdown, signal dropdown, show_phases checkbox
        assert len(controls.children) == 3
        assert isinstance(controls.children[0], widgets.Dropdown)
        assert isinstance(controls.children[1], widgets.Dropdown)
        assert isinstance(controls.children[2], widgets.Checkbox)

    def test_second_child_is_figure_widget(self, mock_db, batch_ids) -> None:
        w = phase_inspector(mock_db, batch_ids)
        assert isinstance(w.children[1], go.FigureWidget)

    def test_third_child_is_html(self, mock_db, batch_ids) -> None:
        w = phase_inspector(mock_db, batch_ids)
        assert isinstance(w.children[2], widgets.HTML)


class TestInspectorInitialRender:
    """Initial render populates figure and info panel."""

    def test_initial_render_creates_traces(self, mock_db, batch_ids) -> None:
        w = phase_inspector(mock_db, batch_ids)
        fig = w.children[1]
        # Should have at least 1 scatter trace from initial render
        assert len(fig.data) >= 1

    def test_initial_render_calls_detect_phases(self, mock_db, batch_ids) -> None:
        phase_inspector(mock_db, batch_ids)
        mock_db.detect_phases.assert_called()

    def test_initial_render_calls_get_telemetry(self, mock_db, batch_ids) -> None:
        phase_inspector(mock_db, batch_ids)
        mock_db.get_telemetry.assert_called_with(batch_ids[0])

    def test_phase_info_not_empty_after_init(self, mock_db, batch_ids) -> None:
        w = phase_inspector(mock_db, batch_ids)
        html = w.children[2]
        assert html.value != ""
        assert "<b>" in html.value  # Contains formatted phase info

    def test_default_signals(self, mock_db, batch_ids) -> None:
        w = phase_inspector(mock_db, batch_ids)
        signal_dropdown = w.children[0].children[1]
        assert list(signal_dropdown.options) == ["OD600", "pH", "DO", "temperature"]

    def test_show_phases_checkbox_default_true(self, mock_db, batch_ids) -> None:
        w = phase_inspector(mock_db, batch_ids)
        cb = w.children[0].children[2]
        assert cb.value is True


class TestInspectorCallbacks:
    """Widget callbacks update figure correctly."""

    def test_batch_dropdown_updates_traces(self, mock_db, batch_ids) -> None:
        w = phase_inspector(mock_db, batch_ids)
        # Change to second batch
        dropdown = w.children[0].children[0]
        dropdown.value = batch_ids[1]
        # get_telemetry should now have been called with second batch
        mock_db.get_telemetry.assert_called_with(batch_ids[1])

    def test_signal_dropdown_updates_detect_phases(self, mock_db, batch_ids) -> None:
        w = phase_inspector(mock_db, batch_ids)
        signal_dropdown = w.children[0].children[1]
        signal_dropdown.value = "pH"
        # detect_phases should have been called with signal="pH"
        mock_db.detect_phases.assert_called_with(batch_ids[0], signal="pH")

    def test_uncheck_phases_hides_phase_info(self, mock_db, batch_ids) -> None:
        w = phase_inspector(mock_db, batch_ids)
        cb = w.children[0].children[2]
        cb.value = False
        html = w.children[2]
        assert "disabled" in html.value.lower()


class TestInspectorValidation:
    """Input validation."""

    def test_empty_batch_ids_raises(self, mock_db) -> None:
        with pytest.raises(ValueError, match="non-empty"):
            phase_inspector(mock_db, [])

    def test_custom_signals(self, mock_db, batch_ids) -> None:
        w = phase_inspector(mock_db, batch_ids, signals=["pH", "DO"])
        signal_dropdown = w.children[0].children[1]
        assert list(signal_dropdown.options) == ["pH", "DO"]
