"""Reset a workspace's derived knowledge; the next sync rebuilds it (ADR-0002)."""

from typing import Any, cast

from sqlalchemy import CursorResult, delete
from sqlalchemy.orm import Session

from ichnos.db.models import (
    Chunk,
    Commit,
    Document,
    GitHubComment,
    GitHubItem,
    Link,
    PullRequestCommit,
    PullRequestFile,
    RepositoryFile,
    SyncCursor,
)

# Operational data (workspace, runs, approvals, audit events) is kept.
DERIVED = (
    Chunk,
    Link,
    PullRequestCommit,
    PullRequestFile,
    GitHubComment,
    Commit,
    GitHubItem,
    Document,
    RepositoryFile,
    SyncCursor,
)


def reset_knowledge(session: Session, workspace_id: str) -> dict[str, int]:
    """Delete every derived row and cursor of the workspace. The caller commits."""
    deleted: dict[str, int] = {}
    for model in DERIVED:
        result = cast(
            CursorResult[Any],
            session.execute(delete(model).where(model.workspace_id == workspace_id)),
        )
        deleted[model.__tablename__] = result.rowcount
    return deleted
