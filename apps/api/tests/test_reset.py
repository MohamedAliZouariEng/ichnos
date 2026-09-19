from collections.abc import Iterator
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from fake_github import FakeGitHub, gh_comment, gh_commit, gh_issue
from ichnos.db.base import new_id
from ichnos.db.models import AuditEvent, Run

DOCS = {
    "docs/index.md": (
        '---\nokf_version: "0.2"\n---\n# Docs\n\n* [Sync](meetings/sync.md) - Notes.\n'
    ),
    "docs/meetings/sync.md": (
        "---\ntype: Meeting Note\ntitle: Onboarding sync\nstatus: draft\n---\n"
        "# Decisions\n\nInvitations expire after 7 days. See [the index](/index.md).\n"
    ),
}


@pytest.fixture
def app(monkeypatch: pytest.MonkeyPatch) -> FastAPI:
    from ichnos.main import create_app
    from ichnos.settings import Settings

    monkeypatch.setenv("ICHNOS_GITHUB_TOKEN", "test-token-value")
    github = FakeGitHub(dict(DOCS))
    github.issues = [
        gh_issue(1, "Invitation lifecycle", "2026-09-19T10:00:00Z", labels=("type:epic",)),
        gh_issue(
            2, "Expired invitation page", "2026-09-19T10:05:00Z", body="## Parent\n- Epic: #1"
        ),
        gh_issue(3, "Add expiry", "2026-09-19T10:10:00Z", body="Closes #2", pull=True),
    ]
    github.pulls[3] = {
        "merged_at": None,
        "draft": True,
        "head": {"ref": "x"},
        "base": {"ref": "main"},
    }
    github.pr_files[3] = [{"filename": "docs/meetings/sync.md", "status": "modified"}]
    github.comments = [
        gh_comment(70, 2, "Invitation links from May still work.", "2026-09-19T10:06:00Z")
    ]
    github.commits = [gh_commit("c1", "Add docs for invitation expiry", "2026-09-19T09:00:00Z")]
    application = create_app(Settings())
    application.state.github_transport = github.transport
    return application


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


def _get(client: TestClient, workspace_id: str, path: str, **params: str) -> Any:
    return client.get(f"/api/workspaces/{workspace_id}/{path}", params=params).json()


def fingerprint(client: TestClient, workspace_id: str) -> dict[str, list[tuple[Any, ...]]]:
    """Everything the API exposes about the workspace's knowledge."""
    return {
        "documents": sorted(
            (d["path"], d["type"], d["trust_tier"], d["findings"])
            for d in _get(client, workspace_id, "documents")
        ),
        "items": sorted(
            (i["number"], i["type"], i["state"], tuple(i["labels"]))
            for i in _get(client, workspace_id, "github/items")
        ),
        "links": sorted(
            (k["source_kind"], k["source_key"], k["relation"], k["target_key"], k["origin"])
            for k in _get(client, workspace_id, "links")
        ),
        "search": [
            (h["source_kind"], h["source_key"], h["heading"])
            for h in _get(client, workspace_id, "search", q="invitation")
        ],
    }


def _sync(client: TestClient, workspace_id: str) -> dict[str, int]:
    run = client.post(f"/api/workspaces/{workspace_id}/sync").json()
    assert run["status"] == "succeeded", run
    counts: dict[str, int] = run["counts"]
    return counts


def _workspace(client: TestClient) -> str:
    body = {"name": "quire", "repository": "octo-org/quire-demo"}
    workspace_id: str = client.post("/api/workspaces", json=body).json()["id"]
    return workspace_id


def test_reset_then_sync_rebuilds_identical_knowledge(app: FastAPI, client: TestClient) -> None:
    workspace_id = _workspace(client)
    _sync(client, workspace_id)
    before = fingerprint(client, workspace_id)
    assert all(before.values()), before  # every part of the knowledge is non-empty

    response = client.delete(f"/api/workspaces/{workspace_id}/knowledge")
    assert response.status_code == 200
    deleted = response.json()["deleted"]
    assert (
        deleted["documents"] == 2 and deleted["github_items"] == 3 and deleted["sync_cursors"] >= 4
    )
    assert all(not part for part in fingerprint(client, workspace_id).values())

    rebuilt = _sync(client, workspace_id)
    assert rebuilt["documents_added"] == 2 and rebuilt["items_added"] == 3  # started from scratch
    assert fingerprint(client, workspace_id) == before

    again = _sync(client, workspace_id)
    assert again["documents_added"] == again["items_added"] == again["commits_added"] == 0
    assert fingerprint(client, workspace_id) == before

    with app.state.session_factory() as session:
        events = [event.event_type for event in session.scalars(select(AuditEvent))]
        workspace_still_there = client.get(f"/api/workspaces/{workspace_id}").status_code == 200
    assert "knowledge.reset" in events
    assert workspace_still_there


def test_reset_is_refused_while_a_sync_runs(app: FastAPI, client: TestClient) -> None:
    workspace_id = _workspace(client)
    with app.state.session_factory() as session:
        session.add(
            Run(id=new_id(), workspace_id=workspace_id, workflow_type="sync", status="running")
        )
        session.commit()
    assert client.delete(f"/api/workspaces/{workspace_id}/knowledge").status_code == 409


def test_reset_of_unknown_workspace_is_not_found(client: TestClient) -> None:
    assert client.delete("/api/workspaces/unknown/knowledge").status_code == 404
