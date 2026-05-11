"""InfluxDB connector with v1+v2 dual-client support.

Supports both InfluxDB v1 (InfluxQL via ``influxdb`` library) and
InfluxDB v2 (Flux via ``influxdb-client`` library), with auto-detection
when version is not specified.

Install dependencies with::

    pip install "sporedb[connectors]"
"""

from __future__ import annotations

import contextlib
import logging
import re
import time
from datetime import UTC
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

# Characters unsafe for interpolation into Flux identifier strings
# (bucket, measurement, field names).
_FLUX_UNSAFE = re.compile(r'["\'\\\n|>{}()/]')

# Pattern for valid Flux time arguments: durations like "-30d", "now()", or
# RFC3339 timestamps.  Only these patterns are allowed for start/end.
_FLUX_TIME_SAFE = re.compile(
    r"^-?\d+[smhdwy]$"  # Flux duration: -30d, 1h, etc.
    r"|^now\(\)$"  # Flux now() literal
    r"|^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$"  # RFC3339 UTC
)

# Valid InfluxQL duration pattern (e.g. "30d", "1h", "500ms").
_INFLUXQL_DURATION = re.compile(r"^\d+[munshd]s?$|^\d+[smhdw]$")

# Allowlist for InfluxQL identifiers (measurement names, field names).
_INFLUXQL_IDENT_SAFE = re.compile(r"^[a-zA-Z0-9_.:\-]+$")


def _import_influxdb_v2() -> Any:
    """Lazy import for influxdb-client (v2)."""
    try:
        import influxdb_client  # noqa: F811

        return influxdb_client
    except ImportError:
        raise ImportError(
            "influxdb-client is required for InfluxDB v2 support. "
            'Install it with: pip install "sporedb[connectors]" '
            "or: pip install influxdb-client"
        ) from None


def _import_influxdb_v1() -> Any:
    """Lazy import for influxdb (v1)."""
    try:
        import influxdb  # noqa: F811

        return influxdb
    except ImportError:
        raise ImportError(
            "influxdb is required for InfluxDB v1 support. "
            'Install it with: pip install "sporedb[connectors]" '
            "or: pip install influxdb"
        ) from None


