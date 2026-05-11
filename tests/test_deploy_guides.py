"""Smoke tests for platform deploy guides and config files.

Covers DEPLOY-01 through DEPLOY-05 requirements:
- DEPLOY-01: Deploy guide pages exist in docs/deploy/
- DEPLOY-02: Config files (railway.json, render.yaml, fly.toml) valid and present
- DEPLOY-03: AWS task-definition.json valid JSON
- DEPLOY-04: README Deploy section has platform links
- DEPLOY-05: Each guide has cost/sizing sections
"""

import json
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# DEPLOY-01: Deploy guide pages exist
# ---------------------------------------------------------------------------

GUIDE_FILES = [
    "docs/deploy/index.md",
    "docs/deploy/railway.md",
    "docs/deploy/render.md",
    "docs/deploy/fly-io.md",
    "docs/deploy/aws.md",
    "docs/deploy/digitalocean.md",
]


@pytest.mark.parametrize("guide_path", GUIDE_FILES)
def test_deploy_guide_pages_exist(guide_path: str) -> None:
    """DEPLOY-01: Each platform guide page exists in docs/deploy/."""
    assert (ROOT / guide_path).is_file(), f"Missing guide: {guide_path}"


# ---------------------------------------------------------------------------
# DEPLOY-02: Config files valid and present
# ---------------------------------------------------------------------------


def test_railway_json_valid() -> None:
    """DEPLOY-02: railway.json is valid JSON with health check."""
    path = ROOT / "railway.json"
    assert path.is_file(), "railway.json missing at repo root"
    data = json.loads(path.read_text())
    assert data["deploy"]["healthcheckPath"] == "/health"


def test_render_yaml_valid() -> None:
    """DEPLOY-02: render.yaml is valid YAML with web service and database."""
    yaml = pytest.importorskip("yaml")
    path = ROOT / "render.yaml"
    assert path.is_file(), "render.yaml missing at repo root"
    data = yaml.safe_load(path.read_text())
    assert data["services"][0]["healthCheckPath"] == "/health"
    assert data["databases"][0]["postgresMajorVersion"] == "16"


def test_fly_toml_valid() -> None:
    """DEPLOY-02: fly.toml is valid TOML with correct port."""
    path = ROOT / "fly.toml"
    assert path.is_file(), "fly.toml missing at repo root"
    data = tomllib.loads(path.read_text())
    assert data["http_service"]["internal_port"] == 8000


# ---------------------------------------------------------------------------
# DEPLOY-03: AWS task-definition.json valid
# ---------------------------------------------------------------------------


def test_aws_task_definition_valid() -> None:
    """DEPLOY-03: task-definition.json is valid JSON with health check.

    NOTE: task-definition.json is an intentional **template** file.
    It contains ACCOUNT_ID and REGION placeholders that users must replace
    with their own AWS account ID and region before running
    ``aws ecs register-task-definition``.  See docs/deploy/aws.md Step 8
    for replacement instructions.
    """
    path = ROOT / "docs" / "deploy" / "aws" / "task-definition.json"
    assert path.is_file(), "task-definition.json missing"
    raw = path.read_text()
    data = json.loads(raw)
    container = data["containerDefinitions"][0]
    assert "8000" in container["healthCheck"]["command"][1]

    # Verify the template placeholders are present — this documents
    # that the file is a template and cannot be used as-is.  Users must
    # replace ACCOUNT_ID and REGION before registering the task definition.
    assert "ACCOUNT_ID" in raw, (
        "task-definition.json should contain ACCOUNT_ID placeholder "
        "(it is a template; see docs/deploy/aws.md Step 8)"
    )
    assert "REGION" in raw, (
        "task-definition.json should contain REGION placeholder "
        "(it is a template; see docs/deploy/aws.md Step 8)"
    )


# ---------------------------------------------------------------------------
# DEPLOY-04: README Deploy section has platform links
# ---------------------------------------------------------------------------

PLATFORMS_IN_README = ["Railway", "Render", "Fly.io", "AWS", "DigitalOcean"]


@pytest.mark.parametrize("platform", PLATFORMS_IN_README)
def test_readme_deploy_section_has_platform(platform: str) -> None:
    """DEPLOY-04: README mentions each platform in Deploy section."""
    readme = (ROOT / "README.md").read_text()
    # Scope the check to the ## Deploy section only
    deploy_start = readme.find("## Deploy")
    assert deploy_start != -1, "README.md missing ## Deploy section"
    # Find next H2 to bound the section
    next_h2 = readme.find("\n## ", deploy_start + 1)
    deploy_section = (
        readme[deploy_start:next_h2] if next_h2 != -1 else readme[deploy_start:]
    )
    assert platform in deploy_section, (
        f"README.md Deploy section missing platform: {platform}"
    )


# ---------------------------------------------------------------------------
# DEPLOY-05: Each guide has cost/sizing sections
# ---------------------------------------------------------------------------

COST_GUIDE_FILES = [
    "docs/deploy/railway.md",
    "docs/deploy/render.md",
    "docs/deploy/fly-io.md",
    "docs/deploy/aws.md",
    "docs/deploy/digitalocean.md",
]


@pytest.mark.parametrize("guide_path", COST_GUIDE_FILES)
def test_guide_has_cost_estimate(guide_path: str) -> None:
    """DEPLOY-05: Each guide has a Cost Estimate section."""
    content = (ROOT / guide_path).read_text()
    assert "Cost Estimate" in content, f"{guide_path} missing Cost Estimate section"


@pytest.mark.parametrize("guide_path", COST_GUIDE_FILES)
def test_guide_has_recommended_sizing(guide_path: str) -> None:
    """DEPLOY-05: Each guide has a Recommended Sizing section."""
    content = (ROOT / guide_path).read_text()
    assert "Recommended Sizing" in content, (
        f"{guide_path} missing Recommended Sizing section"
    )
