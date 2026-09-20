"""Propose a Story's draft pull request from its implementation plan (ADR-0021)."""

from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import select

from ichnos.api.approvals import DECISION_ERRORS, ApprovalDetail, _detail
from ichnos.api.artifacts import artifact_path
from ichnos.api.context import pack_with_code
from ichnos.api.deps import SessionDep, SettingsDep
from ichnos.api.session import ApproverDep
from ichnos.approvals import PENDING
from ichnos.approvals.service import propose
from ichnos.approvals.story_pr import ClaimError, build_draft_pr
from ichnos.context.pack import PackError
from ichnos.db.models import Approval, Artifact, ArtifactVersion, GitHubItem, Run, Workspace
from ichnos.github.contents import ContentsError
from ichnos.workflows.implementation import PLAN_KIND

router = APIRouter(tags=["approvals"])


@router.post(
    "/api/artifacts/{artifact_id}/draft-pull-request",
    response_model=ApprovalDetail,
    status_code=status.HTTP_201_CREATED,
    operation_id="proposeDraftPullRequest",
    responses=DECISION_ERRORS,
)
def propose_draft_pull_request(
    artifact_id: str,
    approver: ApproverDep,
    session: SessionDep,
    settings: SettingsDep,
    request: Request,
) -> ApprovalDetail:
    """Rebuild the Story's context, check it is the one the plan used, and propose the draft."""
    artifact = session.get(Artifact, artifact_id)
    if artifact is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Artifact not found.")
    if artifact.kind != PLAN_KIND:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Draft pull requests are opened from implementation plans."
        )
    recorded = dict(ref.split(":", 1) for ref in artifact.source_ids or [] if ":" in ref)
    story_ref, pack_ref = recorded.get("story"), recorded.get("pack")
    if not story_ref or not story_ref.isdigit() or not pack_ref:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "This plan does not record its Story and pack."
        )
    waiting = session.scalar(
        select(Approval).where(
            Approval.artifact_id == artifact.id, Approval.status.in_((PENDING, "approved"))
        )
    )
    if waiting is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "A draft pull request for this plan is waiting."
        )
    workspace = session.get(Workspace, artifact.workspace_id)
    token = settings.github_token
    if workspace is None or token is None or not token.get_secret_value():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No GitHub token is configured.")
    number = int(story_ref)
    try:
        pack, _ = pack_with_code(
            session, workspace, number, settings.github_token, request.app.state.github_transport
        )
    except PackError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except ContentsError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc
    if pack.hash != pack_ref:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"The Story's context changed since this plan was drafted (pack {pack_ref[:12]}, "
            f"now {pack.hash[:12]}); draft a new plan.",
        )
    version = session.scalar(
        select(ArtifactVersion).where(
            ArtifactVersion.artifact_id == artifact.id,
            ArtifactVersion.number == artifact.current_version,
        )
    )
    story = session.scalar(
        select(GitHubItem).where(
            GitHubItem.workspace_id == workspace.id, GitHubItem.number == number
        )
    )
    assert version is not None and story is not None
    repository = f"{workspace.repo_owner}/{workspace.repo_name}"
    try:
        payload, summary = build_draft_pr(
            story_number=number,
            story_title=story.title,
            story_body=story.body or "",
            plan_markdown=version.content,
            plan_version=version.number,
            plan_path=artifact_path(artifact),
            pack=pack.as_dict(),
            approver=approver.identity,
            repository=repository,
            base_branch=workspace.branch,
            branch=f"ichnos/{artifact.slug}",
            model=version.actor,
        )
    except ClaimError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    run = Run(
        workspace_id=workspace.id,
        workflow_type="draft_pr",
        status="waiting",
        inputs={"artifact_id": artifact.id, "version": version.number},
    )
    session.add(run)
    session.flush()
    approval = propose(
        session,
        run_id=run.id,
        workspace_id=workspace.id,
        action_type="draft_pull_request",
        target=repository,
        branch=workspace.branch,
        payload=payload,
        base={"artifact_id": artifact.id, "artifact_version": artifact.current_version},
        summary=summary,
        proposed_by=approver.identity,
        artifact_id=artifact.id,
    )
    return _detail(approval)
