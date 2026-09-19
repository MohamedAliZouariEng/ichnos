"""Workflow runs: start them and follow them live (ADR-0011, ADR-0013)."""

import datetime as dt
import time
from collections.abc import Iterator
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Header, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from ichnos.api.config import NOT_CONFIGURED
from ichnos.api.deps import SessionDep, SettingsDep
from ichnos.api.workspaces import NOT_FOUND, get_workspace_or_404
from ichnos.db.base import as_utc
from ichnos.db.models import Run, RunEvent, Source
from ichnos.llm import provider_from_settings
from ichnos.workflows import brd
from ichnos.workflows.engine import Stage, start_run

router = APIRouter(tags=["runs"])

WORKFLOWS: dict[str, list[Stage]] = {brd.WORKFLOW_TYPE: brd.STAGES}
FINAL_EVENTS = {"run.completed", "run.failed", "run.interrupted"}
TERMINAL = {"succeeded", "failed", "interrupted"}
POLL_SECONDS = 0.5
GRACE_SECONDS = 2.0
HEARTBEAT_SECONDS = 15.0
RUN_NOT_FOUND: dict[int | str, dict[str, Any]] = {404: {"description": "Run not found"}}


class RunCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workflow: Literal["requirements"] = "requirements"
    source_ids: list[str] = Field(min_length=1, max_length=5)


class RunEventRead(BaseModel):
    id: int
    kind: str
    stage: str | None
    message: str
    data: dict[str, Any]
    created_at: dt.datetime


class RunSummary(BaseModel):
    id: str
    workspace_id: str
    workflow_type: str
    status: str
    stage: str | None
    error: str | None
    created_at: dt.datetime
    finished_at: dt.datetime | None
    total_tokens: int
    artifact_id: str | None


class RunDetail(RunSummary):
    inputs: dict[str, Any]
    outputs: dict[str, Any]
    events: list[RunEventRead]


def _event(event: RunEvent) -> RunEventRead:
    return RunEventRead(
        id=event.id,
        kind=event.kind,
        stage=event.stage,
        message=event.message,
        data=event.data or {},
        created_at=as_utc(event.created_at),
    )


def _summary(run: Run) -> RunSummary:
    outputs = run.outputs or {}
    result = outputs.get("result") or {}
    usage = outputs.get("usage") or {}
    return RunSummary(
        id=run.id,
        workspace_id=run.workspace_id,
        workflow_type=run.workflow_type,
        status=run.status,
        stage=run.stage,
        error=run.error,
        created_at=as_utc(run.created_at),
        finished_at=as_utc(run.finished_at) if run.finished_at else None,
        total_tokens=int(usage.get("total_tokens", 0)),
        artifact_id=result.get("artifact_id") if isinstance(result, dict) else None,
    )


def _detail(session: Session, run: Run) -> RunDetail:
    events = session.scalars(
        select(RunEvent).where(RunEvent.run_id == run.id).order_by(RunEvent.id)
    ).all()
    return RunDetail(
        **_summary(run).model_dump(),
        inputs=run.inputs or {},
        outputs=run.outputs or {},
        events=[_event(event) for event in events],
    )


@router.post(
    "/api/workspaces/{workspace_id}/runs",
    response_model=RunDetail,
    status_code=status.HTTP_202_ACCEPTED,
    operation_id="startRun",
    responses={**NOT_FOUND, 400: {"description": "Invalid sources or no model configured"}},
)
def start_workflow_run(
    workspace_id: str,
    body: RunCreate,
    session: SessionDep,
    settings: SettingsDep,
    request: Request,
) -> RunDetail:
    """Start a workflow in the background; follow it with GET /api/runs/{run_id}/events."""
    workspace = get_workspace_or_404(session, workspace_id)
    for source_id in body.source_ids:
        source = session.get(Source, source_id)
        if source is None or source.workspace_id != workspace_id:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, f"Source {source_id} is not in this workspace."
            )
    provider = provider_from_settings(
        settings,
        model_override=workspace.llm_model,
        transport=request.app.state.llm_transport,
    )
    if provider is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, NOT_CONFIGURED)
    run_id = start_run(
        request.app.state.session_factory,
        request.app.state.runner,
        workspace_id=workspace_id,
        workflow_type=body.workflow,
        stages=WORKFLOWS[body.workflow],
        initial={"source_ids": body.source_ids},
        checkpoint_path=settings.checkpoint_path(),
        services={"provider": provider},
    )
    run = session.get(Run, run_id)
    assert run is not None
    return _detail(session, run)


@router.get(
    "/api/workspaces/{workspace_id}/runs",
    response_model=list[RunSummary],
    operation_id="listRuns",
    responses=NOT_FOUND,
)
def list_runs(
    workspace_id: str,
    session: SessionDep,
    workflow: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
) -> list[RunSummary]:
    """Recent runs, newest first; sync runs only when asked for with workflow=sync."""
    get_workspace_or_404(session, workspace_id)
    query = select(Run).where(Run.workspace_id == workspace_id)
    if workflow:
        query = query.where(Run.workflow_type == workflow)
    else:
        query = query.where(Run.workflow_type != "sync")
    runs = session.scalars(query.order_by(Run.created_at.desc()).limit(limit)).all()
    return [_summary(run) for run in runs]


@router.get(
    "/api/runs/{run_id}", response_model=RunDetail, operation_id="getRun", responses=RUN_NOT_FOUND
)
def get_run(run_id: str, session: SessionDep) -> RunDetail:
    run = session.get(Run, run_id)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Run not found")
    return _detail(session, run)


def _stream(factory: sessionmaker[Session], run_id: str, after: int) -> Iterator[str]:
    """Events after `after`, as they are committed; ends after the run's final event."""
    last = after
    idle = 0.0
    since_heartbeat = 0.0
    while True:
        with factory() as session:
            events = session.scalars(
                select(RunEvent)
                .where(RunEvent.run_id == run_id, RunEvent.id > last)
                .order_by(RunEvent.id)
            ).all()
            run = session.get(Run, run_id)
            finished = run is None or run.status in TERMINAL
            batch = [(event.id, event.kind, _event(event).model_dump_json()) for event in events]
        for event_id, kind, payload in batch:
            last = event_id
            yield f"id: {event_id}\ndata: {payload}\n\n"
            if kind in FINAL_EVENTS:
                return
        if batch:
            idle = 0.0
            since_heartbeat = 0.0
        elif finished:
            idle += POLL_SECONDS
            if idle >= GRACE_SECONDS:
                return
        time.sleep(POLL_SECONDS)
        since_heartbeat += POLL_SECONDS
        if since_heartbeat >= HEARTBEAT_SECONDS:
            since_heartbeat = 0.0
            yield ": keep-alive\n\n"


@router.get(
    "/api/runs/{run_id}/events",
    operation_id="streamRunEvents",
    response_class=StreamingResponse,
    responses={
        200: {"content": {"text/event-stream": {}}, "description": "Server-Sent Events"},
        **RUN_NOT_FOUND,
    },
)
def stream_run_events(
    run_id: str,
    request: Request,
    session: SessionDep,
    last_event_id: Annotated[str | None, Header()] = None,
    after: Annotated[int, Query(ge=0)] = 0,
) -> StreamingResponse:
    """Live run events (ADR-0013); Last-Event-ID resumes after the given event."""
    if session.get(Run, run_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Run not found")
    resume = int(last_event_id) if last_event_id and last_event_id.isdigit() else 0
    return StreamingResponse(
        _stream(request.app.state.session_factory, run_id, max(after, resume)),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
