import os
import sys

# Ensure worktree src takes precedence over the editable install from main repo
_worktree_src = os.path.join(os.path.dirname(__file__), os.pardir, "src")
_worktree_src = os.path.abspath(_worktree_src)
if _worktree_src not in sys.path:
    sys.path.insert(0, _worktree_src)
    # Force re-import of sporedb from worktree src
    for mod_name in list(sys.modules):
        if mod_name.startswith("sporedb"):
            del sys.modules[mod_name]

from datetime import UTC, datetime  # noqa: E402

import pytest  # noqa: E402

from sporedb.models.batch import (  # noqa: E402
    Batch,
    BatchLifecycle,
    BatchMetadata,
    CanonicalTimestamps,
)


@pytest.fixture
def sample_batch() -> Batch:
    return Batch(
        name="CHO-K1-Run-042",
        lifecycle=BatchLifecycle.INOCULATED,
        timestamps=CanonicalTimestamps(
            inoculation=datetime(2026, 4, 20, 8, 0, tzinfo=UTC),
        ),
        metadata=BatchMetadata(
            strain="CHO-K1",
            media="CD-CHO",
            scale_liters=5.0,
            operator="Dr. Smith",
        ),
        tags=["mAb", "platform-process", "scale-up"],
    )


@pytest.fixture
def data_root(tmp_path):
    """Temporary data directory for Parquet storage tests."""
    root = tmp_path / "sporedb_data"
    root.mkdir()
    return root
