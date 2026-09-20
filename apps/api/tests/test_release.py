"""A release is consistent: one version everywhere, notes for it, and a workflow that builds it."""

import json
import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def version() -> str:
    return str(tomllib.loads((ROOT / "apps/api/pyproject.toml").read_text())["project"]["version"])


def test_one_version_everywhere_with_release_notes() -> None:
    api = version()
    web = json.loads((ROOT / "apps/web/package.json").read_text())["version"]
    newest = re.search(r"(?m)^## \[(\d+\.\d+\.\d+)\]", (ROOT / "CHANGELOG.md").read_text())
    assert newest is not None
    assert api == web == newest.group(1)


def test_the_release_workflow_builds_both_images_from_real_paths() -> None:
    workflow = (ROOT / ".github/workflows/release.yml").read_text()
    assert "ghcr.io/" in workflow and "ichnos-api" in workflow and "ichnos-web" in workflow
    for key in ("context", "dockerfile"):
        for path in re.findall(rf"(?m)^\s+{key}: ([^$\s][^\s]*)$", workflow):
            assert (ROOT / path).exists(), f"{key} {path} does not exist"
    override = (ROOT / "docker-compose.release.yml").read_text()
    assert "ichnos-api:${ICHNOS_VERSION" in override and "ichnos-web:${ICHNOS_VERSION" in override
