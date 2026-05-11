"""Hive-style Parquet file path conventions for SporeDB."""

from __future__ import annotations

from pathlib import Path
from uuid import UUID


class ParquetLayout:
    """Defines the directory and file layout for Parquet storage.

    Uses Hive-style partitioning with batch_id as the partition key
    for telemetry, assay, and lineage data.
    """

    def __init__(self, data_root: Path) -> None:
        self.data_root = data_root

    def batches_catalog(self) -> Path:
        """Path to the batch catalog Parquet file."""
        return self.data_root / "batches.parquet"

    def telemetry_dir(self, batch_id: UUID) -> Path:
        """Directory for telemetry data, Hive-partitioned by batch_id."""
        return self.data_root / "telemetry" / f"batch_id={batch_id}"

    def assay_dir(self, batch_id: UUID) -> Path:
        """Directory for assay data, Hive-partitioned by batch_id."""
        return self.data_root / "assay" / f"batch_id={batch_id}"

    def lineage_dir(self, batch_id: UUID) -> Path:
        """Directory for lineage/operations data, Hive-partitioned by batch_id."""
        return self.data_root / "lineage" / f"batch_id={batch_id}"

    def telemetry_file(self, batch_id: UUID) -> Path:
        """Path to the telemetry Parquet file for a specific batch."""
        return self.telemetry_dir(batch_id) / "data.parquet"

    def assay_file(self, batch_id: UUID) -> Path:
        """Path to the assay Parquet file for a specific batch."""
        return self.assay_dir(batch_id) / "data.parquet"

    def lineage_file(self, batch_id: UUID) -> Path:
        """Path to the lineage Parquet file for a specific batch."""
        return self.lineage_dir(batch_id) / "operations.parquet"

    def phases_dir(self, batch_id: UUID) -> Path:
        """Directory for phase annotations, Hive-partitioned by batch_id."""
        return self.data_root / "phases" / f"batch_id={batch_id}"

    def phases_file(self, batch_id: UUID) -> Path:
        """Path to the phase annotation Parquet file for a specific batch."""
        return self.phases_dir(batch_id) / "data.parquet"

    def audit_trail_file(self) -> Path:
        """Path to the audit trail Parquet file."""
        return self.data_root / "audit" / "trail.parquet"

    def merkle_state_dir(self) -> Path:
        """Directory for Merkle tree state files."""
        return self.data_root / "audit" / "merkle"

    def user_store_file(self) -> Path:
        """Path to the local user store JSON file."""
        return self.data_root / "users.json"
