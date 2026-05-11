"""SporeDB Visualization: interactive Jupyter charts for bioprocess data.

Public API:
- overlay_runs: Multi-run overlay chart with phase boundaries
- phase_inspector: Interactive phase inspection widget
- golden_batch_dashboard: Golden batch profiling and scoring widget

Requires: pip install 'sporedb[viz]'
"""

from __future__ import annotations

_VIZ_IMPORT_ERROR: str | None = None

try:
    from sporedb.viz._golden import golden_batch_dashboard as golden_batch_dashboard
    from sporedb.viz._inspector import phase_inspector as phase_inspector
    from sporedb.viz._overlay import overlay_runs as overlay_runs
except ImportError:
    _VIZ_IMPORT_ERROR = (
        "sporedb[viz] extras required for visualization. "
        "Install with: pip install 'sporedb[viz]'"
    )

    def __getattr__(name: str) -> object:
        if name in ("overlay_runs", "phase_inspector", "golden_batch_dashboard"):
            raise ImportError(_VIZ_IMPORT_ERROR)
        raise AttributeError(f"module 'sporedb.viz' has no attribute {name!r}")


__all__ = ["overlay_runs", "phase_inspector", "golden_batch_dashboard"]
