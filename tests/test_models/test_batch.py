"""Tests for the Batch domain model, lifecycle, timestamps, and metadata."""

from datetime import UTC, datetime
from uuid import UUID

import pytest
from hypothesis import given
from hypothesis import strategies as st
from pydantic import ValidationError

from sporedb.models.batch import (
    Batch,
    BatchLifecycle,
    BatchMetadata,
    CanonicalTimestamps,
)


class TestBatchDefaultCreation:
    def test_batch_default_creation(self):
        """Batch() with only name creates valid batch with defaults."""
        batch = Batch(name="test-run-001")

        assert isinstance(batch.batch_id, UUID)
        assert batch.name == "test-run-001"
        assert batch.lifecycle == BatchLifecycle.PLANNED
        assert batch.timestamps == CanonicalTimestamps()
        assert batch.metadata == BatchMetadata()
        assert batch.tags == []

    def test_batch_id_is_uuid(self):
        """Batch.batch_id is a UUID (UUIDv7 from uuid_utils.uuid7)."""
        batch = Batch(name="test-run")
        assert isinstance(batch.batch_id, UUID)
        # UUIDv7 has version 7
        assert batch.batch_id.version == 7

    def test_batch_created_at_and_updated_at_auto_populated(self):
        """Batch.created_at and updated_at are auto-populated datetime fields."""
        batch = Batch(name="test-run")
        assert isinstance(batch.created_at, datetime)
        assert isinstance(batch.updated_at, datetime)
        assert batch.created_at.tzinfo is not None
        assert batch.updated_at.tzinfo is not None


class TestCanonicalTimestamps:
    def test_canonical_timestamps_roundtrip(self):
        """Batch with canonical timestamps round-trips through model_dump/validate."""
        now = datetime(2026, 4, 20, 8, 0, tzinfo=UTC)
        batch = Batch(
            name="roundtrip-test",
            timestamps=CanonicalTimestamps(
                inoculation=now,
                feed_start=datetime(2026, 4, 20, 12, 0, tzinfo=UTC),
                induction=datetime(2026, 4, 21, 8, 0, tzinfo=UTC),
                harvest=datetime(2026, 4, 25, 10, 0, tzinfo=UTC),
            ),
        )

        dumped = batch.model_dump()
        restored = Batch.model_validate(dumped)

        assert restored.timestamps.inoculation == now
        assert restored.timestamps.feed_start == batch.timestamps.feed_start
        assert restored.timestamps.induction == batch.timestamps.induction
        assert restored.timestamps.harvest == batch.timestamps.harvest
        assert restored.name == batch.name
        assert restored.batch_id == batch.batch_id

    def test_canonical_timestamps_all_optional(self):
        """All canonical timestamp fields are optional."""
        ts = CanonicalTimestamps()
        assert ts.inoculation is None
        assert ts.feed_start is None
        assert ts.induction is None
        assert ts.harvest is None


class TestBatchLifecycle:
    def test_lifecycle_enum_values(self):
        """BatchLifecycle enum has exactly 5 values."""
        values = [e.value for e in BatchLifecycle]
        assert values == ["planned", "inoculated", "running", "harvested", "aborted"]
        assert len(BatchLifecycle) == 5

    def test_batch_invalid_lifecycle_raises_validation_error(self):
        """Batch with invalid lifecycle value raises ValidationError."""
        with pytest.raises(ValidationError):
            Batch(name="bad", lifecycle="nonexistent_state")


class TestBatchMetadata:
    def test_batch_metadata_validates(self):
        """BatchMetadata with all fields validates correctly."""
        meta = BatchMetadata(
            strain="CHO-K1",
            media="CD-CHO",
            scale_liters=5.0,
            operator="Dr. Smith",
        )
        assert meta.strain == "CHO-K1"
        assert meta.media == "CD-CHO"
        assert meta.scale_liters == 5.0
        assert meta.operator == "Dr. Smith"

    def test_batch_metadata_extra_dict(self):
        """BatchMetadata.extra dict stores arbitrary key-value pairs."""
        meta = BatchMetadata(extra={"impeller_type": "Rushton", "vessel": "Biostat-B"})
        assert meta.extra["impeller_type"] == "Rushton"
        assert meta.extra["vessel"] == "Biostat-B"

    def test_batch_metadata_extra_defaults_empty(self):
        """BatchMetadata.extra defaults to empty dict."""
        meta = BatchMetadata()
        assert meta.extra == {}


class TestBatchTags:
    def test_batch_tags_list(self):
        """Batch.tags is a list of strings, can contain 0..N tags."""
        batch_no_tags = Batch(name="no-tags")
        assert batch_no_tags.tags == []

        batch_with_tags = Batch(name="tagged", tags=["mAb", "scale-up", "platform"])
        assert len(batch_with_tags.tags) == 3
        assert "mAb" in batch_with_tags.tags


class TestBatchSerialization:
    def test_model_dump_json_serializable(self):
        """model_dump(mode='json') produces JSON-serializable dict."""
        batch = Batch(
            name="json-test",
            timestamps=CanonicalTimestamps(
                inoculation=datetime(2026, 4, 20, 8, 0, tzinfo=UTC),
            ),
        )
        dumped = batch.model_dump(mode="json")

        # UUID should be string
        assert isinstance(dumped["batch_id"], str)
        # datetime should be string
        assert isinstance(dumped["created_at"], str)
        assert isinstance(dumped["updated_at"], str)
        assert isinstance(dumped["timestamps"]["inoculation"], str)

    def test_full_roundtrip(self):
        """Complete batch round-trips through model_dump/model_validate."""
        batch = Batch(
            name="roundtrip",
            lifecycle=BatchLifecycle.RUNNING,
            metadata=BatchMetadata(strain="E. coli", extra={"plasmid": "pET-28a"}),
            tags=["expression", "recombinant"],
        )
        restored = Batch.model_validate(batch.model_dump())
        assert restored == batch


class TestBatchHypothesis:
    @given(
        strain=st.text(min_size=0, max_size=100),
        media=st.text(min_size=0, max_size=100),
        scale=st.floats(min_value=0.001, max_value=100000, allow_nan=False),
        operator=st.text(min_size=0, max_size=100),
    )
    def test_batch_metadata_arbitrary_strings(self, strain, media, scale, operator):
        """Hypothesis: BatchMetadata with arbitrary string fields validates."""
        meta = BatchMetadata(
            strain=strain,
            media=media,
            scale_liters=scale,
            operator=operator,
        )
        assert meta.strain == strain
        assert meta.media == media
        assert meta.scale_liters == scale
        assert meta.operator == operator
