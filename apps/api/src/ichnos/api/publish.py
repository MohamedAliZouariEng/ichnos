"""Propose publishing an artifact to GitHub (ADR-0014, ADR-0017); approval executes it."""

from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import select

from ichnos.api.approvals import DECISION_ERRORS, ApprovalDetail, _detail
from ichnos.api.deps import SessionDep, SettingsDep
from ichnos.api.session import ApproverDep
from ichnos.approvals import PENDING
from ichnos.approvals.publish import build_publish
from ichnos.approvals.service import ApprovalError, propose
from ichnos.db.base import utc_now
from ichnos.db.models import Approval, Artifact, Run, Workspace
from ichnos.github.contents import ContentsError, ContentsReader

router = APIRouter(tags=["approvals"])


@router.post(
    "/api/artifacts/{artifact_id}/publish",
    response_model=ApprovalDetail,
    status_code=status.HTTP_201_CREATED,
    operation_id="publishArtifact",
    responses=DECISION_ERRORS,
)
def publish_artifact(
    artifact_id: str,
    approver: ApproverDep,
    session: SessionDep,
    settings: SettingsDep,
    request: Request,
) -> ApprovalDetail:
    """Build the package against the repository's current files and propose it; writes nothing."""
    artifact = session.get(Artifact, artifact_id)
    if artifact is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Artifact not found.")
    if artifact.status != "draft":
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"This artifact is {artifact.status}; only drafts are published.",
        )
    pending = session.scalar(
        select(Approval).where(Approval.artifact_id == artifact.id, Approval.status == PENDING)
    )
    if pending is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "A publish action is already waiting.")
    workspace = session.get(Workspace, artifact.workspace_id)
    token = settings.github_token
    if workspace is None or token is None or not token.get_secret_value():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No GitHub token is configured.")
    repository = f"{workspace.repo_owner}/{workspace.repo_name}"
    try:
        with ContentsReader(repository, token, request.app.state.github_transport) as reader:
            payload, base, summary = build_publish(
                session,
                artifact,
                approver=approver.identity,
                reader=reader,
                repository=repository,
                base_branch=workspace.branch,
                now=utc_now(),
            )
    except ApprovalError as exc:
        raise HTTPException(exc.status, exc.message) from exc
    except ContentsError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc

    run = Run(
        workspace_id=workspace.id,
        workflow_type="publish",
        status="waiting",
        inputs={"artifact_id": artifact.id, "version": artifact.current_version},
    )
    session.add(run)
    session.flush()
    approval = propose(
        session,
        run_id=run.id,
        workspace_id=workspace.id,
        action_type="docs_pull_request",
        target=repository,
        branch=workspace.branch,
        payload=payload,
        base=base,
        summary=summary,
        proposed_by=approver.identity,
        artifact_id=artifact.id,
    )
    return _detail(approval)
