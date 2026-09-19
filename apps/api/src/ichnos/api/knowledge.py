"""Knowledge queries over synced data: links (ADR-0010)."""

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import and_, or_, select

from ichnos.api.deps import SessionDep
from ichnos.api.workspaces import NOT_FOUND, get_workspace_or_404
from ichnos.db.models import Link

router = APIRouter(prefix="/api/workspaces/{workspace_id}", tags=["knowledge"])


class LinkRead(BaseModel):
    source_kind: str
    source_key: str
    target_kind: str
    target_key: str
    relation: str
    origin: str
    evidence: str
    confidence: float
    resolved: bool


@router.get(
    "/links",
    response_model=list[LinkRead],
    operation_id="listLinks",
    responses=NOT_FOUND,
)
def list_links(
    workspace_id: str,
    session: SessionDep,
    kind: str | None = None,
    key: str | None = None,
    origin: Literal["explicit", "inferred"] | None = None,
) -> list[LinkRead]:
    """All links of the workspace, or only those touching one node (kind and key)."""
    get_workspace_or_404(session, workspace_id)
    query = select(Link).where(Link.workspace_id == workspace_id)
    if kind and key:
        query = query.where(
            or_(
                and_(Link.source_kind == kind, Link.source_key == key),
                and_(Link.target_kind == kind, Link.target_key == key),
            )
        )
    if origin:
        query = query.where(Link.origin == origin)
    rows = session.scalars(
        query.order_by(Link.origin, Link.source_kind, Link.source_key, Link.relation)
    ).all()
    return [
        LinkRead(
            source_kind=row.source_kind,
            source_key=row.source_key,
            target_kind=row.target_kind,
            target_key=row.target_key,
            relation=row.relation,
            origin=row.origin,
            evidence=row.evidence,
            confidence=row.confidence,
            resolved=row.resolved,
        )
        for row in rows
    ]
