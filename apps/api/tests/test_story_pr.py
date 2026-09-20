from collections.abc import Iterator
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from fake_github_writes import FakeGitRepo
from ichnos.approvals.story_pr import ClaimError, build_draft_pr
from ichnos.context.pack import build_pack
from ichnos.db.models import Document, Workspace
from ichnos.honesty import claims
from ichnos.llm import FakeProvider
from ichnos.workflows.implementation import draft_implementation, render_plan, store_plan
from test_context_api import BRD, CODE, seed

PASSPHRASE = "correct horse battery staple"


@pytest.fixture
def repo() -> FakeGitRepo:
    return FakeGitRepo(files=CODE)


@pytest.fixture
def app(monkeypatch: pytest.MonkeyPatch, repo: FakeGitRepo) -> FastAPI:
    from ichnos.main import create_app
    from ichnos.settings import Settings

    monkeypatch.setenv("ICHNOS_GITHUB_TOKEN", "test-token-value")
    monkeypatch.setenv("ICHNOS_APPROVER_PASSWORD", PASSPHRASE)
    application = create_app(Settings())

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/user":
            return httpx.Response(200, json={"login": "octo"})
        return repo.handle(request)

    application.state.github_transport = httpx.MockTransport(handler)
    return application


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


def planned(app: FastAPI, client: TestClient, repo: FakeGitRepo) -> str:
    """Seed Story #7, build its pack with code, draft and store a plan; return the plan's id."""
    ws = seed(app, client, repo)
    blobs = {sha: repo.blobs[sha] for sha in repo.blobs}
    with app.state.session_factory() as session:
        workspace = session.get(Workspace, ws)
        assert workspace is not None
        pack = build_pack(session, workspace, 7, fetch=blobs.__getitem__).as_dict()
        plan, _, _ = draft_implementation(FakeProvider(), pack)
        artifact = store_plan(
            session, workspace_id=ws, plan=plan, markdown=render_plan(plan), actor="ichnos/fake"
        )
        session.commit()
        return artifact.id


def test_approving_opens_a_draft_pull_request_that_changes_nothing(
    app: FastAPI, client: TestClient, repo: FakeGitRepo
) -> None:
    plan_id = planned(app, client, repo)
    assert client.post("/api/session", json={"password": PASSPHRASE}).status_code == 200
    proposed = client.post(f"/api/artifacts/{plan_id}/draft-pull-request")
    assert proposed.status_code == 201, proposed.text
    approval: dict[str, Any] = proposed.json()
    body = approval["payload"]["body"]
    assert body.startswith("Closes #7\n")
    assert "| Not started | None yet |" in body and "## AI assistance" in body
    assert claims(body) == [] and repo.writes == []

    main_files = repo.files_at("main")
    done = client.post(
        f"/api/approvals/{approval['id']}/approve", json={"payload_hash": approval["payload_hash"]}
    ).json()
    assert done["status"] == "executed", done["error"]
    branch = approval["payload"]["branch"]
    assert branch == "ichnos/story-7-default-invitation-expiry"
    assert repo.files_at(branch) == main_files  # 0 files changed
    assert repo.pulls[0]["draft"] is True and repo.pulls[0]["head"] == branch
    assert [route for _, route in repo.writes] == ["/git/commits", "/git/refs", "/pulls"]
    assert done["result"]["draft"] is True


def test_a_changed_context_refuses_the_old_plan(
    app: FastAPI, client: TestClient, repo: FakeGitRepo
) -> None:
    plan_id = planned(app, client, repo)
    with app.state.session_factory() as session:
        brd = session.query(Document).filter_by(path=BRD).one()
        brd.body = "Invitations expire after 14 days."
        session.commit()
    assert client.post("/api/session", json={"password": PASSPHRASE}).status_code == 200
    refused = client.post(f"/api/artifacts/{plan_id}/draft-pull-request")
    assert refused.status_code == 409 and "context changed" in refused.json()["detail"]
    assert repo.writes == []


def test_an_existing_branch_makes_the_action_stale(
    app: FastAPI, client: TestClient, repo: FakeGitRepo
) -> None:
    plan_id = planned(app, client, repo)
    assert client.post("/api/session", json={"password": PASSPHRASE}).status_code == 200
    approval = client.post(f"/api/artifacts/{plan_id}/draft-pull-request").json()
    repo.refs[approval["payload"]["branch"]] = repo.refs["main"]
    done = client.post(
        f"/api/approvals/{approval['id']}/approve", json={"payload_hash": approval["payload_hash"]}
    ).json()
    assert done["status"] == "stale" and "already exists" in done["error"]
    assert repo.pulls == []


def test_claims_are_refused_before_anything_is_proposed() -> None:
    pack = {"hash": "a" * 64, "absent": [], "items": []}
    arguments: dict[str, Any] = {
        "story_number": 7,
        "story_body": "- [ ] AC-01: Given x, then y.",
        "plan_markdown": "",
        "plan_version": 1,
        "plan_path": "ichnos/plans/p.md",
        "pack": pack,
        "approver": "human:octo",
        "repository": "octo/quire",
        "base_branch": "main",
        "branch": "ichnos/p",
        "model": "fake",
    }
    payload, _ = build_draft_pr(story_title="Default invitation expiry", **arguments)
    assert "| AC-01: Given x, then y. | Not started | None yet |" in payload["body"]
    with pytest.raises(ClaimError, match="is done"):
        build_draft_pr(story_title="Invitation expiry is done", **arguments)


def test_a_plan_with_check_errors_opens_nothing(
    app: FastAPI, client: TestClient, repo: FakeGitRepo
) -> None:
    from ichnos.db.models import ArtifactVersion

    plan_id = planned(app, client, repo)
    with app.state.session_factory() as session:
        version = session.query(ArtifactVersion).filter_by(artifact_id=plan_id).one()
        version.content += "\nThe expiry check is implemented.\n"
        session.commit()
    assert client.post("/api/session", json={"password": PASSPHRASE}).status_code == 200
    refused = client.post(f"/api/artifacts/{plan_id}/draft-pull-request")
    assert refused.status_code == 409 and "plan's checks" in refused.json()["detail"]
    assert repo.writes == []
