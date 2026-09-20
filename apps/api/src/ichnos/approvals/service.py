"""The approval service (ADR-0015): the only place that issues execution tickets.

Approving checks, in order: the action is pending, the approver saw this exact payload, the stored
payload still matches its hash, it was prepared for this approver, the artifact has not changed,
and nothing it touches changed on GitHub. Only then is a ticket issued and the write executed.
"""

import copy
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import httpx
from pydantic import SecretStr
from sqlalchemy.orm import Session

from ichnos.approvals.issues import run_create_issues
from ichnos.approvals.payload import (
    APPROVED,
    EXECUTED,
    FAILED,
    PENDING,
    REJECTED,
    STALE,
    payload_hash,
    verify,
)
from ichnos.approvals.story_pr import draft_stale, run_draft_pull_request
from ichnos.approvals.ticket import issue_ticket
from ichnos.db.base import utc_now
from ichnos.db.models import Approval, Artifact, AuditEvent, Run
from ichnos.github.writer import FileChange, GitHubWriteError, GitHubWriter

Payload = dict[str, Any]


class ApprovalError(Exception):
    """A refused decision; nothing was written. The message is safe to show."""

    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


@dataclass(frozen=True)
class Executor:
    stale: Callable[[GitHubWriter, Payload, Payload], str | None]
    run: Callable[[GitHubWriter, Payload], Payload]


def _docs_stale(writer: GitHubWriter, payload: Payload, base: Payload) -> str | None:
    if writer.branch_head(payload["branch"]) is not None:
        return f"Branch {payload['branch']} already exists."
    head = writer.branch_head(payload["base_branch"])
    if head is None:
        return f"Branch {payload['base_branch']} no longer exists."
    if head != base.get("head_sha"):
        for path, sha in (base.get("files") or {}).items():
            if writer.file_sha(path, payload["base_branch"]) != sha:
                return f"{path} changed on {payload['base_branch']} after this action was proposed."
    return None


def _docs_run(writer: GitHubWriter, payload: Payload) -> Payload:
    sha = writer.commit_files(
        base_branch=payload["base_branch"],
        new_branch=payload["branch"],
        message=payload["commit_message"],
        files=[FileChange(f["path"], f["content"]) for f in payload["files"]],
    )
    pull = writer.open_pull_request(
        head=payload["branch"],
        base=payload["base_branch"],
        title=payload["title"],
        body=payload["body"],
    )
    return {
        "commit_sha": sha,
        "branch": payload["branch"],
        "pull_request": {"number": pull.number, "url": pull.url},
    }


def _issues_stale(writer: GitHubWriter, payload: Payload, base: Payload) -> str | None:
    """Issues touch no files; the artifact check in approve() covers the BRD."""
    return None


EXECUTORS: dict[str, Executor] = {
    "docs_pull_request": Executor(_docs_stale, _docs_run),
    "create_issues": Executor(_issues_stale, run_create_issues),
    "draft_pull_request": Executor(draft_stale, run_draft_pull_request),
}


def _audit(session: Session, event: str, approval: Approval, actor: str, **details: Any) -> None:
    session.add(
        AuditEvent(
            actor=actor,
            event_type=event,
            workspace_id=approval.workspace_id,
            run_id=approval.run_id,
            approval_id=approval.id,
            details=details,
        )
    )


RUN_STATUS = {EXECUTED: "succeeded", REJECTED: "rejected", STALE: "failed", FAILED: "failed"}


def _settle(session: Session, approval: Approval, status: str, error: str | None) -> None:
    """A waiting run and a published artifact follow the decision."""
    run = session.get(Run, approval.run_id)
    if run is not None and run.status == "waiting" and run.workflow_type in ("publish", "draft_pr"):
        run.status = RUN_STATUS[status]
        run.error = error
        run.finished_at = utc_now()
    if approval.artifact_id and approval.action_type == "docs_pull_request":
        artifact = session.get(Artifact, approval.artifact_id)
        if artifact is not None:
            artifact.status = "approved" if status == EXECUTED else "draft"


def _finish(
    session: Session,
    approval: Approval,
    status: str,
    actor: str,
    *,
    error: str | None = None,
    result: Payload | None = None,
) -> Approval:
    approval.status = status
    approval.error = error
    approval.result = result
    if status == EXECUTED:
        approval.executed_at = utc_now()
    _settle(session, approval, status, error)
    _audit(session, f"approval.{status}", approval, actor, error=error, result=result)
    session.commit()
    return approval


def propose(
    session: Session,
    *,
    run_id: str,
    workspace_id: str,
    action_type: str,
    target: str,
    branch: str,
    payload: Payload,
    base: Payload,
    summary: str,
    proposed_by: str,
    artifact_id: str | None = None,
) -> Approval:
    """Store a pending action; nothing is written to GitHub."""
    if action_type not in EXECUTORS:
        raise ApprovalError(400, f"Unknown action type {action_type}.")
    approval = Approval(
        run_id=run_id,
        workspace_id=workspace_id,
        artifact_id=artifact_id,
        action_type=action_type,
        target=target,
        branch=branch,
        payload=payload,
        payload_hash=payload_hash(payload),
        base=base,
        summary=summary[:300],
        proposed_by=proposed_by,
        status=PENDING,
    )
    session.add(approval)
    session.flush()
    if artifact_id and action_type == "docs_pull_request":
        artifact = session.get(Artifact, artifact_id)
        if artifact is not None:
            artifact.status = "needs-review"
    _audit(session, "approval.proposed", approval, proposed_by, payload_hash=approval.payload_hash)
    session.commit()
    return approval


