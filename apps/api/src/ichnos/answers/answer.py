"""Grounded answers (ADR-0024): statements that cite retrieved sources, and stated gaps.

The model proposes statements; code keeps only those that cite real sources, and adds the
gaps it can see: weak sources that were cited, and tests asked about but not found passing.
"""

import re
from dataclasses import asdict
from typing import Any

from pydantic import BaseModel, Field

from ichnos.answers.retrieve import Retrieved
from ichnos.llm import ModelProvider, Usage, fake_responder

MAX_EXCERPT = 1_200
NO_EVIDENCE = "No evidence was found in the synced knowledge for this question."
NO_PASSING_TEST = "No passing test was found among the sources."
FLAG_GAPS = {
    "unverified": "is not verified by a person",
    "stale": "is past its review date",
    "inferred": "was linked by inference and nobody has confirmed it",
    "not planned": "was closed as not planned",
    "closed without merging": "was closed without merging",
}

ANSWER_PROMPT = """\
You answer questions about a software project using only the numbered sources given.

Rules:
- Answer as a list of short statements. Every statement cites one or more sources by id (S1).
- Use only what the cited sources say. Never add facts, links or file names they do not contain.
- Prefer sources verified by a person; say when a source is unverified, stale or inferred.
- Say that something is tested only if a test source says its status is passing.
- Put in gaps every part of the question the sources do not answer, and any disagreement.
"""


class StatementDraft(BaseModel):
    text: str
    cites: list[str] = Field(default_factory=list)


class AnswerDraft(BaseModel):
    """What the model returns; enforcement turns it into an Answer."""

    statements: list[StatementDraft] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)


class Statement(BaseModel):
    text: str
    cites: list[str]


class Answer(BaseModel):
    question: str
    statements: list[Statement]
    gaps: list[str]
    cited: list[str]
    sources: list[dict[str, Any]]


def _clean(value: str) -> str:
    return " ".join(value.split())


def build_answer_prompt(retrieved: Retrieved) -> str:
    lines = [f"## Question\n\n{retrieved.question}\n", "## Sources"]
    for source in retrieved.sources:
        flags = f" [{', '.join(source.flags)}]" if source.flags else ""
        lines.append(f"[{source.id}] {source.kind} · {source.trust}{flags} · {source.locator}")
        if source.excerpt:
            lines += ["```", source.excerpt[:MAX_EXCERPT], "```"]
    lines += ["", "Return the answer as JSON matching the schema."]
    return "\n".join(lines)


def enforce_answer(draft: AnswerDraft, retrieved: Retrieved) -> tuple[Answer, list[str]]:
    by_id = {source.id: source for source in retrieved.sources}
    notes: list[str] = []
    statements: list[Statement] = []
    for index, draft_statement in enumerate(draft.statements, start=1):
        text = _clean(draft_statement.text)
        wanted = [c.strip().upper() for c in draft_statement.cites if c.strip()]
        cites = list(dict.fromkeys(c for c in wanted if c in by_id))
        if not text:
            continue
        if not cites:
            notes.append(f"Dropped statement {index}: it cites no retrieved source.")
            continue
        unknown = [c for c in wanted if c not in by_id]
        if unknown:
            notes.append(f"Statement {index}: removed unknown citations {', '.join(unknown)}.")
        statements.append(Statement(text=text, cites=cites))

    cited = list(dict.fromkeys(c for statement in statements for c in statement.cites))
    gaps = [_clean(gap) for gap in draft.gaps if _clean(gap)]
    if not statements:
        gaps.insert(0, NO_EVIDENCE)
    for source_id in cited:
        source = by_id[source_id]
        for flag in source.flags:
            if flag in FLAG_GAPS:
                gaps.append(f"{source_id} ({source.locator}) {FLAG_GAPS[flag]}.")
    asks_about_tests = re.search(r"\btest", retrieved.question, re.IGNORECASE)
    passing = any(by_id[c].kind == "test" and "status: passing" in by_id[c].excerpt for c in cited)
    if asks_about_tests and not passing:
        gaps.append(NO_PASSING_TEST)
    answer = Answer(
        question=retrieved.question,
        statements=statements,
        gaps=list(dict.fromkeys(gaps)),
        cited=cited,
        sources=[asdict(source) for source in retrieved.sources],
    )
    return answer, notes


def draft_answer(provider: ModelProvider, retrieved: Retrieved) -> tuple[Answer, list[str], Usage]:
    """No sources, no model call: the answer is the gap itself."""
    if not retrieved.sources:
        answer, notes = enforce_answer(AnswerDraft(), retrieved)
        return answer, notes, Usage()
    draft, usage = provider.complete_json(
        ANSWER_PROMPT, build_answer_prompt(retrieved), AnswerDraft
    )
    answer, notes = enforce_answer(draft, retrieved)
    return answer, notes, usage


SOURCE_LINE = re.compile(r"^\[(S\d+)\] (\w+) · [^\n]*? · (.+)$", re.M)


@fake_responder("AnswerDraft")
def fake_answer(system: str, user: str) -> dict[str, Any]:
    """Deterministic stand-in: one statement per source, citing it."""
    found = SOURCE_LINE.findall(user)
    return {
        "statements": [
            {"text": f"{kind.capitalize()} {locator} bears on the question.", "cites": [source_id]}
            for source_id, kind, locator in found[:6]
        ],
        "gaps": [],
    }
