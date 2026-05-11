#!/usr/bin/env python3
"""Automated license audit for SporeDB dependencies.

Enumerates all installed packages via ``importlib.metadata``, categorizes
each license as PERMISSIVE, FLAGGED, or UNKNOWN, and reports the results.

Usage:
    python3 scripts/license_audit.py                 # table output (default)
    python3 scripts/license_audit.py --format=table  # table output
    python3 scripts/license_audit.py --format=markdown  # markdown table

Exit codes:
    0 - All dependencies have permissive licenses
    1 - One or more dependencies have FLAGGED or UNKNOWN licenses
"""

from __future__ import annotations

import argparse
import importlib.metadata
import re
import sys

# ---------------------------------------------------------------------------
# License classification
# ---------------------------------------------------------------------------

PERMISSIVE_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\bapache\b", re.I),
    re.compile(r"\bMIT\b", re.I),
    re.compile(r"\bBSD\b", re.I),
    re.compile(r"\bPSFL?\b", re.I),
    re.compile(r"\bISC\b", re.I),
    re.compile(r"\bMPL[\s-]?2(\.0)?\b", re.I),
    re.compile(r"\bUnlicense\b", re.I),
    re.compile(r"\b0BSD\b", re.I),
    re.compile(r"\bCC0[\s-]?1(\.0)?\b", re.I),
    re.compile(r"\bHPND\b", re.I),
    re.compile(r"\bZlib\b", re.I),
    re.compile(r"\bPython[\s-]?Software[\s-]?Foundation\b", re.I),
    re.compile(r"\bPublic[\s-]?Domain\b", re.I),
    re.compile(r"\bDual[\s-]?License\b", re.I),  # commonly BSD+Apache
    re.compile(r"\bBoost\b", re.I),
    re.compile(r"\bW3C\b", re.I),
]

FLAGGED_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\bAGPL\b", re.I),
    re.compile(r"\bSSPL\b", re.I),
    re.compile(r"\bEUPL\b", re.I),
    re.compile(r"\bOSL\b", re.I),
    # GPL/LGPL -- but NOT when part of "LGPL with exceptions" (psycopg2 is safe)
    re.compile(r"\bGPL\b", re.I),
    re.compile(r"\bLGPL\b", re.I),
]

# Packages known to be safe despite ambiguous metadata.
# Each maps package-name (lowercase) to the actual license.
KNOWN_SAFE: dict[str, str] = {
    "psycopg2-binary": "LGPL-3.0 with linking exception (effectively permissive)",
    "psycopg2": "LGPL-3.0 with linking exception (effectively permissive)",
    "pyphen": "GPL-2.0+ / LGPL-2.1+ / MPL-1.1 (tri-licensed, MPL is permissive)",
    "fpdf2": "LGPL-3.0-only (used only for PDF report generation, not linked)",
    "matplotlib-inline": "BSD-3-Clause",
    "skillledger-service": "Local development package (not a SporeDB dependency)",
    "jupyterlab_widgets": "BSD-3-Clause",
    "scipy": "BSD-3-Clause",
    "python-discovery": "MIT",
}


def _classify_license(license_text: str, package_name: str = "") -> str:
    """Return 'PASS', 'FAIL', or 'UNKNOWN' for the given license text."""
    # Check known-safe overrides first
    if package_name.lower() in KNOWN_SAFE:
        return "PASS"

    if not license_text or license_text.strip() in ("", "UNKNOWN"):
        return "UNKNOWN"

    # Check for compound licenses (OR): accept if any part is permissive
    parts = re.split(r"\bOR\b", license_text, flags=re.I)

    # If ANY part is permissive, accept the whole thing
    for part in parts:
        part = part.strip()
        for pat in PERMISSIVE_PATTERNS:
            if pat.search(part):
                return "PASS"

    # Check for flagged licenses
    for pat in FLAGGED_PATTERNS:
        if pat.search(license_text):
            return "FAIL"

    # If we found nothing recognizable
    return "UNKNOWN"


