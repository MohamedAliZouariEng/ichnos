"""Traceability (ADR-0022): requirement, Epic, Story, criterion, pull request, commit and test.

Built by code from synced knowledge, with a status and evidence on every row. Evidence found by
guessing (a changed file that looks like a test) is marked inferred.
"""

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ichnos.db.models import (
    CheckRun,
    Commit,
    Document,
    GitHubItem,
    Link,
    PullRequestCommit,
    PullRequestFile,
    Workspace,
)
from ichnos.workflows.planning import requirements_of

ITEM_KINDS = ("issue", "pull_request")
CRITERION_RE = re.compile(r"^\s*[-*]\s*\[([ xX])\]\s*(AC-\d+)\s*:\s*(.+?)\s*$", re.M)
TABLE_ROW_RE = re.compile(r"^\|\s*(AC-\d+)\b[^|]*\|\s*([^|]*?)\s*\|\s*([^|]*?)\s*\|\s*$", re.M)
TEST_PATH_RE = re.compile(r"[\w./-]*test[\w./-]*\.py(?:::[\w\[\]-]+)?")
TEST_FILE_RE = re.compile(r"(^|/)tests?/|(^|/)test_[^/]+$|_test\.[a-z]+$")
PASSING = {"success", "neutral", "skipped"}


class TraceError(Exception):
    """The trace cannot be built; the message is safe to show."""


@dataclass
class Evidence:
    text: str
    source: str
    url: str | None = None
    origin: str = "explicit"
    link: str | None = None  # an inferred link's identity, for confirmation (ADR-0023)


@dataclass
class TraceRow:
    level: str
    key: str
    title: str
    status: str
    url: str | None = None
    evidence: list[Evidence] = field(default_factory=list)
    children: list["TraceRow"] = field(default_factory=list)
    id: str = ""


@dataclass
class Trace:
    brd: str
    title: str
    rows: list[TraceRow]
    hash: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _section(body: str, heading: str) -> str:
    match = re.search(rf"^## {heading}[ \t]*$(.*?)(?=^## |\Z)", body, re.M | re.S)
    return match.group(1) if match else ""


def requirement_ids(body: str) -> set[str]:
    return set(re.findall(r"\bR-\d+\b", _section(body, "Requirements")))


def item_status(item: GitHubItem) -> str:
    if item.item_type == "pull_request":
        if item.merged_at is not None:
            return "merged"
        if item.state == "closed":
            return "closed without merging"
        return "draft" if item.draft else "open"
    return item.state


def checks_status(runs: list[CheckRun]) -> str:
    if not runs:
        return "not run"
    if any(run.status != "completed" for run in runs):
        return "pending"
    return "passing" if all(run.conclusion in PASSING for run in runs) else "failing"


