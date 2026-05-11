"""Test that docs/configuration.md covers all CloudSettings fields."""

from __future__ import annotations

from pathlib import Path

from sporedb.cloud.config import CloudSettings

DOCS_PATH = Path(__file__).resolve().parent.parent.parent / "docs" / "configuration.md"


class TestConfigDocs:
    def test_docs_file_exists(self):
        assert DOCS_PATH.exists(), f"docs/configuration.md not found at {DOCS_PATH}"

    def test_all_fields_documented(self):
        content = DOCS_PATH.read_text()
        for name in CloudSettings.model_fields:
            env_name = f"SPOREDB_{name.upper()}"
            assert env_name in content, f"{env_name} missing from docs/configuration.md"

    def test_provider_examples_present(self):
        content = DOCS_PATH.read_text()
        for provider in ["AWS", "GCP", "Azure", "MinIO", "Hetzner"]:
            assert provider in content, (
                f"Provider {provider} missing from docs/configuration.md"
            )
