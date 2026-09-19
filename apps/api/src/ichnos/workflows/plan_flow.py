"""The planning workflow (Phase 4): plan, propose Issues, wait for the decision, record.

The decision stage is a LangGraph interrupt: the run waits, survives restarts, and resumes
when the create_issues action is approved or rejected.
"""

from typing import Any

from sqlalchemy import select

from ichnos.approvals.issues import build_issues
from ichnos.approvals.publish import LOG, add_log_line
from ichnos.approvals.service import propose
from ichnos.db.base import utc_now
from ichnos.db.models import Artifact, ArtifactVersion
from ichnos.github.contents import ContentsError, ContentsReader
from ichnos.okf import parse_document, render_document
from ichnos.workflows.engine import Data, Stage, StageContext, StageFailed
from ichnos.workflows.planning import describe_planning, planning_stage, requirements_of

WORKFLOW_TYPE = "planning"


def proposal_stage(data: Data, context: StageContext) -> Data:
    with context.factory() as session:
        artifact = session.get(Artifact, str(data["artifact_id"]))
        version = session.scalar(
            select(ArtifactVersion).where(
                ArtifactVersion.artifact_id == str(data["artifact_id"]),
                ArtifactVersion.number == int(data["artifact_version"]),
            )
        )
        if artifact is None or version is None:
            raise StageFailed("the BRD to plan was not found")
        statements = {r.id: r.statement for r in requirements_of(version.content)}
        payload, summary = build_issues(
            data["plan"],
            approver=data["approver"],
            repository=data["repository"],
            brd_path=data["brd_path"],
            statements=statements,
        )
        approval = propose(
            session,
            run_id=context.run_id,
            workspace_id=context.workspace_id,
            action_type="create_issues",
            target=data["repository"],
            branch=data["base_branch"],
            payload=payload,
            base={"artifact_id": artifact.id, "artifact_version": version.number},
            summary=summary,
            proposed_by=data["approver"],
        )
        return {"approval_id": approval.id, "summary": summary}


def decision_stage(data: Data, context: StageContext) -> Data:
    decision = data.get("decision") or {}
    status = str(decision.get("status", "unknown"))
    if status != "executed":
        context.note(f"The plan was {status}; no Issues were created.")
        return {"issues": None, "decision_status": status}
    return {"issues": decision.get("result"), "decision_status": status}


def link_issues_into_brd(data: Data, context: StageContext, issues: dict[str, Any]) -> str | None:
    """Propose writing the Issue numbers into the BRD's ichnos extension; returns the approval."""
    token = context.services.get("token")
    if token is None:
        context.note("No GitHub token; the Issues were not linked into the BRD.")
        return None
    path, branch = str(data["brd_path"]), str(data["base_branch"])
    try:
        with ContentsReader(data["repository"], token, context.services.get("transport")) as reader:
            brd = reader.file(path, branch)
            log = reader.file(LOG, branch)
            head = reader.head(branch)
    except ContentsError as exc:
        context.note(f"Could not read the BRD from GitHub: {exc}")
        return None
    if brd is None or head is None:
        context.note(f"{path} is not on {branch} yet; merge its pull request to link the Issues.")
        return None

    parsed = parse_document(path, brd.text)
    frontmatter = dict(parsed.frontmatter)
    epic = issues["epic"]
    frontmatter["resource"] = epic["url"]
    frontmatter["ichnos"] = {
        **(frontmatter.get("ichnos") or {}),
        "epic": {"number": epic["number"], "url": epic["url"]},
        "stories": [
            {"key": s["key"], "number": s["number"], "url": s["url"]} for s in issues["stories"]
        ],
    }
    title = parsed.title or "BRD"
    files = [{"path": path, "content": render_document(frontmatter, parsed.body)}]
    base_files: dict[str, str | None] = {path: brd.sha}
    if log is not None:
        link = f"[{title}](/{path.removeprefix('docs/')})"
        line = f"* **Update**: Linked Epic #{epic['number']} and its Stories to the {link} BRD."
        files.append(
            {"path": LOG, "content": add_log_line(log.text, utc_now().date().isoformat(), line)}
        )
        base_files[LOG] = log.sha
    stories = ", ".join(f"#{s['number']}" for s in issues["stories"])
    payload = {
        "kind": "docs_pull_request",
        "approver": data["approver"],
        "repository": data["repository"],
        "base_branch": branch,
        "branch": f"ichnos/{path.split('/')[2]}-issues-{epic['number']}",
        "commit_message": f"docs: link Epic #{epic['number']} to the {title} BRD",
        "title": f"Link Issues to BRD: {title}",
        "body": f"Records Epic #{epic['number']} and Stories {stories} in the BRD's frontmatter.",
        "files": files,
    }
    with context.factory() as session:
        approval = propose(
            session,
            run_id=context.run_id,
            workspace_id=context.workspace_id,
            action_type="docs_pull_request",
            target=data["repository"],
            branch=branch,
            payload=payload,
            base={"head_sha": head, "files": base_files},
            summary=f"Link Issues to BRD: {title}",
            proposed_by=data["approver"],
        )
        return approval.id


def record_stage(data: Data, context: StageContext) -> Data:
    issues = data.get("issues")
    result: dict[str, Any] = {"decision": data.get("decision_status"), "issues": issues}
    if issues:
        result["follow_up_approval_id"] = link_issues_into_brd(data, context, issues)
    return {"result": result}


def describe_proposal(update: Data) -> str:
    return f"Waiting for approval: {update.get('summary')}"


def describe_decision(update: Data) -> str:
    issues = update.get("issues")
    if not issues:
        return f"The plan was {update.get('decision_status')}"
    return f"Created Epic #{issues['epic']['number']} and {len(issues['stories'])} Stories"


def describe_record(update: Data) -> str:
    result = update.get("result", {})
    if result.get("follow_up_approval_id"):
        return "Proposed linking the Issues into the BRD"
    return "Recorded the decision"


STAGES = [
    Stage("planning", planning_stage, describe_planning),
    Stage("proposal", proposal_stage, describe_proposal),
    Stage("decision", decision_stage, describe_decision, waits=True),
    Stage("record", record_stage, describe_record),
]
