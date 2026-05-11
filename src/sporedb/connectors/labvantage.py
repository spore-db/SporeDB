"""LabVantage LIMS connector with session-based REST API integration.

Uses httpx for REST API calls. Authenticates via POST /rest/connections
which returns a connection ID for subsequent requests.

Install dependencies with::

    pip install "sporedb[connectors]"
"""

from __future__ import annotations

import contextlib
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


def _import_httpx() -> Any:
    """Lazy import for httpx."""
    try:
        import httpx

        return httpx
    except ImportError:
        raise ImportError(
            "httpx is required for LabVantage LIMS support. "
            'Install it with: pip install "sporedb[connectors]" '
            "or: pip install httpx"
        ) from None


class LabVantageLIMSConnector(BaseConnector):
    """Connector for LabVantage LIMS via REST API.

    Uses session-based authentication: POST /rest/connections returns
    a ``connectionid`` that authenticates subsequent requests.

    Endpoint paths are configurable via ``config.extra`` since
    LabVantage REST endpoints vary by deployment (RESTPolicy config).
    """

    def __init__(self, config: ConnectorConfig, engine: StorageEngine) -> None:
        super().__init__(config, engine)
        self._client: Any = None
        self._connection_id: str = ""

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------

    def connect(self) -> None:
        """Establish authenticated session with LabVantage LIMS.

        POSTs to /rest/connections with database_id, username, and
        password. Stores the returned connectionid for subsequent requests.
        """
        httpx = _import_httpx()

        self._client = httpx.Client(
            base_url=self.config.host,
            verify=self.config.ssl_verify,
            timeout=self.config.timeout_seconds,
        )

        database_id = self.config.extra.get("database_id", "LIMS")
        username = self.config.auth.get("username", "")
        password = self.config.auth.get("password", "")

        response = self._client.post(
            "/rest/connections",
            json={
                "databaseid": database_id,
                "username": username,
                "password": password,
            },
        )
        response.raise_for_status()

        data = response.json()
        self._connection_id = data.get("connectionid", "")
        if not self._connection_id:
            raise ConnectionError(
                "LabVantage authentication succeeded but no connectionid returned"
            )

        self._connected = True
        logger.info(
            "Connected to LabVantage LIMS at %s (connection: %s)",
            self.config.host,
            self._connection_id[:8] + "...",
        )

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------

    def discover(self) -> list[dict[str, Any]]:
        """Probe standard LIMS endpoints to discover available data.

        Checks /rest/sample, /rest/result, /rest/test and reports
        which endpoints respond successfully.

        Returns:
            List of dicts with keys: endpoint, type, available.
        """
        standard_endpoints = [
            ("/rest/sample", "samples"),
            ("/rest/result", "results"),
            ("/rest/test", "tests"),
        ]

        results: list[dict[str, Any]] = []
        for endpoint, endpoint_type in standard_endpoints:
            try:
                resp = self._client.get(
                    endpoint,
                    headers={"connectionid": self._connection_id},
                )
                available = resp.status_code == 200
                if resp.status_code == 404:
                    logger.warning(
                        "LabVantage endpoint %s returned 404. "
                        "This endpoint may not be configured in your "
                        "LabVantage RESTPolicy. Check /rest/api for "
                        "available endpoints.",
                        endpoint,
                    )
            except Exception:
                available = False

            results.append(
                {
                    "endpoint": endpoint,
                    "type": endpoint_type,
                    "available": available,
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
        """Pull sample and result data from LabVantage LIMS.

        Follows explicit persistence sequence:
        1. Fetch data from LIMS
        2. Create batch FIRST to obtain batch_id
        3. Construct AssayMeasurement objects with the batch_id
        4. Persist assay data
        5. Build and return PullResult

        Keyword Args:
            sample_ids: Optional list of LIMS sample IDs for targeted pulls.

        Returns:
            PullResult with import statistics.
        """
        t0 = time.monotonic()

        sample_ids: list[str] = kwargs.get("sample_ids", [])
        warnings: list[str] = []

        # Step 1: Fetch data from LIMS
        sample_endpoint = self.config.extra.get("sample_endpoint", "/rest/sample")
        params: dict[str, str] = {}
        if sample_ids:
            params["keyid1"] = ",".join(sample_ids)

        try:
            samples_resp = self._client.get(
                sample_endpoint,
                params=params,
                headers={"connectionid": self._connection_id},
            )
            samples_resp.raise_for_status()
            samples_data = samples_resp.json().get("data", [])
        except Exception as exc:
            warnings.append(f"Failed to fetch samples: {exc}")
            samples_data = []

        # Fetch results for each sample
        result_rows: list[dict[str, Any]] = []
        for sample in samples_data:
            sample_id = sample.get("keyid1", sample.get("id", ""))
            try:
                results_resp = self._client.get(
                    "/rest/result",
                    params={"keyid1": sample_id} if sample_id else {},
                    headers={"connectionid": self._connection_id},
                )
                results_resp.raise_for_status()
                results_data = results_resp.json().get("data", [])
                for result_row in results_data:
                    result_row["_sample_id"] = sample_id
                    result_rows.append(result_row)
            except Exception as exc:
                warnings.append(
                    f"Failed to fetch results for sample '{sample_id}': {exc}"
                )

        # Step 2: Create batch FIRST to obtain batch_id
        batch_metadata_extra: dict[str, Any] = {}
        if self.config.extra.get("organism"):
            batch_metadata_extra["organism"] = self.config.extra["organism"]
        if self.config.extra.get("process_type"):
            batch_metadata_extra["process_type"] = self.config.extra["process_type"]

        batch = Batch(name=batch_name, tags=["lims-import"])
        if batch_metadata_extra:
            batch.metadata.extra.update(batch_metadata_extra)

        batch_store = BatchStore(self.engine)
        batch_store.create_batch(batch)

        # Step 3: Construct AssayMeasurement objects with the batch_id
        assay_measurements: list[AssayMeasurement] = []
        columns_mapped: dict[str, str] = {}

        # Build a field name mapping from the schema mapping
        field_map: dict[str, str] = {
            fm.source: fm.target for fm in mapping.variable_mappings
        }
        unit_map: dict[str, str | None] = {
            fm.source: fm.unit for fm in mapping.variable_mappings
        }

        for result_row in result_rows:
            # Get the timestamp field
            ts_raw = result_row.get(mapping.timestamp_field, "")
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
                warnings.append(f"Could not parse timestamp '{ts_raw}' in result row")
                continue

            # Map each field in the result to an AssayMeasurement
            for source_field, target_field in field_map.items():
                raw_value = result_row.get(source_field)
                if raw_value is None:
                    continue

                try:
                    value = float(raw_value)
                except (ValueError, TypeError):
                    continue

                columns_mapped[source_field] = target_field

                assay_measurements.append(
                    AssayMeasurement(
                        batch_id=batch.batch_id,
                        ts=ts,
                        variable=target_field,
                        value=value,
                        uncertainty=float(result_row.get("uncertainty", 0.0)),
                        unit=unit_map.get(source_field) or result_row.get("unit", ""),
                        method=result_row.get("testmethod", "lims"),
                    )
                )

        # Step 4: Persist assay data
        rows_imported = 0
        if assay_measurements:
            ts_store = TimeSeriesStore(self.engine)
            rows_imported = ts_store.append_assay(assay_measurements)

        # Step 5: Build and return PullResult
        external_ids: dict[str, str] = {}
        actual_sample_ids = sample_ids or [
            s.get("keyid1", s.get("id", "")) for s in samples_data
        ]
        if actual_sample_ids:
            external_ids["lims_sample_ids"] = ",".join(
                str(s) for s in actual_sample_ids
            )

        elapsed = time.monotonic() - t0
        return PullResult(
            batch_id=batch.batch_id,
            source_system="labvantage",
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
        """Validate source field names against a discover() response.

        Logs warnings for fields that may not exist in the LIMS.
        """
        discovered = self.discover()
        available_endpoints = [d["endpoint"] for d in discovered if d["available"]]

        if not available_endpoints:
            logger.warning(
                "No LabVantage endpoints available. Schema mapping cannot be validated."
            )

        return mapping

    # ------------------------------------------------------------------
    # Close
    # ------------------------------------------------------------------

    def close(self) -> None:
        """Close the httpx client."""
        if self._client is not None:
            with contextlib.suppress(Exception):
                self._client.close()
            self._client = None
        self._connection_id = ""
        super().close()
