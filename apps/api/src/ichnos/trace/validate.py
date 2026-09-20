"""Trace validation (ADR-0023): what is missing, weak, guessed or failing.

Findings name their row, so a person can go straight to it. Confirmed inferred links are passed
in, so a person's judgement removes the warning without changing the evidence.
"""

import datetime as dt
from collections.abc import Iterator
from dataclasses import asdict, dataclass
from typing import Any

from ichnos.trace.build import Trace, TraceRow

DONE = {"done", "complete", "completed", "implemented"}
FAILED = {"failure", "failing", "cancelled", "timed_out", "action_required"}


@dataclass
class TraceFinding:
    code: str
    level: str
    row: str
    message: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _walk(rows: list[TraceRow]) -> Iterator[TraceRow]:
    for row in rows:
        yield row
        yield from _walk(row.children)


def validate_trace(
    trace: Trace,
    *,
    confirmed: set[str] | None = None,
    brd_frontmatter: dict[str, Any] | None = None,
    today: dt.date | None = None,
) -> list[TraceFinding]:
    confirmed = confirmed or set()
    today = today or dt.date.today()
    findings: list[TraceFinding] = []

    def add(code: str, level: str, row: TraceRow, message: str) -> None:
        findings.append(TraceFinding(code, level, row.id, message))

    stale_after = (brd_frontmatter or {}).get("stale_after")
    if stale_after and trace.rows:
        try:
            if dt.date.fromisoformat(str(stale_after)[:10]) < today:
                add(
                    "stale-source",
                    "warning",
                    trace.rows[0],
                    f"{trace.brd} is past its stale_after date ({stale_after}).",
                )
        except ValueError:
            pass

    for row in _walk(trace.rows):
        if row.level == "requirement":
            if not row.children:
                add(
                    "requirement-without-story",
                    "error",
                    row,
                    f"{row.key} has no Story implementing it.",
                )
            if row.status == "unverified":
                add(
                    "unverified-source",
                    "warning",
                    row,
                    f"The BRD behind {row.key} is not verified by a person.",
                )
        elif row.level == "epic" and row.key == "none":
            add("story-without-epic", "warning", row, "A Story here has no parent Epic.")
        elif row.level == "story":
            prs = [c for c in row.children if c.level == "pull_request"]
            if not prs:
                add(
                    "story-without-pr",
                    "warning",
                    row,
                    f"Story {row.key} has no pull request closing it.",
                )
            merged = any(pr.status == "merged" for pr in prs)
            for criterion in (c for c in row.children if c.level == "criterion"):
                if any(c.level == "test" for c in criterion.children):
                    continue
                if criterion.status in DONE:
                    add(
                        "claimed-without-evidence",
                        "error",
                        criterion,
                        f"{criterion.key} is marked {criterion.status} "
                        "but no test is named for it.",
                    )
                else:
                    add(
                        "criterion-without-test",
                        "error" if merged else "warning",
                        criterion,
                        f"{criterion.key} has no test evidence yet"
                        + (" although the pull request is merged." if merged else "."),
                    )
        elif row.level == "test":
            for evidence in row.evidence:
                if evidence.origin == "inferred" and evidence.link not in confirmed:
                    add(
                        "inferred-unconfirmed",
                        "warning",
                        row,
                        f"{row.key} was linked by inference ({evidence.text}); "
                        "nobody has confirmed it.",
                    )
            if row.status in FAILED:
                add("failing-checks", "error", row, f"{row.key} is failing.")
        elif row.level == "check" and row.status in FAILED:
            add("failing-checks", "error", row, f"CI check {row.key} is {row.status}.")
    return findings
