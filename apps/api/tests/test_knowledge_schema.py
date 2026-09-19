import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from ichnos.db import models
from ichnos.db.engine import make_engine, make_session_factory
from ichnos.db.migrate import upgrade_to_head
from ichnos.settings import Settings

KNOWLEDGE_TABLES = {
    "documents",
    "github_items",
    "github_comments",
    "commits",
    "pull_request_files",
    "pull_request_commits",
    "links",
    "chunks",
    "chunks_fts",
}

SEARCH = (
    "SELECT c.heading FROM chunks_fts JOIN chunks AS c ON c.id = chunks_fts.rowid "
    "WHERE chunks_fts MATCH :query"
)


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


def _document(workspace_id: str, path: str) -> models.Document:
    return models.Document(
        workspace_id=workspace_id,
        path=path,
        blob_sha="a" * 40,
        commit_sha="b" * 40,
        kind="concept",
        trust_tier="human_verified",
        body="Text",
    )


def test_knowledge_tables_exist(factory: sessionmaker[Session]) -> None:
    with factory() as session:
        tables = set(inspect(session.get_bind()).get_table_names())
    assert tables >= KNOWLEDGE_TABLES


def test_full_text_index_follows_chunks(factory: sessionmaker[Session]) -> None:
    with factory() as session:
        workspace_id = _workspace(session)
        chunk = models.Chunk(
            workspace_id=workspace_id,
            source_kind="document",
            source_key="docs/meetings/sync.md",
            ordinal=0,
            heading="Decisions",
            text="Invitations expire after seven days.",
        )
        session.add(chunk)
        session.commit()

        # Porter stemming: "expiring" matches "expire".
        found = session.execute(text(SEARCH), {"query": "expiring"}).scalars().all()
        assert found == ["Decisions"]

        chunk.text = "Admins can resend an invitation."
        session.commit()
        assert session.execute(text(SEARCH), {"query": "expire"}).scalars().all() == []
        assert session.execute(text(SEARCH), {"query": "resend"}).scalars().all() == ["Decisions"]

        session.delete(chunk)
        session.commit()
        assert session.execute(text(SEARCH), {"query": "resend"}).scalars().all() == []


def test_document_path_is_unique_per_workspace(factory: sessionmaker[Session]) -> None:
    with factory() as session:
        workspace_id = _workspace(session)
        session.add(_document(workspace_id, "docs/a.md"))
        session.commit()
        session.add(_document(workspace_id, "docs/a.md"))
        with pytest.raises(IntegrityError):
            session.commit()


def test_deleting_a_workspace_removes_its_knowledge(factory: sessionmaker[Session]) -> None:
    with factory() as session:
        workspace_id = _workspace(session)
        session.add(_document(workspace_id, "docs/a.md"))
        session.add(
            models.Chunk(
                workspace_id=workspace_id,
                source_kind="document",
                source_key="docs/a.md",
                ordinal=0,
                text="Glossary of invitation terms.",
            )
        )
        session.commit()

        workspace = session.get(models.Workspace, workspace_id)
        assert workspace is not None
        session.delete(workspace)
        session.commit()

        assert session.query(models.Document).count() == 0
        assert session.query(models.Chunk).count() == 0
        assert session.execute(text(SEARCH), {"query": "glossary"}).scalars().all() == []
