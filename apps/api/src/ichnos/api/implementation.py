"""Start an implementation run for a Story (Phase 5); it writes nothing to GitHub."""

from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import select

from ichnos.api.config import NOT_CONFIGURED
from ichnos.api.deps import SessionDep, SettingsDep
from ichnos.api.runs import RunDetail, _detail
from ichnos.api.workspaces import get_workspace_or_404
from ichnos.db.models import GitHubItem, Run
from ichnos.llm import provider_from_settings
from ichnos.workflows import implementation_flow
from ichnos.workflows.engine import start_run

router = APIRouter(tags=["runs"])


@router.post(
    "/api/workspaces/{workspace_id}/stories/{number}/plan",
    response_model=RunDetail,
    status_code=status.HTTP_202_ACCEPTED,
    operation_id="planStory",
    responses={
        400: {"description": "No model configured"},
        404: {"description": "Workspace or Issue not found"},
    },
)
def plan_story(
    workspace_id: str,
    number: int,
    session: SessionDep,
    settings: SettingsDep,
    request: Request,
) -> RunDetail:
    """Build the context pack, draft the plan and store it for review."""
    workspace = get_workspace_or_404(session, workspace_id)
    story = session.scalar(
        select(GitHubItem).where(
            GitHubItem.workspace_id == workspace.id, GitHubItem.number == number
        )
    )
    if story is None or story.item_type == "pull_request":
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Issue #{number} is not synced.")
    provider = provider_from_settings(
        settings, model_override=workspace.llm_model, transport=request.app.state.llm_transport
    )
    if provider is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, NOT_CONFIGURED)
    run_id = start_run(
        request.app.state.session_factory,
        request.app.state.runner,
        workspace_id=workspace.id,
        workflow_type=implementation_flow.WORKFLOW_TYPE,
        stages=implementation_flow.STAGES,
        initial={"story": number},
        checkpoint_path=settings.checkpoint_path(),
        services={
            "provider": provider,
            "token": settings.github_token,
            "transport": request.app.state.github_transport,
        },
    )
    run = session.get(Run, run_id)
    assert run is not None
    return _detail(session, run)
