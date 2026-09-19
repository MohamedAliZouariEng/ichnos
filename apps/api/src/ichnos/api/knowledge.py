"""Knowledge queries over synced data: links (ADR-0010) and search (ADR-0008)."""

import re
from typing import Annotated, Literal

from fastapi import APIRouter, Query
from pydantic import BaseModel
from sqlalchemy import and_, or_, select, text

from ichnos.api.deps import SessionDep
from ichnos.api.workspaces import NOT_FOUND, get_workspace_or_404
from ichnos.db.models import Document, GitHubItem, Link

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


TOKEN_RE = re.compile(r"\w+")
MAX_TERMS = 12
SEARCH_SQL = text(
    """
    SELECT c.source_kind, c.source_key, c.heading, c.start_line,
           snippet(chunks_fts, 1, '«', '»', '…', 16) AS snippet,
           bm25(chunks_fts) AS rank
    FROM chunks_fts JOIN chunks AS c ON c.id = chunks_fts.rowid
    WHERE chunks_fts MATCH :query AND c.workspace_id = :workspace_id
    ORDER BY rank
    LIMIT :limit
    """
)


def fts_query(user_text: str) -> str | None:
    """Words only, each quoted, all required; the last one also matches as a prefix."""
    terms = [f'"{term}"' for term in TOKEN_RE.findall(user_text)[:MAX_TERMS]]
    if not terms:
        return None
    terms[-1] += "*"
    return " ".join(terms)


class SearchHit(BaseModel):
    source_kind: str
    source_key: str
    title: str | None
    heading: str | None
    snippet: str
    start_line: int | None
    score: float


@router.get(
    "/search",
    response_model=list[SearchHit],
    operation_id="searchKnowledge",
    responses=NOT_FOUND,
)
def search(
    workspace_id: str,
    session: SessionDep,
    q: Annotated[str, Query(min_length=1, max_length=200)],
    limit: Annotated[int, Query(ge=1, le=50)] = 10,
) -> list[SearchHit]:
    """Full-text search over documents, Issues, pull requests, comments and commits."""
    get_workspace_or_404(session, workspace_id)
    query = fts_query(q)
    if query is None:
        return []
    rows = session.execute(
        SEARCH_SQL, {"query": query, "workspace_id": workspace_id, "limit": limit}
    ).all()
    titles: dict[tuple[str, str], str | None] = {}
    for path, title in session.execute(
        select(Document.path, Document.title).where(Document.workspace_id == workspace_id)
    ):
        titles[("document", path)] = title
    for number, kind, title in session.execute(
        select(GitHubItem.number, GitHubItem.item_type, GitHubItem.title).where(
            GitHubItem.workspace_id == workspace_id
        )
    ):
        titles[(kind, str(number))] = title
    return [
        SearchHit(
            source_kind=row.source_kind,
            source_key=row.source_key,
            title=titles.get((row.source_kind, row.source_key), row.heading),
            heading=row.heading,
            snippet=" ".join(str(row.snippet).split()),
            start_line=row.start_line,
            score=round(-float(row.rank), 4),
        )
        for row in rows
    ]
