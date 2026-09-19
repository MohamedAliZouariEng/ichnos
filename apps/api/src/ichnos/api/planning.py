"""Plan an approved BRD (Phase 4); approving or rejecting its Issues resumes the run."""

from typing import Any

from fastapi import APIRouter, FastAPI, HTTPException, Request, status
from sqlalchemy import select

from ichnos.api.config import NOT_CONFIGURED
from ichnos.api.deps import SessionDep, SettingsDep
from ichnos.api.runs import RunDetail, _detail
from ichnos.api.session import ApproverDep
from ichnos.db.models import Approval, Artifact, Run, Workspace
from ichnos.llm import provider_from_settings
from ichnos.settings import Settings
from ichnos.workflows import plan_flow
from ichnos.workflows.engine import StageContext, resume_run, start_run

router = APIRouter(tags=["runs"])


def _services(settings: Settings, app: FastAPI, model: str | None = None) -> dict[str, Any]:
    return {
        "provider": provider_from_settings(
            settings, model_override=model, transport=app.state.llm_transport
        ),
        "token": settings.github_token,
        "transport": app.state.github_transport,
    }


def already_planned(session: Any, artifact: Artifact) -> str | None:
    """Why a BRD cannot be planned again, or None: one plan per BRD unless it was rejected."""
    runs = session.scalars(
        select(Run).where(
            Run.workspace_id == artifact.workspace_id,
            Run.workflow_type == plan_flow.WORKFLOW_TYPE,
        )
    ).all()
    for run in runs:
        if (run.inputs or {}).get("artifact_id") != artifact.id:
            continue
        if run.status in ("queued", "running", "waiting"):
            return "A planning run for this BRD is already in progress; decide on it in Approvals."
        issues = ((run.outputs or {}).get("result") or {}).get("issues")
        if issues:
            return f"This BRD already has Issues (Epic #{issues['epic']['number']})."
    return None


@router.post(
    "/api/artifacts/{artifact_id}/plan",
    response_model=RunDetail,
    status_code=status.HTTP_202_ACCEPTED,
    operation_id="planArtifact",
    responses={
        400: {"description": "No model or token configured"},
        401: {"description": "Sign in to approve"},
        404: {"description": "Artifact not found"},
        409: {"description": "Only approved BRDs are planned"},
    },
)
def plan_artifact(
    artifact_id: str,
    approver: ApproverDep,
    session: SessionDep,
    settings: SettingsDep,
    request: Request,
) -> RunDetail:
    """Start a planning run; it waits for the decision on its Issues."""
    artifact = session.get(Artifact, artifact_id)
    if artifact is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Artifact not found.")
    if artifact.kind != "brd" or artifact.status != "approved":
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Only approved BRDs are planned; publish and approve it first.",
        )
    reason = already_planned(session, artifact)
    if reason:
        raise HTTPException(status.HTTP_409_CONFLICT, reason)
    workspace = session.get(Workspace, artifact.workspace_id)
    assert workspace is not None
    services = _services(settings, request.app, workspace.llm_model)
    if services["provider"] is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, NOT_CONFIGURED)
    run_id = start_run(
        request.app.state.session_factory,
        request.app.state.runner,
        workspace_id=workspace.id,
        workflow_type=plan_flow.WORKFLOW_TYPE,
        stages=plan_flow.STAGES,
        initial={
            "artifact_id": artifact.id,
            "approver": approver.identity,
            "repository": f"{workspace.repo_owner}/{workspace.repo_name}",
            "base_branch": workspace.branch,
        },
        checkpoint_path=settings.checkpoint_path(),
        services=services,
    )
    run = session.get(Run, run_id)
    assert run is not None
    return _detail(session, run)


def resume_if_waiting(app: FastAPI, settings: Settings, approval: Approval) -> None:
    """A decided create_issues action continues the planning run that waits for it."""
    if approval.action_type != "create_issues":
        return
    with app.state.session_factory() as session:
        run = session.get(Run, approval.run_id)
        if run is None or run.status != "waiting" or run.workflow_type != plan_flow.WORKFLOW_TYPE:
            return
        workspace = session.get(Workspace, run.workspace_id)
        model = workspace.llm_model if workspace else None
    resume_run(
        app.state.session_factory,
        app.state.runner,
        approval.run_id,
        stages=plan_flow.STAGES,
        decision={"approval_id": approval.id, "status": approval.status, "result": approval.result},
        checkpoint_path=settings.checkpoint_path(),
        services=_services(settings, app, model),
    )


@router.post(
    "/api/runs/{run_id}/link-issues",
    response_model=RunDetail,
    operation_id="linkIssues",
    responses={
        401: {"description": "Sign in to approve"},
        404: {"description": "Planning run not found"},
        409: {"description": "No Issues, already proposed, or the BRD is not merged yet"},
    },
)
def link_issues(
    run_id: str,
    approver: ApproverDep,
    session: SessionDep,
    settings: SettingsDep,
    request: Request,
) -> RunDetail:
    """Propose writing a finished plan's Issue numbers into its merged BRD."""
    run = session.get(Run, run_id)
    if run is None or run.workflow_type != plan_flow.WORKFLOW_TYPE:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Planning run not found.")
    result = dict((run.outputs or {}).get("result") or {})
    if not result.get("issues"):
        raise HTTPException(status.HTTP_409_CONFLICT, "This planning run created no Issues.")
    earlier = result.get("follow_up_approval_id")
    if earlier:
        previous = session.get(Approval, earlier)
        if previous is not None and previous.status in ("pending", "approved", "executed"):
            raise HTTPException(status.HTTP_409_CONFLICT, "Linking is already proposed.")
    inputs = dict(run.inputs or {})
    artifact = session.get(Artifact, str(inputs.get("artifact_id")))
    if artifact is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "The planned BRD no longer exists.")
    data = {
        **inputs,
        "approver": approver.identity,
        "brd_path": f"docs/specs/{artifact.slug}/{artifact.kind}.md",
    }
    context = StageContext(
        run.id,
        run.workspace_id,
        request.app.state.session_factory,
        _services(settings, request.app),
    )
    approval_id = plan_flow.link_issues_into_brd(data, context, result["issues"])
    if approval_id is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"{data['brd_path']} is not on {data['base_branch']} yet; "
            "merge its pull request first.",
        )
    run.outputs = {
        **(run.outputs or {}),
        "result": {**result, "follow_up_approval_id": approval_id},
    }
    session.commit()
    return _detail(session, run)
