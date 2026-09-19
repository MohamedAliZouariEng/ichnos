from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from fake_github import FakeGitHub
from ichnos.db.models import AuditEvent
from ichnos.main import create_app
from ichnos.settings import Settings

NOTE = (
    "---\n"
    "type: Note\n"
    "title: A note\n"
    "status: stable\n"
    "verified: { by: human:alice, at: 2026-09-19T10:00:00Z }\n"
    "meeting_date: 2026-09-15\n"
    "---\n"
    "# Note\n\nText.\n"
)
FILES = {
    "docs/index.md": '---\nokf_version: "0.2"\n---\n# Docs\n\n* [Note](note.md) - A note.\n',
    "docs/note.md": NOTE,
    "docs/broken.md": "# No frontmatter\n",
    ".github/pull_request_template.md": "Closes #\n",
    "README.md": "# Outside the index paths\n",
    "docs/diagram.png": "not a text document",
}
SYNCED = {"docs/index.md", "docs/note.md", "docs/broken.md", ".github/pull_request_template.md"}


@pytest.fixture
def github(monkeypatch: pytest.MonkeyPatch) -> FakeGitHub:
    monkeypatch.setenv("ICHNOS_GITHUB_TOKEN", "test-token-value")
    return FakeGitHub(dict(FILES))


@pytest.fixture
def app(github: FakeGitHub) -> FastAPI:
    application = create_app(Settings())
    application.state.github_transport = github.transport
    return application


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


def _workspace(client: TestClient) -> str:
    body = {"name": "quire", "repository": "octo-org/quire-demo"}
    workspace_id: str = client.post("/api/workspaces", json=body).json()["id"]
    return workspace_id


def _sync(client: TestClient, workspace_id: str) -> dict[str, object]:
    response = client.post(f"/api/workspaces/{workspace_id}/sync")
    assert response.status_code == 200, response.text
    run: dict[str, object] = response.json()
    return run


def _documents(run: dict[str, object]) -> dict[str, int]:
    counts = run["counts"]
    assert isinstance(counts, dict)
    return {key: value for key, value in counts.items() if key.startswith("documents_")}


def test_first_sync_imports_selected_documents(client: TestClient) -> None:
    workspace_id = _workspace(client)
    run = _sync(client, workspace_id)
    assert run["status"] == "succeeded", run
    assert _documents(run) == {
        "documents_added": 4,
        "documents_updated": 0,
        "documents_deleted": 0,
        "documents_unchanged": 0,
        "documents_skipped": 0,
    }
    docs = {d["path"]: d for d in client.get(f"/api/workspaces/{workspace_id}/documents").json()}
    assert set(docs) == SYNCED
    note = docs["docs/note.md"]
    assert (note["kind"], note["type"], note["trust_tier"], note["findings"]) == (
        "concept",
        "Note",
        "human_verified",
        0,
    )
    assert docs["docs/broken.md"]["findings"] == 1
    assert docs[".github/pull_request_template.md"]["kind"] == "other"


def test_second_sync_without_changes_is_one_request(client: TestClient, github: FakeGitHub) -> None:
    workspace_id = _workspace(client)
    _sync(client, workspace_id)
    before = len(github.requests)
    run = _sync(client, workspace_id)
    assert _documents(run) == {
        "documents_added": 0,
        "documents_updated": 0,
        "documents_deleted": 0,
        "documents_unchanged": 4,
        "documents_skipped": 0,
    }
    file_requests = [p for p in github.requests[before:] if "/git/" in p or "/branches/" in p]
    assert file_requests == ["/repos/octo-org/quire-demo/branches/main"]
    assert len(client.get(f"/api/workspaces/{workspace_id}/documents").json()) == 4


def test_changes_are_applied_incrementally(client: TestClient, github: FakeGitHub) -> None:
    workspace_id = _workspace(client)
    _sync(client, workspace_id)
    github.files["docs/note.md"] = NOTE.replace("Text.", "Changed text.")
    github.files["docs/new.md"] = "---\ntype: Note\n---\nNew.\n"
    del github.files["docs/broken.md"]
    before = len(github.requests)

    run = _sync(client, workspace_id)

    assert _documents(run) == {
        "documents_added": 1,
        "documents_updated": 1,
        "documents_deleted": 1,
        "documents_unchanged": 2,
        "documents_skipped": 0,
    }
    blob_requests = [path for path in github.requests[before:] if "/git/blobs/" in path]
    assert len(blob_requests) == 2


def test_sync_is_recorded_and_audited(app: FastAPI, client: TestClient) -> None:
    workspace_id = _workspace(client)
    _sync(client, workspace_id)
    runs = client.get(f"/api/workspaces/{workspace_id}/sync-runs").json()
    assert [run["status"] for run in runs] == ["succeeded"]
    assert runs[0]["requests"] >= 3
    with app.state.session_factory() as session:
        events = [event.event_type for event in session.scalars(select(AuditEvent))]
    assert "sync.completed" in events


def test_github_errors_mark_the_run_failed(client: TestClient, github: FakeGitHub) -> None:
    workspace_id = _workspace(client)
    github.branch = "develop"
    run = _sync(client, workspace_id)
    assert run["status"] == "failed"
    assert run["error"] == "documents: Branch not found"
    assert client.get(f"/api/workspaces/{workspace_id}/documents").json() == []


def test_sync_without_token_is_rejected() -> None:
    with TestClient(create_app(Settings())) as client:
        workspace_id = _workspace(client)
        response = client.post(f"/api/workspaces/{workspace_id}/sync")
    assert response.status_code == 400
    assert "ICHNOS_GITHUB_TOKEN" in response.json()["detail"]


def test_document_detail_shows_frontmatter_and_findings(client: TestClient) -> None:
    workspace_id = _workspace(client)
    _sync(client, workspace_id)
    url = f"/api/workspaces/{workspace_id}/documents/detail"

    note = client.get(url, params={"path": "docs/note.md"}).json()
    assert note["trust_tier"] == "human_verified"
    assert note["frontmatter"]["meeting_date"] == "2026-09-15"
    assert note["finding_details"] == []
    assert "Text." in note["body"]

    broken = client.get(url, params={"path": "docs/broken.md"}).json()
    assert [f["code"] for f in broken["finding_details"]] == ["frontmatter-missing"]

    assert client.get(url, params={"path": "docs/missing.md"}).status_code == 404
