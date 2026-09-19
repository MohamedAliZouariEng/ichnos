from collections.abc import Iterator
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from fake_github_writes import FakeGitRepo
from ichnos.approvals.service import propose
from ichnos.db.models import Approval, Artifact, AuditEvent, Run, Workspace
from ichnos.main import create_app
from ichnos.settings import Settings

PASSPHRASE = "correct horse battery staple"
INDEX = "docs/specs/index.md"
BRD = "docs/specs/invitation-expiry/brd.md"


def transport(repo: FakeGitRepo, login: str = "octo") -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/user":
            return httpx.Response(200, json={"login": login})
        return repo.handle(request)

    return httpx.MockTransport(handler)


@pytest.fixture
def repo() -> FakeGitRepo:
    return FakeGitRepo(files={INDEX: "# Specifications\n", "docs/index.md": "# Docs\n"})


@pytest.fixture
def app(monkeypatch: pytest.MonkeyPatch, repo: FakeGitRepo) -> FastAPI:
    monkeypatch.setenv("ICHNOS_GITHUB_TOKEN", "test-token-value")
    monkeypatch.setenv("ICHNOS_APPROVER_PASSWORD", PASSPHRASE)
    application = create_app(Settings())
    application.state.github_transport = transport(repo)
    return application


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


def blob(repo: FakeGitRepo, path: str) -> str:
    return repo.trees[repo.commits[repo.refs["main"]]["tree"]][path]


def proposal(
    app: FastAPI,
    repo: FakeGitRepo,
    *,
    approver: str = "human:octo",
    artifact_version: int | None = None,
) -> str:
    payload = {
        "kind": "docs_pull_request",
        "approver": approver,
        "repository": "octo/quire",
        "base_branch": "main",
        "branch": "ichnos/invitation-expiry-1",
        "commit_message": "docs: publish the invitation expiry BRD",
        "title": "Publish BRD: Invitation expiry",
        "body": "Approved in Ichnos.",
        "files": [
            {"path": BRD, "content": "---\ntype: BRD\nstatus: stable\n---\n# Summary\n"},
            {"path": INDEX, "content": "# Specifications\n\n* [X](invitation-expiry/) - X\n"},
        ],
    }
    with app.state.session_factory() as session:
        workspace = Workspace(name="quire", repo_owner="octo", repo_name="quire")
        session.add(workspace)
        session.flush()
        run = Run(workspace_id=workspace.id, workflow_type="publish")
        session.add(run)
        session.flush()
        base: dict[str, Any] = {
            "head_sha": repo.refs["main"],
            "files": {BRD: None, INDEX: blob(repo, INDEX)},
        }
        if artifact_version is not None:
            artifact = Artifact(
                workspace_id=workspace.id,
                kind="brd",
                title="X",
                slug="x",
                current_version=artifact_version,
            )
            session.add(artifact)
            session.flush()
            base |= {"artifact_id": artifact.id, "artifact_version": artifact_version}
        approval = propose(
            session,
            run_id=run.id,
            workspace_id=workspace.id,
            action_type="docs_pull_request",
            target="octo/quire",
            branch="main",
            payload=payload,
            base=base,
            summary="Publish BRD: Invitation expiry",
            proposed_by=approver,
        )
        return approval.id


def sign_in(client: TestClient) -> None:
    assert client.post("/api/session", json={"password": PASSPHRASE}).status_code == 200


def approve(client: TestClient, approval_id: str, shown: str | None = None) -> Any:
    detail = client.get(f"/api/approvals/{approval_id}").json()
    return client.post(
        f"/api/approvals/{approval_id}/approve",
        json={"payload_hash": shown or detail["payload_hash"]},
    )


def test_a_proposal_writes_nothing(app: FastAPI, client: TestClient, repo: FakeGitRepo) -> None:
    approval_id = proposal(app, repo)
    detail = client.get(f"/api/approvals/{approval_id}").json()
    assert (detail["status"], detail["hash_ok"]) == ("pending", True)
    assert repo.writes == []


def test_approving_needs_a_session_and_the_reviewed_hash(
    app: FastAPI, client: TestClient, repo: FakeGitRepo
) -> None:
    approval_id = proposal(app, repo)
    assert approve(client, approval_id).status_code == 401
    sign_in(client)
    changed = approve(client, approval_id, shown="f" * 64)
    assert changed.status_code == 409 and "reload it" in changed.json()["detail"]
    assert repo.writes == []


