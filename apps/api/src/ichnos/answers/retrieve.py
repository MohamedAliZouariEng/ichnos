"""Retrieval for grounded answers (ADR-0024): numbered sources with links, trust and flags.

Reuses the full-text index, adds what matching BRDs cite and the traces of their matching
requirements, so an answer can reach from a decision to the test that checks it. A trace
source carries its evidence trail: decision, requirement, Story, pull request and tests.
"""

import datetime as dt
import re
from collections import Counter
from collections.abc import Iterator
from dataclasses import asdict, dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ichnos.context.pack import _doc_flags
from ichnos.db.models import Document, GitHubItem, Link, Workspace
from ichnos.trace.build import TraceRow, build_trace
from ichnos.trace.confirm import confirmed_links
from ichnos.workflows.retrieval import SEARCH_SQL, keywords

MAX_CHUNK_SOURCES = 8
PER_FILE = 2
MAX_EXCERPT = 1_200
SKIPPED = ("index", "log")


@dataclass
class AnswerSource:
    id: str
    kind: str
    title: str
    locator: str
    url: str | None
    trust: str
    flags: list[str]
    excerpt: str
    links: list[dict[str, str]] = field(default_factory=list)


@dataclass
class Retrieved:
    question: str
    keywords: list[str]
    sources: list[AnswerSource] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def github_anchor(heading: str) -> str:
    """GitHub's heading anchor: lower case, punctuation removed, spaces as hyphens."""
    return re.sub(r"[^\w\- ]", "", heading.lower()).strip().replace(" ", "-")


def _item_flags(item: GitHubItem) -> list[str]:
    if item.state_reason == "not_planned":
        return ["not planned"]
    if item.item_type == "pull_request":
        if item.merged_at is not None:
            return ["merged"]
        if item.state == "closed":
            return ["closed without merging"]
        return ["draft"] if item.draft else []
    return ["closed"] if item.state == "closed" else []


def _walk(rows: list[TraceRow], depth: int = 0) -> Iterator[tuple[int, TraceRow]]:
    for row in rows:
        yield depth, row
        yield from _walk(row.children, depth + 1)


def _trace_text(requirement: TraceRow) -> str:
    lines = [
        f"{'  ' * depth}{row.level.replace('_', ' ')} {row.key}: {row.title} [{row.status}]"
        for depth, row in _walk([requirement])
    ]
    return "\n".join(lines)[:MAX_EXCERPT]


def _label(row: TraceRow) -> str:
    if row.level == "story":
        return f"Story {row.key}"
    if row.level == "pull_request":
        return row.key.replace("PR ", "Pull request ")
    return f"Test {row.key}"


def _trail(requirement: TraceRow, decisions: list[dict[str, str]]) -> list[dict[str, str]]:
    """Decision, requirement, Story, pull request and tests, each with its link."""
    links = list(decisions)
    if requirement.url:
        links.append({"label": f"BRD {requirement.key}", "url": requirement.url})
    for _, row in _walk([requirement]):
        if row.level in ("story", "pull_request", "test") and row.url:
            links.append({"label": _label(row), "url": row.url})
    return links


class _Sources:
    def __init__(self) -> None:
        self.items: list[AnswerSource] = []
        self.seen: set[str] = set()

    def add(self, key: str, **fields: Any) -> None:
        if key in self.seen:
            return
        self.seen.add(key)
        fields["excerpt"] = str(fields.get("excerpt", ""))[:MAX_EXCERPT]
        self.items.append(AnswerSource(id=f"S{len(self.items) + 1}", **fields))


