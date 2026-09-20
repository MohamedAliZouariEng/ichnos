import datetime as dt

from sqlalchemy.orm import Session, sessionmaker

import test_trace
from ichnos.trace.build import Evidence, Trace, TraceRow
from ichnos.trace.validate import TraceFinding, validate_trace

factory = test_trace.factory  # the Step 3 fixture, shared by name
trace = test_trace.trace
INFERRED = "pull_request:20->file:tests/test_invitations.py"


def codes(found: list[TraceFinding]) -> list[tuple[str, str]]:
    return sorted((f.code, f.level) for f in found)


def test_the_seeded_trace_reports_exactly_its_gaps(factory: sessionmaker[Session]) -> None:
    result = trace(factory)
    found = validate_trace(result)
    assert codes(found) == [
        ("criterion-without-test", "warning"),  # AC-01: PR #19 is only a draft
        ("inferred-unconfirmed", "warning"),  # PR #20's changed test file
    ]
    assert all(f.row.startswith("T") for f in found)
    confirmed = validate_trace(result, confirmed={INFERRED})
    assert codes(confirmed) == [("criterion-without-test", "warning")]


def row(level: str, key: str, status: str, *children: TraceRow) -> TraceRow:
    return TraceRow(level, key, key, status, None, [], list(children), id=f"T-{key}")


def test_merged_work_without_tests_and_failing_checks_are_errors() -> None:
    merged = row("pull_request", "PR #20", "merged", row("check", "pytest", "failure"))
    story = row(
        "story",
        "#8",
        "closed",
        row("criterion", "AC-02", "not started"),
        row("criterion", "AC-03", "done"),
        merged,
    )
    trace_ = Trace(
        "docs/specs/x/brd.md",
        "X",
        [
            row("requirement", "R-01", "unverified", row("epic", "none", "missing", story)),
            row("requirement", "R-02", "approved"),
        ],
    )
    found = validate_trace(
        trace_, brd_frontmatter={"stale_after": "2026-01-01"}, today=dt.date(2026, 9, 20)
    )
    assert codes(found) == [
        ("claimed-without-evidence", "error"),
        ("criterion-without-test", "error"),
        ("failing-checks", "error"),
        ("requirement-without-story", "error"),
        ("stale-source", "warning"),
        ("story-without-epic", "warning"),
        ("unverified-source", "warning"),
    ]


def test_a_story_without_a_pull_request_is_reported() -> None:
    story = row("story", "#9", "open", row("criterion", "AC-04", "not started"))
    trace_ = Trace(
        "b.md", "B", [row("requirement", "R-03", "approved", row("epic", "#6", "open", story))]
    )
    assert codes(validate_trace(trace_)) == [
        ("criterion-without-test", "warning"),
        ("story-without-pr", "warning"),
    ]


def test_evidence_origin_is_what_validation_reads() -> None:
    guessed = Evidence("changed in PR #1", "Pull request #1", None, origin="inferred", link="x")
    test = TraceRow("test", "tests/t.py", "tests/t.py", "passing", None, [guessed], [], id="T9")
    trace_ = Trace("b.md", "B", [row("requirement", "R-04", "approved", test)])
    assert [f.code for f in validate_trace(trace_)] == ["inferred-unconfirmed"]
    assert validate_trace(trace_, confirmed={"x"}) == []
