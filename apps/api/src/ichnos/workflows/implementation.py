"""Implementation plans (ADR-0020): the model proposes from a context pack; code enforces.

Every file, step and test cites pack items; every acceptance criterion maps to steps or tests
or becomes an open question; files outside the pack must be new. A plan never claims that code
changed.
"""

import re
from typing import Any, Literal

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ichnos.db.models import Artifact, ArtifactVersion
from ichnos.honesty import claims
from ichnos.llm import ModelProvider, Usage, fake_responder

AC_RE = re.compile(r"^\s*[-*]\s*\[[ xX]\]\s*(AC-\d+)\s*:\s*(.+?)\s*$", re.M)
AC_ID = re.compile(r"\bAC[-\s]?0*(\d+)", re.IGNORECASE)
MAX_DOC_CHARS = 2_500
MAX_CODE_CHARS = 6_000
HONESTY = "Plan only: no code has changed."
PLAN_KIND = "implementation-plan"
TITLE_PREFIX = "# Implementation plan: Story #"

IMPLEMENTATION_PROMPT = """\
You plan the implementation of one GitHub Story for an engineer.

Rules:
- Use only the context pack. Cite pack items by id (P1, P2...) in every file, step and test.
- Files to change are code files from the pack; a file that does not exist yet has change "new".
- Steps are small and ordered. Tests say what they check and which file they live in.
- Map every acceptance criterion (AC-01...) to the steps and tests that satisfy it, by their
  1-based position in your steps and tests lists. Write criterion as the bare id: AC-01.
- Respect the decisions (ADRs) in the pack. A new lasting decision goes in adr_proposals.
- Anything the pack cannot answer goes in open_questions. Never invent files, APIs or facts.
- This is a plan: never say that code was changed or that tests pass.
"""

Change = Literal["modify", "new", "delete"]
TestKind = Literal["unit", "integration", "end-to-end", "manual"]


class FileDraft(BaseModel):
    path: str
    change: Change = "modify"
    why: str = ""
    cites: list[str] = Field(default_factory=list)


class StepDraft(BaseModel):
    text: str
    cites: list[str] = Field(default_factory=list)


class TestDraft(BaseModel):
    name: str
    checks: str = ""
    file: str | None = None
    kind: TestKind = "unit"
    cites: list[str] = Field(default_factory=list)


class CriterionDraft(BaseModel):
    criterion: str
    steps: list[int] = Field(default_factory=list)
    tests: list[int] = Field(default_factory=list)


class AdrDraft(BaseModel):
    title: str
    context: str = ""
    decision: str = ""
    cites: list[str] = Field(default_factory=list)


class ImplementationDraft(BaseModel):
    """What the model returns; enforcement turns it into an ImplementationPlan."""

    summary: str
    files: list[FileDraft] = Field(default_factory=list)
    data_changes: list[str] = Field(default_factory=list)
    api_changes: list[str] = Field(default_factory=list)
    steps: list[StepDraft] = Field(default_factory=list)
    tests: list[TestDraft] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    criteria: list[CriterionDraft] = Field(default_factory=list)
    adr_proposals: list[AdrDraft] = Field(default_factory=list)


class PlannedFile(BaseModel):
    path: str
    change: Change
    why: str
    cites: list[str]
    in_pack: bool


class PlannedStep(BaseModel):
    id: str
    text: str
    cites: list[str]


class PlannedTest(BaseModel):
    id: str
    name: str
    checks: str
    file: str | None
    kind: TestKind
    cites: list[str]


class Coverage(BaseModel):
    id: str
    text: str
    steps: list[str]
    tests: list[str]


class ProposedAdr(BaseModel):
    title: str
    context: str
    decision: str
    cites: list[str]


class ImplementationPlan(BaseModel):
    story: int
    title: str
    pack_hash: str
    summary: str
    files: list[PlannedFile]
    data_changes: list[str]
    api_changes: list[str]
    steps: list[PlannedStep]
    tests: list[PlannedTest]
    risks: list[str]
    open_questions: list[str]
    criteria: list[Coverage]
    adr_proposals: list[ProposedAdr]


