"""SciNote ELN connector with OAuth2 integration via authlib.

Uses authlib for OAuth2 authentication with automatic token refresh,
and httpx for API calls. The SciNote API uses JSON:API format.

Install dependencies with::

    pip install "sporedb[connectors]"
"""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime
from typing import Any

from sporedb.connectors.base import BaseConnector
from sporedb.connectors.config import ConnectorConfig, SchemaMapping
from sporedb.connectors.result import PullResult
from sporedb.models.assay import AssayMeasurement
from sporedb.models.batch import Batch
from sporedb.storage.batch_store import BatchStore
from sporedb.storage.engine import StorageEngine
from sporedb.storage.ts_store import TimeSeriesStore

logger = logging.getLogger(__name__)


def _import_authlib() -> Any:
    """Lazy import for authlib OAuth2Client."""
    try:
        from authlib.integrations.httpx_client import OAuth2Client

        return OAuth2Client
    except ImportError:
        raise ImportError(
            "authlib is required for SciNote ELN support. "
            'Install it with: pip install "sporedb[connectors]" '
            "or: pip install authlib"
        ) from None


class SciNoteELNConnector(BaseConnector):
    """Connector for SciNote ELN via OAuth2 API.

    Uses authlib ``OAuth2Client`` for authentication with automatic
    token refresh. The SciNote API uses JSON:API format where data
    is in ``response["data"]`` and attributes in ``item["attributes"]``.

    Requires ``team_id`` in ``config.extra`` for all API calls.
    """

    def __init__(self, config: ConnectorConfig, engine: StorageEngine) -> None:
        super().__init__(config, engine)
        self._client: Any = None

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------

    def connect(self) -> None:
        """Establish OAuth2 authenticated connection to SciNote.

        Uses pre-existing access_token and refresh_token from
        ``config.auth``. The authlib OAuth2Client handles automatic
        token refresh.
        """
        OAuth2Client = _import_authlib()

        client_id = self.config.auth.get("client_id", "")
        client_secret = self.config.auth.get("client_secret", "")
        access_token = self.config.auth.get("access_token", "")
        refresh_token = self.config.auth.get("refresh_token", "")

        self._client = OAuth2Client(
            client_id=client_id,
            client_secret=client_secret,
            token_endpoint=f"{self.config.host}/oauth/token",
            token={
                "access_token": access_token,
                "refresh_token": refresh_token,
                "token_type": "Bearer",
            },
        )

        self._connected = True
        logger.info(
            "Connected to SciNote ELN at %s via OAuth2",
            self.config.host,
        )

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------

    def discover(self) -> list[dict[str, Any]]:
        """List available projects and experiments.

        Requires ``team_id`` from ``config.extra["team_id"]``.

        Returns:
            List of dicts with keys: project_id, project_name, experiments.
        """
        team_id = self.config.extra.get("team_id", "")
        if not team_id:
            raise ValueError(
                "team_id is required in config.extra for SciNote discover()"
            )

        results: list[dict[str, Any]] = []

        # List projects
        projects_url = f"{self.config.host}/api/v1/teams/{team_id}/projects"
        proj_resp = self._client.get(projects_url)
        proj_resp.raise_for_status()
        projects_data = proj_resp.json().get("data", [])

        for project in projects_data:
            project_id = project.get("id", "")
            project_attrs = project.get("attributes", {})
            project_name = project_attrs.get("name", "")

            # List experiments for this project
            experiments_url = (
                f"{self.config.host}/api/v1/teams/{team_id}"
                f"/projects/{project_id}/experiments"
            )
            exp_resp = self._client.get(experiments_url)
            exp_resp.raise_for_status()
            experiments_data = exp_resp.json().get("data", [])

            experiments: list[dict[str, Any]] = []
            for exp in experiments_data:
                exp_attrs = exp.get("attributes", {})
                experiments.append(
                    {
                        "id": exp.get("id", ""),
                        "name": exp_attrs.get("name", ""),
                    }
                )

            results.append(
                {
                    "project_id": project_id,
                    "project_name": project_name,
                    "experiments": experiments,
                }
            )

        return results

    # ------------------------------------------------------------------
    # Pull
    # ------------------------------------------------------------------

    def pull(
        self,
        batch_name: str,
        mapping: SchemaMapping,
        **kwargs: Any,
    ) -> PullResult:
        """Pull experiment data from SciNote ELN.

        Follows explicit persistence sequence:
        1. Fetch data from SciNote
        2. Create batch FIRST to obtain batch_id
        3. Map quantitative results to AssayMeasurement
        4. Persist assay data (if any)
        5. Build and return PullResult

        Keyword Args:
            team_id: SciNote team ID (or from config.extra).
            project_id: SciNote project ID (or from config.extra).
            experiment_id: SciNote experiment ID (or from config.extra).

        Returns:
            PullResult with import statistics.
        """
        t0 = time.monotonic()

        team_id = kwargs.get("team_id", self.config.extra.get("team_id", ""))
        project_id = kwargs.get("project_id", self.config.extra.get("project_id", ""))
        experiment_id = kwargs.get(
            "experiment_id", self.config.extra.get("experiment_id", "")
        )

        if not all([team_id, project_id, experiment_id]):
            raise ValueError(
                "team_id, project_id, and experiment_id are required "
                "for SciNote pull(). Provide as kwargs or config.extra."
            )

        warnings: list[str] = []

        # Step 1: Fetch data from SciNote
        # Get tasks (protocols) for the experiment
        tasks_url = (
            f"{self.config.host}/api/v1/teams/{team_id}"
            f"/projects/{project_id}"
            f"/experiments/{experiment_id}/tasks"
        )
        try:
            tasks_resp = self._client.get(tasks_url)
            tasks_resp.raise_for_status()
            tasks_data = tasks_resp.json().get("data", [])
        except Exception as exc:
            warnings.append(f"Failed to fetch tasks: {exc}")
            tasks_data = []

        # Fetch results for each task
        all_results: list[dict[str, Any]] = []
        task_names: list[str] = []
        for task in tasks_data:
            task_id = task.get("id", "")
            task_attrs = task.get("attributes", {})
            task_name = task_attrs.get("name", "")
            task_names.append(task_name)

            results_url = (
                f"{self.config.host}/api/v1/teams/{team_id}"
                f"/projects/{project_id}"
                f"/experiments/{experiment_id}"
                f"/tasks/{task_id}/results"
            )
            try:
                results_resp = self._client.get(results_url)
                results_resp.raise_for_status()
                results_data = results_resp.json().get("data", [])
                for result_item in results_data:
                    result_item["_task_name"] = task_name
                    result_item["_task_id"] = task_id
                    all_results.append(result_item)
            except Exception as exc:
                warnings.append(
                    f"Failed to fetch results for task '{task_name}': {exc}"
                )

        # Step 2: Create batch FIRST to obtain batch_id
        # Get experiment name for metadata
        exp_url = (
            f"{self.config.host}/api/v1/teams/{team_id}"
            f"/projects/{project_id}"
            f"/experiments/{experiment_id}"
        )
        experiment_name = ""
        try:
            exp_resp = self._client.get(exp_url)
            exp_resp.raise_for_status()
            exp_data = exp_resp.json().get("data", {})
            exp_attrs = exp_data.get("attributes", {})
            experiment_name = exp_attrs.get("name", "")
        except Exception:
            pass

        batch = Batch(name=batch_name, tags=["eln-import"])
        batch.metadata.extra["experiment_name"] = experiment_name
        batch.metadata.extra["task_names"] = ",".join(task_names)

        batch_store = BatchStore(self.engine)
        batch_store.create_batch(batch)

        # Step 3: Map quantitative results to AssayMeasurement
        assay_measurements: list[AssayMeasurement] = []
        columns_mapped: dict[str, str] = {}

        # Build field name mapping
        field_map: dict[str, str] = {
            fm.source: fm.target for fm in mapping.variable_mappings
        }
        unit_map: dict[str, str | None] = {
            fm.source: fm.unit for fm in mapping.variable_mappings
        }

        text_observations: dict[str, str] = {}

        for result_item in all_results:
            result_attrs = result_item.get("attributes", {})
            result_name = result_attrs.get("name", "")

            # Get timestamp -- try multiple JSON:API attribute patterns
            ts_raw = result_attrs.get(
                mapping.timestamp_field,
                result_attrs.get("created_at", ""),
            )
            if not ts_raw:
                continue

            # Normalize timestamp to UTC
            try:
                if isinstance(ts_raw, str):
                    from dateutil import parser as dateutil_parser

                    ts = dateutil_parser.parse(ts_raw)
                    if ts.tzinfo is None:
                        ts = ts.replace(tzinfo=UTC)
                elif isinstance(ts_raw, datetime):
                    ts = ts_raw
                    if ts.tzinfo is None:
                        ts = ts.replace(tzinfo=UTC)
                else:
                    continue
            except (ValueError, TypeError):
                warnings.append(f"Could not parse timestamp '{ts_raw}' in result")
                continue

            # Check if this result maps to a known variable
            result_value = result_attrs.get("value", None)

            # Try to find a matching field in the mapping
            mapped_field = field_map.get(result_name)
            if mapped_field is not None:
                # Try to convert to numeric
                try:
                    numeric_value = float(result_value)
                    columns_mapped[result_name] = mapped_field

                    assay_measurements.append(
                        AssayMeasurement(
                            batch_id=batch.batch_id,
                            ts=ts,
                            variable=mapped_field,
                            value=numeric_value,
                            unit=unit_map.get(result_name)
                            or result_attrs.get("unit", ""),
                            method="eln",
                        )
                    )
                except (ValueError, TypeError):
                    # Non-numeric result -- store as text observation
                    text_observations[result_name] = str(result_value)
            else:
                # Unmapped result -- check if numeric anyway
                if result_value is not None:
                    try:
                        float(result_value)
                    except (ValueError, TypeError):
                        # Non-numeric, store as text observation
                        text_observations[result_name] = str(result_value)

        # Store text observations as batch metadata
        if text_observations:
            batch.metadata.extra.update(text_observations)
            try:
                batch_store.update_batch(batch)
            except Exception as exc:
                warnings.append(
                    f"Failed to store text observations in batch metadata: {exc}"
                )

        # Step 4: Persist assay data (if any quantitative measurements)
        rows_imported = 0
        if assay_measurements:
            ts_store = TimeSeriesStore(self.engine)
            rows_imported = ts_store.append_assay(assay_measurements)

        # Step 5: Build and return PullResult
        external_ids: dict[str, str] = {
            "eln_experiment_id": str(experiment_id),
            "eln_project_id": str(project_id),
        }

        elapsed = time.monotonic() - t0
        return PullResult(
            batch_id=batch.batch_id,
            source_system="scinote",
            source_identifier=self.config.host,
            rows_imported=rows_imported,
            columns_mapped=columns_mapped,
            external_ids=external_ids,
            warnings=warnings,
            elapsed_seconds=elapsed,
        )

    # ------------------------------------------------------------------
    # Schema mapping
    # ------------------------------------------------------------------

    def map_schema(self, mapping: SchemaMapping) -> SchemaMapping:
        """Validate that the specified experiment/project exist.

        Uses discover() to check available projects and experiments.
        Warns for unmapped result types.
        """
        try:
            discovered = self.discover()
        except Exception as exc:
            logger.warning("Could not validate schema mapping: %s", exc)
            return mapping

        # Check if project_id and experiment_id from config exist
        project_id = self.config.extra.get("project_id", "")
        experiment_id = self.config.extra.get("experiment_id", "")

        if project_id:
            found_project = False
            for proj in discovered:
                if str(proj["project_id"]) == str(project_id):
                    found_project = True
                    if experiment_id:
                        found_exp = any(
                            str(e["id"]) == str(experiment_id)
                            for e in proj.get("experiments", [])
                        )
                        if not found_exp:
                            logger.warning(
                                "Experiment '%s' not found in project '%s'. "
                                "Available: %s",
                                experiment_id,
                                proj["project_name"],
                                [e["id"] for e in proj.get("experiments", [])],
                            )
                    break
            if not found_project:
                logger.warning(
                    "Project '%s' not found. Available: %s",
                    project_id,
                    [p["project_id"] for p in discovered],
                )

        return mapping

    # ------------------------------------------------------------------
    # Close
    # ------------------------------------------------------------------

    def close(self) -> None:
        """Close the OAuth2Client if it has a close method."""
        if self._client is not None:
            try:
                if hasattr(self._client, "close"):
                    self._client.close()
            except Exception:
                pass
            self._client = None
        super().close()
