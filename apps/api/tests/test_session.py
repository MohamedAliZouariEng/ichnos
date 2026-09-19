from collections.abc import Iterator

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from ichnos.api.session import ApproverDep
from ichnos.auth.session import SessionStore
from ichnos.db.models import AuditEvent
from ichnos.main import create_app
from ichnos.settings import Settings

PASSPHRASE = "correct horse battery staple"


def github(login: str = "octo", status: int = 200) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/user"
        return httpx.Response(status, json={"login": login} if status == 200 else {})

    return httpx.MockTransport(handler)


def build(monkeypatch: pytest.MonkeyPatch, *, password: str | None = PASSPHRASE) -> FastAPI:
    monkeypatch.setenv("ICHNOS_GITHUB_TOKEN", "test-token-value")
    if password:
        monkeypatch.setenv("ICHNOS_APPROVER_PASSWORD", password)
    app = create_app(Settings())
    app.state.github_transport = github()

    @app.get("/test/approve")
    def approve(approver: ApproverDep) -> dict[str, str]:
        return {"approver": approver.identity}

    return app


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    with TestClient(build(monkeypatch)) as test_client:
        yield test_client


def test_approvals_are_disabled_without_a_passphrase(monkeypatch: pytest.MonkeyPatch) -> None:
    with TestClient(build(monkeypatch, password=None)) as client:
        assert client.get("/api/session").json()["approvals_enabled"] is False
        response = client.post("/api/session", json={"password": "anything"})
    assert response.status_code == 403
    assert "ICHNOS_APPROVER_PASSWORD" in response.json()["detail"]


def test_signing_in_identifies_the_token_owner_and_sets_a_strict_cookie(
    client: TestClient,
) -> None:
    response = client.post("/api/session", json={"password": PASSPHRASE})
    assert response.status_code == 200
    assert response.json()["approver"] == "human:octo"
    cookie = response.headers["set-cookie"].lower()
    assert cookie.startswith("ichnos_session=")
    assert "httponly" in cookie and "samesite=strict" in cookie and "path=/" in cookie
    assert PASSPHRASE not in response.text

    state = client.get("/api/session").json()
    assert state["signed_in"] is True and state["expires_at"]
    assert client.get("/test/approve").json() == {"approver": "human:octo"}


def test_approval_needs_a_session(client: TestClient) -> None:
    response = client.get("/test/approve")
    assert response.status_code == 401
    assert response.json()["detail"] == "Sign in to approve."


def test_wrong_passphrases_fail_then_lock(client: TestClient) -> None:
    for _ in range(5):
        assert client.post("/api/session", json={"password": "nope"}).status_code == 401
    locked = client.post("/api/session", json={"password": PASSPHRASE})
    assert locked.status_code == 429


def test_signing_out_ends_the_session_and_everything_is_audited(client: TestClient) -> None:
    client.post("/api/session", json={"password": "nope"})
    client.post("/api/session", json={"password": PASSPHRASE})
    signed_out = client.delete("/api/session")
    assert signed_out.json()["signed_in"] is False
    assert client.get("/test/approve").status_code == 401

    app = client.app
    assert isinstance(app, FastAPI)
    with app.state.session_factory() as session:
        events = session.scalars(
            select(AuditEvent).where(AuditEvent.event_type.startswith("session."))
        ).all()
    assert [(e.event_type, e.actor) for e in events] == [
        ("session.failed", "unknown"),
        ("session.signed_in", "human:octo"),
        ("session.signed_out", "human:octo"),
    ]
    assert all(PASSPHRASE not in str(e.details) for e in events)


def test_an_unidentifiable_token_owner_blocks_sign_in(monkeypatch: pytest.MonkeyPatch) -> None:
    app = build(monkeypatch)
    app.state.github_transport = github(status=401)
    with TestClient(app) as client:
        response = client.post("/api/session", json={"password": PASSPHRASE})
    assert response.status_code == 502
    assert "HTTP 401" in response.json()["detail"]


def test_idle_sessions_expire() -> None:
    store = SessionStore(PASSPHRASE, idle_hours=0)
    session = store.open("octo")
    assert store.get(session.token) is None
    assert SessionStore(None).enabled is False
