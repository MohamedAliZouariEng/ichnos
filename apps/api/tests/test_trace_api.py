from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

import test_trace
from ichnos.db.models import LinkConfirmation

factory = test_trace.factory  # the Step 3 fixture, shared by name
LINK = "pull_request:20->file:tests/test_invitations.py"


@pytest.fixture
def client(factory: sessionmaker[Session]) -> Iterator[TestClient]:
    from ichnos.main import create_app
    from ichnos.settings import Settings

    with TestClient(create_app(Settings())) as test_client:
        yield test_client


def walk(rows: list[dict[str, Any]]) -> Iterator[dict[str, Any]]:
    for row in rows:
        yield row
        yield from walk(row["children"])


def test_brds_are_listed_and_the_trace_is_served_with_findings(client: TestClient) -> None:
    brds = client.get("/api/workspaces/ws/trace/brds").json()
    assert [b["path"] for b in brds] == [test_trace.BRD]
    trace = client.get("/api/workspaces/ws/trace", params={"brd": test_trace.BRD}).json()
    assert [r["key"] for r in trace["rows"]] == ["R-01", "R-02"]
    assert sorted(f["code"] for f in trace["findings"]) == [
        "criterion-without-test",
        "inferred-unconfirmed",
    ]
    inferred = [e for r in walk(trace["rows"]) for e in r["evidence"] if e["origin"] == "inferred"]
    assert inferred[0]["link"] == LINK and inferred[0]["confirmed"] is False


def test_a_confirmed_link_is_marked_and_its_warning_is_gone(
    client: TestClient, factory: sessionmaker[Session]
) -> None:
    with factory() as session:
        session.add(LinkConfirmation(workspace_id="ws", link=LINK, confirmed_by="human:octo"))
        session.commit()
    trace = client.get("/api/workspaces/ws/trace", params={"brd": test_trace.BRD}).json()
    assert [f["code"] for f in trace["findings"]] == ["criterion-without-test"]
    inferred = [e for r in walk(trace["rows"]) for e in r["evidence"] if e["origin"] == "inferred"]
    assert inferred[0]["confirmed"] is True


def test_an_unknown_brd_is_404(client: TestClient) -> None:
    response = client.get("/api/workspaces/ws/trace", params={"brd": "docs/specs/none/brd.md"})
    assert response.status_code == 404
