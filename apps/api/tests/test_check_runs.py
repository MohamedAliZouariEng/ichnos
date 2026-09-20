import datetime as dt
from typing import Any, cast

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from ichnos.db.engine import make_engine, make_session_factory
from ichnos.db.migrate import upgrade_to_head
from ichnos.db.models import CheckRun, GitHubItem, Workspace
from ichnos.github.reader import GitHubError, GitHubReader
from ichnos.settings import Settings
from ichnos.sync.checks import sync_checks
from ichnos.sync.reset import reset_knowledge

NOW = dt.datetime(2026, 9, 20, tzinfo=dt.UTC)


def run(
    run_id: int, status: str = "completed", conclusion: str | None = "success"
) -> dict[str, Any]:
    return {
        "id": run_id,
        "name": "pytest",
        "status": status,
        "conclusion": conclusion,
        "html_url": f"https://github.com/octo/quire/runs/{run_id}",
        "completed_at": "2026-09-20T10:00:00Z" if status == "completed" else None,
    }


class StubReader:
    def __init__(self, runs: dict[str, Any]) -> None:
        self.runs = runs
        self.calls: list[str] = []

    def check_runs(self, owner: str, repo: str, sha: str) -> list[dict[str, Any]]:
        self.calls.append(sha)
        result = self.runs.get(sha, [])
        if isinstance(result, GitHubError):
            raise result
        return list(result)


@pytest.fixture
def factory() -> sessionmaker[Session]:
    settings = Settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    upgrade_to_head(settings.sqlalchemy_url())
    made = make_session_factory(make_engine(settings))
    with made() as session:
        session.add(
            Workspace(
                id="ws", name="quire", repo_owner="octo", repo_name="quire", index_paths=["docs/"]
            )
        )
        session.flush()
        for number, head in ((19, "a" * 40), (18, "b" * 40), (11, "c" * 40)):
            session.add(
                GitHubItem(
                    workspace_id="ws",
                    number=number,
                    item_type="pull_request",
                    github_id=number,
                    title=f"PR {number}",
                    body="",
                    state="open",
                    labels=[],
                    head_sha=head,
                    url=f"https://github.com/octo/quire/pull/{number}",
                    created_at=NOW,
                    updated_at=NOW,
                )
            )
        session.commit()
    return made


def sync(factory: sessionmaker[Session], reader: StubReader) -> dict[str, int]:
    with factory() as session:
        workspace = session.get(Workspace, "ws")
        assert workspace is not None
        counts = sync_checks(session, cast(GitHubReader, reader), workspace)
        session.commit()
        return counts


def stored(factory: sessionmaker[Session]) -> list[tuple[int | None, str, str, str | None]]:
    with factory() as session:
        return [
            (r.pull_number, r.name, r.status, r.conclusion)
            for r in session.scalars(select(CheckRun).order_by(CheckRun.pull_number))
        ]


def test_runs_are_stored_and_completed_heads_cost_nothing_again(
    factory: sessionmaker[Session],
) -> None:
    reader = StubReader({"a" * 40: [run(1)], "b" * 40: [run(2, conclusion="failure")]})
    counts = sync(factory, reader)
    assert counts["checks_added"] == 2 and len(reader.calls) == 3  # PR 11 has no runs
    assert stored(factory) == [
        (18, "pytest", "completed", "failure"),
        (19, "pytest", "completed", "success"),
    ]
    sync(factory, reader)
    assert len(reader.calls) == 3  # every head was complete: no request on the second sync


def test_pending_runs_are_fetched_again_until_complete(factory: sessionmaker[Session]) -> None:
    reader = StubReader({"a" * 40: [run(1, "in_progress", None)]})
    sync(factory, reader)
    reader.runs["a" * 40] = [run(1)]
    counts = sync(factory, reader)
    assert counts["checks_updated"] == 1
    assert reader.calls.count("a" * 40) == 2
    assert (19, "pytest", "completed", "success") in stored(factory)


def test_unavailable_checks_do_not_stop_the_sync(factory: sessionmaker[Session]) -> None:
    reader = StubReader({"a" * 40: GitHubError(403, "Resource not accessible"), "b" * 40: [run(2)]})
    counts = sync(factory, reader)
    assert counts["checks_unavailable"] == 1 and counts["checks_added"] == 1


def test_reset_clears_check_runs(factory: sessionmaker[Session]) -> None:
    sync(factory, StubReader({"a" * 40: [run(1)]}))
    with factory() as session:
        deleted = reset_knowledge(session, "ws")
        session.commit()
    assert deleted["check_runs"] == 1 and stored(factory) == []