def _ac_id(value: str) -> str:
    """AC-01, ac1, AC 01 or 'AC-01: Given ...' all become AC-01."""
    match = AC_ID.search(value)
    return f"AC-{int(match.group(1)):02d}" if match else ""


def _clean(value: str) -> str:
    return " ".join(value.split())


def story_criteria(pack: dict[str, Any]) -> list[tuple[str, str]]:
    story = next((i for i in pack["items"] if i["role"] == "story"), None)
    return [(ac, _clean(text)) for ac, text in AC_RE.findall(story["excerpt"] if story else "")]


def build_prompt(pack: dict[str, Any]) -> str:
    story = next((i for i in pack["items"] if i["role"] == "story"), {"title": ""})
    lines = [f"## Story #{pack['story']}: {story['title']}", "", "## Acceptance criteria"]
    lines += [f"- {ac}: {text}" for ac, text in story_criteria(pack)] or ["- (none stated)"]
    lines += ["", "## Context pack"]
    for item in pack["items"]:
        flags = f" [{', '.join(item['flags'])}]" if item["flags"] else ""
        lines.append(f"[{item['id']}] {item['role']} · {item['trust']}{flags} · {item['title']}")
        limit = MAX_CODE_CHARS if item["role"] == "code" else MAX_DOC_CHARS
        if item["excerpt"]:
            lines += ["```", item["excerpt"][:limit], "```"]
    if pack.get("absent"):
        lines.append(f"Absent from the pack: {', '.join(pack['absent'])}.")
    lines += ["", "Return the plan as JSON matching the schema."]
    return "\n".join(lines)


def enforce_implementation(
    draft: ImplementationDraft, pack: dict[str, Any]
) -> tuple[ImplementationPlan, list[str]]:
    known = {item["id"] for item in pack["items"]}
    code = {item["title"]: item["id"] for item in pack["items"] if item["role"] == "code"}
    notes: list[str] = []
    questions = [_clean(q) for q in draft.open_questions if _clean(q)]

    def cites(values: list[str], where: str) -> tuple[list[str], bool]:
        """(valid ids, True if some were given but none were valid)."""
        wanted = [v.strip().upper() for v in values if v.strip()]
        valid = list(dict.fromkeys(v for v in wanted if v in known))
        unknown = [v for v in wanted if v not in known]
        if unknown:
            notes.append(f"{where}: removed unknown citations {', '.join(unknown)}.")
        return valid, bool(wanted) and not valid

    files: list[PlannedFile] = []
    for draft_file in draft.files:
        path = draft_file.path.strip().removeprefix("./")
        valid, _ = cites(draft_file.cites, path)
        in_pack = path in code
        if in_pack and code[path] not in valid:
            valid.insert(0, code[path])
        if not in_pack and draft_file.change != "new":
            questions.append(
                f"{path} is not in the context pack; confirm it exists before changing it."
            )
        files.append(
            PlannedFile(
                path=path,
                change=draft_file.change,
                why=_clean(draft_file.why),
                cites=valid,
                in_pack=in_pack,
            )
        )

    steps: list[PlannedStep] = []
    step_ids: dict[int, str] = {}
    for index, step in enumerate(draft.steps, start=1):
        valid, invented = cites(step.cites, f"step {index}")
        if invented or not _clean(step.text):
            notes.append(f"Dropped step {index}: it cites nothing in the pack.")
            continue
        step_ids[index] = f"S{len(steps) + 1}"
        steps.append(PlannedStep(id=step_ids[index], text=_clean(step.text), cites=valid))

    tests: list[PlannedTest] = []
    test_ids: dict[int, str] = {}
    for index, test in enumerate(draft.tests, start=1):
        valid, invented = cites(test.cites, f"test {index}")
        if invented or not _clean(test.name):
            notes.append(f"Dropped test {index}: it cites nothing in the pack.")
            continue
        test_ids[index] = f"T{len(tests) + 1}"
        tests.append(
            PlannedTest(
                id=test_ids[index],
                name=_clean(test.name),
                checks=_clean(test.checks),
                file=test.file,
                kind=test.kind,
                cites=valid,
            )
        )

    coverage: list[Coverage] = []
    for ac, text in story_criteria(pack):
        mapped = [c for c in draft.criteria if _ac_id(c.criterion) == ac]
        covered_steps = list(
            dict.fromkeys(step_ids[i] for c in mapped for i in c.steps if i in step_ids)
        )
        covered_tests = list(
            dict.fromkeys(test_ids[i] for c in mapped for i in c.tests if i in test_ids)
        )
        if not covered_steps and not covered_tests:
            questions.append(f"{ac} ({text}) is not covered by any step or test.")
        coverage.append(Coverage(id=ac, text=text, steps=covered_steps, tests=covered_tests))

    adrs = [
        ProposedAdr(
            title=_clean(a.title),
            context=_clean(a.context),
            decision=_clean(a.decision),
            cites=cites(a.cites, f"ADR proposal '{_clean(a.title)}'")[0],
        )
        for a in draft.adr_proposals
        if _clean(a.title) and _clean(a.decision)
    ]
    story = next((i for i in pack["items"] if i["role"] == "story"), {"title": ""})
    plan = ImplementationPlan(
        story=int(pack["story"]),
        title=story["title"],
        pack_hash=pack["hash"],
        summary=_clean(draft.summary),
        files=files,
        data_changes=[_clean(c) for c in draft.data_changes if _clean(c)],
        api_changes=[_clean(c) for c in draft.api_changes if _clean(c)],
        steps=steps,
        tests=tests,
        risks=[_clean(r) for r in draft.risks if _clean(r)],
        open_questions=list(dict.fromkeys(questions)),
        criteria=coverage,
        adr_proposals=adrs,
    )
    return plan, notes


