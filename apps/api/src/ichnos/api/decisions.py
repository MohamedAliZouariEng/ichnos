"""Publish a decision proposed in an implementation plan as an ADR (ADR-0020)."""

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from ichnos.api.approvals import DECISION_ERRORS, ApprovalDetail, _detail
from ichnos.api.artifacts import artifact_path
from ichnos.api.deps import SessionDep, SettingsDep
from ichnos.api.session import ApproverDep
from ichnos.approvals.decisions import build_decision, next_adr_number, proposed_decisions
from ichnos.approvals.service import ApprovalError, propose
from ichnos.context.pack import PackError, build_pack
from ichnos.db.base import utc_now
from ichnos.db.models import Artifact, ArtifactVersion, Run, Workspace
from ichnos.github.contents import ContentsError, ContentsReader
from ichnos.workflows.implementation import PLAN_KIND, plan_findings

router = APIRouter(tags=["approvals"])


class DecisionChoice(BaseModel):
    model_config = ConfigDict(extra="forbid")

    index: int = Field(ge=1, description="1-based position in the plan's Proposed decisions")


@router.post(
    "/api/artifacts/{artifact_id}/decisions",
    response_model=ApprovalDetail,
    status_code=status.HTTP_201_CREATED,
    operation_id="proposeDecision",
    responses=DECISION_ERRORS,
)
def propose_decision(
    artifact_id: str,
    body: DecisionChoice,
    approver: ApproverDep,
    session: SessionDep,
    settings: SettingsDep,
    request: Request,
) -> ApprovalDetail:
    """Propose one of the plan's decisions as an OKF Decision concept; writes nothing."""
    artifact = session.get(Artifact, artifact_id)
    if artifact is None or artifact.kind != PLAN_KIND:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Implementation plan not found.")
    version = session.scalar(
        select(ArtifactVersion).where(
            ArtifactVersion.artifact_id == artifact.id,
            ArtifactVersion.number == artifact.current_version,
        )
    )
    proposals = proposed_decisions(version.content) if version else []
    if version is None or body.index > len(proposals):
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, f"The plan proposes no decision number {body.index}."
        )
    problems = [str(f["message"]) for f in plan_findings(version.content) if f["level"] == "error"]
    if problems:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Fix the plan's checks first: " + " ".join(problems)
        )
    recorded = dict(ref.split(":", 1) for ref in artifact.source_ids or [] if ":" in ref)
    story = int(recorded.get("story", "0") or 0)
    workspace = session.get(Workspace, artifact.workspace_id)
    token = settings.github_token
    if workspace is None or token is None or not token.get_secret_value():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No GitHub token is configured.")
    repository = f"{workspace.repo_owner}/{workspace.repo_name}"
    try:
        items = [item.__dict__ for item in build_pack(session, workspace, story).items]
        with ContentsReader(repository, token, request.app.state.github_transport) as reader:
            payload, base, summary = build_decision(
                proposal=proposals[body.index - 1],
                number=next_adr_number(session, workspace.id),
                story=story,
                plan_ref={
                    "artifact_id": artifact.id,
                    "version": version.number,
                    "path": artifact_path(artifact),
                },
                pack_items=items,
                approver=approver.identity,
                model=version.actor,
                reader=reader,
                repository=repository,
                base_branch=workspace.branch,
                now=utc_now(),
            )
    except PackError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except ApprovalError as exc:
        raise HTTPException(exc.status, exc.message) from exc
    except ContentsError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc
    base |= {"artifact_id": artifact.id, "artifact_version": artifact.current_version}
    run = Run(
        workspace_id=workspace.id,
        workflow_type="publish",
        status="waiting",
        inputs={"artifact_id": artifact.id, "decision": body.index},
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
    )
    return _detail(approval)
