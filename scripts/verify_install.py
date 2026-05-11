#!/usr/bin/env python3
"""Verify a SporeDB installation is complete and functional.

Checks core imports, API surface, CLI entry point, and optional extras.
Uses only stdlib -- no third-party dependencies required by this script itself.

Usage:
    python scripts/verify_install.py                     # core checks only
    python scripts/verify_install.py --check-extras cloud viz  # also check extras
"""

from __future__ import annotations

import argparse
import importlib
import subprocess
import sys


class Result:
    """Single check result."""

    def __init__(self, name: str, passed: bool, detail: str = "") -> None:
        self.name = name
        self.passed = passed
        self.detail = detail


def check_import(module: str, attr: str | None = None) -> Result:
    """Try importing *module* and optionally accessing *attr*."""
    label = f"{module}.{attr}" if attr else module
    try:
        mod = importlib.import_module(module)
        if attr:
            getattr(mod, attr)
        return Result(label, True)
    except Exception as exc:
        return Result(label, False, str(exc))


def check_version() -> Result:
    """Verify sporedb.__version__ is set."""
    try:
        import sporedb

        ver = sporedb.__version__
        if ver:
            return Result("sporedb.__version__", True, ver)
        return Result("sporedb.__version__", False, "empty version string")
    except Exception as exc:
        return Result("sporedb.__version__", False, str(exc))


def check_cli() -> Result:
    """Run ``sporedb --version`` via subprocess."""
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "sporedb.cli", "--version"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        # Fall back to the console_scripts entry point
        if proc.returncode != 0:
            proc = subprocess.run(
                ["sporedb", "--version"],
                capture_output=True,
                text=True,
                timeout=30,
            )
        output = (proc.stdout + proc.stderr).strip()
        if proc.returncode == 0:
            return Result("CLI: sporedb --version", True, output)
        return Result("CLI: sporedb --version", False, f"exit {proc.returncode}: {output}")
    except FileNotFoundError:
        return Result("CLI: sporedb --version", False, "sporedb command not found")
    except Exception as exc:
        return Result("CLI: sporedb --version", False, str(exc))


# ---------------------------------------------------------------------------
# Extra-group import maps
# ---------------------------------------------------------------------------
EXTRAS: dict[str, list[tuple[str, str | None]]] = {
    "cloud": [
        ("fastapi", None),
        ("sqlalchemy", None),
        ("alembic", None),
        ("uvicorn", None),
    ],
    "viz": [
        ("plotly", None),
    ],
    "connectors": [
        ("influxdb_client", None),
    ],
    "osisoft": [
        ("PIWebAPI", None),
    ],
}


def run_checks(extras: list[str] | None = None) -> list[Result]:
    """Run all verification checks and return results."""
    results: list[Result] = []

    # -- 1. Version ----------------------------------------------------------
    results.append(check_version())

    # -- 2. Core API surface -------------------------------------------------
    core_imports: list[tuple[str, str | None]] = [
        # Batch management
        ("sporedb", "SporeDB"),
        ("sporedb", "Batch"),
        ("sporedb", "BatchStore"),
        ("sporedb", "StorageEngine"),
        # Phase detection
        ("sporedb", "DetectionConfig"),
        ("sporedb", "PhaseAnnotation"),
        # Alignment
        ("sporedb.analytics.alignment", "align"),
        # Compliance
        ("sporedb.compliance.audit", "AuditTrailWriter"),
        # Merkle proofs
        ("sporedb.compliance.merkle", "MerkleCheckpointer"),
        # Query DSL
        ("sporedb.query", "parse_query"),
        # Golden batch (uses fastdtw or equivalent DTW)
        ("sporedb.analytics.golden_batch", "score_against_profile"),
    ]
    for module, attr in core_imports:
        results.append(check_import(module, attr))

    # -- 3. CLI entry point --------------------------------------------------
    results.append(check_cli())

    # -- 4. Optional extras --------------------------------------------------
    if extras:
        for extra in extras:
            group = EXTRAS.get(extra, [])
            if not group:
                results.append(Result(f"extras:{extra}", False, "unknown extra group"))
                continue
            for module, attr in group:
                results.append(check_import(module, attr))

    return results


def print_table(results: list[Result]) -> None:
    """Print an ASCII results table (stdlib only)."""
    name_width = max(len(r.name) for r in results)
    header = f"{'Check':<{name_width}}  {'Status':^6}  Detail"
    print()
    print(header)
    print("-" * len(header))
    for r in results:
        status = "PASS" if r.passed else "FAIL"
        marker = " " if r.passed else "!"
        print(f"{r.name:<{name_width}}  [{status}]{marker}  {r.detail}")
    print()
    passed = sum(1 for r in results if r.passed)
    total = len(results)
    print(f"Result: {passed}/{total} checks passed")
    if passed < total:
        failed = [r.name for r in results if not r.passed]
        print(f"Failed: {', '.join(failed)}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify SporeDB installation")
    parser.add_argument(
        "--check-extras",
        nargs="*",
        default=None,
        metavar="EXTRA",
        help="Also verify optional extras (cloud, viz, connectors, osisoft)",
    )
    args = parser.parse_args()

    results = run_checks(extras=args.check_extras)
    print_table(results)

    if all(r.passed for r in results):
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