def _pending(session: Session, approval_id: str) -> Approval:
    approval = session.get(Approval, approval_id)
    if approval is None:
        raise ApprovalError(404, "Approval not found.")
    if approval.status != PENDING:
        raise ApprovalError(409, f"This action is already {approval.status}.")
    return approval


def reject(session: Session, approval_id: str, *, approver: str, note: str | None) -> Approval:
    approval = _pending(session, approval_id)
    approval.status = REJECTED
    approval.decided_by = approver
    approval.decided_at = utc_now()
    approval.decision_note = (note or "").strip() or None
    _settle(session, approval, REJECTED, None)
    _audit(session, "approval.rejected", approval, approver, note=approval.decision_note)
    session.commit()
    return approval


def approve(
    session: Session,
    approval_id: str,
    *,
    approver: str,
    shown_hash: str,
    token: SecretStr | None,
    transport: httpx.BaseTransport | None = None,
) -> Approval:
    """Check everything, then execute exactly the stored payload."""
    approval = _pending(session, approval_id)
    if shown_hash != approval.payload_hash:
        raise ApprovalError(
            409, "This action changed since you reviewed it; reload it before approving."
        )
    prepared_for = (approval.payload or {}).get("approver")
    if prepared_for and prepared_for != approver:
        raise ApprovalError(
            409,
            f"This action was prepared for {prepared_for}; sign in as that approver "
            "or propose it again.",
        )
    if token is None or not token.get_secret_value():
        raise ApprovalError(400, "No GitHub token is configured.")

    approval.decided_by = approver
    approval.decided_at = utc_now()
    if not verify(approval):
        return _finish(
            session,
            approval,
            FAILED,
            approver,
            error="The stored payload no longer matches its hash; nothing was written.",
        )
    base = approval.base or {}
    if base.get("artifact_id"):
        artifact = session.get(Artifact, base["artifact_id"])
        if artifact is None or artifact.current_version != base.get("artifact_version"):
            return _finish(
                session,
                approval,
                STALE,
                approver,
                error="The artifact changed after this action was proposed; propose it again.",
            )

    approval.status = APPROVED
    _audit(session, "approval.approved", approval, approver, payload_hash=approval.payload_hash)
    session.commit()

    executor = EXECUTORS[approval.action_type]
    ticket = issue_ticket(approval.id, approval.payload_hash)
    with GitHubWriter(
        ticket, repository=approval.target, token=token, transport=transport
    ) as writer:
        try:
            reason = executor.stale(writer, approval.payload, base)
            if reason:
                return _finish(session, approval, STALE, approver, error=reason)
            result = executor.run(writer, approval.payload)
        except GitHubWriteError as exc:
            partial = getattr(exc, "partial", None)  # Issues created before the failure
            return _finish(session, approval, FAILED, approver, error=str(exc), result=partial)
    return _finish(session, approval, EXECUTED, approver, result=result)


PARENT_LINE = "- Epic: #{epic}"


def _clean_issue(spec: Payload, what: str) -> tuple[str, str]:
    title = " ".join(str(spec.get("title", "")).split())
    body = str(spec.get("body", "")).strip()
    if not title or not body:
        raise ApprovalError(400, f"{what} needs a title and a body.")
    if len(title) > 256:
        raise ApprovalError(400, f"{what}: titles are limited to 256 characters.")
    return title, body + "\n"


def revise(
    session: Session,
    approval_id: str,
    *,
    approver: str,
    shown_hash: str,
    epic: Payload,
    stories: list[Payload],
) -> Approval:
    """Edit the titles and bodies of a pending create_issues action; the hash changes."""
    approval = _pending(session, approval_id)
    if approval.action_type != "create_issues":
        raise ApprovalError(
            409, "Documentation changes are made in the artifact: edit it, then publish again."
        )
    if shown_hash != approval.payload_hash:
        raise ApprovalError(409, "This action changed since you opened it; reload it first.")
    prepared_for = (approval.payload or {}).get("approver")
    if prepared_for and prepared_for != approver:
        raise ApprovalError(409, f"This action was prepared for {prepared_for}.")

    payload = copy.deepcopy(approval.payload)
    payload["epic"]["title"], payload["epic"]["body"] = _clean_issue(epic, "The Epic")
    by_key = {story["key"]: story for story in payload["stories"]}
    for change in stories:
        key = str(change.get("key", ""))
        target = by_key.get(key)
        if target is None:
            raise ApprovalError(400, f"Unknown story {key}.")
        title, body = _clean_issue(change, key)
        if PARENT_LINE not in body:
            raise ApprovalError(400, f"{key} must keep its ## Parent line: {PARENT_LINE}")
        target["title"], target["body"] = title, body
    approval.payload = payload
    approval.payload_hash = payload_hash(payload)
    _audit(session, "approval.revised", approval, approver, payload_hash=approval.payload_hash)
    session.commit()
    return approval