def test_an_action_prepared_for_someone_else_cannot_be_approved(
    app: FastAPI, client: TestClient, repo: FakeGitRepo
) -> None:
    approval_id = proposal(app, repo, approver="human:alice")
    sign_in(client)
    response = approve(client, approval_id)
    assert response.status_code == 409 and "human:alice" in response.json()["detail"]
    assert repo.writes == []


def test_approval_executes_exactly_the_payload_once(
    app: FastAPI, client: TestClient, repo: FakeGitRepo
) -> None:
    approval_id = proposal(app, repo)
    main_before = repo.refs["main"]
    sign_in(client)
    detail = approve(client, approval_id).json()

    assert detail["status"] == "executed", detail["error"]
    assert detail["decided_by"] == "human:octo"
    assert detail["result"]["pull_request"]["url"] == "https://github.com/octo/quire/pull/1"
    files = repo.files_at("ichnos/invitation-expiry-1")
    assert files[BRD].startswith("---\ntype: BRD\nstatus: stable\n")
    assert repo.refs["main"] == main_before
    assert repo.pulls[0]["head"] == "ichnos/invitation-expiry-1"

    writes = len(repo.writes)
    again = approve(client, approval_id)
    assert again.status_code == 409 and "already executed" in again.json()["detail"]
    assert len(repo.writes) == writes

    with app.state.session_factory() as session:
        events = [
            e.event_type
            for e in session.scalars(
                select(AuditEvent).where(AuditEvent.approval_id == approval_id)
            )
        ]
    assert events == ["approval.proposed", "approval.approved", "approval.executed"]


def test_rejected_actions_never_write(app: FastAPI, client: TestClient, repo: FakeGitRepo) -> None:
    approval_id = proposal(app, repo)
    sign_in(client)
    rejected = client.post(f"/api/approvals/{approval_id}/reject", json={"note": "Not yet"}).json()
    assert (rejected["status"], rejected["decision_note"]) == ("rejected", "Not yet")
    assert approve(client, approval_id).status_code == 409
    assert repo.writes == []


def test_a_touched_file_changing_on_github_makes_the_action_stale(
    app: FastAPI, client: TestClient, repo: FakeGitRepo
) -> None:
    approval_id = proposal(app, repo)
    repo.push("main", {INDEX: "# Specifications\n\n* [Other](other/) - Someone else\n"})
    sign_in(client)
    detail = approve(client, approval_id).json()
    assert detail["status"] == "stale"
    assert INDEX in detail["error"]
    assert repo.writes == [] and repo.pulls == []


def test_unrelated_commits_do_not_block_the_action(
    app: FastAPI, client: TestClient, repo: FakeGitRepo
) -> None:
    approval_id = proposal(app, repo)
    repo.push("main", {"docs/index.md": "# Docs, reworded\n"})
    sign_in(client)
    assert approve(client, approval_id).json()["status"] == "executed"
    assert repo.files_at("ichnos/invitation-expiry-1")["docs/index.md"] == "# Docs, reworded\n"


def test_an_edited_artifact_makes_the_action_stale(
    app: FastAPI, client: TestClient, repo: FakeGitRepo
) -> None:
    approval_id = proposal(app, repo, artifact_version=2)
    with app.state.session_factory() as session:
        approval = session.get(Approval, approval_id)
        assert approval is not None
        artifact = session.get(Artifact, approval.base["artifact_id"])
        assert artifact is not None
        artifact.current_version = 3
        session.commit()
    sign_in(client)
    detail = approve(client, approval_id).json()
    assert detail["status"] == "stale" and "artifact changed" in detail["error"]
    assert repo.writes == []


def test_a_tampered_payload_fails_without_writing(
    app: FastAPI, client: TestClient, repo: FakeGitRepo
) -> None:
    approval_id = proposal(app, repo)
    with app.state.session_factory() as session:
        approval = session.get(Approval, approval_id)
        assert approval is not None
        approval.payload = {**approval.payload, "branch": "main"}  # the hash no longer matches
        session.commit()
    sign_in(client)
    detail = approve(client, approval_id).json()
    assert detail["status"] == "failed" and "no longer matches its hash" in detail["error"]
    assert repo.writes == []
