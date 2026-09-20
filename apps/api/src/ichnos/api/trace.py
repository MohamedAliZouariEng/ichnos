"""Traceability endpoints (ADR-0022, ADR-0023); confirmations are never written to GitHub."""

import datetime as dt
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from ichnos.api.deps import SessionDep
from ichnos.api.session import ApproverDep
from ichnos.api.workspaces import get_workspace_or_404
from ichnos.db.base import as_utc
from ichnos.db.models import AuditEvent, Document, LinkConfirmation
from ichnos.trace.build import TraceError, TraceRow, build_trace
from ichnos.trace.confirm import confirmed_links, inferred_links
from ichnos.trace.validate import validate_trace

router = APIRouter(tags=["trace"])
ERRORS: dict[int | str, dict[str, str]] = {
    401: {"description": "Sign in to confirm"},
    404: {"description": "Workspace, BRD or inferred link not found"},
    409: {"description": "Already confirmed"},
}


class ConfirmationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    brd: str = Field(max_length=500, description="The BRD whose trace contains the link")
    link: str = Field(max_length=500, description="The inferred link's identity")
    note: str | None = Field(default=None, max_length=1000)


class ConfirmationRead(BaseModel):
    link: str
    confirmed_by: str
    note: str | None
    created_at: dt.datetime


def _read(row: LinkConfirmation) -> ConfirmationRead:
    return ConfirmationRead(
        link=row.link,
        confirmed_by=row.confirmed_by,
        note=row.note,
        created_at=as_utc(row.created_at),
    )


@router.get(
    "/api/workspaces/{workspace_id}/trace/confirmations",
    response_model=list[ConfirmationRead],
    operation_id="listLinkConfirmations",
)
def list_confirmations(workspace_id: str, session: SessionDep) -> list[ConfirmationRead]:
    workspace = get_workspace_or_404(session, workspace_id)
    rows = session.scalars(
        select(LinkConfirmation)
        .where(LinkConfirmation.workspace_id == workspace.id)
        .order_by(LinkConfirmation.created_at)
    )
    return [_read(row) for row in rows]


@router.post(
    "/api/workspaces/{workspace_id}/trace/confirmations",
    response_model=ConfirmationRead,
    status_code=status.HTTP_201_CREATED,
    operation_id="confirmLink",
    responses=ERRORS,
)
def confirm_link(
    workspace_id: str, body: ConfirmationRequest, approver: ApproverDep, session: SessionDep
) -> ConfirmationRead:
    """Record that a person checked an inferred link; nothing is written to GitHub."""
    workspace = get_workspace_or_404(session, workspace_id)
    try:
        trace = build_trace(session, workspace, body.brd)
    except TraceError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    if body.link not in inferred_links(trace):
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "No inferred link with that identity in this trace."
        )
    existing = session.scalar(
        select(LinkConfirmation).where(
            LinkConfirmation.workspace_id == workspace.id, LinkConfirmation.link == body.link
        )
    )
    if existing is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"Already confirmed by {existing.confirmed_by}."
        )
    row = LinkConfirmation(
        workspace_id=workspace.id,
        link=body.link,
        confirmed_by=approver.identity,
        note=(body.note or "").strip() or None,
    )
    session.add(row)
    session.add(
        AuditEvent(
            actor=approver.identity,
            event_type="link.confirmed",
            workspace_id=workspace.id,
            details={"link": body.link, "brd": body.brd, "note": row.note},
        )
    )
    session.commit()
    return _read(row)


@router.delete(
    "/api/workspaces/{workspace_id}/trace/confirmations",
    response_model=ConfirmationRead,
    operation_id="withdrawLinkConfirmation",
    responses=ERRORS,
)
def withdraw_confirmation(
    workspace_id: str,
    link: Annotated[str, Query(max_length=500)],
    approver: ApproverDep,
    session: SessionDep,
) -> ConfirmationRead:
    workspace = get_workspace_or_404(session, workspace_id)
    row = session.scalar(
        select(LinkConfirmation).where(
            LinkConfirmation.workspace_id == workspace.id, LinkConfirmation.link == link
        )
    )
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "That link is not confirmed.")
    read = _read(row)
    session.delete(row)
    session.add(
        AuditEvent(
            actor=approver.identity,
            event_type="link.withdrawn",
            workspace_id=workspace.id,
            details={"link": link, "was_confirmed_by": read.confirmed_by},
        )
    )
    session.commit()
    return read


class EvidenceRead(BaseModel):
    text: str
    source: str
    url: str | None
    origin: str
    link: str | None
    confirmed: bool


class TraceRowRead(BaseModel):
    id: str
    level: str
    key: str
    title: str
    status: str
    url: str | None
    evidence: list[EvidenceRead]
    children: list["TraceRowRead"]


class TraceFindingRead(BaseModel):
    code: str
    level: str
    row: str
    message: str


class TraceRead(BaseModel):
    brd: str
    title: str
    hash: str
    rows: list[TraceRowRead]
    findings: list[TraceFindingRead]


class BrdRead(BaseModel):
    path: str
    title: str | None
    trust_tier: str
    status: str | None


TraceRowRead.model_rebuild()


def _row(row: TraceRow, confirmed: set[str]) -> TraceRowRead:
    return TraceRowRead(
        id=row.id,
        level=row.level,
        key=row.key,
        title=row.title,
        status=row.status,
        url=row.url,
        evidence=[
            EvidenceRead(
                text=e.text,
                source=e.source,
                url=e.url,
                origin=e.origin,
                link=e.link,
                confirmed=bool(e.link and e.link in confirmed),
            )
            for e in row.evidence
        ],
        children=[_row(child, confirmed) for child in row.children],
    )


@router.get(
    "/api/workspaces/{workspace_id}/trace/brds",
    response_model=list[BrdRead],
    operation_id="listTraceableBrds",
)
def list_brds(workspace_id: str, session: SessionDep) -> list[BrdRead]:
    workspace = get_workspace_or_404(session, workspace_id)
    documents = session.scalars(
        select(Document)
        .where(Document.workspace_id == workspace.id, Document.doc_type == "BRD")
        .order_by(Document.path)
    )
    return [
        BrdRead(path=d.path, title=d.title, trust_tier=d.trust_tier, status=d.status)
        for d in documents
    ]


@router.get(
    "/api/workspaces/{workspace_id}/trace",
    response_model=TraceRead,
    operation_id="getTrace",
    responses={404: {"description": "Workspace or BRD not found"}},
)
def get_trace(
    workspace_id: str, brd: Annotated[str, Query(max_length=500)], session: SessionDep
) -> TraceRead:
    """A BRD's requirements traced to Stories, pull requests, commits and tests, validated."""
    workspace = get_workspace_or_404(session, workspace_id)
    try:
        trace = build_trace(session, workspace, brd)
    except TraceError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    confirmed = confirmed_links(session, workspace.id)
    document = session.scalar(
        select(Document).where(Document.workspace_id == workspace.id, Document.path == brd)
    )
    findings = validate_trace(
        trace, confirmed=confirmed, brd_frontmatter=document.frontmatter if document else None
    )
    return TraceRead(
        brd=trace.brd,
        title=trace.title,
        hash=trace.hash,
        rows=[_row(row, confirmed) for row in trace.rows],
        findings=[TraceFindingRead(**f.as_dict()) for f in findings],
    )
