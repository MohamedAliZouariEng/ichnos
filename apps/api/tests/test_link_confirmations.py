from collections.abc import Iterator

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

import test_trace
from ichnos.db.models import AuditEvent, LinkConfirmation, Workspace
from ichnos.sync.reset import reset_knowledge
from ichnos.trace.confirm import confirmed_links
from ichnos.trace.validate import validate_trace

factory = test_trace.factory  # the Step 3 fixture, shared by name
PASSPHRASE = "correct horse battery staple"
LINK = "pull_request:20->file:tests/test_invitations.py"
URL = "/api/workspaces/ws/trace/confirmations"


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch, factory: sessionmaker[Session]) -> Iterator[TestClient]:
    from ichnos.main import create_app
    from ichnos.settings import Settings

    monkeypatch.setenv("ICHNOS_GITHUB_TOKEN", "test-token-value")
    monkeypatch.setenv("ICHNOS_APPROVER_PASSWORD", PASSPHRASE)
    app: FastAPI = create_app(Settings())
    app.state.github_transport = httpx.MockTransport(
        lambda request: httpx.Response(200, json={"login": "octo"})
    )
    with TestClient(app) as test_client:
        yield test_client


def body(link: str = LINK) -> dict[str, str]:
    return {"brd": test_trace.BRD, "link": link, "note": "Checked the diff: it tests resending."}


def test_confirming_needs_a_session_and_a_real_inferred_link(client: TestClient) -> None:
    assert client.post(URL, json=body()).status_code == 401
    assert client.post("/api/session", json={"password": PASSPHRASE}).status_code == 200
    unknown = client.post(URL, json=body("pull_request:20->file:README.md"))
    assert unknown.status_code == 404 and "No inferred link" in unknown.json()["detail"]


def test_a_confirmation_clears_the_warning_survives_a_reset_and_is_audited(
    client: TestClient, factory: sessionmaker[Session]
) -> None:
    assert client.post("/api/session", json={"password": PASSPHRASE}).status_code == 200
    created = client.post(URL, json=body())
    assert created.status_code == 201, created.text
    assert created.json()["confirmed_by"] == "human:octo"
    assert client.post(URL, json=body()).status_code == 409

    with factory() as session:
        confirmed = confirmed_links(session, "ws")
        assert confirmed == {LINK}
        found = validate_trace(test_trace.trace(factory), confirmed=confirmed)
        assert [f.code for f in found] == ["criterion-without-test"]  # the guess is now confirmed
        reset_knowledge(session, "ws")
        session.commit()
        assert session.scalar(select(LinkConfirmation.link)) == LINK  # kept across a reset
        events = [e.event_type for e in session.scalars(select(AuditEvent))]
    assert "link.confirmed" in events


def test_a_confirmation_can_be_withdrawn(
    client: TestClient, factory: sessionmaker[Session]
) -> None:
    assert client.post("/api/session", json={"password": PASSPHRASE}).status_code == 200
    client.post(URL, json=body())
    withdrawn = client.delete(URL, params={"link": LINK})
    assert withdrawn.status_code == 200 and withdrawn.json()["link"] == LINK
    assert client.get(URL).json() == []
    assert client.delete(URL, params={"link": LINK}).status_code == 404
    with factory() as session:
        workspace = session.get(Workspace, "ws")
        assert workspace is not None
        events = [e.event_type for e in session.scalars(select(AuditEvent))]
    assert "link.withdrawn" in events
