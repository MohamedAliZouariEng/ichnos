"""Checks stage: CI check runs on pull request heads, as test evidence (ADR-0022).

A pull request's head is fetched again only while it has pending runs or after it moves, so an
unchanged repository costs no request here.
"""

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ichnos.db.models import CheckRun, GitHubItem, Workspace
from ichnos.github.reader import GitHubError, GitHubReader
from ichnos.sync.cursors import get_cursor, set_cursor
from ichnos.sync.history import parse_time


def _cursor(number: int) -> str:
    return f"checks:{number}"


def _apply(run: CheckRun, data: dict[str, Any], number: int, head: str) -> None:
    run.head_sha = head
    run.pull_number = number
    run.name = str(data.get("name", ""))[:200]
    run.status = str(data.get("status", ""))[:20]
    run.conclusion = data.get("conclusion")
    run.url = str(data.get("html_url") or data.get("url") or "")[:500]
    run.completed_at = parse_time(data.get("completed_at"))


def sync_checks(session: Session, reader: GitHubReader, workspace: Workspace) -> dict[str, int]:
    counts = {"checks_added": 0, "checks_updated": 0, "checks_unavailable": 0}
    pulls = session.scalars(
        select(GitHubItem).where(
            GitHubItem.workspace_id == workspace.id,
            GitHubItem.item_type == "pull_request",
            GitHubItem.head_sha.is_not(None),
        )
    ).all()
    for pull in pulls:
        head = str(pull.head_sha)
        if get_cursor(session, workspace.id, _cursor(pull.number)) == head:
            continue  # fetched with every run completed; nothing can change until it moves
        try:
            runs = reader.check_runs(workspace.repo_owner, workspace.repo_name, head)
        except GitHubError as exc:
            if exc.status_code in (403, 404):
                counts["checks_unavailable"] += 1
                continue
            raise
        existing = {
            run.github_id: run
            for run in session.scalars(
                select(CheckRun).where(
                    CheckRun.workspace_id == workspace.id, CheckRun.head_sha == head
                )
            )
        }
        for data in runs:
            run = existing.get(int(data["id"]))
            if run is None:
                run = CheckRun(workspace_id=workspace.id, github_id=int(data["id"]))
                session.add(run)
                counts["checks_added"] += 1
            else:
                counts["checks_updated"] += 1
            _apply(run, data, pull.number, head)
        if all(data.get("status") == "completed" for data in runs):
            set_cursor(session, workspace.id, _cursor(pull.number), head)
    return counts
