from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from fake_github_writes import FakeGitRepo
from ichnos.db.models import Approval, Artifact, ArtifactVersion, RunEvent, Workspace
from test_planning import BRD

PASSPHRASE = "correct horse battery staple"
BRD_PATH = "docs/specs/invitation-expiry/brd.md"
DEMO = Path(__file__).resolve().parents[3] / "examples/demo-repository/docs"


def files(*, merged: bool) -> dict[str, str]:
    found = {f"docs/{p.relative_to(DEMO).as_posix()}": p.read_text() for p in DEMO.rglob("*.md")}
    if merged:
        found[BRD_PATH] = BRD
    return found


def build(monkeypatch: pytest.MonkeyPatch, repo: FakeGitRepo) -> FastAPI:
    from ichnos.main import create_app
    from ichnos.settings import Settings

    monkeypatch.setenv("ICHNOS_LLM_PROVIDER", "fake")
    monkeypatch.setenv("ICHNOS_GITHUB_TOKEN", "test-token-value")
    monkeypatch.setenv("ICHNOS_APPROVER_PASSWORD", PASSPHRASE)
    app = create_app(Settings())

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/user":
            return httpx.Response(200, json={"login": "octo"})
        return repo.handle(request)

    app.state.github_transport = httpx.MockTransport(handler)
    return app


def approved_brd(app: FastAPI, status: str = "approved") -> str:
    with app.state.session_factory() as session:
        workspace = Workspace(name="quire", repo_owner="octo", repo_name="quire")
        session.add(workspace)
        session.flush()
        artifact = Artifact(
            workspace_id=workspace.id,
            kind="brd",
            title="Invitation expiry",
            slug="invitation-expiry",
            status=status,
            current_version=1,
        )
        session.add(artifact)
        session.flush()
        session.add(
            ArtifactVersion(
                artifact_id=artifact.id,
                number=1,
                content=BRD,
                origin="edited",
                actor="human:octo",
            )
        )
        session.commit()
        return artifact.id


def sign_in(client: TestClient) -> None:
    assert client.post("/api/session", json={"password": PASSPHRASE}).status_code == 200


def plan(app: FastAPI, client: TestClient, artifact_id: str) -> dict[str, Any]:
    sign_in(client)
    response = client.post(f"/api/artifacts/{artifact_id}/plan")
    assert response.status_code == 202, response.text
    app.state.runner.wait(response.json()["id"], timeout=60)
    run: dict[str, Any] = client.get(f"/api/runs/{response.json()['id']}").json()
    return run


def issues_approval(app: FastAPI, run_id: str) -> Approval:
    with app.state.session_factory() as session:
        approval: Approval | None = session.scalar(
            select(Approval).where(
                Approval.run_id == run_id, Approval.action_type == "create_issues"
            )
        )
        assert approval is not None
        session.expunge(approval)
        return approval


def decide(app: FastAPI, client: TestClient, approval: Approval, action: str) -> dict[str, Any]:
    body = {"payload_hash": approval.payload_hash} if action == "approve" else {"note": "No"}
    decided: dict[str, Any] = client.post(
        f"/api/approvals/{approval.id}/{action}", json=body
    ).json()
    app.state.runner.wait(approval.run_id, timeout=60)
    return decided


def test_a_planning_run_waits_for_its_issues_to_be_approved(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = FakeGitRepo(files=files(merged=True))
    app = build(monkeypatch, repo)
    with TestClient(app) as client:
        run = plan(app, client, approved_brd(app))
        assert run["status"] == "waiting"
        assert run["events"][-1]["kind"] == "run.waiting"
        assert repo.writes == []

        approval = issues_approval(app, run["id"])
        assert decide(app, client, approval, "approve")["status"] == "executed"
        finished = client.get(f"/api/runs/{run['id']}").json()

    assert finished["status"] == "succeeded", finished["error"]
    kinds = [event["kind"] for event in finished["events"]]
    assert kinds.count("stage.started") == 4  # planning and proposal never ran twice
    assert "run.resumed" in kinds
    result = finished["outputs"]["result"]
    assert result["issues"]["epic"]["number"] == 1
    assert len(result["issues"]["stories"]) == 4
    assert len(repo.issues) == 5

    with app.state.session_factory() as session:
        follow_up = session.get(Approval, result["follow_up_approval_id"])
        assert follow_up is not None and follow_up.status == "pending"
        brd = follow_up.payload["files"][0]["content"]
    assert "resource: https://github.com/octo/quire/issues/1" in brd
    assert "number: 1" in brd and "S-4" in brd
    assert not any(route.startswith("/git/") for _, route in repo.writes)  # not approved yet


def test_rejecting_the_plan_finishes_the_run_without_issues(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = FakeGitRepo(files=files(merged=True))
    app = build(monkeypatch, repo)
    with TestClient(app) as client:
        run = plan(app, client, approved_brd(app))
        decide(app, client, issues_approval(app, run["id"]), "reject")
        finished = client.get(f"/api/runs/{run['id']}").json()
    assert finished["status"] == "succeeded"
    assert finished["outputs"]["result"]["decision"] == "rejected"
    assert repo.writes == []


def test_a_waiting_run_survives_a_restart(monkeypatch: pytest.MonkeyPatch) -> None:
    repo = FakeGitRepo(files=files(merged=False))
    first = build(monkeypatch, repo)
    with TestClient(first) as client:
        run = plan(first, client, approved_brd(first))
    assert run["status"] == "waiting"

    second = build(monkeypatch, repo)  # a new process state; same database and checkpoints
    with TestClient(second) as client:
        assert client.get(f"/api/runs/{run['id']}").json()["status"] == "waiting"
        sign_in(client)
        decide(second, client, issues_approval(second, run["id"]), "approve")
        finished = client.get(f"/api/runs/{run['id']}").json()
    assert finished["status"] == "succeeded", finished["error"]
    assert len(repo.issues) == 5
    assert finished["outputs"]["result"]["follow_up_approval_id"] is None  # BRD not merged yet
    with second.state.session_factory() as session:
        notes = [
            e.message for e in session.scalars(select(RunEvent).where(RunEvent.run_id == run["id"]))
        ]
    assert any("merge its pull request" in note for note in notes)


def test_only_approved_brds_are_planned(monkeypatch: pytest.MonkeyPatch) -> None:
    app = build(monkeypatch, FakeGitRepo())
    with TestClient(app) as client:
        sign_in(client)
        response = client.post(f"/api/artifacts/{approved_brd(app, status='draft')}/plan")
    assert response.status_code == 409
