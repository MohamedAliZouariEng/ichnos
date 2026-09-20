from typing import Any

from ichnos.answers.answer import (
    NO_EVIDENCE,
    NO_PASSING_TEST,
    AnswerDraft,
    build_answer_prompt,
    draft_answer,
    enforce_answer,
)
from ichnos.answers.retrieve import AnswerSource, Retrieved
from ichnos.llm import FakeProvider

BRD = "docs/specs/x/brd.md"


def source(
    sid: str,
    kind: str,
    locator: str,
    trust: str = "human_verified",
    flags: list[str] | None = None,
    excerpt: str = "text",
) -> AnswerSource:
    return AnswerSource(
        sid, kind, locator, locator, f"https://example.test/{locator}", trust, flags or [], excerpt
    )


RETRIEVED = Retrieved(
    question=(
        "What approved evidence shows that invitation links must expire, and where is that tested?"
    ),
    keywords=["invitation", "expire", "tested"],
    sources=[
        source(
            "S1",
            "document",
            "docs/meetings/note.md",
            excerpt="Decision: links expire after 7 days.",
        ),
        source("S2", "document", f"{BRD}#r-01", excerpt="Must. Invitations expire after 7 days."),
        source("S3", "issue", "#7", trust="github"),
        source(
            "S4",
            "test",
            "tests/test_invitations.py",
            trust="repository",
            flags=["inferred"],
            excerpt="test file modified in PR #20; status: passing",
        ),
    ],
)


def draft(**fields: Any) -> AnswerDraft:
    return AnswerDraft.model_validate(fields)


def test_statements_without_real_sources_are_dropped() -> None:
    answer, notes = enforce_answer(
        draft(
            statements=[
                {"text": "The meeting decided that links expire.", "cites": ["s1"]},
                {"text": "The BRD requires expiry after 7 days.", "cites": ["S2", "S42"]},
                {"text": "An invented fact.", "cites": ["S99"]},
                {"text": "Uncited.", "cites": []},
            ]
        ),
        RETRIEVED,
    )
    assert [(s.text, s.cites) for s in answer.statements] == [
        ("The meeting decided that links expire.", ["S1"]),
        ("The BRD requires expiry after 7 days.", ["S2"]),
    ]
    assert answer.cited == ["S1", "S2"]
    assert any("S42" in n for n in notes) and sum("Dropped statement" in n for n in notes) == 2


def test_gaps_name_weak_sources_and_missing_tests() -> None:
    answer, _ = enforce_answer(
        draft(statements=[{"text": "Expiry is required.", "cites": ["S2"]}]), RETRIEVED
    )
    assert (
        NO_PASSING_TEST in answer.gaps
    )  # the question asks about tests; no passing test was cited
    with_test, _ = enforce_answer(
        draft(statements=[{"text": "A test checks expiry.", "cites": ["S4"]}]), RETRIEVED
    )
    assert NO_PASSING_TEST not in with_test.gaps
    assert (
        "S4 (tests/test_invitations.py) was linked by inference and nobody has confirmed it."
        in with_test.gaps
    )


def test_no_statement_means_no_evidence() -> None:
    answer, _ = enforce_answer(draft(statements=[], gaps=["Nothing about SSO."]), RETRIEVED)
    assert answer.gaps[:2] == [NO_EVIDENCE, "Nothing about SSO."]


def test_the_prompt_lists_sources_with_trust_and_flags() -> None:
    prompt = build_answer_prompt(RETRIEVED)
    assert "[S4] test · repository [inferred] · tests/test_invitations.py" in prompt
    assert "Decision: links expire after 7 days." in prompt


def test_the_fake_answer_cites_every_statement() -> None:
    answer, notes, usage = draft_answer(FakeProvider(), RETRIEVED)
    assert notes == [] and usage.calls == 1
    assert all(statement.cites for statement in answer.statements)
    assert answer.cited == ["S1", "S2", "S3", "S4"]


class Refusing:
    model = "refusing"

    def complete_json(self, *args: Any) -> Any:
        raise AssertionError("the model must not be called without sources")


def test_no_sources_means_no_model_call() -> None:
    empty = Retrieved(question="What about SSO?", keywords=["sso"], sources=[])
    answer, _, usage = draft_answer(Refusing(), empty)  # type: ignore[arg-type]
    assert answer.gaps == [NO_EVIDENCE] and usage.calls == 0


def test_citing_a_trace_attaches_its_trail_once() -> None:
    trail = [
        {"label": "Meeting", "url": "https://example.test/note"},
        {"label": "BRD R-01", "url": "https://example.test/brd#r-01"},
    ]
    trace = AnswerSource(
        "S5", "trace", "Trace of R-01", "trace of brd#r-01", None, "derived", [], "x", trail
    )
    retrieved = Retrieved(
        question=RETRIEVED.question, keywords=[], sources=[*RETRIEVED.sources, trace]
    )
    answer, _ = enforce_answer(
        draft(
            statements=[
                {"text": "R-01 is approved.", "cites": ["S5"]},
                {"text": "It came from the meeting.", "cites": ["S5", "S1"]},
            ]
        ),
        retrieved,
    )
    assert answer.trail == trail  # both statements cite S5; the trail appears once
