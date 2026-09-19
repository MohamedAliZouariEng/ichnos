"""Run a workspace sync as a sequence of stages and record it (ADR-0009)."""

import datetime as dt
import logging
from collections.abc import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from ichnos.db.base import new_id, utc_now
from ichnos.db.models import AuditEvent, Run, Workspace
from ichnos.github.reader import GitHubError, GitHubReader
from ichnos.sync.documents import sync_documents
from ichnos.sync.history import sync_comments, sync_commits, sync_issues

logger = logging.getLogger(__name__)

Stage = Callable[[Session, GitHubReader, Workspace], dict[str, int]]
STAGES: list[tuple[str, Stage]] = [
    ("documents", sync_documents),
    ("issues", sync_issues),
    ("comments", sync_comments),
    ("commits", sync_commits),
]
STALE_AFTER = dt.timedelta(minutes=30)


class SyncInProgress(Exception):
    """Another sync of the same workspace is still running."""


def _start(session: Session, workspace: Workspace) -> str:
    running = session.scalar(
        select(Run).where(
            Run.workspace_id == workspace.id,
            Run.workflow_type == "sync",
            Run.status == "running",
            Run.created_at > utc_now() - STALE_AFTER,
        )
    )
    if running is not None:
        raise SyncInProgress(running.id)
    run = Run(
        id=new_id(),
        workspace_id=workspace.id,
        workflow_type="sync",
        status="running",
        stage=STAGES[0][0],
        inputs={
            "repository": f"{workspace.repo_owner}/{workspace.repo_name}",
            "branch": workspace.branch,
        },
    )
    session.add(run)
    session.commit()
    return run.id


def run_sync(
    factory: sessionmaker[Session],
    workspace_id: str,
    make_reader: Callable[[], GitHubReader],
    *,
    actor: str,
) -> Run:
    """Run every stage; each commits on its own, so a failure keeps earlier stages."""
    with factory() as session:
        workspace = session.get(Workspace, workspace_id)
        if workspace is None:
            raise LookupError(workspace_id)
        run_id = _start(session, workspace)

    counts: dict[str, int] = {}
    error: str | None = None
    with make_reader() as reader:
        for stage, step in STAGES:
            try:
                with factory() as session:
                    run = session.get(Run, run_id)
                    workspace = session.get(Workspace, workspace_id)
                    assert run is not None and workspace is not None
                    run.stage = stage
                    counts.update(step(session, reader, workspace))
                    session.commit()
            except GitHubError as exc:
                error = f"{stage}: {exc.message}"
                break
            except Exception:
                logger.exception("Sync stage %s failed", stage)
                error = f"{stage}: unexpected error; see the API logs."
                break
        requests, remaining = reader.requests, reader.rate_limit_remaining

    with factory() as session:
        run = session.get(Run, run_id)
        assert run is not None
        run.status = "failed" if error else "succeeded"
        run.error = error
        run.outputs = {"counts": counts, "requests": requests, "rate_limit_remaining": remaining}
        run.finished_at = utc_now()
        session.add(
            AuditEvent(
                actor=actor,
                event_type="sync.failed" if error else "sync.completed",
                workspace_id=workspace_id,
                run_id=run_id,
                details={"counts": counts, "error": error},
            )
        )
        session.commit()
        return run
