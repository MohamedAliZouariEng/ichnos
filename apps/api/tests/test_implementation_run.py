from collections.abc import Iterator
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from fake_github_writes import FakeGitRepo
from test_context_api import CODE, seed

PASSPHRASE = "correct horse battery staple"


@pytest.fixture
def repo() -> FakeGitRepo:
    return FakeGitRepo(files=CODE)


@pytest.fixture
def app(monkeypatch: pytest.MonkeyPatch, repo: FakeGitRepo) -> FastAPI:
    from ichnos.main import create_app
    from ichnos.settings import Settings

    monkeypatch.setenv("ICHNOS_LLM_PROVIDER", "fake")
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


def run_plan(app: FastAPI, client: TestClient, ws: str, number: int) -> dict[str, Any]:
    started = client.post(f"/api/workspaces/{ws}/stories/{number}/plan")
    assert started.status_code == 202, started.text
    app.state.runner.wait(started.json()["id"], timeout=60)
    run: dict[str, Any] = client.get(f"/api/runs/{started.json()['id']}").json()
    return run


def test_a_story_is_planned_and_its_plan_can_open_a_draft_pull_request(
    app: FastAPI, client: TestClient, repo: FakeGitRepo
) -> None:
    ws = seed(app, client, repo)
    run = run_plan(app, client, ws, 7)
    assert run["status"] == "succeeded", run["error"]
    stages = [e["stage"] for e in run["events"] if e["kind"] == "stage.completed"]
    assert stages == ["context", "plan", "store"]
    result = run["outputs"]["result"]

    pack = client.get(f"/api/workspaces/{ws}/stories/7/context").json()
    assert result["pack_hash"] == pack["hash"]  # the plan rests on today's pack
    plan = client.get(f"/api/artifacts/{result['artifact_id']}").json()
    assert plan["kind"] == "implementation-plan" and plan["status"] == "draft"
    assert plan["current"]["findings"] == 0
    assert repo.writes == []  # planning writes nothing

    assert client.post("/api/session", json={"password": PASSPHRASE}).status_code == 200
    proposed = client.post(f"/api/artifacts/{result['artifact_id']}/draft-pull-request")
    assert proposed.status_code == 201, proposed.text
    assert proposed.json()["status"] == "pending" and repo.writes == []


def test_unknown_stories_are_refused_before_a_run_starts(
    app: FastAPI, client: TestClient, repo: FakeGitRepo
) -> None:
    ws = seed(app, client, repo)
    assert client.post(f"/api/workspaces/{ws}/stories/99/plan").status_code == 404
