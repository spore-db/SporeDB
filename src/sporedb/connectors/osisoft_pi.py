"""OSIsoft PI connector with PI Web API integration.

Supports PI Web API access via Basic Auth using either pi-web-sdk
(typed controllers) or a raw httpx fallback for environments where
pi-web-sdk has compatibility issues.

Install dependencies with::

    pip install "sporedb[connectors]"
"""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime
from typing import Any

import pandas as pd

from sporedb.connectors.base import BaseConnector
from sporedb.connectors.config import ConnectorConfig, SchemaMapping
from sporedb.connectors.result import PullResult
from sporedb.models.batch import Batch
from sporedb.models.timeseries import TelemetryRecord
from sporedb.storage.batch_store import BatchStore
from sporedb.storage.engine import StorageEngine
from sporedb.storage.ts_store import TimeSeriesStore

logger = logging.getLogger(__name__)


def _import_pi_web_sdk() -> Any:
    """Lazy import for pi-web-sdk."""
    try:
        import pi_web_sdk

        return pi_web_sdk
    except ImportError:
        raise ImportError(
            "pi-web-sdk is required for OSIsoft PI support. "
            'Install it with: pip install "sporedb[connectors]" '
            "or: pip install pi-web-sdk"
        ) from None


def _import_httpx() -> Any:
    """Lazy import for httpx (fallback HTTP client)."""
    try:
        import httpx

        return httpx
    except ImportError:
        raise ImportError(
            "httpx is required for OSIsoft PI raw HTTP fallback. "
            'Install it with: pip install "sporedb[connectors]" '
            "or: pip install httpx"
        ) from None


