"""Targeted tests for modules with no other test coverage.

Covers:
- sporedb/_types.py (0%): TypeAlias definitions for BatchId/OperationId
"""

from __future__ import annotations


class TestTypesModule:
    """Tests that simply import _types.py to register its lines as covered."""

    def test_batch_id_type_alias(self) -> None:
        """BatchId is a type alias for UUID."""
        from uuid import UUID

        from sporedb._types import BatchId

        # TypeAlias is just a marker; verify the underlying type
        assert BatchId is UUID

    def test_operation_id_type_alias(self) -> None:
        """OperationId is a type alias for UUID."""
        from uuid import UUID

        from sporedb._types import OperationId

        assert OperationId is UUID

    def test_batch_id_can_be_used_as_uuid(self) -> None:
        """BatchId values are standard UUIDs."""
        import uuid

        from sporedb._types import BatchId

        batch_uuid = uuid.uuid4()
        # BatchId is just UUID -- we can annotate with it
        batch_id: BatchId = batch_uuid
        assert isinstance(batch_id, uuid.UUID)
