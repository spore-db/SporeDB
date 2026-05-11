"""File-level locking for Parquet read-modify-write operations.

Uses ``filelock`` for cross-platform advisory locking. Lock files are
created adjacent to the target Parquet file (``<path>.lock``).
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from filelock import FileLock


@contextmanager
def parquet_lock(file_path: Path, timeout: float = 10.0) -> Iterator[None]:
    """Acquire a file-level lock adjacent to a Parquet file.

    Parameters
    ----------
    file_path:
        Path to the Parquet file being protected.
    timeout:
        Seconds to wait for the lock. Raises ``filelock.Timeout`` on
        expiry.
    """
    lock = FileLock(str(file_path) + ".lock", timeout=timeout)
    with lock:
        yield
