from collections.abc import Callable, Iterator

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from ichnos.db.models import AuditEvent
from ichnos.main import create_app
from ichnos.settings import Settings

PAYLOAD = {"name": "demo", "repository": "octo-org/demo", "branch": "main"}
Handler = Callable[[httpx.Request], httpx.Response]


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(create_app(Settings())) as test_client:
        yield test_client


def _github_client(handler: Handler) -> TestClient:
    app = create_app(Settings())
    app.state.github_transport = httpx.MockTransport(handler)
    return TestClient(app)


def test_create_and_list_workspace(client: TestClient) -> None:
    response = client.post("/api/workspaces", json=PAYLOAD)
    assert response.status_code == 201
    created = response.json()
    assert created["repository"] == "octo-org/demo"
    assert created["index_paths"] == ["docs/", ".github/"]
    listed = client.get("/api/workspaces").json()
    assert [workspace["id"] for workspace in listed] == [created["id"]]


def test_duplicate_workspace_is_conflict(client: TestClient) -> None:
    assert client.post("/api/workspaces", json=PAYLOAD).status_code == 201
    assert client.post("/api/workspaces", json=PAYLOAD).status_code == 409


@pytest.mark.parametrize(
    "override",
    [
        {"repository": "not a repository"},
        {"index_paths": ["../outside"]},
        {"index_paths": ["/absolute"]},
        {"unexpected": "field"},
    ],
)
def test_invalid_input_is_rejected(client: TestClient, override: dict[str, object]) -> None:
    response = client.post("/api/workspaces", json={**PAYLOAD, **override})
    assert response.status_code == 422


def test_update_workspace(client: TestClient) -> None:
    created = client.post("/api/workspaces", json=PAYLOAD).json()
    response = client.patch(f"/api/workspaces/{created['id']}", json={"branch": "develop"})
    assert response.status_code == 200
    assert response.json()["branch"] == "develop"
    assert response.json()["name"] == "demo"


def test_unknown_workspace_is_not_found(client: TestClient) -> None:
    assert client.get("/api/workspaces/unknown").status_code == 404


def test_workspace_survives_restart() -> None:
    settings = Settings()
    with TestClient(create_app(settings)) as first:
        workspace_id = first.post("/api/workspaces", json=PAYLOAD).json()["id"]
    with TestClient(create_app(settings)) as second:
        assert second.get(f"/api/workspaces/{workspace_id}").status_code == 200


def test_workspace_changes_are_audited() -> None:
    app = create_app(Settings())
    with TestClient(app) as client:
        created = client.post("/api/workspaces", json=PAYLOAD).json()
        client.patch(f"/api/workspaces/{created['id']}", json={"branch": "develop"})
    with app.state.session_factory() as session:
        events = session.scalars(select(AuditEvent).order_by(AuditEvent.id)).all()
    assert [event.event_type for event in events] == ["workspace.created", "workspace.updated"]
    assert all(event.actor == "human:local" for event in events)


def test_config_reports_token_without_exposing_it(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ICHNOS_GITHUB_TOKEN", "test-token-value")
    with TestClient(create_app(Settings())) as client:
        response = client.get("/api/config")
    assert response.json()["github_token_configured"] is True
    assert "test-token-value" not in response.text


def test_github_check_without_token(client: TestClient) -> None:
    created = client.post("/api/workspaces", json=PAYLOAD).json()
    body = client.post(f"/api/workspaces/{created['id']}/github-check").json()
    assert body["token_configured"] is False
    assert body["repository_accessible"] is False


def test_github_check_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ICHNOS_GITHUB_TOKEN", "test-token-value")
    seen_auth: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_auth.append(request.headers["Authorization"])
        if request.url.path == "/repos/octo-org/demo":
            return httpx.Response(200, json={"default_branch": "main", "private": True})
        if request.url.path == "/repos/octo-org/demo/branches/main":
            return httpx.Response(200, json={"name": "main"})
        return httpx.Response(404)

    with _github_client(handler) as client:
        created = client.post("/api/workspaces", json=PAYLOAD).json()
        response = client.post(f"/api/workspaces/{created['id']}/github-check")
    body = response.json()
    assert body["repository_accessible"] is True
    assert body["branch_exists"] is True
    assert body["private"] is True
    assert "test-token-value" not in response.text
    assert seen_auth == ["Bearer test-token-value"] * 2


def test_github_check_missing_branch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ICHNOS_GITHUB_TOKEN", "test-token-value")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/repos/octo-org/demo":
            return httpx.Response(200, json={"default_branch": "main", "private": False})
        return httpx.Response(404)

    with _github_client(handler) as client:
        created = client.post("/api/workspaces", json=PAYLOAD).json()
        body = client.post(f"/api/workspaces/{created['id']}/github-check").json()
    assert body["repository_accessible"] is True
    assert body["branch_exists"] is False


def test_github_check_repository_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ICHNOS_GITHUB_TOKEN", "test-token-value")
    with _github_client(lambda request: httpx.Response(404)) as client:
        created = client.post("/api/workspaces", json=PAYLOAD).json()
        body = client.post(f"/api/workspaces/{created['id']}/github-check").json()
    assert body["repository_accessible"] is False
    assert "not found" in body["message"]


def test_github_check_unreachable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ICHNOS_GITHUB_TOKEN", "test-token-value")

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("network down", request=request)

    with _github_client(handler) as client:
        created = client.post("/api/workspaces", json=PAYLOAD).json()
        body = client.post(f"/api/workspaces/{created['id']}/github-check").json()
    assert body["repository_accessible"] is False
    assert "Could not reach GitHub" in body["message"]
