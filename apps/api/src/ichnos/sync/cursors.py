"""Sync cursors: where the last successful sync of each source stopped."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from ichnos.db.models import SyncCursor


def _row(session: Session, workspace_id: str, source: str) -> SyncCursor | None:
    return session.scalar(
        select(SyncCursor).where(
            SyncCursor.workspace_id == workspace_id, SyncCursor.source == source
        )
    )


def get_cursor(session: Session, workspace_id: str, source: str) -> str | None:
    row = _row(session, workspace_id, source)
    return None if row is None else row.cursor


def set_cursor(session: Session, workspace_id: str, source: str, value: str) -> None:
    """Stage a cursor update; it only takes effect when the caller's transaction commits."""
    row = _row(session, workspace_id, source)
    if row is None:
        session.add(SyncCursor(workspace_id=workspace_id, source=source, cursor=value))
    else:
        row.cursor = value
