from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

import test_trace
from ichnos.db.models import StoredAnswer, Workspace
from ichnos.evaluate.metrics import Metric, compute_metrics, is_testable

factory = test_trace.factory  # the Step 3 fixture, shared by name
BRD = test_trace.BRD
STORY_31 = (
    "As an admin.\n\n## Acceptance criteria\n"
    "- [ ] AC-06: Given an invitation older than 7 days, when it is opened, then it is refused.\n"
    "- [ ] AC-07: Given the invitation page, when it loads, then it is fast.\n"
)


def seed(factory: sessionmaker[Session]) -> None:
    link = test_trace.link
    with factory() as session:
        session.add_all(
            [
                link(("issue", "7"), ("document", BRD), "references"),
                link(("issue", "8"), ("document", BRD), "references"),
                test_trace.item(31, "Expiry without links", STORY_31),
                StoredAnswer(
                    workspace_id="ws",
                    question="Valid?",
                    model="ichnos/fake",
                    answer={
                        "statements": [{"text": "Yes.", "cites": ["S1"]}],
                        "gaps": [],
                        "sources": [{"id": "S1"}],
                    },
                ),
                StoredAnswer(
                    workspace_id="ws",
                    question="Invented?",
                    model="ichnos/fake",
                    answer={
                        "statements": [{"text": "No.", "cites": ["S9"]}],
                        "gaps": [],
                        "sources": [{"id": "S1"}],
                    },
                ),
            ]
        )
        session.commit()


def metrics(factory: sessionmaker[Session]) -> dict[str, Metric]:
    with factory() as session:
        ws = session.get(Workspace, "ws")
        assert ws is not None
        return {m.key: m for m in compute_metrics(session, ws)}


def test_each_metric_counts_what_it_says(factory: sessionmaker[Session]) -> None:
    seed(factory)
    found = metrics(factory)
    links = found["story_links"]
    assert (links.numerator, links.denominator, links.passed) == (2, 4, False)
    assert links.details == ["#30 has no parent or source link", "#31 has no parent or source link"]
    criteria = found["testable_criteria"]
    assert (criteria.numerator, criteria.denominator) == (1, 5)
    assert "#31 AC-07: vague without a number: fast" in criteria.details
    answers = found["valid_answers"]
    assert (answers.numerator, answers.denominator, answers.value) == (1, 2, 0.5)
    writes = found["unapproved_writes"]
    assert (writes.numerator, writes.passed) == (0, True)


def test_testability_rules() -> None:
    assert is_testable("Given a link sent 7 days ago, when opened, then it is refused.") == (
        True,
        "",
    )
    assert is_testable("Given x, then y.") == (False, "no when")
    assert is_testable("Given a page, when it loads, then it is fast.")[0] is False
    assert is_testable("Given a page, when it loads, then it is fast: under 2 seconds.")[0] is True


@pytest.fixture
def client(factory: sessionmaker[Session]) -> Iterator[TestClient]:
    from ichnos.main import create_app
    from ichnos.settings import Settings

    seed(factory)
    with TestClient(create_app(Settings())) as test_client:
        yield test_client


def test_the_metrics_api(client: TestClient) -> None:
    found = {m["key"]: m for m in client.get("/api/workspaces/ws/metrics").json()}
    assert set(found) == {"story_links", "valid_answers", "testable_criteria", "unapproved_writes"}
    assert found["story_links"]["value"] == 0.5 and found["unapproved_writes"]["passed"] is True
