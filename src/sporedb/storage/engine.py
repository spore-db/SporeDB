"""DuckDB connection management for SporeDB storage layer."""

from __future__ import annotations

import threading
from pathlib import Path

import duckdb


class StorageEngine:
    """Manages DuckDB connection and data root directory.

    Uses an in-memory DuckDB instance that reads/writes Parquet files directly.
    The data_root directory is created if it does not exist.

    Args:
        data_root: Path to the directory where Parquet files are stored.
            Created automatically if it does not exist.
    """

    def __init__(self, data_root: Path | str) -> None:
        self.data_root = Path(data_root)
        self.data_root.mkdir(parents=True, exist_ok=True)
        self._con: duckdb.DuckDBPyConnection | None = None
        self._lock = threading.Lock()
        self._closed = False

    @property
    def con(self) -> duckdb.DuckDBPyConnection:
        """Lazy-initialize and return the DuckDB connection.

        Thread-safe via ``_lock``. Raises ``RuntimeError`` after ``close()``.
        """
        with self._lock:
            if self._closed:
                raise RuntimeError("StorageEngine is closed")
            if self._con is None:
                self._con = duckdb.connect()
            return self._con

    def close(self) -> None:
        """Close the DuckDB connection if open. Further access raises RuntimeError."""
        with self._lock:
            if self._con is not None:
                self._con.close()
                self._con = None
            self._closed = True

    def __enter__(self) -> StorageEngine:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()
