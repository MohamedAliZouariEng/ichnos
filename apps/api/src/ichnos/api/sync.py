"""Workspace sync and synced documents (ADR-0009)."""

import datetime as dt
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query, Request, status
from pydantic import BaseModel
from sqlalchemy import select

from ichnos.api.deps import SessionDep, SettingsDep
from ichnos.api.workspaces import LOCAL_ACTOR, NOT_FOUND, get_workspace_or_404
from ichnos.db.base import as_utc
from ichnos.db.models import Document, GitHubItem, Run
from ichnos.github.reader import GitHubReader
from ichnos.sync.service import SyncInProgress, run_sync

router = APIRouter(prefix="/api/workspaces/{workspace_id}", tags=["sync"])

SYNC_RESPONSES: dict[int | str, dict[str, Any]] = {
    **NOT_FOUND,
    400: {"description": "No GitHub token configured"},
    409: {"description": "A sync of this workspace is already running"},
}


class SyncRunRead(BaseModel):
    id: str
    status: str
    stage: str | None
    error: str | None
    counts: dict[str, int]
    requests: int | None
    created_at: dt.datetime
    finished_at: dt.datetime | None


class DocumentSummary(BaseModel):
    path: str
    kind: str
    concept_id: str | None
    type: str | None
    title: str | None
    status: str | None
    trust_tier: str
    findings: int
    commit_sha: str


def _run_read(run: Run) -> SyncRunRead:
    outputs = run.outputs or {}
    return SyncRunRead(
        id=run.id,
        status=run.status,
        stage=run.stage,
        error=run.error,
        counts=dict(outputs.get("counts", {})),
        requests=outputs.get("requests"),
        created_at=as_utc(run.created_at),
        finished_at=None if run.finished_at is None else as_utc(run.finished_at),
    )


@router.post(
    "/sync",
    response_model=SyncRunRead,
    operation_id="syncWorkspace",
    responses=SYNC_RESPONSES,
)
def sync_workspace(
    workspace_id: str, request: Request, session: SessionDep, settings: SettingsDep
) -> SyncRunRead:
    get_workspace_or_404(session, workspace_id)
    token = settings.github_token
    if token is None or not token.get_secret_value():
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "No GitHub token configured; set ICHNOS_GITHUB_TOKEN in .env.",
        )
    transport = request.app.state.github_transport
    try:
        run = run_sync(
            request.app.state.session_factory,
            workspace_id,
            lambda: GitHubReader(token, transport=transport),
            actor=LOCAL_ACTOR,
        )
    except SyncInProgress as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "A sync of this workspace is already running."
        ) from exc
    return _run_read(run)


@router.get(
    "/sync-runs",
    response_model=list[SyncRunRead],
    operation_id="listSyncRuns",
    responses=NOT_FOUND,
)
def list_sync_runs(
    workspace_id: str,
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> list[SyncRunRead]:
    get_workspace_or_404(session, workspace_id)
    runs = session.scalars(
        select(Run)
        .where(Run.workspace_id == workspace_id, Run.workflow_type == "sync")
        .order_by(Run.created_at.desc())
        .limit(limit)
    ).all()
    return [_run_read(run) for run in runs]


@router.get(
    "/documents",
    response_model=list[DocumentSummary],
    operation_id="listDocuments",
    responses=NOT_FOUND,
)
def list_documents(workspace_id: str, session: SessionDep) -> list[DocumentSummary]:
    get_workspace_or_404(session, workspace_id)
    documents = session.scalars(
        select(Document).where(Document.workspace_id == workspace_id).order_by(Document.path)
    ).all()
    return [
        DocumentSummary(
            path=doc.path,
            kind=doc.kind,
            concept_id=doc.concept_id,
            type=doc.doc_type,
            title=doc.title,
            status=doc.status,
            trust_tier=doc.trust_tier,
            findings=len(doc.findings or []),
            commit_sha=doc.commit_sha,
        )
        for doc in documents
    ]


class GitHubItemSummary(BaseModel):
    number: int
    type: str
    title: str
    state: str
    author: str | None
    labels: list[str]
    url: str
    updated_at: dt.datetime
    merged_at: dt.datetime | None


@router.get(
    "/github/items",
    response_model=list[GitHubItemSummary],
    operation_id="listGitHubItems",
    responses=NOT_FOUND,
)
def list_github_items(workspace_id: str, session: SessionDep) -> list[GitHubItemSummary]:
    get_workspace_or_404(session, workspace_id)
    items = session.scalars(
        select(GitHubItem)
        .where(GitHubItem.workspace_id == workspace_id)
        .order_by(GitHubItem.number.desc())
    ).all()
    return [
        GitHubItemSummary(
            number=item.number,
            type=item.item_type,
            title=item.title,
            state=item.state,
            author=item.author,
            labels=list(item.labels or []),
            url=item.url,
            updated_at=as_utc(item.updated_at),
            merged_at=None if item.merged_at is None else as_utc(item.merged_at),
        )
        for item in items
    ]
