import datetime as dt

import pytest
from sqlalchemy.orm import Session, sessionmaker

from ichnos.context.pack import ContextPack, PackError, build_pack
from ichnos.db.engine import make_engine, make_session_factory
from ichnos.db.migrate import upgrade_to_head
from ichnos.db.models import Document, GitHubItem, Link, RepositoryFile, Workspace
from ichnos.settings import Settings

NOW = dt.datetime(2026, 9, 20, tzinfo=dt.UTC)
BRD = "docs/specs/invitation-expiry/brd.md"
ADR1 = "docs/adr/0001-invitation-tokens.md"
ADR9 = "docs/adr/0009-old-invitation-emails.md"
STORY = (
    "As a workspace administrator, I want invitation links to expire after 7 days.\n\n"
    "## Parent\n- Epic: #6\n\n## Source specification\n- " + BRD + "\n\n"
    "## Acceptance criteria\n"
    "- [ ] AC-01: Given an invitation link sent 7 days ago, then it expires.\n"
)
FILES = {
    "src/quire/invitations/service.py": "def accept(token): ...\n",
    "src/quire/invitations/tokens.py": "def new_token(): ...\n",
    "src/quire/invitations/__init__.py": '"""Invitations."""\n',
    "src/quire/billing.py": "def charge(): ...\n",
    "tests/test_invitations.py": "def test_accept(): ...\n",
    "src/quire/invitations/huge.py": "x" * 50_000,
}
BLOBS = {f"{n:040x}": text for n, text in enumerate(FILES.values(), start=1)}
SHAS = {path: f"{n:040x}" for n, path in enumerate(FILES, start=1)}


def issue(
    number: int, title: str, body: str, state: str = "open", reason: str | None = None
) -> GitHubItem:
    return GitHubItem(
        workspace_id="ws",
        number=number,
        item_type="issue",
        github_id=number,
        title=title,
        body=body,
        state=state,
        state_reason=reason,
        labels=[],
        url=f"https://github.com/octo/quire/issues/{number}",
        created_at=NOW,
        updated_at=NOW,
    )


def doc(
    path: str, doc_type: str, title: str, body: str, trust: str, fm: dict[str, str] | None = None
) -> Document:
    return Document(
        workspace_id="ws",
        path=path,
        blob_sha="b" * 40,
        commit_sha="c" * 40,
        kind="concept",
        doc_type=doc_type,
        title=title,
        trust_tier=trust,
        frontmatter=fm or {},
        body=body,
        findings=[],
    )


def link(
    source: tuple[str, str], target: tuple[str, str], relation: str, origin: str = "explicit"
) -> Link:
    return Link(
        workspace_id="ws",
        source_kind=source[0],
        source_key=source[1],
        target_kind=target[0],
        target_key=target[1],
        relation=relation,
        origin=origin,
        evidence="test",
        confidence=1.0,
        resolved=True,
    )


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
        session.add_all(
            [
                issue(
                    6,
                    "Invitation lifecycle",
                    "Harden invitations.\n\n## Source specification\n- " + BRD,
                ),
                issue(7, "Default invitation expiry", STORY),
                issue(8, "Resend invitations", "## Dependencies\n- Depends on #7"),
                issue(13, "Duplicate expiry", "dup", state="closed", reason="not_planned"),
                doc(
                    BRD,
                    "BRD",
                    "Invitation expiry",
                    "Invitation links must expire after 7 days.",
                    "human_verified",
                ),
                doc(
                    ADR1,
                    "Decision",
                    "ADR-0001: Invitation tokens",
                    "Invitation links carry single-use tokens.",
                    "human_verified",
                ),
                doc(
                    ADR9,
                    "Decision",
                    "ADR-0009: Invitation emails",
                    "Invitation emails expire links.",
                    "generated",
                    {"stale_after": "2026-01-01"},
                ),
                link(("issue", "7"), ("issue", "6"), "parent"),
                link(("issue", "8"), ("issue", "6"), "parent"),
                link(("issue", "7"), ("document", BRD), "references"),
                link(("document", BRD), ("document", ADR1), "cites"),
                link(("issue", "8"), ("issue", "7"), "depends_on"),
                link(("issue", "13"), ("issue", "7"), "mentions", "inferred"),
            ]
        )
        for path, text in FILES.items():
            session.add(
                RepositoryFile(
                    workspace_id="ws",
                    path=path,
                    blob_sha=SHAS[path],
                    commit_sha="c" * 40,
                    size=len(text),
                    language="Python",
                )
            )
        session.commit()
    return made


def build(factory: sessionmaker[Session], number: int = 7) -> ContextPack:
    with factory() as session:
        ws = session.get(Workspace, "ws")
        assert ws is not None
        return build_pack(session, ws, number, fetch=BLOBS.__getitem__, today=dt.date(2026, 9, 20))


def test_the_pack_follows_links_and_marks_trust(factory: sessionmaker[Session]) -> None:
    pack = build(factory)
    roles = [(i.id, i.role, i.source.split("@")[0]) for i in pack.items]
    assert roles[:4] == [
        ("P1", "story", "Issue #7"),
        ("P2", "epic", "Issue #6"),
        ("P3", "brd", BRD),
        ("P4", "adr", ADR1),
    ]
    by_source = {i.source.split("@")[0]: i for i in pack.items}
    assert by_source[ADR1].reason == f"cited by {BRD}"
    assert by_source[ADR9].flags == ["unverified", "stale"]
    assert by_source["Issue #8"].reason == "#8 depends on #7"
    assert "Issue #13" not in by_source  # closed as not planned
    assert pack.absent == ["initiative", "techspec"]


def test_code_files_are_chosen_by_name_and_fetched_within_limits(
    factory: sessionmaker[Session],
) -> None:
    pack = build(factory)
    code = {i.title: i for i in pack.items if i.role == "code"}
    assert set(code) == {
        "src/quire/invitations/service.py",
        "src/quire/invitations/tokens.py",
        "tests/test_invitations.py",
        "src/quire/invitations/huge.py",
    }
    assert code["src/quire/invitations/service.py"].excerpt == "def accept(token): ...\n"
    assert code["src/quire/invitations/huge.py"].flags == ["not fetched"]
    assert code["tests/test_invitations.py"].reason.startswith("name matches invitation")


def test_the_hash_is_stable_and_follows_content(factory: sessionmaker[Session]) -> None:
    first, second = build(factory), build(factory)
    assert first.hash == second.hash and len(first.hash) == 64
    with factory() as session:
        brd = session.query(Document).filter_by(path=BRD).one()
        brd.body = "Invitation links must expire after 14 days."
        session.commit()
    assert build(factory).hash != first.hash


def test_unknown_numbers_are_refused(factory: sessionmaker[Session]) -> None:
    with pytest.raises(PackError, match="#99"):
        build(factory, 99)
