"""Requirements stage (ADR-0012): the model extracts, code enforces citations.

Every requirement must cite the sources (S1, S2, ...) or retrieved context (C1, C2, ...).
A requirement left without a valid citation becomes an assumption, never a requirement.
"""

import re
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, Field

from ichnos.llm import ModelProvider, fake_responder
from ichnos.okf import parse_document
from ichnos.workflows.engine import Data, StageContext, StageFailed

MAX_SOURCE_CHARS = 30_000
Priority = Literal["must", "should", "could"]

SYSTEM_PROMPT = """\
You turn meeting notes and product briefs into business requirements for a BRD.

Rules:
- Use only the material under Sources and Context. Never invent facts, names, numbers or dates.
- Every requirement cites the material that supports it with ids such as S1 or C2.
- A requirement is one testable statement of what the product must do, without implementation.
- Anything uncertain, undecided or unsupported goes under open_questions or assumptions.
- Priority: "must" for decisions and hard constraints, "should" for strong wishes,
  "could" for ideas.
- Acceptance criteria use the form "Given ..., when ..., then ...".
- out_of_scope lists only what the material explicitly excludes.
- Prefer the wording and the language of the sources.
"""


class PointDraft(BaseModel):
    text: str
    citations: list[str] = Field(default_factory=list)


class RequirementDraft(BaseModel):
    statement: str
    priority: Priority = "must"
    rationale: str = ""
    citations: list[str] = Field(default_factory=list)
    acceptance_criteria: list[str] = Field(default_factory=list)


class Extraction(BaseModel):
    """What the model returns; enforcement turns it into a Brief."""

    title: str
    problem: str
    goals: list[PointDraft] = Field(default_factory=list)
    requirements: list[RequirementDraft] = Field(default_factory=list)
    assumptions: list[PointDraft] = Field(default_factory=list)
    open_questions: list[PointDraft] = Field(default_factory=list)
    risks: list[PointDraft] = Field(default_factory=list)
    out_of_scope: list[PointDraft] = Field(default_factory=list)


class Point(BaseModel):
    text: str
    citations: list[str]


class Criterion(BaseModel):
    id: str
    text: str


class Requirement(BaseModel):
    id: str
    statement: str
    priority: Priority
    rationale: str
    citations: list[str]
    acceptance_criteria: list[Criterion]


class Brief(BaseModel):
    """Enforced content: every requirement carries at least one valid citation."""

    title: str
    problem: str
    goals: list[Point]
    requirements: list[Requirement]
    assumptions: list[Point]
    open_questions: list[Point]
    risks: list[Point]
    out_of_scope: list[Point]


@dataclass
class Enforced:
    brief: Brief
    demoted: list[str]
    dropped_citations: int


def _clean(value: str) -> str:
    return " ".join(value.split())


def _valid(citations: list[str], allowed: set[str]) -> list[str]:
    kept: list[str] = []
    for citation in citations:
        cid = citation.strip().strip("[]").upper()
        if cid in allowed and cid not in kept:
            kept.append(cid)
    return kept


def _points(items: list[PointDraft], allowed: set[str]) -> list[Point]:
    points: list[Point] = []
    seen: set[str] = set()
    for item in items:
        text = _clean(item.text)
        if text and text.lower() not in seen:
            seen.add(text.lower())
            points.append(Point(text=text, citations=_valid(item.citations, allowed)))
    return points


def enforce(extraction: Extraction, allowed: set[str]) -> Enforced:
    requirements: list[Requirement] = []
    assumptions = list(extraction.assumptions)
    demoted: list[str] = []
    seen: set[str] = set()
    dropped = 0
    criterion_number = 0
    for draft in extraction.requirements:
        statement = _clean(draft.statement)
        if not statement or statement.lower() in seen:
            continue
        seen.add(statement.lower())
        citations = _valid(draft.citations, allowed)
        dropped += len(draft.citations) - len(citations)
        if not citations:
            demoted.append(statement)
            assumptions.append(PointDraft(text=f"Not supported by the sources: {statement}"))
            continue
        criteria: list[Criterion] = []
        for text in draft.acceptance_criteria:
            if _clean(text):
                criterion_number += 1
                criteria.append(Criterion(id=f"AC-{criterion_number:02d}", text=_clean(text)))
        requirements.append(
            Requirement(
                id=f"R-{len(requirements) + 1:02d}",
                statement=statement,
                priority=draft.priority,
                rationale=_clean(draft.rationale),
                citations=citations,
                acceptance_criteria=criteria,
            )
        )
    brief = Brief(
        title=_clean(extraction.title) or "Untitled feature",
        problem=_clean(extraction.problem),
        goals=_points(extraction.goals, allowed),
        requirements=requirements,
        assumptions=_points(assumptions, allowed),
        open_questions=_points(extraction.open_questions, allowed),
        risks=_points(extraction.risks, allowed),
        out_of_scope=_points(extraction.out_of_scope, allowed),
    )
    return Enforced(brief, demoted, dropped)


