from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from ichnos.db.models import Artifact, AuditEvent
from ichnos.main import create_app
from ichnos.settings import Settings

REPO_ROOT = Path(__file__).resolve().parents[3]
MEETING = REPO_ROOT / "examples/demo-repository/docs/meetings/2026-09-15-workspace-onboarding.md"
EDIT = "# Summary\n\nReviewed on 2026-09-19.\n"


@pytest.fixture
def app(monkeypatch: pytest.MonkeyPatch) -> FastAPI:
    monkeypatch.setenv("ICHNOS_LLM_PROVIDER", "fake")
    return create_app(Settings())


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def draft(app: FastAPI, client: TestClient) -> dict[str, Any]:
    """A BRD draft produced by a real run with the fake provider."""
    workspace = client.post(
        "/api/workspaces", json={"name": "quire", "repository": "octo-org/quire"}
    ).json()
    source = client.post(
        f"/api/workspaces/{workspace['id']}/sources",
        json={"content": MEETING.read_text(encoding="utf-8")},
    ).json()
    run = client.post(
        f"/api/workspaces/{workspace['id']}/runs", json={"source_ids": [source["id"]]}
    ).json()
    app.state.runner.wait(run["id"], timeout=60)
    artifact_id = client.get(f"/api/runs/{run['id']}").json()["artifact_id"]
    detail: dict[str, Any] = client.get(f"/api/artifacts/{artifact_id}").json()
    return detail


def _edit(content: str) -> str:
    return content.replace("# Summary\n", EDIT, 1)


def test_a_generated_draft_is_listed_with_its_first_version(
    client: TestClient, draft: dict[str, Any]
) -> None:
    listed = client.get(f"/api/workspaces/{draft['workspace_id']}/artifacts").json()
    assert [item["id"] for item in listed] == [draft["id"]]
    assert draft["status"] == "draft"
    assert draft["path"] == f"docs/specs/{draft['slug']}/brd.md"
    assert draft["current_version"] == 1
    assert [v["origin"] for v in draft["versions"]] == ["generated"]
    assert draft["current"]["actor"] == "ichnos/fake"
    assert draft["current"]["finding_details"] == []
    assert draft["current"]["content"].startswith("---\ntype: BRD\n")


def test_an_edit_becomes_a_new_version_and_the_old_one_stays(
    app: FastAPI, client: TestClient, draft: dict[str, Any]
) -> None:
    original = draft["current"]["content"]
    response = client.post(
        f"/api/artifacts/{draft['id']}/versions",
        json={"content": _edit(original), "base_version": 1, "note": "Added review date"},
    )
    assert response.status_code == 201
    saved = response.json()
    assert saved["current_version"] == 2
    current = saved["current"]
    assert (current["number"], current["origin"], current["parent_number"]) == (2, "edited", 1)
    assert current["actor"].startswith("human:")
    assert current["note"] == "Added review date"
    assert current["findings"] == 0
    assert [v["number"] for v in saved["versions"]] == [1, 2]

    first = client.get(f"/api/artifacts/{draft['id']}/versions/1").json()
    assert first["content"] == original and first["origin"] == "generated"
    with app.state.session_factory() as session:
        events = session.scalars(
            select(AuditEvent).where(AuditEvent.event_type == "artifact.version_created")
        ).all()
    assert [e.details["version"] for e in events] == [2]


def test_stale_empty_and_unchanged_saves_are_refused(
    client: TestClient, draft: dict[str, Any]
) -> None:
    url = f"/api/artifacts/{draft['id']}/versions"
    content = draft["current"]["content"]
    assert client.post(url, json={"content": content, "base_version": 1}).status_code == 400
    assert client.post(url, json={"content": "  \n ", "base_version": 1}).status_code == 400
    assert client.post(url, json={"content": _edit(content), "base_version": 1}).status_code == 201
    stale = client.post(url, json={"content": content + "\nMore.", "base_version": 1})
    assert stale.status_code == 409
    assert "Version 2 was saved after you started editing version 1" in stale.json()["detail"]


def test_invalid_okf_is_saved_but_flagged_and_validate_matches(
    client: TestClient, draft: dict[str, Any]
) -> None:
    broken = "# Just a heading\n\nNo frontmatter at all.\n"
    findings = client.post(f"/api/artifacts/{draft['id']}/validate", json={"content": broken})
    assert findings.status_code == 200
    codes = [f["code"] for f in findings.json()]
    assert "frontmatter-missing" in codes

    saved = client.post(
        f"/api/artifacts/{draft['id']}/versions", json={"content": broken, "base_version": 1}
    ).json()
    assert [f["code"] for f in saved["current"]["finding_details"]] == codes
    assert saved["findings"] == len(codes)


def test_only_drafts_can_change(app: FastAPI, client: TestClient, draft: dict[str, Any]) -> None:
    with app.state.session_factory() as session:
        artifact = session.get(Artifact, draft["id"])
        assert artifact is not None
        artifact.status = "approved"
        session.commit()
    response = client.post(
        f"/api/artifacts/{draft['id']}/versions",
        json={"content": _edit(draft["current"]["content"]), "base_version": 1},
    )
    assert response.status_code == 409
    assert "approved" in response.json()["detail"]


def test_unknown_artifacts_and_versions_are_not_found(
    client: TestClient, draft: dict[str, Any]
) -> None:
    assert client.get("/api/artifacts/missing").status_code == 404
    assert client.get(f"/api/artifacts/{draft['id']}/versions/9").status_code == 404
    assert client.post("/api/artifacts/missing/validate", json={"content": "x"}).status_code == 404
