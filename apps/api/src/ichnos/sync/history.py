"""History stages: Issues, pull requests, comments and commits (ADR-0009)."""

import datetime as dt
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ichnos.db.base import as_utc, utc_now
from ichnos.db.models import (
    Commit,
    GitHubComment,
    GitHubItem,
    PullRequestCommit,
    PullRequestFile,
    Workspace,
)
from ichnos.github.reader import GitHubReader
from ichnos.sync.cursors import get_cursor, set_cursor

ISSUES_CURSOR = "issues:updated_at"
COMMENTS_CURSOR = "comments:updated_at"
COMMITS_CURSOR = "commits:date"
EPOCH = dt.datetime.min.replace(tzinfo=dt.UTC)


def parse_time(value: Any) -> dt.datetime | None:
    if not isinstance(value, str) or not value:
        return None
    return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))


def _latest(current: str | None, value: Any) -> str | None:
    candidates = [v for v in (current, value) if isinstance(v, str) and v]
    return max(candidates, key=lambda v: parse_time(v) or EPOCH) if candidates else None


def _login(user: Any) -> str | None:
    return str(user["login"]) if isinstance(user, dict) and user.get("login") else None


def _nested(data: Any, *keys: str) -> Any:
    for key in keys:
        data = data.get(key) if isinstance(data, dict) else None
    return data


def _upsert_commit(session: Session, workspace_id: str, data: dict[str, Any]) -> bool:
    """Commits never change, so an existing SHA is left alone. Returns True if added."""
    sha = str(data["sha"])
    found = session.scalar(
        select(Commit).where(Commit.workspace_id == workspace_id, Commit.sha == sha)
    )
    if found is not None:
        return False
    session.add(
        Commit(
            workspace_id=workspace_id,
            sha=sha,
            message=str(_nested(data, "commit", "message") or ""),
            author_name=_nested(data, "commit", "author", "name"),
            author_login=_login(data.get("author")),
            authored_at=parse_time(_nested(data, "commit", "author", "date")),
            url=str(data.get("html_url") or ""),
        )
    )
    return True


def _upsert_comment(
    session: Session,
    workspace_id: str,
    kind: str,
    github_id: int,
    item_number: int,
    data: dict[str, Any],
    created: dt.datetime,
    updated: dt.datetime,
) -> str:
    """Returns 'added', 'updated' or 'unchanged'."""
    found = session.scalar(
        select(GitHubComment).where(
            GitHubComment.workspace_id == workspace_id,
            GitHubComment.kind == kind,
            GitHubComment.github_id == github_id,
        )
    )
    if found is not None and as_utc(found.updated_at) == updated:
        return "unchanged"
    comment = found or GitHubComment(workspace_id=workspace_id, kind=kind, github_id=github_id)
    if found is None:
        session.add(comment)
    comment.item_number = item_number
    comment.author = _login(data.get("user"))
    comment.body = str(data.get("body") or "")
    comment.review_state = data.get("state") if kind == "review" else None
    comment.path = data.get("path")
    comment.url = str(data.get("html_url") or "")
    comment.created_at = created
    comment.updated_at = updated
    return "added" if found is None else "updated"


def _apply_issue(item: GitHubItem, data: dict[str, Any]) -> None:
    item.item_type = "pull_request" if "pull_request" in data else "issue"
    item.github_id = int(data["id"])
    item.title = str(data.get("title") or "")
    item.body = data.get("body")
    item.state = str(data.get("state") or "open")
    item.state_reason = data.get("state_reason")
    item.author = _login(data.get("user"))
    item.labels = [
        str(label["name"])
        for label in data.get("labels") or []
        if isinstance(label, dict) and label.get("name")
    ]
    item.milestone = _nested(data, "milestone", "title")
    item.url = str(data.get("html_url") or "")
    item.created_at = parse_time(data.get("created_at")) or utc_now()
    item.updated_at = parse_time(data.get("updated_at")) or utc_now()
    item.closed_at = parse_time(data.get("closed_at"))


