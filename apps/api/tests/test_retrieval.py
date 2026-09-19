import pytest
from sqlalchemy.orm import Session, sessionmaker

from ichnos.db import models
from ichnos.db.base import utc_now
from ichnos.db.engine import make_engine, make_session_factory
from ichnos.db.migrate import upgrade_to_head
from ichnos.settings import Settings
from ichnos.workflows.engine import StageContext, StageFailed
from ichnos.workflows.retrieval import describe_retrieval, keywords, retrieval_stage, retrieve

NOTE_BODY = (
    "# Decisions\n\nInvitations expire after 7 days. Invitation tokens must stay single-use.\n"
)
NOTE = "---\ntype: Meeting Note\ntitle: Onboarding sync\n---\n" + NOTE_BODY
TOKEN_TEXT = "Invitation tokens are single-use and stored as hashes."


@pytest.fixture
def factory() -> sessionmaker[Session]:
    settings = Settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    upgrade_to_head(settings.sqlalchemy_url())
    return make_session_factory(make_engine(settings))


def _doc(
    ws: str,
    path: str,
    *,
    kind: str = "concept",
    tier: str = "human_verified",
    doc_type: str | None = "Decision",
    title: str | None = None,
    body: str = "",
) -> models.Document:
    return models.Document(
        workspace_id=ws,
        path=path,
        blob_sha="a" * 40,
        commit_sha="c" * 40,
        kind=kind,
        doc_type=doc_type,
        title=title or path,
        trust_tier=tier,
        body=body,
    )


def _chunk(ws: str, kind: str, key: str, heading: str, body: str) -> models.Chunk:
    return models.Chunk(
        workspace_id=ws, source_kind=kind, source_key=key, ordinal=0, heading=heading, text=body
    )


@pytest.fixture
def workspace(factory: sessionmaker[Session]) -> str:
    with factory() as session:
        ws = models.Workspace(name="quire", repo_owner="octo", repo_name="quire")
        session.add(ws)
        session.flush()
        w = ws.id
        session.add_all(
            [
                _doc(w, "docs/adr/0001-tokens.md", title="ADR-0001: Tokens"),
                _doc(w, "docs/notes/draft.md", tier="unknown", doc_type="Note", title="Draft"),
                _doc(w, "docs/index.md", kind="index", tier="unknown", doc_type=None),
                _doc(w, "docs/project/overview.md", doc_type="Reference", title="Overview"),
                _chunk(w, "document", "docs/adr/0001-tokens.md", "Decision", TOKEN_TEXT),
                _chunk(w, "document", "docs/notes/draft.md", "Draft", TOKEN_TEXT),
                _chunk(w, "document", "docs/index.md", "Docs", "Invitation tokens index entry."),
                _chunk(
                    w, "document", "docs/project/overview.md", "Product", "Quire is a notebook."
                ),
                models.GitHubItem(
                    workspace_id=w,
                    number=2,
                    item_type="issue",
                    github_id=1002,
                    title="Explain invalid invitation links",
                    state="open",
                    url="https://github.com/o/r/issues/2",
                    created_at=utc_now(),
                    updated_at=utc_now(),
                ),
                _chunk(w, "issue", "2", "Explain", "Invitation links that expire should say why."),
                models.Link(
                    workspace_id=w,
                    source_kind="document",
                    source_key="docs/adr/0001-tokens.md",
                    target_kind="document",
                    target_key="docs/project/overview.md",
                    relation="references",
                    origin="explicit",
                    evidence="The ADR links the overview",
                    confidence=1.0,
                    resolved=True,
                ),
                models.Source(
                    id="src-1",
                    workspace_id=w,
                    kind="pasted",
                    title="Onboarding sync",
                    content=NOTE,
                    content_sha256="0" * 64,
                    created_by="human:local",
                ),
            ]
        )
        session.commit()
        return w


def _keys(factory: sessionmaker[Session], workspace: str) -> tuple[list[str], list[dict[str, str]]]:
    with factory() as session:
        source = session.get(models.Source, "src-1")
        assert source is not None
        found = retrieve(session, workspace, [source])
    return [item["key"] for item in found.context], found.context


def test_keywords_come_from_the_body_not_the_frontmatter() -> None:
    words = keywords([NOTE])
    assert {"invitations", "expire", "tokens"} <= set(words)
    assert "meeting" not in words and "type" not in words


def test_retrieval_weights_trust_skips_indexes_and_expands_links(
    factory: sessionmaker[Session], workspace: str
) -> None:
    keys, context = _keys(factory, workspace)
    assert [item["id"] for item in context] == [f"C{n}" for n in range(1, len(keys) + 1)]
    assert keys.index("docs/adr/0001-tokens.md") < keys.index("docs/notes/draft.md")
    assert "docs/index.md" not in keys
    assert "2" in keys
    overview = next(item for item in context if item["key"] == "docs/project/overview.md")
    assert overview["reason"] == "linked from docs/adr/0001-tokens.md (references)"
    adr = next(item for item in context if item["key"] == "docs/adr/0001-tokens.md")
    assert adr["reason"].startswith("matched: ")
    assert adr["trust_tier"] == "human_verified"


def test_a_document_identical_to_a_source_is_skipped(
    factory: sessionmaker[Session], workspace: str
) -> None:
    with factory() as session:
        session.add_all(
            [
                _doc(
                    workspace,
                    "docs/meetings/sync.md",
                    doc_type="Meeting Note",
                    title="Onboarding sync",
                    body="\n" + NOTE_BODY.replace(" ", "  "),  # same text, other whitespace
                ),
                _chunk(workspace, "document", "docs/meetings/sync.md", "Decisions", NOTE_BODY),
            ]
        )
        session.commit()
    keys, _ = _keys(factory, workspace)
    assert "docs/meetings/sync.md" not in keys
    assert "docs/adr/0001-tokens.md" in keys


def test_a_document_used_as_source_is_not_returned_as_context(
    factory: sessionmaker[Session], workspace: str
) -> None:
    with factory() as session:
        source = models.Source(
            workspace_id=workspace,
            kind="document",
            title="ADR",
            content=TOKEN_TEXT,
            content_sha256="1" * 64,
            created_by="human:local",
            document_path="docs/adr/0001-tokens.md",
        )
        found = retrieve(session, workspace, [source])
    assert "docs/adr/0001-tokens.md" not in [item["key"] for item in found.context]


def test_the_stage_reports_what_it_found(factory: sessionmaker[Session], workspace: str) -> None:
    context = StageContext(run_id="run-1", workspace_id=workspace, factory=factory)
    update = retrieval_stage({"source_ids": ["src-1"]}, context)
    assert update["sources"][0]["id"] == "S1"
    assert update["sources"][0]["title"] == "Onboarding sync"
    summary = describe_retrieval(update)
    assert summary.startswith(f"{len(update['context'])} context items (")
    assert "keywords: " in summary


def test_the_stage_fails_clearly_without_sources(
    factory: sessionmaker[Session], workspace: str
) -> None:
    context = StageContext(run_id="run-1", workspace_id=workspace, factory=factory)
    with pytest.raises(StageFailed, match="no sources"):
        retrieval_stage({"source_ids": []}, context)
    with pytest.raises(StageFailed, match="not found"):
        retrieval_stage({"source_ids": ["missing"]}, context)
