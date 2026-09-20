from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

import test_answer_retrieval
import test_trace
from ichnos.answers.answer import NO_EVIDENCE

factory = test_trace.factory  # the Step 3 fixture, shared by name


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch, factory: sessionmaker[Session]) -> Iterator[TestClient]:
    from ichnos.main import create_app
    from ichnos.settings import Settings

    monkeypatch.setenv("ICHNOS_LLM_PROVIDER", "fake")
    test_answer_retrieval.seed(factory)
    with TestClient(create_app(Settings())) as test_client:
        yield test_client


def test_a_question_is_answered_with_cited_statements_and_kept(client: TestClient) -> None:
    asked = client.post(
        "/api/workspaces/ws/questions",
        json={"question": "Where is resending tested, and must invitations expire?"},
    )
    assert asked.status_code == 201, asked.text
    answer = asked.json()
    assert answer["statements"] and all(s["cites"] for s in answer["statements"])
    ids = {s["id"] for s in answer["sources"]}
    assert set(answer["cited"]) <= ids and answer["model"] == "ichnos/fake"
    assert any(s["url"] and s["url"].endswith("#r-02") for s in answer["sources"])

    history = client.get("/api/workspaces/ws/questions").json()
    assert history[0]["id"] == answer["id"] and history[0]["statements"] == len(
        answer["statements"]
    )
    assert client.get(f"/api/answers/{answer['id']}").json()["question"] == answer["question"]


def test_a_question_with_nothing_to_retrieve_is_a_stated_gap(client: TestClient) -> None:
    answer = client.post("/api/workspaces/ws/questions", json={"question": "Why?"}).json()
    assert answer["statements"] == [] and answer["gaps"] == [NO_EVIDENCE]
    assert answer["model"] == "none" and answer["tokens"] == 0


def test_questions_are_validated(client: TestClient) -> None:
    assert client.post("/api/workspaces/ws/questions", json={"question": "x"}).status_code == 422
    assert client.get("/api/answers/missing").status_code == 404