def _refs(cites: list[str]) -> str:
    return f" [{', '.join(cites)}]" if cites else ""


def _bullets(values: list[str]) -> list[str]:
    return [f"- {value}" for value in values] or ["None."]


def _criterion_row(c: Coverage) -> str:
    steps = ", ".join(c.steps) or "none"
    tests = ", ".join(c.tests) or "none"
    return f"| {c.id}: {c.text} | {steps} | {tests} |"


def _file_row(f: PlannedFile) -> str:
    change = f.change if f.in_pack or f.change == "new" else f"{f.change} (not in pack)"
    return f"| `{f.path}` | {change} | {f.why} | {', '.join(f.cites)} |"


def _test_line(t: PlannedTest) -> str:
    where = f"{t.kind}, {t.file}" if t.file else t.kind
    return f"- **{t.id}** `{t.name}` ({where}): {t.checks}{_refs(t.cites)}"


def render_plan(plan: ImplementationPlan) -> str:
    lines = [
        f"# Implementation plan: Story #{plan.story}, {plan.title}",
        "",
        f"Context pack `{plan.pack_hash[:12]}`. {HONESTY}",
        "",
        "## Summary",
        "",
        plan.summary or "None.",
        "",
        "## Acceptance criteria",
        "",
        "| Criterion | Steps | Tests |",
        "| --- | --- | --- |",
        *[_criterion_row(c) for c in plan.criteria],
        "",
        "## Files",
        "",
        "| File | Change | Why | Sources |",
        "| --- | --- | --- | --- |",
        *[_file_row(f) for f in plan.files],
        "",
        "## Data changes",
        "",
        *_bullets(plan.data_changes),
        "",
        "## API changes",
        "",
        *_bullets(plan.api_changes),
        "",
        "## Steps",
        "",
        *[f"1. **{s.id}** {s.text}{_refs(s.cites)}" for s in plan.steps],
        "",
        "## Tests",
        "",
        *[_test_line(t) for t in plan.tests],
        "",
        "## Risks",
        "",
        *_bullets(plan.risks),
        "",
        "## Open questions",
        "",
        *_bullets(plan.open_questions),
    ]
    if plan.adr_proposals:
        lines += ["", "## Proposed decisions", ""]
        for adr in plan.adr_proposals:
            lines += [
                f"### {adr.title}",
                "",
                f"**Context.** {adr.context or 'None given.'}",
                "",
                f"**Decision.** {adr.decision}",
                "",
                f"Sources: {', '.join(adr.cites) or 'none'}",
                "",
            ]
    return "\n".join(lines) + "\n"