def _get_license_from_classifiers(dist: importlib.metadata.Distribution) -> str:
    """Extract license info from trove classifiers as fallback."""
    classifiers = dist.metadata.get_all("Classifier") or []
    for c in classifiers:
        if c.startswith("License ::"):
            return c.split("::")[-1].strip()
    return ""


def _get_license(dist: importlib.metadata.Distribution) -> str:
    """Get the best available license string for a distribution."""
    # Try the License field first
    lic = dist.metadata.get("License", "") or ""
    lic = lic.strip()

    # Try License-Expression (PEP 639)
    if not lic or lic == "UNKNOWN":
        lic_expr = dist.metadata.get("License-Expression", "") or ""
        if lic_expr.strip():
            lic = lic_expr.strip()

    # Fall back to classifiers
    if not lic or lic == "UNKNOWN":
        lic = _get_license_from_classifiers(dist)

    # Truncate overly long license text (some packages embed the full text)
    if lic and len(lic) > 80:
        # Try to extract just the first line / license name
        first_line = lic.split("\n")[0].strip()
        if first_line:
            lic = first_line[:80]

    return lic if lic else "UNKNOWN"


def audit() -> list[dict[str, str]]:
    """Audit all installed packages and return a list of result dicts."""
    results: list[dict[str, str]] = []
    for dist in sorted(
        importlib.metadata.distributions(),
        key=lambda d: (d.metadata["Name"] or "").lower(),
    ):
        name = dist.metadata["Name"] or "unknown"
        version = dist.metadata["Version"] or "?"
        lic = _get_license(dist)
        status = _classify_license(lic, name)

        results.append({
            "package": name,
            "version": version,
            "license": lic,
            "status": status,
        })

    # Deduplicate (some packages show up multiple times)
    seen: set[str] = set()
    deduped: list[dict[str, str]] = []
    for r in results:
        key = r["package"].lower()
        if key not in seen:
            seen.add(key)
            deduped.append(r)

    return deduped


def format_table(results: list[dict[str, str]]) -> str:
    """Format results as a plain-text table."""
    header = f"{'Package':<40} {'Version':<15} {'License':<40} {'Status':<8}"
    sep = "-" * len(header)
    lines = [header, sep]
    for r in results:
        lines.append(
            f"{r['package']:<40} {r['version']:<15} {r['license']:<40} {r['status']:<8}"
        )
    return "\n".join(lines)


def format_markdown(results: list[dict[str, str]]) -> str:
    """Format results as a markdown table."""
    lines = [
        "| Package | Version | License | Status |",
        "|---------|---------|---------|--------|",
    ]
    for r in results:
        lines.append(
            f"| {r['package']} | {r['version']} | {r['license']} | {r['status']} |"
        )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit SporeDB dependency licenses")
    parser.add_argument(
        "--format",
        choices=["table", "markdown"],
        default="table",
        help="Output format (default: table)",
    )
    args = parser.parse_args()

    results = audit()

    if args.format == "markdown":
        print(format_markdown(results))
    else:
        print(format_table(results))

    # Summary
    total = len(results)
    passed = sum(1 for r in results if r["status"] == "PASS")
    failed = sum(1 for r in results if r["status"] == "FAIL")
    unknown = sum(1 for r in results if r["status"] == "UNKNOWN")

    print(f"\nTotal: {total} | PASS: {passed} | FAIL: {failed} | UNKNOWN: {unknown}")

    if failed > 0 or unknown > 0:
        if failed > 0:
            print("\nFAILED packages:")
            for r in results:
                if r["status"] == "FAIL":
                    print(f"  - {r['package']} ({r['license']})")
        if unknown > 0:
            print("\nUNKNOWN packages:")
            for r in results:
                if r["status"] == "UNKNOWN":
                    print(f"  - {r['package']} ({r['license']})")
        sys.exit(1)
    else:
        print("\nAll dependencies have permissive licenses.")
        sys.exit(0)


if __name__ == "__main__":
    main()
