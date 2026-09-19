"""Workflow engine (ADR-0011).

A workflow is a list of stages. Each stage is a plain function that takes the pipeline state
and a context and returns updates; LangGraph only wires the stages together and checkpoints
the state. Every stage change is written to run_events as it happens (ADR-0013).

A stage marked waits=True pauses at a LangGraph interrupt: the run becomes `waiting`, and
resume_run continues it from its SQLite checkpoint with a decision, even after a restart.
"""

import logging
import sqlite3
import time
from collections.abc import Callable, Mapping
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TypedDict

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from ichnos.db.base import new_id, utc_now
from ichnos.db.models import Run, RunEvent
from ichnos.llm import ModelError, Usage

logger = logging.getLogger(__name__)

UNEXPECTED = "unexpected error; see the API logs"
Data = dict[str, Any]


class StageFailed(Exception):
    """A stage failed with a message that is safe and useful to show to people."""


class PipelineState(TypedDict, total=False):
    data: Data


@dataclass
class StageContext:
    run_id: str
    workspace_id: str
    factory: sessionmaker[Session]
    services: Mapping[str, Any] = field(default_factory=dict)
    usage: Usage = field(default_factory=Usage)
    stage: str | None = None

    def note(self, message: str, **data: Any) -> None:
        """Add an informational event to the run's log."""
        record_event(self.factory, self.run_id, "log", message, stage=self.stage, data=data)


@dataclass(frozen=True)
class Stage:
    name: str
    run: Callable[[Data, StageContext], Data]
    describe: Callable[[Data], str] | None = None
    waits: bool = False  # pause for a human decision first (a LangGraph interrupt)


def record_event(
    factory: sessionmaker[Session],
    run_id: str,
    kind: str,
    message: str,
    *,
    stage: str | None = None,
    data: Mapping[str, Any] | None = None,
    status: str | None = None,
) -> None:
    """Commit one event immediately, optionally moving the run to a new stage or status."""
    with factory() as session:
        session.add(
            RunEvent(run_id=run_id, kind=kind, stage=stage, message=message, data=dict(data or {}))
        )
        run = session.get(Run, run_id)
        if run is not None:
            if kind == "stage.started":
                run.stage = stage
            if status is not None:
                run.status = status
        session.commit()


def _wrap(stage: Stage, context: StageContext) -> Callable[..., PipelineState]:
    """LangGraph types nodes as a protocol with a parameter named state; `...` satisfies it."""

    def node(state: PipelineState) -> PipelineState:
        data = dict(state.get("data", {}))
        if stage.waits:
            # First arrival pauses the graph here; resuming returns the decision.
            data["decision"] = interrupt({"stage": stage.name, "run_id": context.run_id})
        context.stage = stage.name
        record_event(context.factory, context.run_id, "stage.started", stage.name, stage=stage.name)
        started = time.monotonic()
        try:
            update = stage.run(data, context)
        except (StageFailed, ModelError) as exc:
            message = str(exc)
        except Exception:
            logger.exception("Stage %s of run %s failed", stage.name, context.run_id)
            message = UNEXPECTED
        else:
            duration = int((time.monotonic() - started) * 1000)
            summary = stage.describe(update) if stage.describe else f"{stage.name} completed"
            record_event(
                context.factory,
                context.run_id,
                "stage.completed",
                summary,
                stage=stage.name,
                data={"duration_ms": duration},
            )
            return {"data": {**data, **update}}
        duration = int((time.monotonic() - started) * 1000)
        record_event(
            context.factory,
            context.run_id,
            "stage.failed",
            message,
            stage=stage.name,
            data={"duration_ms": duration},
        )
        raise StageFailed(f"{stage.name}: {message}")

    return node


def _usage(prior: Any, usage: Usage) -> dict[str, int]:
    base = prior if isinstance(prior, dict) else {}
    return {key: int(base.get(key, 0)) + value for key, value in usage.as_dict().items()}


