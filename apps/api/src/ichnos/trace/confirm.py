"""Confirmed inferred links (ADR-0023): a person's judgement, kept in Ichnos only."""

from collections.abc import Iterator

from sqlalchemy import select
from sqlalchemy.orm import Session

from ichnos.db.models import LinkConfirmation
from ichnos.trace.build import Trace, TraceRow


def _walk(rows: list[TraceRow]) -> Iterator[TraceRow]:
    for row in rows:
        yield row
        yield from _walk(row.children)


def inferred_links(trace: Trace) -> set[str]:
    """Identities of the inferred links a trace relies on."""
    return {
        evidence.link
        for row in _walk(trace.rows)
        for evidence in row.evidence
        if evidence.origin == "inferred" and evidence.link
    }


def confirmed_links(session: Session, workspace_id: str) -> set[str]:
    return set(
        session.scalars(
            select(LinkConfirmation.link).where(LinkConfirmation.workspace_id == workspace_id)
        )
    )
