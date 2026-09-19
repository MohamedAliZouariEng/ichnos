import pytest
from sqlalchemy import inspect, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from ichnos.db import models
from ichnos.db.engine import make_engine, make_session_factory
from ichnos.db.migrate import upgrade_to_head
from ichnos.settings import Settings
from ichnos.sync.reset import reset_knowledge

WORKFLOW_TABLES = {"sources", "artifacts", "artifact_versions", "run_events"}


@pytest.fixture
def factory() -> sessionmaker[Session]:
    settings = Settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    upgrade_to_head(settings.sqlalchemy_url())
    return make_session_factory(make_engine(settings))


def _workspace(session: Session) -> str:
    workspace = models.Workspace(name="demo", repo_owner="octo", repo_name="demo")
    session.add(workspace)
    session.flush()
    return workspace.id


def _artifact(session: Session, workspace_id: str) -> models.Artifact:
    artifact = models.Artifact(
        workspace_id=workspace_id, kind="brd", title="Invitation expiry", slug="invitation-expiry"
    )
    session.add(artifact)
    session.flush()
    return artifact


def _version(artifact_id: str, number: int) -> models.ArtifactVersion:
    return models.ArtifactVersion(
        artifact_id=artifact_id,
        number=number,
        content=f"# Version {number}\n",
        origin="generated" if number == 1 else "edited",
        actor="ichnos/fake" if number == 1 else "human:local",
        parent_number=None if number == 1 else number - 1,
    )


def test_workflow_tables_exist(factory: sessionmaker[Session]) -> None:
    with factory() as session:
        tables = set(inspect(session.get_bind()).get_table_names())
    assert tables >= WORKFLOW_TABLES


def test_version_numbers_are_unique_per_artifact(factory: sessionmaker[Session]) -> None:
    with factory() as session:
        artifact = _artifact(session, _workspace(session))
        session.add(_version(artifact.id, 1))
        session.commit()
        session.add(_version(artifact.id, 1))
        with pytest.raises(IntegrityError):
            session.commit()


def test_versions_and_events_follow_their_parent(factory: sessionmaker[Session]) -> None:
    with factory() as session:
        workspace_id = _workspace(session)
        run = models.Run(workspace_id=workspace_id, workflow_type="requirements")
        session.add(run)
        session.flush()
        artifact = _artifact(session, workspace_id)
        artifact.run_id = run.id
        session.add_all([_version(artifact.id, 1), _version(artifact.id, 2)])
        for kind in ("run.started", "stage.started", "stage.completed"):
            session.add(models.RunEvent(run_id=run.id, kind=kind, message=kind))
        session.commit()

        events = session.scalars(select(models.RunEvent).order_by(models.RunEvent.id)).all()
        assert [event.kind for event in events] == [
            "run.started",
            "stage.started",
            "stage.completed",
        ]

        session.delete(run)
        session.commit()
        assert session.query(models.RunEvent).count() == 0
        session.refresh(artifact)
        assert artifact.run_id is None  # the artifact outlives its run

        session.delete(artifact)
        session.commit()
        assert session.query(models.ArtifactVersion).count() == 0


def test_knowledge_reset_keeps_sources_and_drafts(factory: sessionmaker[Session]) -> None:
    with factory() as session:
        workspace_id = _workspace(session)
        session.add(
            models.Source(
                workspace_id=workspace_id,
                kind="pasted",
                title="Onboarding sync",
                content="Invitations expire after 7 days.",
                content_sha256="0" * 64,
                created_by="human:local",
            )
        )
        artifact = _artifact(session, workspace_id)
        session.add(_version(artifact.id, 1))
        session.commit()

        reset_knowledge(session, workspace_id)
        session.commit()

        assert session.query(models.Source).count() == 1
        assert session.query(models.Artifact).count() == 1
        assert session.query(models.ArtifactVersion).count() == 1
