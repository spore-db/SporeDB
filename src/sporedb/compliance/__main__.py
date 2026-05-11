"""CLI entry point for compliance validation.

Usage:
    python -m sporedb.compliance.validator --check

Validates the audit trail against FDA 21 CFR Part 11 and EU Annex 11
checklists, printing results and exiting with code 0 on success or 1
on failure.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sporedb.compliance.validator import CheckStatus, ComplianceValidator
from sporedb.storage.engine import StorageEngine


def main() -> None:
    """Run compliance validation from CLI."""
    parser = argparse.ArgumentParser(
        prog="sporedb.compliance.validator",
        description="Validate SporeDB audit trail compliance",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Run all compliance checks and report results",
    )
    parser.add_argument(
        "--data-root",
        type=str,
        default="data",
        help="Path to SporeDB data root directory (default: data)",
    )
    parser.add_argument(
        "--regulation",
        type=str,
        default=None,
        choices=["21_CFR_Part_11", "EU_Annex_11"],
        help="Specific regulation to validate (default: both)",
    )
    parser.add_argument(
        "--public-key",
        type=str,
        default=None,
        help="Path to Ed25519 public key PEM file for signature verification",
    )

    args = parser.parse_args()

    if not args.check:
        parser.print_help()
        sys.exit(0)

    # Initialize storage engine
    data_root = Path(args.data_root)
    engine = StorageEngine(data_root=data_root)

    # Load public key if provided
    public_key = None
    if args.public_key:
        from cryptography.hazmat.primitives.serialization import load_pem_public_key

        with open(args.public_key, "rb") as f:
            public_key = load_pem_public_key(f.read())

    # Run validation
    validator = ComplianceValidator(engine=engine, public_key=public_key)  # type: ignore[arg-type]
    report = validator.validate(regulation=args.regulation)

    # Print results
    print(f"\n{'=' * 60}")
    print("SporeDB Compliance Validation Report")
    print(f"{'=' * 60}")
    print(f"Regulation: {report.regulation}")
    print(f"Entries checked: {report.total_entries_checked}")
    print(f"Generated: {report.generated_at.isoformat()}")
    print(f"{'=' * 60}\n")

    for result in report.results:
        status_icon = {
            CheckStatus.PASS: "PASS",
            CheckStatus.FAIL: "FAIL",
            CheckStatus.NOT_APPLICABLE: "N/A ",
            CheckStatus.ERROR: "ERR ",
        }.get(result.status, "????")
        print(f"  [{status_icon}] {result.item_id}: {result.evidence}")
        if result.details:
            print(f"         Detail: {result.details}")

    print(f"\n{'=' * 60}")
    print(f"Overall: {report.overall_status.value.upper()}")
    print(f"Summary: {report.summary}")
    print(f"{'=' * 60}\n")

    # Exit code: 0 for pass, 1 for fail
    sys.exit(0 if report.overall_status == CheckStatus.PASS else 1)


if __name__ == "__main__":
    main()
