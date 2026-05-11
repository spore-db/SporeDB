"""Tests that CloudSettings works with multiple cloud providers."""

from __future__ import annotations

from sporedb.cloud.config import CloudSettings


class TestVendorNeutrality:
    """CloudSettings accepts configs for any S3-compatible provider."""

    def test_aws_config(self):
        settings = CloudSettings(
            database_url="postgresql+asyncpg://user:pass@rds.amazonaws.com:5432/sporedb",
            s3_endpoint="https://s3.us-east-1.amazonaws.com",
            s3_access_key="AKIAIOSFODNN7EXAMPLE",
            s3_secret_key="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
            s3_bucket="my-sporedb-bucket",
            s3_region="us-east-1",
        )
        assert settings.s3_endpoint == "https://s3.us-east-1.amazonaws.com"

    def test_gcp_config(self):
        settings = CloudSettings(
            database_url="postgresql+asyncpg://user:pass@/sporedb?host=/cloudsql/project:region:instance",
            s3_endpoint="https://storage.googleapis.com",
            s3_access_key="GOOG1EXAMPLE",
            s3_secret_key="secret",
            s3_bucket="sporedb-gcp",
            s3_region="auto",
        )
        assert settings.s3_endpoint == "https://storage.googleapis.com"

    def test_azure_config(self):
        settings = CloudSettings(
            database_url="postgresql+asyncpg://user:pass@myserver.postgres.database.azure.com:5432/sporedb",
            s3_endpoint="https://myaccount.blob.core.windows.net",
            s3_access_key="myaccount",
            s3_secret_key="base64key==",
            s3_bucket="sporedb-container",
            s3_region="eastus",
        )
        assert settings.s3_endpoint == "https://myaccount.blob.core.windows.net"

    def test_minio_config(self):
        settings = CloudSettings(
            database_url="postgresql+asyncpg://sporedb:sporedb@localhost:5432/sporedb",
            s3_endpoint="http://localhost:9000",
            s3_access_key="minioadmin",
            s3_secret_key="minioadmin",
            s3_bucket="sporedb",
            s3_region="us-east-1",
        )
        assert settings.s3_endpoint == "http://localhost:9000"

    def test_hetzner_config(self):
        settings = CloudSettings(
            database_url="postgresql+asyncpg://user:pass@hetzner-pg.example.com:5432/sporedb",
            s3_endpoint="https://fsn1.your-objectstorage.com",
            s3_access_key="hetzner-key",
            s3_secret_key="hetzner-secret",
            s3_bucket="sporedb-hetzner",
            s3_region="fsn1",
        )
        assert settings.s3_endpoint == "https://fsn1.your-objectstorage.com"

    def test_no_vendor_specific_defaults(self):
        """Default s3_endpoint is localhost (not any provider)."""
        settings = CloudSettings(
            database_url="postgresql+asyncpg://user:pass@localhost:5432/db",
            s3_access_key="key",
            s3_secret_key="secret",
        )
        assert "amazonaws" not in settings.s3_endpoint
        assert "hetzner" not in settings.s3_endpoint
        assert "googleapis" not in settings.s3_endpoint
