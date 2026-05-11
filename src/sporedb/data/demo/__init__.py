"""Bundled demo datasets for SporeDB.

Includes ABPDU (Advanced Biofuels and Bioproducts Process Development Unit)
fermentation data from Lawrence Berkeley National Lab.
"""

from __future__ import annotations

from importlib.resources import files
from pathlib import Path


def get_demo_csv_paths() -> list[Path]:
    """Return paths to all bundled demo CSV files.

    Uses importlib.resources to locate CSV files regardless of
    how SporeDB was installed (wheel, editable, zip).
    """
    demo_pkg = files("sporedb.data.demo")
    result = []
    for item in demo_pkg.iterdir():
        name = getattr(item, "name", str(item))
        if name.endswith(".csv"):
            # as_posix returns a Traversable; for file operations we need Path
            path = item if isinstance(item, Path) else Path(str(item))
            result.append(path)
    return sorted(result, key=lambda p: p.name)


def get_demo_csv_dir() -> Path:
    """Return the directory containing bundled demo CSV files."""
    pkg = files("sporedb.data.demo")
    return Path(str(pkg))
