"""Index stage: rebuild the full-text chunks from synced data (ADR-0008)."""

from collections import defaultdict

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ichnos.db.models import Chunk, Commit, Document, GitHubComment, GitHubItem, Workspace
from ichnos.github.reader import GitHubReader
from ichnos.knowledge.chunks import ChunkText, chunk_markdown

COMMENT_LABELS = {
    "issue_comment": "Comment",
    "review": "Review",
    "review_comment": "Review comment",
}


def sync_index(session: Session, reader: GitHubReader, workspace: Workspace) -> dict[str, int]:
    """Uses no GitHub requests. The FTS5 triggers keep chunks_fts in step."""
    ws = workspace.id
    session.execute(delete(Chunk).where(Chunk.workspace_id == ws))
    total = 0

    def add(kind: str, key: str, pieces: list[ChunkText]) -> None:
        nonlocal total
        for ordinal, piece in enumerate(pieces):
            session.add(
                Chunk(
                    workspace_id=ws,
                    source_kind=kind,
                    source_key=key,
                    ordinal=ordinal,
                    heading=piece.heading,
                    text=piece.text,
                    start_line=piece.start_line,
                )
            )
            total += 1

    for doc in session.scalars(select(Document).where(Document.workspace_id == ws)):
        if doc.kind != "log":
            add("document", doc.path, chunk_markdown(doc.body, default_heading=doc.title))

    comments: dict[int, list[GitHubComment]] = defaultdict(list)
    for comment in session.scalars(select(GitHubComment).where(GitHubComment.workspace_id == ws)):
        comments[comment.item_number].append(comment)
    for item in session.scalars(select(GitHubItem).where(GitHubItem.workspace_id == ws)):
        pieces = chunk_markdown(f"{item.title}\n\n{item.body or ''}", default_heading=item.title)
        for comment in comments[item.number]:
            label = (
                f"{COMMENT_LABELS.get(comment.kind, 'Comment')} by {comment.author or 'unknown'}"
            )
            pieces += chunk_markdown(comment.body, default_heading=label)
        add(item.item_type, str(item.number), pieces)

    for commit in session.scalars(select(Commit).where(Commit.workspace_id == ws)):
        first_line = commit.message.splitlines()[0] if commit.message else commit.sha[:7]
        add("commit", commit.sha, chunk_markdown(commit.message, default_heading=first_line))

    return {"chunks_indexed": total}
