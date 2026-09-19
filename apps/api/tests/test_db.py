import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError

from ichnos.db import models
from ichnos.db.base import Base
from ichnos.db.engine import make_engine, make_session_factory
from ichnos.db.migrate import upgrade_to_head
from ichnos.settings import Settings

EXPECTED_TABLES = {"workspaces", "sync_cursors", "runs", "approvals", "audit_events"}


@pytest.fixture
def settings() -> Settings:
    settings = Settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    upgrade_to_head(settings.sqlalchemy_url())
    return settings


def test_migrations_create_all_tables(settings: Settings) -> None:
    tables = set(inspect(make_engine(settings)).get_table_names())
    assert EXPECTED_TABLES <= tables
    assert "alembic_version" in tables


def test_migrations_match_models(settings: Settings) -> None:
    with make_engine(settings).connect() as connection:
        diff = compare_metadata(MigrationContext.configure(connection), Base.metadata)
    assert diff == []


def test_workspace_round_trip(settings: Settings) -> None:
    factory = make_session_factory(make_engine(settings))
    with factory() as session:
        workspace = models.Workspace(
            name="demo", repo_owner="octo", repo_name="demo", index_paths=["docs/"]
        )
        session.add(workspace)
        session.commit()
        workspace_id = workspace.id
    with factory() as session:
        loaded = session.get(models.Workspace, workspace_id)
        assert loaded is not None
        assert loaded.branch == "main"
        assert loaded.index_paths == ["docs/"]


def test_foreign_keys_are_enforced(settings: Settings) -> None:
    factory = make_session_factory(make_engine(settings))
    with factory() as session:
        session.add(models.Run(workspace_id="missing", workflow_type="requirements"))
        with pytest.raises(IntegrityError):
            session.commit()
