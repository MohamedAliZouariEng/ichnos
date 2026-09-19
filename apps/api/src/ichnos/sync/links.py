"""Links stage: rebuild every link of the workspace from synced data (ADR-0010)."""

from collections import defaultdict
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ichnos.db.models import (
    Commit,
    Document,
    GitHubComment,
    GitHubItem,
    Link,
    PullRequestFile,
    Workspace,
)
from ichnos.github.reader import GitHubReader
from ichnos.knowledge.links import CommentText, DocText, ItemText, Snapshot, extract_links


def _resources(frontmatter: dict[str, Any]) -> list[str]:
    sources = frontmatter.get("sources")
    if not isinstance(sources, list):
        return []
    return [str(s["resource"]) for s in sources if isinstance(s, dict) and s.get("resource")]


def build_snapshot(session: Session, workspace_id: str) -> Snapshot:
    pr_files: dict[int, list[str]] = defaultdict(list)
    for file in session.scalars(
        select(PullRequestFile).where(PullRequestFile.workspace_id == workspace_id)
    ):
        pr_files[file.pr_number].append(file.path)
    return Snapshot(
        documents={
            doc.path: DocText(doc.body, _resources(doc.frontmatter or {}))
            for doc in session.scalars(
                select(Document).where(Document.workspace_id == workspace_id)
            )
        },
        items={
            item.number: ItemText(item.item_type, item.body or "")
            for item in session.scalars(
                select(GitHubItem).where(GitHubItem.workspace_id == workspace_id)
            )
        },
        comments=[
            CommentText(comment.item_number, comment.author, comment.kind, comment.body)
            for comment in session.scalars(
                select(GitHubComment).where(GitHubComment.workspace_id == workspace_id)
            )
        ],
        commits={
            commit.sha: commit.message
            for commit in session.scalars(select(Commit).where(Commit.workspace_id == workspace_id))
        },
        pr_files=dict(pr_files),
    )


def sync_links(session: Session, reader: GitHubReader, workspace: Workspace) -> dict[str, int]:
    """Uses no GitHub requests: links are derived from what earlier stages stored."""
    records = extract_links(build_snapshot(session, workspace.id))
    session.execute(delete(Link).where(Link.workspace_id == workspace.id))
    for record in records:
        session.add(
            Link(
                workspace_id=workspace.id,
                source_kind=record.source.kind,
                source_key=record.source.key,
                target_kind=record.target.kind,
                target_key=record.target.key,
                relation=record.relation,
                origin=record.origin,
                evidence=record.evidence,
                confidence=record.confidence,
                resolved=record.resolved,
            )
        )
    return {
        "links_explicit": sum(1 for r in records if r.origin == "explicit"),
        "links_inferred": sum(1 for r in records if r.origin == "inferred"),
        "links_unresolved": sum(1 for r in records if not r.resolved),
    }
