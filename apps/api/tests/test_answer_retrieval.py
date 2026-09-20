import datetime as dt

from sqlalchemy.orm import Session, sessionmaker

import test_trace
from ichnos.answers.retrieve import Retrieved, github_anchor, retrieve_for_question
from ichnos.db.models import Chunk, Document, Link, Workspace

factory = test_trace.factory  # the Step 3 fixture, shared by name
BRD = test_trace.BRD
NOTE = "docs/meetings/2026-09-15-workspace-onboarding.md"


def seed(factory: sessionmaker[Session]) -> None:
    with factory() as session:
        session.add(
            Document(
                workspace_id="ws",
                path=NOTE,
                blob_sha="n" * 40,
                commit_sha="c" * 40,
                kind="concept",
                doc_type="Meeting Note",
                title="Workspace onboarding sync",
                trust_tier="human_verified",
                frontmatter={},
                body="Decision: invitation links must expire after 7 days.",
                findings=[],
            )
        )
        session.add(
            Link(
                workspace_id="ws",
                source_kind="document",
                source_key=BRD,
                target_kind="document",
                target_key=NOTE,
                relation="cites",
                origin="explicit",
                evidence="sources",
                confidence=1.0,
                resolved=True,
            )
        )
        for ordinal, (heading, text) in enumerate(
            [
                ("R-01", "Must. Invitations expire after 7 days."),
                ("R-02", "Should. Resending invalidates the old link."),
            ]
        ):
            session.add(
                Chunk(
                    workspace_id="ws",
                    source_kind="document",
                    source_key=BRD,
                    ordinal=ordinal,
                    heading=heading,
                    text=text,
                    start_line=ordinal,
                )
            )
        session.add(
            Chunk(
                workspace_id="ws",
                source_kind="issue",
                source_key="7",
                ordinal=0,
                heading="Default expiry",
                text="Invitation links expire after 7 days.",
                start_line=0,
            )
        )
        session.commit()


def ask(factory: sessionmaker[Session], question: str) -> Retrieved:
    with factory() as session:
        ws = session.get(Workspace, "ws")
        assert ws is not None
        return retrieve_for_question(session, ws, question, today=dt.date(2026, 9, 20))


def test_sources_reach_from_the_meeting_note_to_the_test(factory: sessionmaker[Session]) -> None:
    seed(factory)
    result = ask(factory, "Where is resending tested, and must invitations expire?")
    by_locator = {s.locator: s for s in result.sources}
    assert [s.id for s in result.sources][:2] == ["S1", "S2"]

    heading = by_locator[f"{BRD}#r-02"]
    assert heading.url is not None and heading.url.endswith(f"/blob/{'c' * 40}/{BRD}#r-02")
    assert heading.trust == "human_verified"
    assert by_locator[NOTE].title == "Workspace onboarding sync"  # cited by the BRD
    assert "#7" in by_locator

    trace = next(s for s in result.sources if s.kind == "trace" and s.locator.endswith("#r-02"))
    assert "tested: passing" in trace.excerpt
    test = by_locator["tests/test_invitations.py::test_resend"]
    assert test.kind == "test" and test.url is not None and f"/blob/{'e' * 40}/tests/" in test.url


def test_a_question_without_words_retrieves_nothing(factory: sessionmaker[Session]) -> None:
    assert ask(factory, "Why?").sources == []


def test_heading_anchors_match_github() -> None:
    assert github_anchor("R-01") == "r-01"
    assert github_anchor("Out of scope") == "out-of-scope"
    assert github_anchor("What's next?") == "whats-next"
