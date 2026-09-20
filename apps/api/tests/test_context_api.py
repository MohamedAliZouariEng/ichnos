import datetime as dt
from collections.abc import Iterator
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from fake_github_writes import FakeGitRepo
from ichnos.db.models import Document, GitHubItem, Link, RepositoryFile

NOW = dt.datetime(2026, 9, 20, tzinfo=dt.UTC)
BRD = "docs/specs/invitation-expiry/brd.md"
CODE = {
    "src/quire/invitations/service.py": "def accept(token): ...\n",
    "tests/test_invitations.py": "def test_accept(): ...\n",
}


def build(monkeypatch: pytest.MonkeyPatch, repo: FakeGitRepo, *, token: bool = True) -> FastAPI:
    from ichnos.main import create_app
    from ichnos.settings import Settings

    if token:
        monkeypatch.setenv("ICHNOS_GITHUB_TOKEN", "test-token-value")
    else:
        monkeypatch.delenv("ICHNOS_GITHUB_TOKEN", raising=False)
    app = create_app(Settings())
    app.state.github_transport = repo.transport
    return app


def seed(app: FastAPI, client: TestClient, repo: FakeGitRepo) -> str:
    ws: str = client.post(
        "/api/workspaces", json={"name": "quire", "repository": "octo/quire"}
    ).json()["id"]
    head = repo.refs["main"]
    tree = repo.trees[repo.commits[head]["tree"]]
    with app.state.session_factory() as session:
        for number, title, body in (
            (6, "Invitation lifecycle", "Harden invitations."),
            (
                7,
                "Default invitation expiry",
                "As an admin, I want invitation links to expire.\n\n"
                "## Parent\n- Epic: #6\n\n## Source specification\n- " + BRD,
            ),
        ):
            session.add(
                GitHubItem(
                    workspace_id=ws,
                    number=number,
                    item_type="issue",
                    github_id=number,
                    title=title,
                    body=body,
                    state="open",
                    labels=[],
                    url=f"https://github.com/octo/quire/issues/{number}",
                    created_at=NOW,
                    updated_at=NOW,
                )
            )
        session.add(
            Document(
                workspace_id=ws,
                path=BRD,
                blob_sha="b" * 40,
                commit_sha=head,
                kind="concept",
                doc_type="BRD",
                title="Invitation expiry",
                trust_tier="human_verified",
                frontmatter={},
                body="Invitations expire.",
                findings=[],
            )
        )
        for source, target, relation in (
            (("issue", "7"), ("issue", "6"), "parent"),
            (("issue", "7"), ("document", BRD), "references"),
        ):
            session.add(
                Link(
                    workspace_id=ws,
                    source_kind=source[0],
                    source_key=source[1],
                    target_kind=target[0],
                    target_key=target[1],
                    relation=relation,
                    origin="explicit",
                    evidence="test",
                    confidence=1.0,
                    resolved=True,
                )
            )
        for path, text in CODE.items():
            session.add(
                RepositoryFile(
                    workspace_id=ws,
                    path=path,
                    blob_sha=tree[path],
                    commit_sha=head,
                    size=len(text),
                    language="Python",
                )
            )
        session.commit()
    return ws


@pytest.fixture
def repo() -> FakeGitRepo:
    return FakeGitRepo(files=CODE)


@pytest.fixture
def client(
    monkeypatch: pytest.MonkeyPatch, repo: FakeGitRepo
) -> Iterator[tuple[TestClient, FastAPI]]:
    app = build(monkeypatch, repo)
    with TestClient(app) as test_client:
        yield test_client, app


def test_the_pack_fetches_code_at_the_synced_commit(
    client: tuple[TestClient, FastAPI], repo: FakeGitRepo
) -> None:
    test_client, app = client
    ws = seed(app, test_client, repo)
    repo.push("main", {"src/quire/invitations/service.py": "def accept(token, now): ...\n"})

    response = test_client.get(f"/api/workspaces/{ws}/stories/7/context")
    assert response.status_code == 200, response.text
    pack: dict[str, Any] = response.json()
    roles = [(item["id"], item["role"]) for item in pack["items"]]
    assert roles[:3] == [("P1", "story"), ("P2", "epic"), ("P3", "brd")]
    code = {i["title"]: i for i in pack["items"] if i["role"] == "code"}
    # The synced commit, not the newer head: content matches the blob SHA the pack cites.
    assert code["src/quire/invitations/service.py"]["excerpt"] == "def accept(token): ...\n"
    assert len(pack["hash"]) == 64 and "initiative" in pack["absent"]
    assert repo.writes == []


def test_code_false_makes_no_github_request(
    client: tuple[TestClient, FastAPI], repo: FakeGitRepo
) -> None:
    test_client, app = client
    ws = seed(app, test_client, repo)
    calls: list[str] = []

    def recording(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return repo.handle(request)

    app.state.github_transport = httpx.MockTransport(recording)
    pack = test_client.get(
        f"/api/workspaces/{ws}/stories/7/context", params={"code": "false"}
    ).json()
    assert calls == []
    assert all("not fetched" in i["flags"] for i in pack["items"] if i["role"] == "code")


def test_without_a_token_the_pack_says_why(
    monkeypatch: pytest.MonkeyPatch, repo: FakeGitRepo
) -> None:
    app = build(monkeypatch, repo, token=False)
    with TestClient(app) as test_client:
        ws = seed(app, test_client, repo)
        pack = test_client.get(f"/api/workspaces/{ws}/stories/7/context").json()
    assert any("no GitHub token" in note for note in pack["notes"])


def test_unknown_stories_are_404(client: tuple[TestClient, FastAPI], repo: FakeGitRepo) -> None:
    test_client, app = client
    ws = seed(app, test_client, repo)
    assert test_client.get(f"/api/workspaces/{ws}/stories/99/context").status_code == 404
