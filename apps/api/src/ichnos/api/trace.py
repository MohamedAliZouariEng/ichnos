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
from ichnos.db.models import AuditEvent, LinkConfirmation
from ichnos.trace.build import TraceError, build_trace
from ichnos.trace.confirm import inferred_links

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
