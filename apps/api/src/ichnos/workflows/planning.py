"""Planning stage (Phase 4): one Epic and 3-5 Stories from an approved BRD.

The model proposes; code enforces that every Story implements real BRD requirements, has
acceptance criteria, and that dependencies point at Stories that exist.
"""

import re
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, Field
from sqlalchemy import select

from ichnos.db.models import Artifact, ArtifactVersion
from ichnos.llm import ModelProvider, fake_responder
from ichnos.okf import parse_document
from ichnos.workflows.engine import Data, StageContext, StageFailed

MAX_BRD_CHARS = 40_000
MIN_STORIES = 3
MAX_STORIES = 5
Priority = Literal["must", "should", "could"]

PLANNING_PROMPT = """\
You plan delivery work for an approved business requirements document (BRD).

Rules:
- Propose exactly one Epic and three to five Stories.
- Every Story implements one or more BRD requirements; list their IDs exactly as written (R-01).
- A Story is one independently deliverable slice, with a short title and a user story in the
  form "As a ..., I want ..., so that ...".
- Acceptance criteria use "Given ..., when ..., then ..." and come from the BRD.
- depends_on lists the numbers (1, 2, ...) of Stories that must be done first.
- Priority follows the requirements: must, should or could.
- exclusions repeat only what the BRD puts out of scope. Never invent features.
"""


class StoryDraft(BaseModel):
    title: str
    user_story: str = ""
    requirement_ids: list[str] = Field(default_factory=list)
    acceptance_criteria: list[str] = Field(default_factory=list)
    depends_on: list[int] = Field(default_factory=list)
    priority: Priority = "should"


class PlanDraft(BaseModel):
    """What the model returns; enforcement turns it into a Plan."""

    epic_title: str
    epic_summary: str
    stories: list[StoryDraft] = Field(default_factory=list)
    exclusions: list[str] = Field(default_factory=list)


class Criterion(BaseModel):
    id: str
    text: str


class Story(BaseModel):
    key: str
    title: str
    user_story: str
    requirement_ids: list[str]
    acceptance_criteria: list[Criterion]
    depends_on: list[str]
    priority: Priority


class Plan(BaseModel):
    epic_title: str
    epic_summary: str
    stories: list[Story]
    exclusions: list[str]
    uncovered: list[str]


@dataclass(frozen=True)
class BrdRequirement:
    id: str
    priority: str
    statement: str
    criteria: tuple[str, ...]


SECTION = re.compile(r"^## (R-\d+)[ \t]*$(.*?)(?=^## |^# |\Z)", re.M | re.S)
PRIORITY = re.compile(r"\*\*(Must|Should|Could)\.\*\*\s*(.+)")
CRITERION = re.compile(r"^- \*\*(AC-\d+)\*\*:\s*(.+)$", re.M)
FOOTNOTE_REF = re.compile(r"\[\^[^\]]+\]")
REQUIREMENT_ID = re.compile(r"^R-?0*(\d+)$", re.I)


def _clean(value: str) -> str:
    return " ".join(FOOTNOTE_REF.sub("", value).split())


def requirements_of(content: str) -> list[BrdRequirement]:
    """The R-xx sections of a BRD rendered by the specification stage."""
    body = parse_document("docs/specs/brd/brd.md", content).body
    found: list[BrdRequirement] = []
    for match in SECTION.finditer(body):
        section = match.group(2)
        priority = PRIORITY.search(section)
        found.append(
            BrdRequirement(
                id=match.group(1),
                priority=priority.group(1).lower() if priority else "should",
                statement=_clean(priority.group(2)) if priority else "",
                criteria=tuple(_clean(text) for _, text in CRITERION.findall(section)),
            )
        )
    return found


def _section_items(body: str, heading: str) -> list[str]:
    match = re.search(rf"^# {heading}[ \t]*$(.*?)(?=^# |\Z)", body, re.M | re.S)
    if not match:
        return []
    return [_clean(line[2:]) for line in match.group(1).splitlines() if line.startswith("- ")]


def _requirement_id(value: str) -> str | None:
    match = REQUIREMENT_ID.match(value.strip())
    return f"R-{int(match.group(1)):02d}" if match else None


