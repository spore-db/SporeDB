"""Pydantic models for phase detection and batch analytics."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator
from uuid_utils import uuid7


def _make_uuid7() -> UUID:
    """Generate a UUIDv7 and return as stdlib UUID for Pydantic compatibility."""
    return UUID(str(uuid7()))


class PhaseType(StrEnum):
    """Growth phases in a bioprocess batch.

    Each phase corresponds to a distinct segment of the growth curve:

    - ``LAG``: Initial adaptation period after inoculation.
    - ``EXPONENTIAL``: Rapid cell growth at maximum specific growth rate.
    - ``STATIONARY``: Growth rate equals death rate; nutrient limitation.
    - ``DECLINE``: Cell viability decreasing; nutrient depletion.
    - ``UNKNOWN``: Phase could not be classified.
    """

    LAG = "lag"
    EXPONENTIAL = "exponential"
    STATIONARY = "stationary"
    DECLINE = "decline"
    UNKNOWN = "unknown"


class DetectionConfig(BaseModel):
    """Configuration for changepoint detection algorithms.

    Controls PELT algorithm parameters used by :class:`~sporedb.SporeDB.detect_phases`.

    Attributes:
        signal_variable: Telemetry variable to analyze. Defaults to ``"OD600"``.
        kernel: Cost function kernel for ``ruptures``. Defaults to ``"rbf"``.
        min_size: Minimum segment length. Defaults to ``10``.
        penalty: Penalty value for PELT. Auto-calibrated if ``None``.
        smoothing_window: Rolling average window applied before detection.
            Defaults to ``5``.

    Example:
        >>> from sporedb.analytics.models import DetectionConfig
        >>> config = DetectionConfig(signal_variable="pH", min_size=20)
    """

    signal_variable: str = "OD600"
    kernel: str = "rbf"
    min_size: int = 10
    penalty: float | None = None
    smoothing_window: int = 5


class PhaseAnnotation(BaseModel):
    """A detected or manually annotated phase boundary in a batch run.

    Attributes:
        annotation_id: UUIDv7 identifier (auto-generated).
        batch_id: UUID of the batch this annotation belongs to.
        phase_type: The :class:`PhaseType` of this segment.
        start_ts: Start timestamp of the phase (must be timezone-aware).
        end_ts: End timestamp of the phase (must be timezone-aware).
        signal_variable: The telemetry variable that was analyzed.
        confidence: Detection confidence score (0.0 to 1.0). Defaults to ``0.0``.
        metadata: Additional metadata (e.g. algorithm parameters).

    Raises:
        ValueError: If *start_ts* or *end_ts* is not timezone-aware.
    """

    annotation_id: UUID = Field(default_factory=_make_uuid7)
    batch_id: UUID
    phase_type: PhaseType
    start_ts: datetime
    end_ts: datetime
    signal_variable: str
    confidence: float = 0.0
    metadata: dict[str, object] = Field(default_factory=dict)

    @field_validator("start_ts", "end_ts")
    @classmethod
    def datetime_must_be_aware(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("Datetime must be timezone-aware (use UTC)")
        return v

    @model_validator(mode="after")
    def start_before_end(self) -> PhaseAnnotation:
        if self.start_ts > self.end_ts:
            raise ValueError("start_ts must not be after end_ts")
        return self


class BatchMetrics(BaseModel):
    """Computed kinetic metrics for a specific phase of a batch run.

    Attributes:
        batch_id: UUID of the batch.
        phase_type: The growth phase these metrics apply to.
        mu: Specific growth rate in h^-1.
        qp: Volumetric productivity in g/L/h.
        yx_s: Biomass yield coefficient (g biomass / g substrate).
        yp_s: Product yield coefficient (g product / g substrate).
        r_squared: Regression fit quality (0.0 to 1.0).
        signal_variable: Telemetry variable used for computation.
            Defaults to ``"OD600"``.
    """

    batch_id: UUID
    phase_type: PhaseType
    mu: float | None = None  # specific growth rate (h^-1)
    qp: float | None = None  # volumetric productivity (g/L/h)
    yx_s: float | None = None  # biomass yield (g/g)
    yp_s: float | None = None  # product yield (g/g)
    r_squared: float | None = None  # regression fit quality
    signal_variable: str = "OD600"


class BOCPDConfig(BaseModel):
    """Configuration for Bayesian Online Changepoint Detection."""

    signal_variable: str = "OD600"
    hazard_rate: float = 0.01  # 1/expected_run_length
    mu0: float = 0.0  # prior mean
    kappa0: float = 1.0  # prior precision scale
    alpha0: float = 1.0  # prior shape
    beta0: float = 1.0  # prior rate
    threshold: float = 0.5  # changepoint detection threshold
    max_run_length: int = 500  # truncation limit for run length posterior

    @field_validator("hazard_rate")
    @classmethod
    def hazard_rate_valid(cls, v: float) -> float:
        if v <= 0 or v >= 1:
            raise ValueError("hazard_rate must be in (0, 1)")
        return v


class GoldenBatchProfile(BaseModel):
    """Reference trajectory from top-N aligned batches for golden batch scoring.

    Stores the mean and standard deviation of aligned time-series trajectories
    for a set of reference (golden) batches.

    Attributes:
        profile_id: UUIDv7 identifier (auto-generated).
        variables: List of telemetry variable names in the profile.
        mean_trajectory: Mean trajectory matrix (n_timepoints x n_variables).
        std_trajectory: Standard deviation matrix (same shape as mean).
        elapsed_hours: Elapsed time values for each row (n_timepoints,).
        source_batch_ids: String UUIDs of the batches used to build this profile.
        metadata: Optional metadata (e.g. creation date, notes).
    """

    profile_id: UUID = Field(default_factory=_make_uuid7)
    variables: list[str]
    mean_trajectory: list[list[float]]  # (n_timepoints, n_variables)
    std_trajectory: list[list[float]]  # same shape
    elapsed_hours: list[float]  # (n_timepoints,)
    source_batch_ids: list[str]
    metadata: dict[str, object] = Field(default_factory=dict)


class BatchScore(BaseModel):
    """Score of a batch against a golden batch profile."""

    batch_id: UUID
    profile_id: UUID
    score: float  # 0-100, 100 = perfect match
    variables: list[str]
    dtw_normalized_distance: float = 0.0
    metadata: dict[str, object] = Field(default_factory=dict)

    @field_validator("score")
    @classmethod
    def score_in_range(cls, v: float) -> float:
        if v < 0 or v > 100:
            raise ValueError("Score must be in [0, 100]")
        return v


class SoftSensorConfig(BaseModel):
    """Configuration for a PAT soft-sensor prediction model."""

    input_variables: list[str]
    output_variable: str
    model_type: str = "linear"  # "linear", "pls", "custom"
    prediction_std: float = 0.0  # default uncertainty
    metadata: dict[str, object] = Field(default_factory=dict)
