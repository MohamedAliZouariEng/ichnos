"""Plan an approved BRD (Phase 4); approving or rejecting its Issues resumes the run."""

from typing import Any

from fastapi import APIRouter, FastAPI, HTTPException, Request, status

from ichnos.api.config import NOT_CONFIGURED
from ichnos.api.deps import SessionDep, SettingsDep
from ichnos.api.runs import RunDetail, _detail
from ichnos.api.session import ApproverDep
from ichnos.db.models import Approval, Artifact, Run, Workspace
from ichnos.llm import provider_from_settings
from ichnos.settings import Settings
from ichnos.workflows import plan_flow
from ichnos.workflows.engine import resume_run, start_run

router = APIRouter(tags=["runs"])


def _services(settings: Settings, app: FastAPI, model: str | None = None) -> dict[str, Any]:
    return {
        "provider": provider_from_settings(
            settings, model_override=model, transport=app.state.llm_transport
        ),
        "token": settings.github_token,
        "transport": app.state.github_transport,
    }


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