def enforce_plan(
    draft: PlanDraft,
    requirements: list[BrdRequirement],
    *,
    minimum: int = MIN_STORIES,
    maximum: int = MAX_STORIES,
) -> tuple[Plan, list[str]]:
    known = {requirement.id: requirement for requirement in requirements}
    notes: list[str] = []
    kept: list[tuple[int, StoryDraft, list[str]]] = []
    seen: set[str] = set()
    for index, story in enumerate(draft.stories, start=1):
        title = _clean(story.title)
        if not title or title.lower() in seen:
            continue
        ids: list[str] = []
        for raw in story.requirement_ids:
            rid = _requirement_id(raw)
            if rid in known and rid not in ids:
                ids.append(rid)
        if not ids:
            notes.append(f'Dropped the story "{title}": it implements no BRD requirement.')
            continue
        seen.add(title.lower())
        kept.append((index, story, ids))
    if len(kept) > maximum:
        notes.append(f"Kept the first {maximum} of {len(kept)} stories.")
        kept = kept[:maximum]
    if len(kept) < minimum:
        raise StageFailed(
            f"the plan has {len(kept)} stories linked to BRD requirements; "
            f"at least {minimum} are needed"
        )

    keys = {index: f"S-{number}" for number, (index, _, _) in enumerate(kept, start=1)}
    stories: list[Story] = []
    counter = 0
    for index, story, ids in kept:
        texts = [_clean(text) for text in story.acceptance_criteria if _clean(text)]
        if not texts:  # inherit the BRD's criteria for these requirements
            texts = [text for rid in ids for text in known[rid].criteria]
        criteria = []
        for text in texts:
            counter += 1
            criteria.append(Criterion(id=f"AC-{counter:02d}", text=text))
        depends = [
            keys[number] for number in story.depends_on if number in keys and number != index
        ]
        stories.append(
            Story(
                key=keys[index],
                title=_clean(story.title),
                user_story=_clean(story.user_story),
                requirement_ids=ids,
                acceptance_criteria=criteria,
                depends_on=list(dict.fromkeys(depends)),
                priority=story.priority,
            )
        )
    covered = {rid for story in stories for rid in story.requirement_ids}
    uncovered = [rid for rid in known if rid not in covered]
    if uncovered:
        notes.append("Not covered by any story: " + ", ".join(uncovered))
    plan = Plan(
        epic_title=_clean(draft.epic_title) or "Untitled Epic",
        epic_summary=_clean(draft.epic_summary),
        stories=stories,
        exclusions=[_clean(item) for item in draft.exclusions if _clean(item)],
        uncovered=uncovered,
    )
    return plan, notes


def build_plan_prompt(content: str) -> str:
    return (
        "## BRD\n\n"
        + content[:MAX_BRD_CHARS].strip()
        + "\n\nPropose the Epic and Stories as JSON matching the schema. "
        "Use the requirement IDs exactly as written (R-01, R-02, ...)."
    )


@fake_responder("PlanDraft")
def fake_plan(system: str, user: str) -> dict[str, Any]:
    """Deterministic stand-in: one Story per BRD requirement, with the BRD's own criteria."""
    brd = user.split("## BRD\n\n", 1)[-1].rsplit("\n\nPropose the Epic", 1)[0]
    parsed = parse_document("docs/specs/brd/brd.md", brd)
    summary = re.search(r"^# Summary[ \t]*\n+(.+?)(?:\n\n|\Z)", parsed.body, re.M | re.S)
    stories = [
        {
            "title": requirement.statement[:80] or requirement.id,
            "user_story": f"As a workspace member, I want this: {requirement.statement}",
            "requirement_ids": [requirement.id],
            "acceptance_criteria": list(requirement.criteria),
            "priority": requirement.priority,
        }
        for requirement in requirements_of(brd)[:MAX_STORIES]
    ]
    return {
        "epic_title": parsed.title or "Epic",
        "epic_summary": _clean(summary.group(1)) if summary else "",
        "stories": stories,
        "exclusions": _section_items(parsed.body, "Out of scope"),
    }


def planning_stage(data: Data, context: StageContext) -> Data:
    provider: ModelProvider | None = context.services.get("provider")
    if provider is None:
        raise StageFailed("no model provider is configured; see the workspace settings")
    with context.factory() as session:
        artifact = session.get(Artifact, str(data.get("artifact_id", "")))
        if artifact is None or artifact.kind != "brd":
            raise StageFailed("the BRD to plan was not found")
        if artifact.status != "approved":
            raise StageFailed("only approved BRDs are planned; publish and approve it first")
        version = session.scalar(
            select(ArtifactVersion).where(
                ArtifactVersion.artifact_id == artifact.id,
                ArtifactVersion.number == artifact.current_version,
            )
        )
        if version is None:
            raise StageFailed("the BRD has no current version")
        content, number, slug = version.content, version.number, artifact.slug
    requirements = requirements_of(content)
    if not requirements:
        raise StageFailed("the BRD has no requirements to plan")
    draft, usage = provider.complete_json(PLANNING_PROMPT, build_plan_prompt(content), PlanDraft)
    context.usage.merge(usage)
    plan, notes = enforce_plan(draft, requirements)
    for note in notes:
        context.note(note)
    return {
        "plan": plan.model_dump(),
        "model": f"ichnos/{provider.model}",
        "artifact_version": number,
        "brd_path": f"docs/specs/{slug}/brd.md",
    }


def describe_planning(update: Data) -> str:
    plan = update.get("plan", {})
    stories = plan.get("stories", [])
    covered = {rid for story in stories for rid in story.get("requirement_ids", [])}
    total = len(covered) + len(plan.get("uncovered", []))
    return f"1 Epic and {len(stories)} Stories covering {len(covered)} of {total} requirements"