def _sync_pull(
    session: Session, reader: GitHubReader, workspace: Workspace, item: GitHubItem
) -> None:
    owner, repo, number, ws = workspace.repo_owner, workspace.repo_name, item.number, workspace.id
    pull = reader.pull(owner, repo, number)
    item.merged_at = parse_time(pull.get("merged_at"))
    item.draft = bool(pull.get("draft"))
    item.head_ref = _nested(pull, "head", "ref")
    item.head_sha = _nested(pull, "head", "sha")
    item.base_ref = _nested(pull, "base", "ref")

    session.execute(
        delete(PullRequestFile).where(
            PullRequestFile.workspace_id == ws, PullRequestFile.pr_number == number
        )
    )
    for file in reader.pull_files(owner, repo, number):
        session.add(
            PullRequestFile(
                workspace_id=ws,
                pr_number=number,
                path=str(file["filename"]),
                status=str(file.get("status") or "modified"),
                additions=int(file.get("additions") or 0),
                deletions=int(file.get("deletions") or 0),
                previous_path=file.get("previous_filename"),
            )
        )

    session.execute(
        delete(PullRequestCommit).where(
            PullRequestCommit.workspace_id == ws, PullRequestCommit.pr_number == number
        )
    )
    for commit in reader.pull_commits(owner, repo, number):
        session.add(PullRequestCommit(workspace_id=ws, pr_number=number, sha=str(commit["sha"])))
        _upsert_commit(session, ws, commit)

    for review in reader.pull_reviews(owner, repo, number):
        submitted = parse_time(review.get("submitted_at"))
        if submitted is None:  # pending reviews are not submitted yet
            continue
        _upsert_comment(
            session, ws, "review", int(review["id"]), number, review, submitted, submitted
        )

    for comment in reader.pull_review_comments(owner, repo, number):
        created = parse_time(comment.get("created_at")) or utc_now()
        updated = parse_time(comment.get("updated_at")) or created
        _upsert_comment(
            session, ws, "review_comment", int(comment["id"]), number, comment, created, updated
        )


def sync_issues(session: Session, reader: GitHubReader, workspace: Workspace) -> dict[str, int]:
    counts = dict.fromkeys(
        ("items_added", "items_updated", "items_unchanged", "pull_requests_detailed"), 0
    )
    cursor = get_cursor(session, workspace.id, ISSUES_CURSOR)
    existing = {
        item.number: item
        for item in session.scalars(
            select(GitHubItem).where(GitHubItem.workspace_id == workspace.id)
        )
    }
    newest = cursor
    for data in reader.issues(workspace.repo_owner, workspace.repo_name, since=cursor):
        newest = _latest(newest, data.get("updated_at"))
        number = int(data["number"])
        current = existing.get(number)
        if current is not None and as_utc(current.updated_at) == parse_time(data.get("updated_at")):
            counts["items_unchanged"] += 1
            continue
        if current is None:
            current = GitHubItem(workspace_id=workspace.id, number=number)
            session.add(current)
            existing[number] = current
            counts["items_added"] += 1
        else:
            counts["items_updated"] += 1
        _apply_issue(current, data)
        if current.item_type == "pull_request":
            _sync_pull(session, reader, workspace, current)
            counts["pull_requests_detailed"] += 1
    if newest:
        set_cursor(session, workspace.id, ISSUES_CURSOR, newest)
    return counts


def sync_comments(session: Session, reader: GitHubReader, workspace: Workspace) -> dict[str, int]:
    counts = dict.fromkeys(("comments_added", "comments_updated", "comments_unchanged"), 0)
    cursor = get_cursor(session, workspace.id, COMMENTS_CURSOR)
    newest = cursor
    for data in reader.issue_comments(workspace.repo_owner, workspace.repo_name, since=cursor):
        newest = _latest(newest, data.get("updated_at"))
        created = parse_time(data.get("created_at")) or utc_now()
        updated = parse_time(data.get("updated_at")) or created
        number = int(str(data.get("issue_url", "")).rstrip("/").rsplit("/", 1)[-1])
        outcome = _upsert_comment(
            session, workspace.id, "issue_comment", int(data["id"]), number, data, created, updated
        )
        counts[f"comments_{outcome}"] += 1
    if newest:
        set_cursor(session, workspace.id, COMMENTS_CURSOR, newest)
    return counts


def sync_commits(session: Session, reader: GitHubReader, workspace: Workspace) -> dict[str, int]:
    counts = dict.fromkeys(("commits_added", "commits_unchanged"), 0)
    cursor = get_cursor(session, workspace.id, COMMITS_CURSOR)
    newest = cursor
    branch = workspace.branch
    for data in reader.commits(workspace.repo_owner, workspace.repo_name, branch, since=cursor):
        newest = _latest(newest, _nested(data, "commit", "committer", "date"))
        added = _upsert_commit(session, workspace.id, data)
        counts["commits_added" if added else "commits_unchanged"] += 1
    if newest:
        set_cursor(session, workspace.id, COMMITS_CURSOR, newest)
    return counts
