"""Tests for extended analytics Pydantic models.

Covers: BOCPDConfig, GoldenBatchProfile, BatchScore, SoftSensorConfig.
"""

from __future__ import annotations

from uuid import UUID

import pytest
from uuid_utils import uuid7


class TestBOCPDConfig:
    """BOCPDConfig validation and defaults."""

    def test_defaults(self):
        from sporedb.analytics.models import BOCPDConfig

        c = BOCPDConfig()
        assert c.hazard_rate == 0.01
        assert c.threshold == 0.5
        assert c.max_run_length == 500
        assert c.signal_variable == "OD600"
        assert c.mu0 == 0.0
        assert c.kappa0 == 1.0
        assert c.alpha0 == 1.0
        assert c.beta0 == 1.0

    def test_hazard_rate_zero_raises(self):
        from sporedb.analytics.models import BOCPDConfig

        with pytest.raises(Exception, match="hazard_rate"):
            BOCPDConfig(hazard_rate=0)

    def test_hazard_rate_one_raises(self):
        from sporedb.analytics.models import BOCPDConfig

        with pytest.raises(Exception, match="hazard_rate"):
            BOCPDConfig(hazard_rate=1.0)

    def test_hazard_rate_negative_raises(self):
        from sporedb.analytics.models import BOCPDConfig

        with pytest.raises(Exception, match="hazard_rate"):
            BOCPDConfig(hazard_rate=-0.1)

    def test_valid_custom_hazard(self):
        from sporedb.analytics.models import BOCPDConfig

        c = BOCPDConfig(hazard_rate=0.05)
        assert c.hazard_rate == 0.05


class TestGoldenBatchProfile:
    """GoldenBatchProfile required fields."""

    def test_requires_all_fields(self):
        from sporedb.analytics.models import GoldenBatchProfile

        p = GoldenBatchProfile(
            variables=["OD600"],
            mean_trajectory=[[1.0, 2.0]],
            std_trajectory=[[0.1, 0.2]],
            elapsed_hours=[0.0, 1.0],
            source_batch_ids=["batch-1"],
        )
        assert p.variables == ["OD600"]
        assert isinstance(p.profile_id, UUID)

    def test_missing_variables_raises(self):
        from sporedb.analytics.models import GoldenBatchProfile

        with pytest.raises(Exception, match="."):
            GoldenBatchProfile(
                mean_trajectory=[[1.0]],
                std_trajectory=[[0.1]],
                elapsed_hours=[0.0],
                source_batch_ids=["batch-1"],
            )


class TestBatchScore:
    """BatchScore validation."""

    def test_score_in_range(self):
        from sporedb.analytics.models import BatchScore

        bid = UUID(str(uuid7()))
        pid = UUID(str(uuid7()))
        s = BatchScore(batch_id=bid, profile_id=pid, score=85.0, variables=["OD600"])
        assert s.score == 85.0

    def test_score_above_100_raises(self):
        from sporedb.analytics.models import BatchScore

        bid = UUID(str(uuid7()))
        pid = UUID(str(uuid7()))
        with pytest.raises(Exception, match="Score"):
            BatchScore(batch_id=bid, profile_id=pid, score=101, variables=[])

    def test_score_below_0_raises(self):
        from sporedb.analytics.models import BatchScore

        bid = UUID(str(uuid7()))
        pid = UUID(str(uuid7()))
        with pytest.raises(Exception, match="Score"):
            BatchScore(batch_id=bid, profile_id=pid, score=-1, variables=[])


class TestSoftSensorConfig:
    """SoftSensorConfig defaults and required fields."""

    def test_defaults(self):
        from sporedb.analytics.models import SoftSensorConfig

        c = SoftSensorConfig(
            input_variables=["turbidity"],
            output_variable="biomass_predicted",
        )
        assert c.model_type == "linear"
        assert c.prediction_std == 0.0
        assert c.input_variables == ["turbidity"]

    def test_requires_input_variables(self):
        from sporedb.analytics.models import SoftSensorConfig

        with pytest.raises(Exception, match="."):
            SoftSensorConfig(output_variable="biomass_predicted")