def _execute(
    factory: sessionmaker[Session],
    run_id: str,
    stages: list[Stage],
    graph_input: Any,
    *,
    checkpoint_path: Path,
    services: Mapping[str, Any] | None,
) -> None:
    with factory() as session:
        run = session.get(Run, run_id)
        if run is None:
            raise LookupError(run_id)
        workspace_id = run.workspace_id
    context = StageContext(run_id, workspace_id, factory, services or {})

    builder = StateGraph(PipelineState)
    previous = START
    for stage in stages:
        builder.add_node(stage.name, _wrap(stage, context))
        builder.add_edge(previous, stage.name)
        previous = stage.name
    builder.add_edge(previous, END)

    config: Any = {"configurable": {"thread_id": run_id}}
    error: str | None = None
    paused = False
    result: dict[str, Any] = {}
    connection = sqlite3.connect(checkpoint_path, check_same_thread=False)
    try:
        graph = builder.compile(checkpointer=SqliteSaver(connection))
        result = graph.invoke(graph_input, config=config)
        paused = bool(graph.get_state(config).next)
    except StageFailed as exc:
        error = str(exc)
    except Exception:
        logger.exception("Run %s failed outside a stage", run_id)
        error = UNEXPECTED
    finally:
        connection.close()

    waiting = paused and error is None
    with factory() as session:
        run = session.get(Run, run_id)
        assert run is not None
        outputs = dict(run.outputs or {})
        outputs["usage"] = _usage(outputs.get("usage"), context.usage)
        if waiting:
            run.status = "waiting"
        else:
            run.status = "failed" if error else "succeeded"
            run.error = error
            run.finished_at = utc_now()
            outputs["result"] = dict(result.get("data", {})).get("result", {})
        run.outputs = outputs
        session.commit()
    if waiting:
        record_event(factory, run_id, "run.waiting", "Waiting for a human decision")
    elif error:
        record_event(factory, run_id, "run.failed", error)
    else:
        record_event(factory, run_id, "run.completed", "Run completed")


def run_pipeline(
    factory: sessionmaker[Session],
    run_id: str,
    stages: list[Stage],
    initial: Data,
    *,
    checkpoint_path: Path,
    services: Mapping[str, Any] | None = None,
) -> None:
    """Execute the stages in order; the run's status, events and outputs record everything."""
    record_event(factory, run_id, "run.started", "Run started", status="running")
    _execute(
        factory,
        run_id,
        stages,
        {"data": initial},
        checkpoint_path=checkpoint_path,
        services=services,
    )


def resume_pipeline(
    factory: sessionmaker[Session],
    run_id: str,
    stages: list[Stage],
    decision: Data,
    *,
    checkpoint_path: Path,
    services: Mapping[str, Any] | None = None,
) -> None:
    """Continue a waiting run from its checkpoint; finished stages do not run again."""
    record_event(factory, run_id, "run.resumed", "Run resumed after a decision", status="running")
    _execute(
        factory,
        run_id,
        stages,
        Command(resume=decision),
        checkpoint_path=checkpoint_path,
        services=services,
    )


class WorkflowRunner:
    """A small background pool: starting a run returns at once (ADR-0011)."""

    def __init__(self, max_workers: int = 2) -> None:
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers, thread_name_prefix="ichnos-run"
        )
        self._futures: dict[str, Future[None]] = {}

    def submit(self, run_id: str, job: Callable[[], None]) -> None:
        self._futures[run_id] = self._executor.submit(job)

    def wait(self, run_id: str, timeout: float | None = None) -> None:
        """Block until the run's latest job finishes; used by tests and scripts."""
        future = self._futures.get(run_id)
        if future is not None:
            future.result(timeout=timeout)

    def shutdown(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)


def start_run(
    factory: sessionmaker[Session],
    runner: WorkflowRunner,
    *,
    workspace_id: str,
    workflow_type: str,
    stages: list[Stage],
    initial: Data,
    checkpoint_path: Path,
    services: Mapping[str, Any] | None = None,
) -> str:
    """Create a queued run and hand it to the background pool; returns the run id."""
    run_id = new_id()
    with factory() as session:
        session.add(
            Run(
                id=run_id,
                workspace_id=workspace_id,
                workflow_type=workflow_type,
                status="queued",
                inputs=dict(initial),
            )
        )
        session.commit()
    record_event(factory, run_id, "run.queued", f"{workflow_type} run queued")

    def job() -> None:
        run_pipeline(
            factory, run_id, stages, initial, checkpoint_path=checkpoint_path, services=services
        )

    runner.submit(run_id, job)
    return run_id


def resume_run(
    factory: sessionmaker[Session],
    runner: WorkflowRunner,
    run_id: str,
    *,
    stages: list[Stage],
    decision: Data,
    checkpoint_path: Path,
    services: Mapping[str, Any] | None = None,
) -> None:
    """Hand a waiting run's continuation to the background pool."""

    def job() -> None:
        resume_pipeline(
            factory, run_id, stages, decision, checkpoint_path=checkpoint_path, services=services
        )

    runner.submit(run_id, job)


def mark_interrupted(factory: sessionmaker[Session]) -> int:
    """At startup nothing can be running: mark leftover runs interrupted; checkpoints remain.

    Waiting runs are untouched: they wait for a human, not for this process.
    """
    message = "The API stopped while this run was in progress."
    with factory() as session:
        runs = session.scalars(select(Run).where(Run.status.in_(("queued", "running")))).all()
        ids = [run.id for run in runs]
        for run in runs:
            run.status = "interrupted"
            run.error = message
            run.finished_at = utc_now()
        session.commit()
    for run_id in ids:
        record_event(factory, run_id, "run.interrupted", message)
    return len(ids)