def build_prompt(sources: list[dict[str, Any]], context: list[dict[str, Any]]) -> str:
    parts = ["## Sources"]
    for source in sources:
        text = str(source["text"])[:MAX_SOURCE_CHARS].strip()
        parts.append(f"### [{source['id']}] {source['title']} ({source['kind']})\n{text}")
    parts.append("## Context")
    if not context:
        parts.append("(no synced knowledge matched)")
    for item in context:
        labels = (
            str(item["kind"]).replace("_", " "),
            item.get("title") or item["key"],
            item.get("doc_type"),
            item.get("trust_tier"),
        )
        label = " · ".join(str(value) for value in labels if value)
        section = f"Section: {item['heading']}\n" if item.get("heading") else ""
        parts.append(f"### [{item['id']}] {label}\n{section}{str(item['excerpt']).strip()}")
    parts.append("Return the requirements as JSON matching the schema. Cite ids such as S1 or C2.")
    return "\n\n".join(parts)


BLOCK_RE = re.compile(r"^### \[(S\d+)\][^\n]*\n(.*?)(?=^### \[|^## |\Z)", re.S | re.M)
MODAL_RE = re.compile(r"\b(must|should|needs? to|has to|have to)\b", re.I)
BULLET_RE = re.compile(r"^\s*[-*]\s+(.*)$")


@fake_responder("Extraction")
def fake_extraction(system: str, user: str) -> dict[str, Any]:
    """Deterministic stand-in for a model: reads the first source's sections."""
    blocks = {match.group(1): match.group(2) for match in BLOCK_RE.finditer(user)}
    doc = parse_document("docs/source.md", blocks.get("S1", ""))
    heading = ""
    requirements: list[str] = []
    questions: list[str] = []
    excluded: list[str] = []
    paragraphs: list[str] = []
    for raw in doc.body.splitlines():
        line = raw.strip()
        if line.startswith("#"):
            heading = line.lstrip("#").strip().lower()
            continue
        bullet = BULLET_RE.match(raw)
        item = (bullet.group(1) if bullet else line).replace("**", "").strip()
        if not item:
            continue
        if "question" in heading:
            questions.append(item)
        elif "scope" in heading:
            excluded.append(item)
        elif "decision" in heading or MODAL_RE.search(item):
            requirements.append(item)
        elif not bullet and not paragraphs:
            paragraphs.append(item)
    title = doc.title or "Requirements"
    return {
        "title": title[:120],
        "problem": paragraphs[0] if paragraphs else title,
        "requirements": [
            {
                "statement": item,
                "priority": "must" if "must" in item.lower() or "decision" in heading else "should",
                "rationale": "Stated in the source.",
                "citations": ["S1"],
                "acceptance_criteria": [
                    f"Given the change is released, when it is tested, then: {item}"
                ],
            }
            for item in requirements
        ],
        "open_questions": [{"text": item, "citations": ["S1"]} for item in questions],
        "out_of_scope": [{"text": item, "citations": ["S1"]} for item in excluded],
    }


def requirements_stage(data: Data, context: StageContext) -> Data:
    provider: ModelProvider | None = context.services.get("provider")
    if provider is None:
        raise StageFailed("no model provider is configured; see the workspace settings")
    sources = list(data.get("sources", []))
    items = list(data.get("context", []))
    if not sources:
        raise StageFailed("retrieval produced no sources")
    allowed = {str(s["id"]) for s in sources} | {str(c["id"]) for c in items}
    extraction, usage = provider.complete_json(
        SYSTEM_PROMPT, build_prompt(sources, items), Extraction
    )
    context.usage.merge(usage)
    enforced = enforce(extraction, allowed)
    if enforced.demoted:
        context.note(
            f"{len(enforced.demoted)} requirement(s) without a valid citation became assumptions",
            demoted=enforced.demoted,
        )
    if not enforced.brief.requirements:
        raise StageFailed("the model found no requirements supported by the sources")
    return {
        "brief": enforced.brief.model_dump(),
        "model": f"ichnos/{provider.model}",
        "demoted": enforced.demoted,
        "dropped_citations": enforced.dropped_citations,
    }


def describe_requirements(update: Data) -> str:
    brief = update.get("brief", {})
    return (
        f"{len(brief.get('requirements', []))} requirements, "
        f"{len(brief.get('assumptions', []))} assumptions, "
        f"{len(brief.get('open_questions', []))} open questions"
    )
