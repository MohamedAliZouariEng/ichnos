import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from ichnos.main import create_app
from ichnos.settings import Settings

REPO_ROOT = Path(__file__).resolve().parents[3]
MEETING = REPO_ROOT / "examples/demo-repository/docs/meetings/2026-09-15-workspace-onboarding.md"


@pytest.fixture
def app(monkeypatch: pytest.MonkeyPatch) -> FastAPI:
    monkeypatch.setenv("ICHNOS_LLM_PROVIDER", "fake")
    return create_app(Settings())


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


def _workspace(client: TestClient, name: str = "quire") -> str:
    body = {"name": name, "repository": f"octo-org/{name}"}
    value: str = client.post("/api/workspaces", json=body).json()["id"]
    return value


def _source(client: TestClient, workspace_id: str) -> str:
    body = {"content": MEETING.read_text(encoding="utf-8")}
    value: str = client.post(f"/api/workspaces/{workspace_id}/sources", json=body).json()["id"]
    return value


def _finished_run(app: FastAPI, client: TestClient) -> tuple[str, dict[str, Any]]:
    workspace_id = _workspace(client)
    body = {"workflow": "requirements", "source_ids": [_source(client, workspace_id)]}
    response = client.post(f"/api/workspaces/{workspace_id}/runs", json=body)
    assert response.status_code == 202
    run_id: str = response.json()["id"]
    app.state.runner.wait(run_id, timeout=60)
    return workspace_id, client.get(f"/api/runs/{run_id}").json()


def _sse(client: TestClient, url: str, **headers: str) -> list[dict[str, Any]]:
    with client.stream("GET", url, headers=headers) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        body = "".join(response.iter_text())
    events = []
    for block in body.strip().split("\n\n"):
        fields = dict(line.split(": ", 1) for line in block.splitlines() if ": " in line)
        if "data" in fields:
            event = json.loads(fields["data"])
            assert int(fields["id"]) == event["id"]
            events.append(event)
    return events


def test_a_run_produces_a_brd_and_is_listed(app: FastAPI, client: TestClient) -> None:
    workspace_id, run = _finished_run(app, client)

    assert run["status"] == "succeeded", run["error"]
    assert run["artifact_id"]
    completed = [e["stage"] for e in run["events"] if e["kind"] == "stage.completed"]
    assert completed == ["retrieval", "requirements", "specification"]
    listed = client.get(f"/api/workspaces/{workspace_id}/runs").json()
    assert [item["id"] for item in listed] == [run["id"]]
    assert client.get(f"/api/workspaces/{workspace_id}/runs?workflow=sync").json() == []


def test_events_stream_and_resume_after_last_event_id(app: FastAPI, client: TestClient) -> None:
    _, run = _finished_run(app, client)
    url = f"/api/runs/{run['id']}/events"

    events = _sse(client, url)
    assert [e["id"] for e in events] == [e["id"] for e in run["events"]]
    assert events[-1]["kind"] == "run.completed"

    middle = events[3]["id"]
    resumed = _sse(client, url, **{"Last-Event-ID": str(middle)})
    assert resumed[0]["id"] > middle
    assert resumed[-1]["kind"] == "run.completed"


def test_starting_a_run_validates_its_sources(client: TestClient) -> None:
    workspace_id = _workspace(client)
    other_source = _source(client, _workspace(client, "other"))
    for source_ids in (["missing"], [other_source]):
        body = {"workflow": "requirements", "source_ids": source_ids}
        response = client.post(f"/api/workspaces/{workspace_id}/runs", json=body)
        assert response.status_code == 400
    empty = client.post(f"/api/workspaces/{workspace_id}/runs", json={"source_ids": []})
    assert empty.status_code == 422


def test_starting_a_run_needs_a_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ICHNOS_LLM_PROVIDER", raising=False)
    with TestClient(create_app(Settings())) as client:
        workspace_id = _workspace(client)
        body = {"source_ids": [_source(client, workspace_id)]}
        response = client.post(f"/api/workspaces/{workspace_id}/runs", json=body)
    assert response.status_code == 400
    assert "ICHNOS_LLM_PROVIDER" in response.json()["detail"]


def test_unknown_runs_are_not_found(client: TestClient) -> None:
    assert client.get("/api/runs/missing").status_code == 404
    assert client.get("/api/runs/missing/events").status_code == 404