def retrieve_for_question(
    session: Session,
    workspace: Workspace,
    question: str,
    *,
    today: dt.date | None = None,
    expand: bool = True,
) -> Retrieved:
    today = today or dt.date.today()
    words = keywords([question])
    result = Retrieved(question=question, keywords=words)
    if not words:
        return result
    ws = workspace.id
    repo_url = f"https://github.com/{workspace.repo_owner}/{workspace.repo_name}"
    docs = {d.path: d for d in session.scalars(select(Document).where(Document.workspace_id == ws))}
    items = {
        str(i.number): i
        for i in session.scalars(select(GitHubItem).where(GitHubItem.workspace_id == ws))
    }
    sources = _Sources()

    def doc_url(doc: Document, suffix: str = "") -> str:
        return f"{repo_url}/blob/{doc.commit_sha}/{doc.path}{suffix}"

    def add_document(doc: Document, heading: str | None, excerpt: str) -> None:
        anchor = github_anchor(heading) if heading and heading != doc.title else ""
        suffix = f"#{anchor}" if anchor else ""
        sources.add(
            f"doc:{doc.path}{suffix}",
            kind="document",
            title=doc.title or doc.path,
            locator=f"{doc.path}{suffix}",
            url=doc_url(doc, suffix),
            trust=doc.trust_tier,
            flags=_doc_flags(doc, today),
            excerpt=excerpt,
        )

    query = " OR ".join(f'"{word}"' for word in words)
    rows = session.execute(SEARCH_SQL, {"query": query, "workspace_id": ws}).all()
    per_file: Counter[str] = Counter()
    brds: dict[str, set[str]] = {}
    for row in rows:
        if len(sources.items) >= MAX_CHUNK_SOURCES:
            break
        if per_file[row.source_key] >= PER_FILE:
            continue
        if row.source_kind == "document":
            doc = docs.get(row.source_key)
            if doc is None or doc.kind in SKIPPED:
                continue
            add_document(doc, row.heading, row.text)
            if doc.doc_type == "BRD":
                brds.setdefault(doc.path, set()).add(str(row.heading or ""))
        elif row.source_kind in ("issue", "pull_request"):
            item = items.get(row.source_key)
            if item is None:
                continue
            sources.add(
                f"item:{item.number}",
                kind=item.item_type,
                title=item.title,
                locator=f"#{item.number}",
                url=item.url,
                trust="github",
                flags=_item_flags(item),
                excerpt=row.text,
            )
        elif row.source_kind == "commit":
            sha = row.source_key
            sources.add(
                f"commit:{sha}",
                kind="commit",
                title=row.heading or sha[:8],
                locator=sha[:8],
                url=f"{repo_url}/commit/{sha}",
                trust="repository",
                flags=[],
                excerpt=row.text,
            )
        else:
            continue
        per_file[row.source_key] += 1

    confirmed = confirmed_links(session, ws)
    for path, headings in brds.items() if expand else []:  # expand=False: full text only
        decisions: list[dict[str, str]] = []
        for link in session.scalars(
            select(Link).where(
                Link.workspace_id == ws,
                Link.source_kind == "document",
                Link.source_key == path,
                Link.relation == "cites",
                Link.target_kind == "document",
            )
        ):
            cited = docs.get(link.target_key)
            if cited is not None:
                add_document(cited, None, cited.body)
                decisions.append({"label": cited.title or cited.path, "url": doc_url(cited)})
        trace = build_trace(session, workspace, path)
        for requirement in trace.rows:
            statement = requirement.title.lower()
            shared = sum(1 for word in words if word in statement)
            if requirement.key not in headings and shared < 2:
                continue
            sources.add(
                f"trace:{path}#{requirement.key}",
                kind="trace",
                title=f"Trace of {requirement.key}",
                locator=f"trace of {path}#{requirement.key.lower()}",
                url=requirement.url,
                trust="derived",
                flags=[],
                excerpt=_trace_text(requirement),
                links=_trail(requirement, decisions),
            )
            for _, test_row in _walk([requirement]):
                if test_row.level != "test":
                    continue
                inferred = any(
                    e.origin == "inferred" and e.link not in confirmed for e in test_row.evidence
                )
                evidence = [e.text for e in test_row.evidence]
                sources.add(
                    f"test:{test_row.key}",
                    kind="test",
                    title=test_row.key,
                    locator=test_row.key,
                    url=test_row.url,
                    trust="repository",
                    flags=["inferred"] if inferred else [],
                    excerpt="; ".join([*evidence, f"status: {test_row.status}"]),
                )
            brd_doc = docs.get(path)  # the trace's own heading, Stories and PRs, as sources
            if brd_doc is not None:
                add_document(brd_doc, requirement.key, requirement.title)
            for _, item_row in _walk([requirement]):
                if item_row.level not in ("story", "pull_request"):
                    continue
                traced = items.get(item_row.key.split("#")[-1])
                if traced is not None:
                    sources.add(
                        f"item:{traced.number}",
                        kind=traced.item_type,
                        title=traced.title,
                        locator=f"#{traced.number}",
                        url=traced.url,
                        trust="github",
                        flags=_item_flags(traced),
                        excerpt=f"{traced.title}\n\n{traced.body or ''}",
                    )
    result.sources = sources.items
    return result
