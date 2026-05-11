"""SporeDB facade client -- single entry point for all SDK operations."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import UUID

import pandas as pd

from sporedb.models.batch import (
    Batch,
    BatchLifecycle,
    BatchMetadata,
    CanonicalTimestamps,
)
from sporedb.storage.batch_store import BatchStore
from sporedb.storage.engine import StorageEngine
from sporedb.storage.ts_store import TimeSeriesStore

if TYPE_CHECKING:
    from sporedb.analytics.models import (
        BatchMetrics,
        BatchScore,
        GoldenBatchProfile,
        PhaseAnnotation,
    )
    from sporedb.analytics.pat import SoftSensor
    from sporedb.ingestion.result import ImportResult


class SporeDB:
    """Primary entry point for SporeDB operations.

    Composes storage, ingestion, analytics, export, and query layers
    behind a single high-level API so scientists never interact with
    internal store objects directly.

    Args:
        data_root: Path to local data directory. Defaults to ``"./sporedb_data"``.
        endpoint: Cloud API endpoint URL. If provided, operates in cloud mode.
        api_key: API key for cloud authentication. Required when *endpoint* is set.

    Raises:
        ValueError: If *endpoint* is provided without *api_key*.

    Example:
        >>> with SporeDB("./my_data") as db:
        ...     batch = db.create_batch("CHO-Run-001", strain="CHO-K1")
        ...     result = db.import_csv("telemetry.csv", "CHO-Run-001")
        ...     df = db.get_telemetry(result.batch_id)
    """

    def __init__(
        self,
        data_root: str | Path = "./sporedb_data",
        *,
        endpoint: str | None = None,
        api_key: str | None = None,
    ) -> None:
        self._engine: StorageEngine | None
        self._batches: BatchStore | None
        self._timeseries: TimeSeriesStore | None
        if endpoint is not None:
            # Cloud mode -- lazy import to avoid httpx dependency when local-only
            from sporedb.cloud_client import CloudClient

            if api_key is None:
                raise ValueError(
                    "api_key is required when using cloud mode (endpoint=...)"
                )
            self._cloud: CloudClient | None = CloudClient(endpoint, api_key)
            self._engine = None
            self._batches = None
            self._timeseries = None
        else:
            self._cloud = None
            self._engine = StorageEngine(data_root)
            self._batches = BatchStore(self._engine)
            self._timeseries = TimeSeriesStore(self._engine)

    @property
    def is_cloud(self) -> bool:
        """Return ``True`` if this instance delegates to the cloud tier."""
        return self._cloud is not None

    def close(self) -> None:
        """Close the underlying storage engine or cloud client."""
        if self._cloud is not None:
            self._cloud.close()
        elif self._engine is not None:
            self._engine.close()

    def __enter__(self) -> SporeDB:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    # ------------------------------------------------------------------ #
    # Batch CRUD
    # ------------------------------------------------------------------ #

    def create_batch(
        self,
        name: str,
        *,
        strain: str | None = None,
        media: str | None = None,
        scale_liters: float | None = None,
        operator: str | None = None,
        tags: list[str] | None = None,
        inoculation: datetime | None = None,
    ) -> Batch:
        """Create a new batch.

        Constructs a ``Batch`` model internally from keyword arguments and
        persists it via the batch store.

        Args:
            name: Human-readable batch identifier (e.g. ``"CHO-Run-001"``).
            strain: Organism strain name.
            media: Growth media description.
            scale_liters: Bioreactor working volume in liters.
            operator: Name of the operator running the batch.
            tags: Optional list of free-form tags for categorization.
            inoculation: Inoculation timestamp (timezone-aware).

        Returns:
            The newly created :class:`Batch` with a generated ``batch_id``.

        Example:
            >>> batch = db.create_batch(
            ...     "CHO-Run-001", strain="CHO-K1", scale_liters=5.0
            ... )
        """
        if self._cloud is not None:
            return self._cloud.create_batch(
                name,
                strain=strain,
                media=media,
                scale_liters=scale_liters,
                operator=operator,
                tags=tags,
                inoculation=inoculation,
            )
        batch = Batch(
            name=name,
            lifecycle=BatchLifecycle.INOCULATED,
            timestamps=CanonicalTimestamps(inoculation=inoculation),
            metadata=BatchMetadata(
                strain=strain,
                media=media,
                scale_liters=scale_liters,
                operator=operator,
            ),
            tags=tags or [],
        )
        assert self._batches is not None
        return self._batches.create_batch(batch)

    def get_batch(self, batch_id: UUID) -> Batch | None:
        """Retrieve a batch by its ID, or ``None`` if not found.

        Args:
            batch_id: UUID of the batch to retrieve.

        Returns:
            The :class:`Batch` if found, otherwise ``None``.
        """
        if self._cloud is not None:
            return self._cloud.get_batch(batch_id)
        assert self._batches is not None
        return self._batches.get_batch(batch_id)

    def list_batches(self) -> list[Batch]:
        """Return all batches.

        Returns:
            A list of all :class:`Batch` records in the store.
        """
        if self._cloud is not None:
            return self._cloud.list_batches()
        assert self._batches is not None
        return self._batches.list_batches()

    def delete_batch(self, batch_id: UUID) -> bool:
        """Delete a batch.

        Args:
            batch_id: UUID of the batch to delete.

        Returns:
            ``True`` if the batch existed and was deleted, ``False`` otherwise.
        """
        if self._cloud is not None:
            return self._cloud.delete_batch(batch_id)
        assert self._batches is not None
        return self._batches.delete_batch(batch_id)

    # ------------------------------------------------------------------ #
    # Data ingestion
    # ------------------------------------------------------------------ #

    def import_csv(
        self,
        file_path: str | Path,
        batch_name: str,
        inoculation_ts: datetime | None = None,
    ) -> ImportResult:
        """Import a CSV file into SporeDB.

        Creates a batch automatically and returns an :class:`ImportResult`.

        Args:
            file_path: Path to the CSV file on disk.
            batch_name: Human-readable name for the new batch.
            inoculation_ts: Optional inoculation timestamp (timezone-aware).

        Returns:
            An :class:`ImportResult` with row count, column mappings, and timing.

        Raises:
            NotImplementedError: If called in cloud mode.

        Example:
            >>> result = db.import_csv("telemetry.csv", "CHO-Run-001")
            >>> print(f"Imported {result.rows_imported} rows")
        """
        if self._cloud is not None:
            raise NotImplementedError("CSV import not yet supported in cloud mode")
        from sporedb.ingestion.csv_reader import import_csv as _import_csv

        assert self._engine is not None
        return _import_csv(
            Path(file_path),
            batch_name,
            self._engine,
            inoculation_ts=inoculation_ts,
        )

    def import_excel(
        self,
        file_path: str | Path,
        batch_name: str,
        inoculation_ts: datetime | None = None,
    ) -> ImportResult | list[ImportResult]:
        """Import an Excel file into SporeDB.

        Creates a batch automatically and returns an :class:`ImportResult`
        (or a list when multiple sheets are present).

        Args:
            file_path: Path to the Excel file on disk.
            batch_name: Human-readable name for the new batch.
            inoculation_ts: Optional inoculation timestamp (timezone-aware).

        Returns:
            An :class:`ImportResult` for single-sheet files, or a list of
            :class:`ImportResult` when the workbook contains multiple sheets.

        Raises:
            NotImplementedError: If called in cloud mode.
        """
        if self._cloud is not None:
            raise NotImplementedError("Excel import not yet supported in cloud mode")
        from sporedb.ingestion.excel_reader import import_excel as _import_excel

        assert self._engine is not None
        return _import_excel(
            Path(file_path),
            batch_name,
            self._engine,
            inoculation_ts=inoculation_ts,
        )

    # ------------------------------------------------------------------ #
    # Data retrieval
    # ------------------------------------------------------------------ #

    def get_telemetry(self, batch_id: UUID) -> pd.DataFrame:
        """Return telemetry data for a batch as a pandas DataFrame.

        Args:
            batch_id: UUID of the batch to retrieve telemetry for.

        Returns:
            A :class:`pandas.DataFrame` with columns ``ts``, ``variable``,
            ``value``, and ``unit``.
        """
        if self._cloud is not None:
            return self._cloud.get_telemetry(batch_id)
        assert self._timeseries is not None
        return self._timeseries.get_telemetry(batch_id)

    def get_assay(self, batch_id: UUID) -> pd.DataFrame:
        """Return assay measurements for a batch as a pandas DataFrame.

        Args:
            batch_id: UUID of the batch to retrieve assay data for.

        Returns:
            A :class:`pandas.DataFrame` with assay measurement rows.
        """
        if self._cloud is not None:
            return self._cloud.get_assay(batch_id)
        assert self._timeseries is not None
        return self._timeseries.get_assay(batch_id)

    def get_unified_view(self, batch_id: UUID) -> pd.DataFrame:
        """Return combined telemetry + assay data for a batch.

        Args:
            batch_id: UUID of the batch.

        Returns:
            A :class:`pandas.DataFrame` with telemetry and assay data merged
            via an ASOF JOIN on timestamp.

        Raises:
            NotImplementedError: If called in cloud mode.
        """
        if self._cloud is not None:
            raise NotImplementedError("Unified view not yet supported in cloud mode")
        assert self._timeseries is not None
        return self._timeseries.get_unified_view(batch_id)

    # ------------------------------------------------------------------ #
    # Export
    # ------------------------------------------------------------------ #

    def export(
        self,
        batch_id: UUID,
        format: str = "csv",
        output_path: str | Path | None = None,
    ) -> bytes | None:
        """Export batch data in the specified format.

        Args:
            batch_id: Batch to export.
            format: ``"csv"``, ``"parquet"``, or ``"arrow"``.
            output_path: If given, write to file and return ``None``.

        Returns:
            Serialized bytes, or ``None`` when *output_path* is provided.
        """
        if self._cloud is not None:
            raise NotImplementedError("Export not yet supported in cloud mode")
        from sporedb.export import export_batch

        assert self._engine is not None
        return export_batch(
            batch_id,
            self._engine,
            format=format,
            output_path=Path(output_path) if output_path else None,
        )

    # ------------------------------------------------------------------ #
    # Analytics
    # ------------------------------------------------------------------ #

    def detect_phases(
        self,
        batch_id: UUID,
        signal: str = "OD600",
        min_size: int = 10,
    ) -> list[PhaseAnnotation]:
        """Run PELT changepoint detection on a batch's telemetry.

        Uses the ``ruptures`` library with an RBF kernel cost function to
        identify changepoints in the specified signal and classify the
        resulting segments as growth phases.

        Args:
            batch_id: UUID of the batch to analyze.
            signal: Telemetry variable to analyze. Defaults to ``"OD600"``.
            min_size: Minimum segment length for PELT. Defaults to ``10``.

        Returns:
            A list of :class:`PhaseAnnotation` objects describing the
            detected growth phases (lag, exponential, stationary, decline).

        Example:
            >>> phases = db.detect_phases(batch_id)
            >>> for p in phases:
            ...     print(f"{p.phase_type.value}: {p.start_ts} - {p.end_ts}")
        """
        if self._cloud is not None:
            return self._cloud.detect_phases(batch_id, signal=signal, min_size=min_size)
        from sporedb.analytics.detector import PhaseDetector
        from sporedb.analytics.models import DetectionConfig
        from sporedb.analytics.phase_store import PhaseStore

        df = self.get_telemetry(batch_id)
        detector = PhaseDetector(
            DetectionConfig(signal_variable=signal, min_size=min_size)
        )
        annotations = detector.detect(df, batch_id)
        # Persist detected phases via PhaseStore
        assert self._engine is not None
        PhaseStore(self._engine).save_phases(batch_id, annotations)
        return annotations

    def align(
        self,
        batch_ids: list[UUID],
        signal: str = "OD600",
    ) -> pd.DataFrame:
        """Align multiple batch runs by phase boundary for comparison.

        Detects phases for each batch, then aligns them by elapsed time
        from the exponential phase boundary.

        Args:
            batch_ids: List of batch UUIDs to align.
            signal: Telemetry variable used for phase detection and alignment.
                Defaults to ``"OD600"``.

        Returns:
            A :class:`pandas.DataFrame` with aligned time-series data indexed
            by elapsed hours from the exponential phase boundary.
        """
        if self._cloud is not None:
            return self._cloud.align(batch_ids, signal=signal)
        from sporedb.analytics.alignment import align as _align
        from sporedb.analytics.models import PhaseType

        batches: dict[str, pd.DataFrame] = {}
        phase_annotations: dict[str, list[Any]] = {}
        for bid in batch_ids:
            df = self.get_telemetry(bid)
            batches[str(bid)] = df
            phases = self.detect_phases(bid, signal=signal)
            phase_annotations[str(bid)] = phases

        return _align(
            batches,
            phase_annotations,
            anchor_phase=PhaseType.EXPONENTIAL,
            variables=[signal],
        )

    def compute_metrics(
        self,
        batch_id: UUID,
    ) -> list[BatchMetrics]:
        """Compute derived bioprocess metrics for a batch.

        Runs phase detection first, then calculates kinetic parameters
        (growth rate, productivity, yields) for each detected phase.

        Args:
            batch_id: UUID of the batch to analyze.

        Returns:
            A list of :class:`BatchMetrics`, one per detected phase.
        """
        from sporedb.analytics.metrics import compute_batch_metrics

        df = self.get_telemetry(batch_id)
        phases = self.detect_phases(batch_id)
        return compute_batch_metrics(df, phases, batch_id)

    def detect_phases_online(
        self,
        batch_id: UUID,
        signal: str = "OD600",
        *,
        hazard_rate: float = 1 / 250,
        threshold: float = 0.5,
    ) -> list[PhaseAnnotation]:
        """Run Bayesian Online Changepoint Detection on a batch.

        Uses BOCPD (Adams & MacKay 2007) for real-time / streaming-style
        phase detection. Results are persisted via PhaseStore.

        Args:
            batch_id: UUID of the batch to analyze.
            signal: Telemetry variable to analyze. Defaults to ``"OD600"``.
            hazard_rate: Prior probability of a changepoint at each step.
                Defaults to ``1/250``.
            threshold: Posterior probability threshold for declaring a
                changepoint. Defaults to ``0.5``.

        Returns:
            A list of :class:`PhaseAnnotation` objects.

        Raises:
            NotImplementedError: If called in cloud mode.
        """
        if self._cloud is not None:
            raise NotImplementedError(
                "Online phase detection not yet supported in cloud mode"
            )
        from sporedb.analytics.bocpd import BOCPDDetector
        from sporedb.analytics.models import BOCPDConfig
        from sporedb.analytics.phase_store import PhaseStore

        config = BOCPDConfig(
            signal_variable=signal,
            hazard_rate=hazard_rate,
            threshold=threshold,
        )
        detector = BOCPDDetector(config)
        df = self.get_telemetry(batch_id)
        annotations = detector.detect_batch(df, batch_id)
        assert self._engine is not None
        PhaseStore(self._engine).save_phases(batch_id, annotations)
        return annotations

    def create_golden_profile(
        self,
        batch_ids: list[UUID],
        variables: list[str],
        signal: str = "OD600",
        metadata: dict[str, Any] | None = None,
    ) -> GoldenBatchProfile:
        """Create a golden batch reference profile from aligned runs.

        Aligns the given batches and computes mean/std trajectories
        across the specified variables.

        Args:
            batch_ids: UUIDs of the reference batches to include.
            variables: Telemetry variable names to include in the profile.
            signal: Variable used for phase-based alignment. Defaults to ``"OD600"``.
            metadata: Optional metadata dict stored with the profile.

        Returns:
            A :class:`GoldenBatchProfile` with mean and standard deviation
            trajectories.

        Raises:
            NotImplementedError: If called in cloud mode.
        """
        if self._cloud is not None:
            raise NotImplementedError(
                "Golden batch profiling not yet supported in cloud mode"
            )
        from sporedb.analytics.golden_batch import (
            create_golden_profile as _create_golden_profile,
        )

        aligned_df = self.align(batch_ids, signal=signal)
        batch_names = [str(bid) for bid in batch_ids]
        return _create_golden_profile(
            aligned_df, batch_names, variables, metadata=metadata
        )

    def score_batch(
        self,
        profile: GoldenBatchProfile,
        batch_id: UUID,
    ) -> BatchScore:
        """Score a batch against a golden batch profile.

        Args:
            profile: The :class:`GoldenBatchProfile` to compare against.
            batch_id: UUID of the batch to score.

        Returns:
            A :class:`BatchScore` with a 0--100 similarity score
            derived from Dynamic Time Warping distance.

        Raises:
            NotImplementedError: If called in cloud mode.
        """
        if self._cloud is not None:
            raise NotImplementedError("Batch scoring not yet supported in cloud mode")
        from sporedb.analytics.golden_batch import (
            extract_batch_trajectory,
            score_against_profile,
        )

        df = self.get_telemetry(batch_id)
        trajectory = extract_batch_trajectory(df, profile.variables)
        return score_against_profile(profile, trajectory, batch_id)

    def predict_pat(
        self,
        batch_id: UUID,
        sensor: SoftSensor,
    ) -> pd.DataFrame:
        """Run a PAT soft-sensor and return predictions merged with telemetry.

        Retrieves telemetry, extracts the sensor's input variables,
        calls ``sensor.predict()``, and returns the original telemetry
        DataFrame with predicted rows appended.

        Args:
            batch_id: UUID of the batch to predict on.
            sensor: A :class:`SoftSensor` model instance.

        Returns:
            A :class:`pandas.DataFrame` combining original telemetry with
            predicted values.

        Raises:
            NotImplementedError: If called in cloud mode.
        """
        if self._cloud is not None:
            raise NotImplementedError("PAT prediction not yet supported in cloud mode")
        from sporedb.analytics.pat import apply_soft_sensor

        df = self.get_telemetry(batch_id)
        predictions = apply_soft_sensor(sensor, df)
        return pd.concat([df, predictions], ignore_index=True)

    # ------------------------------------------------------------------ #
    # Query (DSL)
    # ------------------------------------------------------------------ #

    def query(self, dsl_query: str) -> pd.DataFrame:
        """Execute a bioprocess DSL query and return results as a DataFrame.

        The query string is parsed via the Lark-based grammar, compiled to
        parameterized DuckDB SQL, and executed against the storage engine.

        Args:
            dsl_query: A SporeDB DSL query string (PromQL-style syntax).

        Returns:
            A :class:`pandas.DataFrame` with the query results.

        Example:
            >>> df = db.query("SELECT OD600 FROM batch WHERE name = 'CHO-Run-001'")
        """
        if self._cloud is not None:
            return self._cloud.query(dsl_query)
        from sporedb.query import DuckDBCompiler, parse_query

        ast = parse_query(dsl_query)
        compiler = DuckDBCompiler()
        sql, params = compiler.compile(ast)
        assert self._engine is not None
        return self._engine.con.execute(sql, params).fetchdf()
