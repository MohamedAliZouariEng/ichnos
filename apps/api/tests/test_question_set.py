"""Phase 6 answers in CI: a fixed question set, and no source means no claim (ADR-0024)."""

from typing import Any

import pytest
from sqlalchemy.orm import Session, sessionmaker

import test_answer_retrieval
import test_trace
from ichnos.answers.answer import NO_EVIDENCE, NO_PASSING_TEST, AnswerDraft, draft_answer
from ichnos.answers.retrieve import Retrieved, retrieve_for_question
from ichnos.db.models import Workspace
from ichnos.llm import FakeProvider, Usage

factory = test_trace.factory  # the Step 3 fixture, shared by name
BRD = test_trace.BRD
NOTE = test_answer_retrieval.NOTE
DEMO = (
    "What approved evidence shows that invitation links must expire, "
    "and where is that behavior tested?"
)
QUESTIONS: list[tuple[str, set[str], set[str], set[str]]] = [
    # question, sources it must retrieve, gaps it must have, gaps it must not have
    (DEMO, {NOTE, f"{BRD}#r-01", "#7"}, {NO_PASSING_TEST}, set()),
    (
        "Where is resending tested?",
        {f"{BRD}#r-02", "tests/test_invitations.py::test_resend"},
        set(),
        {NO_PASSING_TEST},
    ),
    ("Which meeting decided that invitations expire?", {NOTE, f"{BRD}#r-01"}, set(), set()),
    ("What about single sign-on?", set(), {NO_EVIDENCE}, set()),
]


def retrieve(factory: sessionmaker[Session], question: str) -> Retrieved:
    with factory() as session:
        ws = session.get(Workspace, "ws")
        assert ws is not None
        return retrieve_for_question(session, ws, question)


class Scripted:
    """A model that says exactly what the test wants, to see what enforcement keeps."""

    model = "scripted"

    def __init__(self, draft: dict[str, Any]) -> None:
        self.draft = draft

    def complete_json(self, system: str, user: str, schema: Any) -> tuple[AnswerDraft, Usage]:
        return AnswerDraft.model_validate(self.draft), Usage()


@pytest.mark.parametrize(("question", "expected", "gaps", "absent"), QUESTIONS)
def test_the_question_set(
    factory: sessionmaker[Session],
    question: str,
    expected: set[str],
    gaps: set[str],
    absent: set[str],
) -> None:
    test_answer_retrieval.seed(factory)
    retrieved = retrieve(factory, question)
    found = {s.locator for s in retrieved.sources}
    assert expected <= found, f"missing {expected - found}"
    answer, notes, usage = draft_answer(FakeProvider(), retrieved)
    assert notes == []
    assert all(
        s.cites and set(s.cites) <= {x.id for x in retrieved.sources} for s in answer.statements
    )
    assert gaps <= set(answer.gaps) and not (absent & set(answer.gaps)), answer.gaps
    if not expected:
        assert usage.calls == 0  # no sources, no model call


def test_retrieval_finds_at_least_90_percent_of_expected_sources(
    factory: sessionmaker[Session],
) -> None:
    test_answer_retrieval.seed(factory)
    wanted = found = 0
    for question, expected, _, _ in QUESTIONS:
        locators = {s.locator for s in retrieve(factory, question).sources}
        wanted += len(expected)
        found += len(expected & locators)
    assert wanted and found / wanted >= 0.9, f"{found} of {wanted}"


def test_invented_or_missing_citations_leave_no_claim(factory: sessionmaker[Session]) -> None:
    test_answer_retrieval.seed(factory)
    retrieved = retrieve(factory, DEMO)
    liar = Scripted(
        {
            "statements": [
                {"text": "Expiry was approved by the board.", "cites": ["S99"]},
                {"text": "Links expire after 30 days.", "cites": []},
            ]
        }
    )
    answer, notes, _ = draft_answer(liar, retrieved)  # type: ignore[arg-type]
    assert answer.statements == [] and answer.gaps[0] == NO_EVIDENCE
    assert sum("Dropped statement" in n for n in notes) == 2


def test_saying_it_is_tested_does_not_make_it_tested(factory: sessionmaker[Session]) -> None:
    test_answer_retrieval.seed(factory)
    retrieved = retrieve(factory, DEMO)
    heading = next(s.id for s in retrieved.sources if s.locator == f"{BRD}#r-01")
    overclaim = Scripted(
        {"statements": [{"text": "Expiry is tested and all tests pass.", "cites": [heading]}]}
    )
    answer, _, _ = draft_answer(overclaim, retrieved)  # type: ignore[arg-type]
    assert NO_PASSING_TEST in answer.gaps
