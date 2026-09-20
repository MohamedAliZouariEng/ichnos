"""Release metrics (ADR-0025): computed by code from Ichnos's own data, never estimated.

Each metric keeps the items that fail it, so a low number always points somewhere.
"""

import re
from dataclasses import asdict, dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ichnos.db.models import Approval, AuditEvent, GitHubItem, Link, StoredAnswer, Workspace
from ichnos.trace.build import CRITERION_RE

VAGUE = (
    "fast",
    "quick",
    "quickly",
    "easy",
    "easily",
    "simple",
    "intuitive",
    "user-friendly",
    "appropriate",
    "appropriately",
    "reasonable",
    "robust",
    "seamless",
    "efficient",
    "properly",
)
GIVEN_WHEN_THEN = {word: re.compile(rf"\b{word}\b", re.I) for word in ("given", "when", "then")}
SOURCE_RELATIONS = ("references", "implements", "cites")


@dataclass
class Metric:
    key: str
    label: str
    numerator: int
    denominator: int
    threshold: float
    higher_is_better: bool = True
    details: list[str] = field(default_factory=list)

    @property
    def value(self) -> float | None:
        if not self.higher_is_better:
            return float(self.numerator)
        return self.numerator / self.denominator if self.denominator else None

    @property
    def passed(self) -> bool | None:
        if not self.higher_is_better:
            return self.numerator <= self.threshold
        value = self.value
        return None if value is None else value >= self.threshold

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data.update(value=self.value, passed=self.passed)
        return data


def is_testable(text: str) -> tuple[bool, str]:
    """Code rules for a testable criterion; the reason says why not."""
    missing = [word for word, pattern in GIVEN_WHEN_THEN.items() if not pattern.search(text)]
    if missing:
        return False, f"no {', '.join(missing)}"
    vague = [w for w in VAGUE if re.search(rf"\b{re.escape(w)}\b", text, re.I)]
    if vague and not re.search(r"\d", text):
        return False, f"vague without a number: {', '.join(vague)}"
    return True, ""


def stories(session: Session, workspace_id: str) -> list[GitHubItem]:
    items = session.scalars(
        select(GitHubItem).where(
            GitHubItem.workspace_id == workspace_id, GitHubItem.item_type != "pull_request"
        )
    ).all()
    parents = {
        link.target_key
        for link in session.scalars(
            select(Link).where(Link.workspace_id == workspace_id, Link.relation == "parent")
        )
    }
    return [
        item
        for item in items
        if item.state_reason != "not_planned"
        and "type:epic" not in (item.labels or [])
        and str(item.number) not in parents
        and ("type:story" in (item.labels or []) or "## Acceptance criteria" in (item.body or ""))
    ]


def story_links(session: Session, workspace: Workspace) -> Metric:
    links = session.scalars(
        select(Link).where(Link.workspace_id == workspace.id, Link.source_kind == "issue")
    ).all()
    with_parent = {link.source_key for link in links if link.relation == "parent"}
    with_source = {
        link.source_key
        for link in links
        if link.relation in SOURCE_RELATIONS and link.target_kind == "document"
    }
    found = stories(session, workspace.id)
    details = []
    for story in found:
        missing = [
            name
            for name, keys in (("parent", with_parent), ("source", with_source))
            if str(story.number) not in keys
        ]
        if missing:
            details.append(f"#{story.number} has no {' or '.join(missing)} link")
    linked = len(found) - len(details)
    return Metric(
        "story_links",
        "Stories with parent and source links",
        linked,
        len(found),
        0.9,
        details=details,
    )


def valid_answers(session: Session, workspace: Workspace) -> Metric:
    rows = session.scalars(
        select(StoredAnswer).where(StoredAnswer.workspace_id == workspace.id)
    ).all()
    details = []
    for row in rows:
        data = row.answer or {}
        ids = {str(source.get("id")) for source in data.get("sources", [])}
        statements = data.get("statements", [])
        cited = all(s.get("cites") and set(s["cites"]) <= ids for s in statements)
        if not cited or not (statements or data.get("gaps")):
            details.append(f"answer {row.id[:8]}: {row.question[:60]}")
    return Metric(
        "valid_answers",
        "Answers with valid sources",
        len(rows) - len(details),
        len(rows),
        0.9,
        details=details,
    )


def testable_criteria(session: Session, workspace: Workspace) -> Metric:
    total, details = 0, []
    for story in stories(session, workspace.id):
        for _, ac, text in CRITERION_RE.findall(story.body or ""):
            total += 1
            ok, why = is_testable(text)
            if not ok:
                details.append(f"#{story.number} {ac}: {why}")
    return Metric(
        "testable_criteria",
        "Acceptance criteria judged testable",
        total - len(details),
        total,
        0.8,
        details=details,
    )


def unapproved_writes(session: Session, workspace: Workspace) -> Metric:
    executed = session.scalars(
        select(Approval).where(Approval.workspace_id == workspace.id, Approval.status == "executed")
    ).all()
    approved = {
        event.approval_id
        for event in session.scalars(
            select(AuditEvent).where(AuditEvent.event_type == "approval.approved")
        )
    }
    details = [
        f"approval {a.id[:8]} executed without an approval event"
        for a in executed
        if a.id not in approved
    ]
    return Metric(
        "unapproved_writes",
        "Writes without a human approval",
        len(details),
        len(executed),
        0,
        higher_is_better=False,
        details=details,
    )


def compute_metrics(session: Session, workspace: Workspace) -> list[Metric]:
    return [
        story_links(session, workspace),
        valid_answers(session, workspace),
        testable_criteria(session, workspace),
        unapproved_writes(session, workspace),
    ]
