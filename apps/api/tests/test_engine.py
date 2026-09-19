import sqlite3
from typing import Any

import pytest
from langgraph.checkpoint.sqlite import SqliteSaver
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from ichnos.db import models
from ichnos.db.engine import make_engine, make_session_factory
from ichnos.db.migrate import upgrade_to_head
from ichnos.llm import ModelError, Usage
from ichnos.settings import Settings
from ichnos.workflows.engine import (
    Stage,
    StageContext,
    StageFailed,
    WorkflowRunner,
    mark_interrupted,
    start_run,
)

Data = dict[str, Any]


@pytest.fixture
def settings() -> Settings:
    settings = Settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    upgrade_to_head(settings.sqlalchemy_url())
    return settings


@pytest.fixture
def factory(settings: Settings) -> sessionmaker[Session]:
    return make_session_factory(make_engine(settings))


@pytest.fixture
def workspace_id(factory: sessionmaker[Session]) -> str:
    with factory() as session:
        workspace = models.Workspace(name="demo", repo_owner="octo", repo_name="demo")
        session.add(workspace)
        session.commit()
        return workspace.id


def collect(data: Data, context: StageContext) -> Data:
    context.note("collected", items=2)
    return {"items": [data["seed"], data["seed"] * 2]}


def total(data: Data, context: StageContext) -> Data:
    extra = Usage()
    extra.add({"prompt_tokens": 7, "completion_tokens": 3, "total_tokens": 10})
    context.usage.merge(extra)
    return {"result": {"total": sum(data["items"])}}


STAGES = [
    Stage("collect", collect, describe=lambda update: f"{len(update['items'])} items"),
    Stage("total", total),
]


def run(
    settings: Settings,
    factory: sessionmaker[Session],
    workspace_id: str,
    stages: list[Stage],
) -> models.Run:
    runner = WorkflowRunner()
    run_id = start_run(
        factory,
        runner,
        workspace_id=workspace_id,
        workflow_type="example",
        stages=stages,
        initial={"seed": 2},
        checkpoint_path=settings.checkpoint_path(),
    )
    runner.wait(run_id, timeout=30)
    runner.shutdown()
    with factory() as session:
        found = session.get(models.Run, run_id)
        assert found is not None
        return found


def events(factory: sessionmaker[Session], run_id: str) -> list[tuple[str, str | None, str]]:
    with factory() as session:
        rows = session.scalars(
            select(models.RunEvent)
            .where(models.RunEvent.run_id == run_id)
            .order_by(models.RunEvent.id)
        ).all()
    return [(row.kind, row.stage, row.message) for row in rows]


def test_stages_run_in_order_in_the_background(
    settings: Settings, factory: sessionmaker[Session], workspace_id: str
) -> None:
    finished = run(settings, factory, workspace_id, STAGES)

    assert finished.status == "succeeded"
    assert finished.stage == "total"
    assert finished.outputs["result"] == {"total": 6}
    assert finished.outputs["usage"]["total_tokens"] == 10
    assert events(factory, finished.id) == [
        ("run.queued", None, "example run queued"),
        ("run.started", None, "Run started"),
        ("stage.started", "collect", "collect"),
        ("log", "collect", "collected"),
        ("stage.completed", "collect", "2 items"),
        ("stage.started", "total", "total"),
        ("stage.completed", "total", "total completed"),
        ("run.completed", None, "Run completed"),
    ]


def test_state_is_checkpointed_per_run(
    settings: Settings, factory: sessionmaker[Session], workspace_id: str
) -> None:
    finished = run(settings, factory, workspace_id, STAGES)
    connection = sqlite3.connect(settings.checkpoint_path(), check_same_thread=False)
    try:
        saved = SqliteSaver(connection).get_tuple({"configurable": {"thread_id": finished.id}})
    finally:
        connection.close()
    assert saved is not None
    assert saved.checkpoint["channel_values"]["data"]["result"] == {"total": 6}


@pytest.mark.parametrize(
    ("error", "shown"),
    [
        (StageFailed("no sources were given"), "total: no sources were given"),
        (
            ModelError("The model provider returned HTTP 429"),
            "total: The model provider returned HTTP 429",
        ),
        (RuntimeError("secret internal detail"), "total: unexpected error; see the API logs"),
    ],
)
def test_failures_stop_the_run_with_a_readable_message(
    settings: Settings,
    factory: sessionmaker[Session],
    workspace_id: str,
    error: Exception,
    shown: str,
) -> None:
    def broken(data: Data, context: StageContext) -> Data:
        raise error

    reached: list[str] = []

    def after(data: Data, context: StageContext) -> Data:
        reached.append("after")
        return {}

    stages = [STAGES[0], Stage("total", broken), Stage("after", after)]
    finished = run(settings, factory, workspace_id, stages)

    assert finished.status == "failed"
    assert finished.error == shown
    assert reached == []
    kinds = [kind for kind, _, _ in events(factory, finished.id)]
    assert kinds[-2:] == ["stage.failed", "run.failed"]
    assert "secret internal detail" not in str(events(factory, finished.id))


def test_leftover_runs_are_marked_interrupted_at_startup(
    factory: sessionmaker[Session], workspace_id: str
) -> None:
    with factory() as session:
        session.add(
            models.Run(workspace_id=workspace_id, workflow_type="requirements", status="running")
        )
        session.add(models.Run(workspace_id=workspace_id, workflow_type="sync", status="succeeded"))
        session.commit()

    assert mark_interrupted(factory) == 1
    with factory() as session:
        statuses = sorted(run.status for run in session.scalars(select(models.Run)))
    assert statuses == ["interrupted", "succeeded"]