def draft_implementation(
    provider: ModelProvider, pack: dict[str, Any]
) -> tuple[ImplementationPlan, list[str], Usage]:
    draft, usage = provider.complete_json(
        IMPLEMENTATION_PROMPT, build_prompt(pack), ImplementationDraft
    )
    plan, notes = enforce_implementation(draft, pack)
    return plan, notes, usage


ITEM_LINE = re.compile(r"^\[(P\d+)\] (\w+) · [^\n]*? · (\S+)$", re.M)


@fake_responder("ImplementationDraft")
def fake_implementation(system: str, user: str) -> dict[str, Any]:
    """Deterministic stand-in: one step and one test per criterion, on the pack's code files."""
    items = ITEM_LINE.findall(user)
    story = next((pid for pid, role, _ in items if role == "story"), "P1")
    sources = [(pid, path) for pid, role, path in items if role == "code" and "test" not in path]
    test_files = [path for _, role, path in items if role == "code" and "test" in path]
    criteria = re.findall(r"^- (AC-\d+): (.+)$", user, re.M)
    first = [sources[0][0]] if sources else []
    return {
        "summary": "Implement the Story in the files the context pack names.",
        "files": [
            {"path": path, "change": "modify", "why": "Implements the Story.", "cites": [pid]}
            for pid, path in sources
        ],
        "steps": [
            {"text": f"Implement {ac}: {text}", "cites": [story, *first]} for ac, text in criteria
        ],
        "tests": [
            {
                "name": f"test_{ac.lower().replace('-', '_')}",
                "checks": text,
                "file": test_files[0] if test_files else None,
                "cites": [story],
            }
            for ac, text in criteria
        ],
        "criteria": [
            {"criterion": ac, "steps": [n], "tests": [n]}
            for n, (ac, _) in enumerate(criteria, start=1)
        ],
        "risks": ["Existing invitations need a clear rule when the behaviour changes."],
    }


def plan_findings(markdown: str) -> list[dict[str, Any]]:
    """Checks for a plan, in the shape OKF findings are stored in."""
    findings: list[dict[str, Any]] = []

    def error(code: str, message: str, line: int = 1) -> None:
        findings.append({"level": "error", "code": code, "message": message, "line": line})

    first = next((line for line in markdown.splitlines() if line.strip()), "")
    if not first.startswith(TITLE_PREFIX):
        error("plan-title", f"A plan starts with its title: {TITLE_PREFIX}<number>, <title>.")
    if HONESTY not in markdown:
        error("plan-honesty", f"A plan keeps the line: {HONESTY}")
    if "## Acceptance criteria" not in markdown:
        error("plan-criteria", "A plan keeps its Acceptance criteria section.")
    for line, words in claims(markdown):
        error(
            "plan-claim", f'A plan cannot claim finished work before code exists: "{words}".', line
        )
    return findings


def plan_slug(plan: ImplementationPlan) -> str:
    words = re.sub(r"[^a-z0-9]+", "-", plan.title.lower()).strip("-")[:60].rstrip("-")
    return f"story-{plan.story}-{words}" if words else f"story-{plan.story}"


def store_plan(
    session: Session,
    *,
    workspace_id: str,
    plan: ImplementationPlan,
    markdown: str,
    actor: str,
    run_id: str | None = None,
) -> Artifact:
    """Keep the plan as an Ichnos artifact with append-only versions (ADR-0020)."""
    artifact = Artifact(
        workspace_id=workspace_id,
        kind=PLAN_KIND,
        title=f"Story #{plan.story}: {plan.title}"[:300],
        slug=plan_slug(plan),
        status="draft",
        run_id=run_id,
        source_ids=[f"story:{plan.story}", f"pack:{plan.pack_hash}"],
        current_version=1,
    )
    session.add(artifact)
    session.flush()
    session.add(
        ArtifactVersion(
            artifact_id=artifact.id,
            number=1,
            content=markdown,
            origin="generated",
            actor=actor,
            findings=plan_findings(markdown),
        )
    )
    return artifact