class OSIsoftPIConnector(BaseConnector):
    """Connector for OSIsoft/AVEVA PI Data Archive via PI Web API.

    Supports two backend modes:
    - **pi-web-sdk** (default): Uses the typed Python SDK for PI Web API.
    - **raw httpx** (fallback): Uses raw HTTP calls if pi-web-sdk has issues.

    Select the backend via ``config.extra["use_raw_httpx"]``:
    - ``"false"`` (default): Use pi-web-sdk.
    - ``"true"``: Use raw httpx.

    Authentication is Basic Auth (username/password) via ``config.auth``.
    """

    def __init__(self, config: ConnectorConfig, engine: StorageEngine) -> None:
        super().__init__(config, engine)
        self._client: Any = None
        self._use_raw_httpx: bool = (
            config.extra.get("use_raw_httpx", "false").lower() == "true"
        )

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------

    def connect(self) -> None:
        """Establish connection to PI Web API.

        Uses pi-web-sdk by default, or raw httpx when
        ``config.extra["use_raw_httpx"]`` is ``"true"``.
        """
        if self._use_raw_httpx:
            self._connect_httpx()
        else:
            self._connect_sdk()
        self._connected = True

    def _connect_sdk(self) -> None:
        """Connect using pi-web-sdk."""
        pi_web_sdk = _import_pi_web_sdk()

        username = self.config.auth.get("username", "")
        password = self.config.auth.get("password", "")

        config = pi_web_sdk.PIWebAPIConfig(
            base_url=self.config.host,
            auth_type="basic",
            username=username,
            password=password,
            verify_ssl=self.config.ssl_verify,
        )
        self._client = pi_web_sdk.PIWebAPIClient(config)

    def _connect_httpx(self) -> None:
        """Connect using raw httpx as fallback."""
        httpx = _import_httpx()

        username = self.config.auth.get("username", "")
        password = self.config.auth.get("password", "")

        self._client = httpx.Client(
            base_url=self.config.host,
            auth=(username, password),
            verify=self.config.ssl_verify,
            timeout=self.config.timeout_seconds,
        )

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------

    def discover(self) -> list[dict[str, Any]]:
        """List available PI points on the data server.

        Returns:
            List of dicts with keys: name, path, type, engineering_units.
        """
        if self._use_raw_httpx:
            return self._discover_httpx()
        return self._discover_sdk()

    def _discover_sdk(self) -> list[dict[str, Any]]:
        """Discover PI points using pi-web-sdk."""
        results: list[dict[str, Any]] = []

        # List data servers
        servers = self._client.dataserver.list()
        for server in servers:
            # Get points from each server
            points = self._client.point.get_points(web_id=server.web_id)
            for point in points:
                results.append(
                    {
                        "name": point.name,
                        "path": point.path,
                        "type": "point",
                        "engineering_units": getattr(point, "engineering_units", ""),
                    }
                )
        return results

    def _discover_httpx(self) -> list[dict[str, Any]]:
        """Discover PI points using raw httpx."""
        results: list[dict[str, Any]] = []

        # List data servers
        resp = self._client.get("/piwebapi/dataservers")
        resp.raise_for_status()
        servers = resp.json().get("Items", [])

        for server in servers:
            server_web_id = server.get("WebId", "")
            # Get points for this server
            points_resp = self._client.get(
                f"/piwebapi/dataservers/{server_web_id}/points",
                params={"nameFilter": "*"},
            )
            points_resp.raise_for_status()
            points = points_resp.json().get("Items", [])

            for point in points:
                results.append(
                    {
                        "name": point.get("Name", ""),
                        "path": point.get("Path", ""),
                        "type": "point",
                        "engineering_units": point.get("EngineeringUnits", ""),
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
        """Pull recorded values from PI points and persist as a SporeDB batch.

        Keyword Args:
            start_time: Start time in PI AF syntax (e.g., ``"*-7d"``,
                        ISO8601). Defaults to ``"*-7d"``.
            end_time: End time in PI AF syntax (e.g., ``"*"``).
                      Defaults to ``"*"``.

        Returns:
            PullResult with import statistics.
        """
        t0 = time.monotonic()

        start_time = kwargs.get("start_time", "*-7d")
        end_time = kwargs.get("end_time", "*")

        warnings: list[str] = []
        all_data: dict[str, list[dict[str, Any]]] = {}

        # Fetch recorded values for each mapped PI point
        for fm in mapping.variable_mappings:
            point_path = fm.source
            try:
                if self._use_raw_httpx:
                    records = self._pull_point_httpx(point_path, start_time, end_time)
                else:
                    records = self._pull_point_sdk(point_path, start_time, end_time)
                all_data[fm.source] = records
            except Exception as exc:
                warnings.append(f"Failed to pull PI point '{point_path}': {exc}")

        # Combine into DataFrame
        rows: list[dict[str, Any]] = []
        for fm in mapping.variable_mappings:
            point_records = all_data.get(fm.source, [])
            for rec in point_records:
                rows.append(
                    {
                        "timestamp": rec["timestamp"],
                        "variable": fm.target,
                        "value": rec["value"],
                        "unit": fm.unit,
                        "source_point": fm.source,
                    }
                )

        if not rows:
            warnings.append("No data retrieved from PI points")
            batch = Batch(name=batch_name, tags=["pi-import"])
            batch_store = BatchStore(self.engine)
            batch_store.create_batch(batch)

            return PullResult(
                batch_id=batch.batch_id,
                source_system="osisoft_pi",
                source_identifier=self.config.host,
                rows_imported=0,
                columns_mapped={},
                external_ids={},
                warnings=warnings,
                elapsed_seconds=time.monotonic() - t0,
            )

        # Normalize timestamps to UTC-aware datetimes
        for row in rows:
            ts = row["timestamp"]
            if isinstance(ts, str):
                ts = pd.to_datetime(ts, utc=True).to_pydatetime()
            elif isinstance(ts, datetime):
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=UTC)
            else:
                ts = pd.to_datetime(ts, utc=True).to_pydatetime()
            row["timestamp"] = ts

        # Create batch
        batch = Batch(name=batch_name, tags=["pi-import"])
        batch_store = BatchStore(self.engine)
        batch_store.create_batch(batch)

        # Build TelemetryRecords
        telemetry_records: list[TelemetryRecord] = []
        columns_mapped: dict[str, str] = {}

        for fm in mapping.variable_mappings:
            point_records = all_data.get(fm.source, [])
            if point_records:
                columns_mapped[fm.source] = fm.target

        for row in rows:
            telemetry_records.append(
                TelemetryRecord(
                    batch_id=batch.batch_id,
                    ts=row["timestamp"],
                    variable=row["variable"],
                    value=float(row["value"]),
                    unit=row["unit"],
                )
            )

        # Persist telemetry
        rows_imported = 0
        if telemetry_records:
            ts_store = TimeSeriesStore(self.engine)
            rows_imported = ts_store.append_telemetry(telemetry_records)

        # Store PI point paths as external IDs
        external_ids: dict[str, str] = {
            "pi_point_paths": ",".join(fm.source for fm in mapping.variable_mappings)
        }

        elapsed = time.monotonic() - t0
        return PullResult(
            batch_id=batch.batch_id,
            source_system="osisoft_pi",
            source_identifier=self.config.host,
            rows_imported=rows_imported,
            columns_mapped=columns_mapped,
            external_ids=external_ids,
            warnings=warnings,
            elapsed_seconds=elapsed,
        )

    def _pull_point_sdk(
        self, point_path: str, start_time: str, end_time: str
    ) -> list[dict[str, Any]]:
        """Pull recorded values for a single PI point using pi-web-sdk."""
        point = self._client.point.get_by_path(point_path)
        recorded = self._client.stream.get_recorded(
            web_id=point.web_id,
            start_time=start_time,
            end_time=end_time,
        )
        results: list[dict[str, Any]] = []
        for item in recorded.items:
            results.append(
                {
                    "timestamp": item.timestamp,
                    "value": item.value,
                }
            )
        return results

    def _pull_point_httpx(
        self, point_path: str, start_time: str, end_time: str
    ) -> list[dict[str, Any]]:
        """Pull recorded values for a single PI point using raw httpx."""
        # Step 1: Get WebID for the point
        resp = self._client.get(
            "/piwebapi/points",
            params={"path": point_path},
        )
        resp.raise_for_status()
        point_data = resp.json()
        web_id = point_data.get("WebId", "")

        # Step 2: Get recorded values
        stream_resp = self._client.get(
            f"/piwebapi/streams/{web_id}/recorded",
            params={"startTime": start_time, "endTime": end_time},
        )
        stream_resp.raise_for_status()
        items = stream_resp.json().get("Items", [])

        results: list[dict[str, Any]] = []
        for item in items:
            results.append(
                {
                    "timestamp": item.get("Timestamp", ""),
                    "value": item.get("Value", 0.0),
                }
            )
        return results

    # ------------------------------------------------------------------
    # Schema mapping
    # ------------------------------------------------------------------

    def map_schema(self, mapping: SchemaMapping) -> SchemaMapping:
        """Validate mapping against discovered PI points.

        Checks that source PI point paths exist by calling discover().
        Warns for unmapped points and engineering unit mismatches.
        """
        discovered = self.discover()
        discovered_paths = {item["path"] for item in discovered}
        discovered_names = {item["name"] for item in discovered}

        for fm in mapping.variable_mappings:
            if fm.source not in discovered_paths and fm.source not in discovered_names:
                logger.warning(
                    f"Source PI point '{fm.source}' not found. "
                    f"Available paths: {sorted(discovered_paths)}"
                )

            # Check engineering units if specified
            if fm.unit:
                for item in discovered:
                    if item["path"] == fm.source or item["name"] == fm.source:
                        eu = item.get("engineering_units", "")
                        if eu and eu != fm.unit:
                            logger.warning(
                                f"PI point '{fm.source}' has engineering units "
                                f"'{eu}', but mapping specifies '{fm.unit}'"
                            )
                        break

        return mapping

    # ------------------------------------------------------------------
    # Close
    # ------------------------------------------------------------------

    def close(self) -> None:
        """Close the PI Web API client."""
        if self._client is not None:
            try:
                if hasattr(self._client, "close"):
                    self._client.close()
            except Exception:
                pass
            self._client = None
        super().close()
