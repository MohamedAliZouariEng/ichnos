import hashlib
from types import SimpleNamespace
from typing import Any, cast

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from ichnos.db.engine import make_engine, make_session_factory
from ichnos.db.migrate import upgrade_to_head
from ichnos.db.models import RepositoryFile, Workspace
from ichnos.github.reader import GitHubReader, TreeEntry
from ichnos.knowledge.links import Node, _Collector
from ichnos.settings import Settings
from ichnos.sync.cursors import set_cursor
from ichnos.sync.documents import sync_documents
from ichnos.sync.files import FILES_CURSOR, language_of
from ichnos.sync.reset import reset_knowledge

DOC = "---\ntype: Reference\ntitle: Overview\ndescription: About.\n---\n\n# Overview\n"


class StubReader:
    """Serves one branch head and a fixed tree; counts blob reads."""

    def __init__(self, files: dict[str, str], head: str = "c1") -> None:
        self.files, self.head, self.blob_reads = files, head, 0

    @staticmethod
    def sha(text: str) -> str:
        return hashlib.sha1(text.encode()).hexdigest()

    def branch_head(self, owner: str, repo: str, branch: str) -> str:
        return self.head

    def tree(self, owner: str, repo: str, sha: str) -> list[TreeEntry]:
        return [TreeEntry(p, self.sha(t), len(t)) for p, t in self.files.items()]

    def blob_text(self, owner: str, repo: str, sha: str) -> str:
        self.blob_reads += 1
        return next(t for t in self.files.values() if self.sha(t) == sha)


@pytest.fixture
def factory() -> sessionmaker[Session]:
    settings = Settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    upgrade_to_head(settings.sqlalchemy_url())
    return make_session_factory(make_engine(settings))


def sync(factory: sessionmaker[Session], reader: StubReader) -> dict[str, int]:
    with factory() as session:
        workspace = session.scalar(select(Workspace))
        if workspace is None:
            workspace = Workspace(
                name="quire", repo_owner="octo", repo_name="quire", index_paths=["docs/"]
            )
            session.add(workspace)
            session.flush()
        counts = sync_documents(session, cast(GitHubReader, reader), workspace)
        session.commit()
        return counts


def files(factory: sessionmaker[Session]) -> dict[str, Any]:
    with factory() as session:
        return {
            f.path: (f.language, f.size, f.commit_sha)
            for f in session.scalars(select(RepositoryFile))
        }


def test_files_outside_the_bundle_are_recorded_without_contents(
    factory: sessionmaker[Session],
) -> None:
    reader = StubReader(
        {
            "docs/index.md": DOC,
            "docs/images/logo.png": "png",
            "src/quire/invitations/service.py": "def accept(): ...\n",
            "pyproject.toml": "[project]\n",
            "Dockerfile": "FROM python\n",
        }
    )
    counts = sync(factory, reader)
    assert counts["files_added"] == 3 and counts["documents_added"] == 1
    assert files(factory) == {
        "src/quire/invitations/service.py": ("Python", 18, "c1"),
        "pyproject.toml": ("TOML", 10, "c1"),
        "Dockerfile": ("Dockerfile", 12, "c1"),
    }
    assert reader.blob_reads == 1  # only the document was read


def test_files_follow_blob_changes_and_deletions(factory: sessionmaker[Session]) -> None:
    sync(factory, StubReader({"docs/index.md": DOC, "a.py": "1", "b.py": "2"}))
    counts = sync(
        factory,
        StubReader({"docs/index.md": DOC, "a.py": "1", "c.py": "3", "b.py": "22"}, head="c2"),
    )
    assert (counts["files_unchanged"], counts["files_added"], counts["files_updated"]) == (1, 1, 1)
    again = sync(factory, StubReader({"docs/index.md": DOC, "a.py": "1"}, head="c3"))
    assert again["files_deleted"] == 2
    assert set(files(factory)) == {"a.py"}


def test_existing_workspaces_record_files_once_even_when_documents_are_current(
    factory: sessionmaker[Session],
) -> None:
    reader = StubReader({"docs/index.md": DOC, "a.py": "1"})
    sync(factory, reader)
    with factory() as session:  # simulate a workspace synced before Phase 5
        session.query(RepositoryFile).delete()
        workspace = session.scalar(select(Workspace))
        assert workspace is not None
        set_cursor(session, workspace.id, FILES_CURSOR, "older")
        session.commit()
    counts = sync(factory, reader)
    assert counts["files_added"] == 1
    assert sync(factory, reader)["files_unchanged"] == 1  # now the cheap path


def test_reset_clears_repository_files(factory: sessionmaker[Session]) -> None:
    sync(factory, StubReader({"docs/index.md": DOC, "a.py": "1"}))
    with factory() as session:
        workspace = session.scalar(select(Workspace))
        assert workspace is not None
        deleted = reset_knowledge(session, workspace.id)
        session.commit()
    assert deleted["repository_files"] == 1 and files(factory) == {}


def test_languages() -> None:
    assert language_of("src/app.tsx") == "TypeScript"
    assert language_of("Makefile") == "Makefile"
    assert language_of("LICENSE") is None


def test_depends_on_is_an_explicit_link() -> None:
    collector = _Collector(cast(Any, SimpleNamespace(items={}, documents={})))
    body = "As a user...\n\n## Dependencies\n- Depends on #7\n\nSee also #9.\n"
    collector.scan_text(Node("issue", "8"), body, "Issue #8 body", conventions=True, closing=False)
    links = {(r.target.key, r.relation, r.origin) for r in collector.result()}
    assert ("7", "depends_on", "explicit") in links
    assert ("7", "mentions", "inferred") not in links  # the explicit link replaces the mention
    assert ("9", "mentions", "inferred") in links
