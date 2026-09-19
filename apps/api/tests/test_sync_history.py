from collections.abc import Iterator
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from fake_github import FakeGitHub, gh_comment, gh_commit, gh_issue
from ichnos.db.models import (
    Commit,
    GitHubComment,
    GitHubItem,
    PullRequestCommit,
    PullRequestFile,
)
from ichnos.main import create_app
from ichnos.settings import Settings


@pytest.fixture
def github(monkeypatch: pytest.MonkeyPatch) -> FakeGitHub:
    monkeypatch.setenv("ICHNOS_GITHUB_TOKEN", "test-token-value")
    fake = FakeGitHub({"docs/index.md": "# Docs\n"})
    fake.issues = [
        gh_issue(1, "Invitation lifecycle", "2026-09-19T10:00:00Z", labels=("type:epic",)),
        gh_issue(2, "Explain invalid links", "2026-09-19T10:05:00Z", body="## Parent\n- Epic: #1"),
        gh_issue(3, "Add glossary", "2026-09-19T10:10:00Z", body="Closes #2", pull=True),
    ]
    fake.pulls[3] = {
        "merged_at": "2026-09-19T10:10:00Z",
        "draft": False,
        "head": {"ref": "docs/glossary", "sha": "c2"},
        "base": {"ref": "main"},
    }
    fake.reviews[3] = [
        {
            "id": 50,
            "user": {"login": "bob"},
            "body": "Looks right",
            "state": "COMMENTED",
            "submitted_at": "2026-09-19T10:08:00Z",
        },
        {"id": 51, "user": {"login": "bob"}, "body": "", "state": "PENDING"},
    ]
    fake.review_comments[3] = [
        {
            "id": 60,
            "user": {"login": "bob"},
            "body": "Typo",
            "path": "docs/project/glossary.md",
            "created_at": "2026-09-19T10:07:00Z",
            "updated_at": "2026-09-19T10:07:00Z",
        }
    ]
    fake.pr_files[3] = [
        {"filename": "docs/project/glossary.md", "status": "added", "additions": 20}
    ]
    fake.pr_commits[3] = [gh_commit("c2", "Add glossary", "2026-09-19T10:09:00Z")]
    fake.comments = [gh_comment(70, 2, "Seen twice this week", "2026-09-19T10:06:00Z")]
    fake.commits = [
        gh_commit("c2", "Add glossary", "2026-09-19T10:09:00Z"),
        gh_commit("c1", "Add docs", "2026-09-19T09:00:00Z"),
    ]
    return fake


@pytest.fixture
def app(github: FakeGitHub) -> FastAPI:
    application = create_app(Settings())
    application.state.github_transport = github.transport
    return application


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


def _sync(client: TestClient, workspace_id: str) -> dict[str, int]:
    run = client.post(f"/api/workspaces/{workspace_id}/sync").json()
    assert run["status"] == "succeeded", run
    counts: dict[str, int] = run["counts"]
    return {
        key: value
        for key, value in counts.items()
        if not key.startswith(("documents_", "links_", "chunks_"))
    }


def _workspace(client: TestClient) -> str:
    body = {"name": "quire", "repository": "octo-org/quire-demo"}
    workspace_id: str = client.post("/api/workspaces", json=body).json()["id"]
    return workspace_id


def test_first_sync_imports_history(app: FastAPI, client: TestClient) -> None:
    workspace_id = _workspace(client)
    assert _sync(client, workspace_id) == {
        "items_added": 3,
        "items_updated": 0,
        "items_unchanged": 0,
        "pull_requests_detailed": 1,
        "comments_added": 1,
        "comments_updated": 0,
        "comments_unchanged": 0,
        "commits_added": 1,
        "commits_unchanged": 1,
    }
    with app.state.session_factory() as session:
        items = {item.number: item for item in session.scalars(select(GitHubItem))}
        kinds = sorted(comment.kind for comment in session.scalars(select(GitHubComment)))
        files = [file.path for file in session.scalars(select(PullRequestFile))]
        pr_commits = [link.sha for link in session.scalars(select(PullRequestCommit))]
        shas = {commit.sha for commit in session.scalars(select(Commit))}
    assert [items[n].item_type for n in (1, 2, 3)] == ["issue", "issue", "pull_request"]
    assert items[1].labels == ["type:epic"]
    assert items[3].merged_at is not None and items[3].head_ref == "docs/glossary"
    assert kinds == ["issue_comment", "review", "review_comment"]  # pending review skipped
    assert files == ["docs/project/glossary.md"]
    assert pr_commits == ["c2"]
    assert shas == {"c1", "c2"}

    listed = client.get(f"/api/workspaces/{workspace_id}/github/items").json()
    assert [(item["number"], item["type"]) for item in listed] == [
        (3, "pull_request"),
        (2, "issue"),
        (1, "issue"),
    ]


def test_second_sync_fetches_no_pull_request_details(
    client: TestClient, github: FakeGitHub
) -> None:
    workspace_id = _workspace(client)
    _sync(client, workspace_id)
    before = len(github.requests)
    counts = _sync(client, workspace_id)
    assert counts["items_added"] == counts["items_updated"] == 0
    assert counts["items_unchanged"] >= 1
    assert counts["comments_added"] == counts["commits_added"] == 0
    assert [path for path in github.requests[before:] if "/pulls/" in path] == []


def test_changed_items_are_updated(app: FastAPI, client: TestClient, github: FakeGitHub) -> None:
    workspace_id = _workspace(client)
    _sync(client, workspace_id)
    changed: dict[str, Any] = dict(github.issues[1])
    changed.update(title="Explain invalid or used links", updated_at="2026-09-19T11:00:00Z")
    github.issues[1] = changed

    counts = _sync(client, workspace_id)

    assert counts["items_updated"] == 1
    assert counts["pull_requests_detailed"] == 0
    with app.state.session_factory() as session:
        story = session.scalar(select(GitHubItem).where(GitHubItem.number == 2))
    assert story is not None and story.title == "Explain invalid or used links"


def test_run_timestamps_are_utc(client: TestClient) -> None:
    workspace_id = _workspace(client)
    run = client.post(f"/api/workspaces/{workspace_id}/sync").json()
    assert run["created_at"].endswith("Z") or run["created_at"].endswith("+00:00")
    assert run["finished_at"].endswith("Z") or run["finished_at"].endswith("+00:00")


def test_sync_extracts_links_and_keeps_them_stable(client: TestClient) -> None:
    workspace_id = _workspace(client)
    _sync(client, workspace_id)
    links = client.get(f"/api/workspaces/{workspace_id}/links").json()
    found = {
        (link["source_key"], link["relation"], link["target_key"], link["origin"]) for link in links
    }
    assert ("2", "parent", "1", "explicit") in found
    assert ("3", "closes", "2", "explicit") in found
    assert ("3", "changes", "docs/project/glossary.md", "explicit") in found

    story = client.get(f"/api/workspaces/{workspace_id}/links?kind=issue&key=2").json()
    assert {link["relation"] for link in story} >= {"parent", "closes"}

    _sync(client, workspace_id)
    assert len(client.get(f"/api/workspaces/{workspace_id}/links").json()) == len(links)
