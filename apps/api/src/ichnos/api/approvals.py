"""Pending GitHub writes and the decisions on them (ADR-0015, ADR-0016)."""

import datetime as dt
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from ichnos.api.deps import SessionDep, SettingsDep
from ichnos.api.session import ApproverDep
from ichnos.api.workspaces import NOT_FOUND, get_workspace_or_404
from ichnos.approvals import verify
from ichnos.approvals.service import ApprovalError, approve, reject
from ichnos.db.base import as_utc
from ichnos.db.models import Approval

router = APIRouter(tags=["approvals"])

DECISION_ERRORS: dict[int | str, dict[str, Any]] = {
    400: {"description": "No GitHub token configured"},
    401: {"description": "Sign in to approve"},
    404: {"description": "Approval not found"},
    409: {"description": "Not pending, changed since reviewed, or prepared for someone else"},
}


class ApprovalSummary(BaseModel):
    id: str
    workspace_id: str | None
    run_id: str
    artifact_id: str | None
    action_type: str
    target: str
    branch: str | None
    summary: str | None
    status: str
    payload_hash: str
    proposed_by: str | None
    decided_by: str | None
    decided_at: dt.datetime | None
    decision_note: str | None
    created_at: dt.datetime
    executed_at: dt.datetime | None
    error: str | None
    result: dict[str, Any] | None


class ApprovalDetail(ApprovalSummary):
    payload: dict[str, Any]
    base: dict[str, Any]
    hash_ok: bool


class Decision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    payload_hash: str = Field(min_length=64, max_length=64)


class Rejection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    note: str | None = Field(default=None, max_length=1000)


def _when(value: dt.datetime | None) -> dt.datetime | None:
    return as_utc(value) if value else None


def _summary(approval: Approval) -> ApprovalSummary:
    return ApprovalSummary(
        id=approval.id,
        workspace_id=approval.workspace_id,
        run_id=approval.run_id,
        artifact_id=approval.artifact_id,
        action_type=approval.action_type,
        target=approval.target,
        branch=approval.branch,
        summary=approval.summary,
        status=approval.status,
        payload_hash=approval.payload_hash,
        proposed_by=approval.proposed_by,
        decided_by=approval.decided_by,
        decided_at=_when(approval.decided_at),
        decision_note=approval.decision_note,
        created_at=as_utc(approval.created_at),
        executed_at=_when(approval.executed_at),
        error=approval.error,
        result=approval.result,
    )


def _detail(approval: Approval) -> ApprovalDetail:
    return ApprovalDetail(
        **_summary(approval).model_dump(),
        payload=approval.payload or {},
        base=approval.base or {},
        hash_ok=verify(approval),
    )


@router.get(
    "/api/workspaces/{workspace_id}/approvals",
    response_model=list[ApprovalSummary],
    operation_id="listApprovals",
    responses=NOT_FOUND,
)
def list_approvals(
    workspace_id: str,
    session: SessionDep,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[ApprovalSummary]:
    get_workspace_or_404(session, workspace_id)
    query = select(Approval).where(Approval.workspace_id == workspace_id)
    if status_filter:
        query = query.where(Approval.status == status_filter)
    approvals = session.scalars(query.order_by(Approval.created_at.desc()).limit(limit)).all()
    return [_summary(approval) for approval in approvals]


@router.get(
    "/api/approvals/{approval_id}",
    response_model=ApprovalDetail,
    operation_id="getApproval",
    responses={404: {"description": "Approval not found"}},
)
def get_approval(approval_id: str, session: SessionDep) -> ApprovalDetail:
    approval = session.get(Approval, approval_id)
    if approval is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Approval not found.")
    return _detail(approval)


@router.post(
    "/api/approvals/{approval_id}/approve",
    response_model=ApprovalDetail,
    operation_id="approveAction",
    responses=DECISION_ERRORS,
)
def approve_action(
    approval_id: str,
    body: Decision,
    approver: ApproverDep,
    session: SessionDep,
    settings: SettingsDep,
    request: Request,
) -> ApprovalDetail:
    """Execute exactly the stored payload, after every check (ADR-0015)."""
    try:
        approval = approve(
            session,
            approval_id,
            approver=approver.identity,
            shown_hash=body.payload_hash,
            token=settings.github_token,
            transport=request.app.state.github_transport,
        )
    except ApprovalError as exc:
        raise HTTPException(exc.status, exc.message) from exc
    return _detail(approval)


@router.post(
    "/api/approvals/{approval_id}/reject",
    response_model=ApprovalDetail,
    operation_id="rejectAction",
    responses=DECISION_ERRORS,
)
def reject_action(
    approval_id: str, body: Rejection, approver: ApproverDep, session: SessionDep
) -> ApprovalDetail:
    try:
        approval = reject(session, approval_id, approver=approver.identity, note=body.note)
    except ApprovalError as exc:
        raise HTTPException(exc.status, exc.message) from exc
    return _detail(approval)