class _Builder:
    def __init__(self, session: Session, workspace: Workspace) -> None:
        self.session, self.ws = session, workspace
        self.repo_url = f"https://github.com/{workspace.repo_owner}/{workspace.repo_name}"
        self.items = {
            item.number: item
            for item in session.scalars(
                select(GitHubItem).where(GitHubItem.workspace_id == workspace.id)
            )
        }
        links = session.scalars(select(Link).where(Link.workspace_id == workspace.id)).all()
        self.parent: dict[int, int] = {}
        self.closes: dict[int, list[int]] = {}
        for link in links:
            if link.source_kind not in ITEM_KINDS or link.target_kind not in ITEM_KINDS:
                continue
            if not (link.source_key.isdigit() and link.target_key.isdigit()):
                continue
            if link.relation == "parent":
                self.parent[int(link.source_key)] = int(link.target_key)
            elif link.relation == "closes":
                self.closes.setdefault(int(link.target_key), []).append(int(link.source_key))

    def runs(self, head: str | None) -> list[CheckRun]:
        if not head:
            return []
        return list(
            self.session.scalars(
                select(CheckRun).where(
                    CheckRun.workspace_id == self.ws.id, CheckRun.head_sha == head
                )
            )
        )

    def criterion(
        self,
        story: GitHubItem,
        box: str,
        ac: str,
        text: str,
        table: dict[str, tuple[GitHubItem, str, str]],
    ) -> TraceRow:
        entry = table.get(ac)
        if entry is None:
            status = "checked in the Story" if box.lower() == "x" else "not started"
            evidence = [
                Evidence(f"{ac} is listed in #{story.number}", f"Issue #{story.number}", story.url)
            ]
            return TraceRow("criterion", ac, " ".join(text.split()), status, story.url, evidence)
        pr, stated, cell = entry
        paths = list(dict.fromkeys(TEST_PATH_RE.findall(cell)))
        runs = self.runs(pr.head_sha)
        ci = checks_status(runs)
        row = TraceRow(
            "criterion",
            ac,
            " ".join(text.split()),
            f"tested: {ci}" if paths else (stated.lower() or "not started"),
            pr.url,
            [
                Evidence(
                    f"PR #{pr.number} evidence table: {stated or '(empty)'}; {cell or '(empty)'}",
                    f"Pull request #{pr.number}",
                    pr.url,
                )
            ],
        )
        for path in paths:
            row.children.append(
                TraceRow(
                    "test",
                    path,
                    path,
                    ci if runs else "named, not run",
                    f"{self.repo_url}/blob/{pr.head_sha}/{path.split('::')[0]}",
                    [
                        Evidence(
                            f"named for {ac} in PR #{pr.number}'s evidence table",
                            f"Pull request #{pr.number}",
                            pr.url,
                        )
                    ],
                )
            )
        return row

    def pull_request(self, pr: GitHubItem, story: int) -> TraceRow:
        row = TraceRow(
            "pull_request",
            f"PR #{pr.number}",
            pr.title,
            item_status(pr),
            pr.url,
            [Evidence(f"PR #{pr.number} closes #{story}", f"Pull request #{pr.number}", pr.url)],
        )
        for member in self.session.scalars(
            select(PullRequestCommit).where(
                PullRequestCommit.workspace_id == self.ws.id,
                PullRequestCommit.pr_number == pr.number,
            )
        ):
            commit = self.session.scalar(
                select(Commit).where(Commit.workspace_id == self.ws.id, Commit.sha == member.sha)
            )
            message = str(getattr(commit, "message", "") or "").splitlines()
            row.children.append(
                TraceRow(
                    "commit",
                    member.sha[:8],
                    message[0] if message else member.sha[:8],
                    "committed",
                    f"{self.repo_url}/commit/{member.sha}",
                    [Evidence(f"commit of PR #{pr.number}", f"Pull request #{pr.number}", pr.url)],
                )
            )
        runs = self.runs(pr.head_sha)
        for file in self.session.scalars(
            select(PullRequestFile).where(
                PullRequestFile.workspace_id == self.ws.id, PullRequestFile.pr_number == pr.number
            )
        ):
            if TEST_FILE_RE.search(file.path):
                row.children.append(
                    TraceRow(
                        "test",
                        file.path,
                        file.path,
                        checks_status(runs),
                        f"{self.repo_url}/blob/{pr.head_sha}/{file.path}",
                        [
                            Evidence(
                                f"test file {file.status} in PR #{pr.number}",
                                f"Pull request #{pr.number}",
                                pr.url,
                                origin="inferred",
                                link=f"pull_request:{pr.number}->file:{file.path}",
                            )
                        ],
                    )
                )
        for run in runs:
            row.children.append(
                TraceRow(
                    "check",
                    run.name,
                    run.name,
                    run.conclusion or run.status,
                    run.url,
                    [
                        Evidence(
                            f"CI check run on {str(pr.head_sha)[:8]}",
                            f"Pull request #{pr.number}",
                            run.url,
                        )
                    ],
                )
            )
        return row

    def story(self, story: GitHubItem, rid: str) -> TraceRow:
        row = TraceRow(
            "story",
            f"#{story.number}",
            story.title,
            item_status(story),
            story.url,
            [
                Evidence(
                    f"#{story.number} lists {rid} under Requirements",
                    f"Issue #{story.number}",
                    story.url,
                )
            ],
        )
        prs = [self.items[n] for n in sorted(self.closes.get(story.number, [])) if n in self.items]
        table: dict[str, tuple[GitHubItem, str, str]] = {}
        for pr in prs:
            for ac, stated, cell in TABLE_ROW_RE.findall(pr.body or ""):
                table.setdefault(ac, (pr, stated.strip(), cell.strip()))
        for box, ac, text in CRITERION_RE.findall(story.body or ""):
            row.children.append(self.criterion(story, box, ac, text, table))
        row.children += [self.pull_request(pr, story.number) for pr in prs]
        return row


def _number(rows: list[TraceRow], counter: list[int]) -> None:
    for row in rows:
        counter[0] += 1
        row.id = f"T{counter[0]}"
        _number(row.children, counter)


def build_trace(session: Session, workspace: Workspace, brd_path: str) -> Trace:
    doc = session.scalar(
        select(Document).where(Document.workspace_id == workspace.id, Document.path == brd_path)
    )
    if doc is None or doc.doc_type != "BRD":
        raise TraceError(f"{brd_path} is not a synced BRD in this workspace.")
    b = _Builder(session, workspace)
    parents = set(b.parent.values())  # an Issue with children is an Epic, not a Story
    stories = sorted(
        (
            i
            for i in b.items.values()
            if i.item_type != "pull_request"
            and i.state_reason != "not_planned"
            and "type:epic" not in (i.labels or [])
            and i.number not in parents
            and brd_path in (i.body or "")
        ),
        key=lambda i: i.number,
    )
    rows: list[TraceRow] = []
    for requirement in requirements_of(doc.body):
        anchor = requirement.id.lower()
        url = f"{b.repo_url}/blob/{doc.commit_sha}/{brd_path}#{anchor}"
        row = TraceRow(
            "requirement",
            requirement.id,
            requirement.statement,
            "approved" if doc.trust_tier == "human_verified" else "unverified",
            url,
            [
                Evidence(
                    f"BRD section {requirement.id}, {doc.trust_tier.replace('_', ' ')}",
                    f"{brd_path}#{anchor}",
                    url,
                )
            ],
        )
        epics: dict[int | None, TraceRow] = {}
        for story in stories:
            if requirement.id not in requirement_ids(story.body or ""):
                continue
            number = b.parent.get(story.number)
            epic = b.items.get(number) if number is not None else None
            if number not in epics:
                epics[number] = (
                    TraceRow(
                        "epic",
                        f"#{epic.number}",
                        epic.title,
                        item_status(epic),
                        epic.url,
                        [
                            Evidence(
                                f"#{story.number} names #{epic.number} as its parent",
                                f"Issue #{story.number}",
                                story.url,
                            )
                        ],
                    )
                    if epic
                    else TraceRow("epic", "none", "No Epic", "missing")
                )
                row.children.append(epics[number])
            epics[number].children.append(b.story(story, requirement.id))
        rows.append(row)
    _number(rows, [0])
    trace = Trace(brd_path, doc.title or brd_path, rows)
    canonical = json.dumps(
        {k: v for k, v in trace.as_dict().items() if k != "hash"},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    trace.hash = hashlib.sha256(canonical.encode()).hexdigest()
    return trace