class InfluxDBConnector(BaseConnector):
    """Connector for InfluxDB v1 and v2 instances.

    Determines version from ``config.extra["version"]`` (``"1"``, ``"2"``,
    or ``"auto"``). In auto mode, attempts a v2 health check first and
    falls back to v1 if that fails.

    Data source is specified as ``config.extra["bucket"]`` (v2) or
    ``config.extra["database"]`` (v1).
    """

    def __init__(self, config: ConnectorConfig, engine: StorageEngine) -> None:
        super().__init__(config, engine)
        self._client: Any = None
        self._version: str | None = None  # "1" or "2" once resolved

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------

    def connect(self) -> None:
        """Establish connection to InfluxDB.

        For v2: uses ``influxdb_client.InfluxDBClient`` with token auth.
        For v1: uses ``influxdb.InfluxDBClient`` with username/password.
        For auto: tries v2 health endpoint first, falls back to v1.
        """
        requested_version = self.config.extra.get("version", "auto")

        if requested_version == "2":
            self._connect_v2()
        elif requested_version == "1":
            self._connect_v1()
        else:
            # Auto-detect: try v2 health endpoint, fall back to v1
            try:
                self._connect_v2()
                # Verify with health check
                health = self._client.health()
                if health.status != "pass":
                    raise ConnectionError("v2 health check did not pass")
            except Exception:
                # Fall back to v1
                logger.info("InfluxDB v2 health check failed, falling back to v1")
                if self._client is not None:
                    with contextlib.suppress(Exception):
                        self._client.close()
                self._connect_v1()

        self._connected = True

    def _connect_v2(self) -> None:
        """Connect using the InfluxDB v2 client."""
        influxdb_client = _import_influxdb_v2()

        url = self.config.host
        if self.config.port and ":" not in url.split("//")[-1]:
            # Only append port if host doesn't already contain one
            url = f"{url}:{self.config.port}"

        token = self.config.auth.get("token", "")
        org = self.config.auth.get("org", "")

        self._client = influxdb_client.InfluxDBClient(
            url=url,
            token=token,
            org=org,
            timeout=self.config.timeout_seconds * 1000,  # ms
            verify_ssl=self.config.ssl_verify,
        )
        self._version = "2"

    def _connect_v1(self) -> None:
        """Connect using the InfluxDB v1 client."""
        influxdb = _import_influxdb_v1()

        host = self.config.host
        # Determine SSL from URL scheme before stripping protocol prefix
        use_ssl = host.startswith("https://")
        # Strip protocol prefix for v1 client (expects bare hostname)
        for prefix in ("http://", "https://"):
            if host.startswith(prefix):
                host = host[len(prefix) :]
                break

        port = self.config.port or 8086
        username = self.config.auth.get("username", "")
        password = self.config.auth.get("password", "")
        database = self.config.extra.get(
            "database", self.config.extra.get("bucket", "")
        )

        self._client = influxdb.InfluxDBClient(
            host=host,
            port=port,
            username=username,
            password=password,
            database=database,
            ssl=use_ssl,
            verify_ssl=self.config.ssl_verify,
            timeout=self.config.timeout_seconds,
        )
        self._version = "1"

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------

    def discover(self) -> list[dict[str, Any]]:
        """List available measurements, fields, and tags.

        Returns:
            List of dicts with keys: name, type, data_type.
        """
        if self._version == "2":
            return self._discover_v2()
        return self._discover_v1()

    def _discover_v2(self) -> list[dict[str, Any]]:
        """Discover measurements in an InfluxDB v2 bucket."""
        bucket = self.config.extra.get("bucket", "")
        if _FLUX_UNSAFE.search(bucket):
            raise ValueError(f"Unsafe characters in bucket name: {bucket!r}")
        org = self.config.auth.get("org", "")
        query_api = self._client.query_api()

        # List measurements
        flux = (
            f'import "influxdata/influxdb/schema"\n'
            f'schema.measurements(bucket: "{bucket}")'
        )
        tables = query_api.query(flux, org=org)

        results: list[dict[str, Any]] = []
        for table in tables:
            for record in table.records:
                results.append(
                    {
                        "name": record.get_value(),
                        "type": "measurement",
                        "data_type": "string",
                    }
                )
        return results

    def _discover_v1(self) -> list[dict[str, Any]]:
        """Discover measurements, fields, and tags in InfluxDB v1."""
        results: list[dict[str, Any]] = []

        # List measurements
        rs = self._client.query("SHOW MEASUREMENTS")
        for item in rs.get_points():
            results.append(
                {
                    "name": item.get("name", ""),
                    "type": "measurement",
                    "data_type": "string",
                }
            )

        # List field keys for each measurement
        for meas in [r["name"] for r in results if r["type"] == "measurement"]:
            if not _INFLUXQL_IDENT_SAFE.match(meas):
                logger.warning("Skipping measurement with unsafe name: %r", meas)
                continue
            rs = self._client.query(f'SHOW FIELD KEYS FROM "{meas}"')
            for item in rs.get_points():
                results.append(
                    {
                        "name": f"{meas}.{item.get('fieldKey', '')}",
                        "type": "field",
                        "data_type": item.get("fieldType", "unknown"),
                    }
                )

            rs = self._client.query(f'SHOW TAG KEYS FROM "{meas}"')
            for item in rs.get_points():
                results.append(
                    {
                        "name": f"{meas}.{item.get('tagKey', '')}",
                        "type": "tag",
                        "data_type": "string",
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
        """Pull data from InfluxDB and persist as a SporeDB batch.

        Keyword Args:
            start: Start time (Flux duration like ``"-30d"`` for v2,
                   or InfluxQL like ``"30d"`` for v1). Defaults to ``"-30d"``/``"30d"``.
            end: End time (Flux duration for v2). Defaults to ``"now()"``.
            measurement: Measurement name to query. Required.

        Returns:
            PullResult with import statistics.
        """
        t0 = time.monotonic()

        measurement = kwargs.get("measurement", "")
        if not measurement:
            raise ValueError("'measurement' keyword argument is required for pull()")

        if self._version == "2":
            df = self._pull_v2(mapping, measurement, kwargs)
        else:
            df = self._pull_v1(mapping, measurement, kwargs)

        warnings: list[str] = []

        if df.empty:
            warnings.append("Query returned no data")
            # Create batch with no data
            batch = Batch(name=batch_name, tags=["influxdb-import"])
            batch_store = BatchStore(self.engine)
            batch_store.create_batch(batch)

            return PullResult(
                batch_id=batch.batch_id,
                source_system="influxdb",
                source_identifier=measurement,
                rows_imported=0,
                columns_mapped={},
                external_ids={},
                warnings=warnings,
                elapsed_seconds=time.monotonic() - t0,
            )

        # Normalize timestamps to UTC-aware datetimes
        ts_col = mapping.timestamp_field
        if ts_col in df.columns:
            df[ts_col] = pd.to_datetime(df[ts_col], utc=True)
        elif "_time" in df.columns:
            ts_col = "_time"
            df[ts_col] = pd.to_datetime(df[ts_col], utc=True)
        else:
            raise ValueError(
                f"Timestamp column '{mapping.timestamp_field}' "
                f"not found in query results. "
                f"Available columns: {list(df.columns)}"
            )

        # Create batch
        batch = Batch(name=batch_name, tags=["influxdb-import"])
        batch_store = BatchStore(self.engine)
        batch_store.create_batch(batch)

        # Map columns and build TelemetryRecords
        records: list[TelemetryRecord] = []
        columns_mapped: dict[str, str] = {}

        for fm in mapping.variable_mappings:
            if fm.source in df.columns:
                columns_mapped[fm.source] = fm.target
                for _, row in df.iterrows():
                    val = row[fm.source]
                    if pd.isna(val):
                        continue
                    ts = row[ts_col]
                    # Ensure timezone-aware
                    if hasattr(ts, "tzinfo") and ts.tzinfo is None:
                        ts = ts.replace(tzinfo=UTC)
                    records.append(
                        TelemetryRecord(
                            batch_id=batch.batch_id,
                            ts=ts,
                            variable=fm.target,
                            value=float(val),
                            unit=fm.unit,
                        )
                    )
            else:
                warnings.append(
                    f"Source field '{fm.source}' not found in query results"
                )

        # Persist telemetry
        rows_imported = 0
        if records:
            ts_store = TimeSeriesStore(self.engine)
            rows_imported = ts_store.append_telemetry(records)

        # Handle external IDs from metadata mappings
        external_ids: dict[str, str] = {}
        if mapping.external_id_field and mapping.external_id_field in df.columns:
            first_val = df[mapping.external_id_field].iloc[0]
            if not pd.isna(first_val):
                external_ids[mapping.external_id_field] = str(first_val)

        elapsed = time.monotonic() - t0
        return PullResult(
            batch_id=batch.batch_id,
            source_system="influxdb",
            source_identifier=measurement,
            rows_imported=rows_imported,
            columns_mapped=columns_mapped,
            external_ids=external_ids,
            warnings=warnings,
            elapsed_seconds=elapsed,
        )

    def _pull_v2(
        self,
        mapping: SchemaMapping,
        measurement: str,
        kwargs: dict[str, Any],
    ) -> pd.DataFrame:
        """Execute Flux query and return DataFrame."""
        bucket = self.config.extra.get("bucket", "")
        org = self.config.auth.get("org", "")
        start = kwargs.get("start", "-30d")
        end = kwargs.get("end", "now()")

        # Build field filter from mapping
        fields = [fm.source for fm in mapping.variable_mappings]

        # --- CR-01: Validate all interpolated values against Flux metacharacters ---
        for name, val in [("bucket", bucket), ("measurement", measurement)]:
            if _FLUX_UNSAFE.search(str(val)):
                raise ValueError(f"Unsafe characters in {name}: {val!r}")
        for f in fields:
            if _FLUX_UNSAFE.search(f):
                raise ValueError(f"Unsafe characters in field name: {f!r}")
        for name, val in [("start", str(start)), ("end", str(end))]:
            if not _FLUX_TIME_SAFE.match(val):
                raise ValueError(f"Unsafe characters in {name}: {val!r}")

        flux = (
            f'from(bucket: "{bucket}")\n'
            f"  |> range(start: {start}, stop: {end})\n"
            f'  |> filter(fn: (r) => r._measurement == "{measurement}")\n'
        )
        if fields:
            field_filter = " or ".join(f'r._field == "{f}"' for f in fields)
            flux += f"  |> filter(fn: (r) => {field_filter})\n"
        pivot_line = (
            '  |> pivot(rowKey: ["_time"], columnKey: ["_field"],'
            ' valueColumn: "_value")\n'
        )
        flux += pivot_line

        query_api = self._client.query_api()
        df = query_api.query_data_frame(flux, org=org)

        # query_data_frame may return a list of DataFrames
        if isinstance(df, list):
            df = pd.concat(df, ignore_index=True) if df else pd.DataFrame()

        return df  # type: ignore[no-any-return]

    def _pull_v1(
        self,
        mapping: SchemaMapping,
        measurement: str,
        kwargs: dict[str, Any],
    ) -> pd.DataFrame:
        """Execute InfluxQL query and return DataFrame."""
        time_range = kwargs.get("start", "30d")

        # --- CR-02: Validate time_range format ---
        if not _INFLUXQL_DURATION.match(time_range):
            raise ValueError(f"Invalid time range format: {time_range}")

        # Validate measurement and field names against allowlist
        if not _INFLUXQL_IDENT_SAFE.match(measurement):
            raise ValueError(f"Unsafe measurement name: {measurement!r}")

        # Build field list from mapping
        fields = [fm.source for fm in mapping.variable_mappings]
        for f in fields:
            if not _INFLUXQL_IDENT_SAFE.match(f):
                raise ValueError(f"Unsafe field name: {f!r}")

        # Escape double-quotes in measurement and field names
        measurement_safe = measurement.replace('"', '\\"')

        if fields:
            select_clause = ", ".join(
                f'"{f.replace(chr(34), chr(92) + chr(34))}"' for f in fields
            )
        else:
            select_clause = "*"

        query = (
            f'SELECT {select_clause} FROM "{measurement_safe}" '
            f"WHERE time > now() - {time_range}"
        )

        result = self._client.query(query)
        points = list(result.get_points())

        if not points:
            return pd.DataFrame()

        df = pd.DataFrame(points)
        return df

    # ------------------------------------------------------------------
    # Schema mapping
    # ------------------------------------------------------------------

    def map_schema(self, mapping: SchemaMapping) -> SchemaMapping:
        """Validate mapping against discovered schema.

        Checks that source fields in the mapping exist in the external
        system. Logs warnings for unmapped fields.
        """
        discovered = self.discover()
        discovered_names = {
            item["name"].split(".")[-1] if "." in item["name"] else item["name"]
            for item in discovered
        }

        warnings: list[str] = []
        for fm in mapping.variable_mappings:
            if fm.source not in discovered_names:
                warnings.append(
                    f"Source field '{fm.source}' not found in InfluxDB. "
                    f"Available: {sorted(discovered_names)}"
                )
                logger.warning(warnings[-1])

        return mapping

    # ------------------------------------------------------------------
    # Close
    # ------------------------------------------------------------------

    def close(self) -> None:
        """Close the InfluxDB client connection."""
        if self._client is not None:
            with contextlib.suppress(Exception):
                self._client.close()
            self._client = None
        super().close()
