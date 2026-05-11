"""Tests for viz foundation modules: colors, utils, phase markers."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest


class TestGetBatchColors:
    """Tests for _colors.get_batch_colors."""

    def test_returns_dict_with_hex_colors(self) -> None:
        from sporedb.viz._colors import get_batch_colors

        result = get_batch_colors(["A", "B", "C"])
        assert isinstance(result, dict)
        assert len(result) == 3
        for _name, color in result.items():
            assert color.startswith("#")
            assert len(color) == 7  # #RRGGBB

    def test_consistent_assignment(self) -> None:
        from sporedb.viz._colors import get_batch_colors

        r1 = get_batch_colors(["X", "Y"])
        r2 = get_batch_colors(["X", "Y"])
        assert r1 == r2

    def test_distinct_colors_up_to_10(self) -> None:
        from sporedb.viz._colors import get_batch_colors

        names = [f"batch-{i}" for i in range(10)]
        result = get_batch_colors(names)
        assert len(set(result.values())) == 10

    def test_cycles_beyond_10(self) -> None:
        from sporedb.viz._colors import get_batch_colors

        names = [f"batch-{i}" for i in range(12)]
        result = get_batch_colors(names)
        assert result["batch-0"] == result["batch-10"]

    def test_empty_raises_value_error(self) -> None:
        from sporedb.viz._colors import get_batch_colors

        with pytest.raises(ValueError, match="non-empty"):
            get_batch_colors([])


class TestFormatTraceName:
    """Tests for _utils.format_trace_name."""

    def test_short_name_unchanged(self) -> None:
        from sporedb.viz._utils import format_trace_name

        assert format_trace_name("CHO-42", "OD600") == "CHO-42 OD600"

    def test_long_name_truncated(self) -> None:
        from sporedb.viz._utils import format_trace_name

        result = format_trace_name("a" * 30, "pH", max_len=10)
        assert result == "aaaaaaaa.. pH"
        assert len(result.split(" ")[0]) == 10


class TestPhaseMarkers:
    """Tests for _phase_markers module."""

    def test_phase_colors_has_five_keys(self) -> None:
        from sporedb.viz._phase_markers import PHASE_COLORS

        assert len(PHASE_COLORS) == 5
        assert "lag" in PHASE_COLORS
        assert "exponential" in PHASE_COLORS
        assert "stationary" in PHASE_COLORS
        assert "decline" in PHASE_COLORS
        assert "unknown" in PHASE_COLORS

    def test_phase_colors_are_rgba(self) -> None:
        from sporedb.viz._phase_markers import PHASE_COLORS

        for color in PHASE_COLORS.values():
            assert color.startswith("rgba(")

    def test_add_phase_markers_calls_add_vrect(self) -> None:
        from unittest.mock import MagicMock

        from sporedb.analytics.models import PhaseAnnotation, PhaseType
        from sporedb.viz._phase_markers import add_phase_markers

        fig = MagicMock()
        base = datetime(2026, 1, 1, tzinfo=UTC)
        anns = [
            PhaseAnnotation(
                batch_id=UUID("00000000-0000-0000-0000-000000000001"),
                phase_type=PhaseType.LAG,
                start_ts=base,
                end_ts=base + timedelta(hours=1),
                signal_variable="OD600",
            ),
        ]
        add_phase_markers(fig, anns)
        fig.add_vrect.assert_called_once()
        call_kwargs = fig.add_vrect.call_args[1]
        assert call_kwargs["x0"] == base
        assert call_kwargs["layer"] == "below"

    def test_add_phase_markers_empty_raises(self) -> None:
        from unittest.mock import MagicMock

        from sporedb.viz._phase_markers import add_phase_markers

        with pytest.raises(ValueError, match="non-empty"):
            add_phase_markers(MagicMock(), [])
