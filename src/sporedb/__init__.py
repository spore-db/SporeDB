from __future__ import annotations

from typing import TYPE_CHECKING

from sporedb.analytics.models import (
    BatchMetrics,
    DetectionConfig,
    GoldenBatchProfile,
    PhaseAnnotation,
    PhaseType,
)
from sporedb.client import SporeDB
from sporedb.ingestion.result import ImportResult
from sporedb.models.assay import AssayMeasurement, UncertainValue
from sporedb.models.batch import (
    Batch,
    BatchLifecycle,
    BatchMetadata,
    CanonicalTimestamps,
)
from sporedb.models.lineage import UnitOperation
from sporedb.models.timeseries import TelemetryRecord
from sporedb.storage import BatchStore, LineageStore, StorageEngine, TimeSeriesStore

if TYPE_CHECKING:
    from sporedb.cloud_client import CloudClient

__version__ = "0.1.0"
__all__ = [
    "AssayMeasurement",
    "Batch",
    "BatchLifecycle",
    "BatchMetadata",
    "BatchMetrics",
    "BatchStore",
    "CanonicalTimestamps",
    "CloudClient",
    "DetectionConfig",
    "GoldenBatchProfile",
    "ImportResult",
    "LineageStore",
    "PhaseAnnotation",
    "PhaseType",
    "SporeDB",
    "StorageEngine",
    "TelemetryRecord",
    "TimeSeriesStore",
    "UncertainValue",
    "UnitOperation",
]


def __getattr__(name: str) -> object:
    """Lazy import for CloudClient to avoid requiring httpx at import time."""
    if name == "CloudClient":
        from sporedb.cloud_client import CloudClient

        return CloudClient
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
