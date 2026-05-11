"""DuckDB query execution service for tenant-scoped S3 Parquet data.

Creates ephemeral DuckDB connections per query to avoid shared-connection
pitfalls (RESEARCH.md Pitfall 1). Configures httpfs for S3 access and
enforces query timeouts (T-8-18).

Threat mitigations:
- T-8-17: All user queries go through DSL parser -> SQL compiler.
- T-8-18: Query timeout set to 30 seconds via SET timeout.
"""

from __future__ import annotations

import logging
from typing import Any

import duckdb

from sporedb.query.dsl import DuckDBCompiler, parse_query

logger = logging.getLogger(__name__)


class QueryService:
    """Execute DSL or internal SQL queries against S3 Parquet via DuckDB.

    Each query creates an ephemeral DuckDB connection with httpfs
    configured for the S3 backend. Connections are always closed in
    a finally block to prevent resource leaks.

    Parameters
    ----------
    s3_config:
        Dict with keys: region, key_id, secret, endpoint, bucket.
    """

    def __init__(self, s3_config: dict[str, str]) -> None:
        self._s3_config = s3_config
        self._compiler = DuckDBCompiler()

    def _create_connection(self) -> duckdb.DuckDBPyConnection:
        """Create an ephemeral DuckDB in-memory connection with S3 httpfs."""
        conn = duckdb.connect(":memory:")

        # Install and load httpfs for S3 access
        conn.execute("INSTALL httpfs;")
        conn.execute("LOAD httpfs;")

        # Validate S3 config values contain no SQL metacharacters
        for key, value in self._s3_config.items():
            if key == "bucket":
                continue  # bucket is not used in SET statements
            if "'" in value or ";" in value:
                raise ValueError(f"Invalid character in S3 config key '{key}'")

        # Configure S3 credentials
        conn.execute(f"SET s3_region='{self._s3_config['region']}';")
        conn.execute(f"SET s3_access_key_id='{self._s3_config['key_id']}';")
        conn.execute(f"SET s3_secret_access_key='{self._s3_config['secret']}';")
        conn.execute(f"SET s3_endpoint='{self._s3_config['endpoint']}';")
        conn.execute("SET s3_url_style='path';")

        # Query timeout: 30 seconds (T-8-18)
        conn.execute("SET timeout=30000;")

        return conn

    def _s3_url(self, tenant_id: str, *parts: str) -> str:
        """Build S3 URL for a tenant-scoped path."""
        bucket = self._s3_config["bucket"]
        suffix = "/".join(parts)
        return f"s3://{bucket}/tenants/{tenant_id}/{suffix}"

    def execute_dsl(self, tenant_id: str, query_str: str) -> list[dict[str, Any]]:
        """Parse and execute a DSL query against tenant's S3 Parquet data.

        Parameters
        ----------
        tenant_id:
            The tenant whose data to query.
        query_str:
            A bioprocess DSL query string.

        Returns
        -------
        list[dict]
            Query results as a list of row dictionaries.

        Raises
        ------
        ValueError
            If the DSL query cannot be parsed.
        RuntimeError
            If query execution fails.
        """
        # Parse DSL to AST (raises on malformed input)
        ast = parse_query(query_str)

        # Compile AST to SQL
        sql, params = self._compiler.compile(ast)

        # Replace local path placeholders with tenant-scoped S3 URLs
        telemetry_url = self._s3_url(tenant_id, "telemetry", "**/*.parquet")
        assay_url = self._s3_url(tenant_id, "assay", "**/*.parquet")
        sql = sql.replace("batch_catalog", f"read_parquet('{telemetry_url}')")
        sql = sql.replace("golden_profiles", f"read_parquet('{assay_url}')")

        conn = self._create_connection()
        try:
            result = conn.execute(sql, params)
            columns = [desc[0] for desc in result.description]
            rows = result.fetchall()
            return [dict(zip(columns, row, strict=False)) for row in rows]
        except Exception as exc:
            logger.error("DuckDB query execution failed: %s", exc)
            raise RuntimeError(f"Query execution failed: {exc}") from exc
        finally:
            conn.close()

    def execute_raw_sql(
        self,
        tenant_id: str,
        sql: str,
        params: list[Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Execute server-generated SQL against tenant's S3 Parquet data.

        This method is for internal use by analytics routes only.
        It does NOT accept user-supplied SQL.

        Parameters
        ----------
        tenant_id:
            The tenant whose data to query.
        sql:
            Server-generated SQL string.
        params:
            Optional positional parameters for the SQL query.
        """
        conn = self._create_connection()
        try:
            result = conn.execute(sql, params) if params else conn.execute(sql)
            columns = [desc[0] for desc in result.description]
            rows = result.fetchall()
            return [dict(zip(columns, row, strict=False)) for row in rows]
        except Exception as exc:
            logger.error("DuckDB raw SQL execution failed: %s", exc)
            raise RuntimeError(f"Query execution failed: {exc}") from exc
        finally:
            conn.close()
