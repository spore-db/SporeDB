"""SporeDB Analytics: phase detection, cross-run alignment, and derived metrics.

Public API for bioprocess analytics including:
- Phase detection (PELT changepoint detection, BOCPD online detection)
- Cross-run alignment by elapsed time
- Derived bioprocess metrics (mu, Qp, Yx/s, Yp/s)
- Golden batch profiling and DTW-based scoring
- PAT soft-sensor integration
- Phase annotation persistence
"""

from __future__ import annotations

from sporedb.analytics.alignment import align
from sporedb.analytics.bocpd import BOCPDDetector
from sporedb.analytics.detector import PhaseDetector
from sporedb.analytics.golden_batch import (
    create_golden_profile,
    extract_batch_trajectory,
    score_against_profile,
)
from sporedb.analytics.metrics import (
    compute_batch_metrics,
    compute_specific_growth_rate,
    compute_volumetric_productivity,
    compute_yield_coefficient,
)
from sporedb.analytics.models import (
    BatchMetrics,
    BatchScore,
    BOCPDConfig,
    DetectionConfig,
    GoldenBatchProfile,
    PhaseAnnotation,
    PhaseType,
    SoftSensorConfig,
)
from sporedb.analytics.pat import LinearSoftSensor, SoftSensor, apply_soft_sensor
from sporedb.analytics.phase_store import PhaseStore

__all__ = [
    "BatchMetrics",
    "BatchScore",
    "BOCPDConfig",
    "BOCPDDetector",
    "DetectionConfig",
    "GoldenBatchProfile",
    "LinearSoftSensor",
    "PhaseAnnotation",
    "PhaseDetector",
    "PhaseStore",
    "PhaseType",
    "SoftSensor",
    "SoftSensorConfig",
    "align",
    "apply_soft_sensor",
    "compute_batch_metrics",
    "compute_specific_growth_rate",
    "compute_volumetric_productivity",
    "compute_yield_coefficient",
    "create_golden_profile",
    "extract_batch_trajectory",
    "score_against_profile",
]
