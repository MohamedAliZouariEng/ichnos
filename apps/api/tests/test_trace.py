import datetime as dt

import pytest
from sqlalchemy.orm import Session, sessionmaker

from ichnos.db.engine import make_engine, make_session_factory
from ichnos.db.migrate import upgrade_to_head
from ichnos.db.models import (
    CheckRun,
    Document,
    GitHubItem,
    Link,
    PullRequestCommit,
    PullRequestFile,
    Workspace,
)
from ichnos.settings import Settings
from ichnos.trace.build import Trace, TraceError, TraceRow, build_trace

NOW = dt.datetime(2026, 9, 20, tzinfo=dt.UTC)
BRD = "docs/specs/invitation-expiry/brd.md"
BODY = (
    "# Requirements\n\n## R-01\n\n**Must.** Invitations expire after 7 days.[^s1]\n\n"
    "## R-02\n\n**Should.** Resending invalidates the old link.[^s1]\n\n# Out of scope\n\n- SSO.\n"
)


def item(number: int, title: str, body: str, kind: str = "issue", **extra: object) -> GitHubItem:
    segment = "pull" if kind == "pull_request" else "issues"
    return GitHubItem(
        workspace_id="ws",
        number=number,
        item_type=kind,
        github_id=number,
        title=title,
        body=body,
        state=str(extra.get("state", "open")),
        state_reason=extra.get("reason"),
        labels=[],
        url=f"https://github.com/octo/quire/{segment}/{number}",
        created_at=NOW,
        updated_at=NOW,
        draft=extra.get("draft"),
        head_sha=extra.get("head"),
        merged_at=extra.get("merged"),
    )


def story(number: int, rid: str, ac: str, brd: str = BRD) -> str:
    return (
        f"As an admin.\n\n## Parent\n- Epic: #6\n\n## Source specification\n- {brd}\n\n"
        f"## Requirements\n- {rid}: text\n\n## Acceptance criteria\n- [ ] {ac}: Given x, then y.\n"
    )


def link(source: tuple[str, str], target: tuple[str, str], relation: str) -> Link:
    return Link(
        workspace_id="ws",
        source_kind=source[0],
        source_key=source[1],
        target_kind=target[0],
        target_key=target[1],
        relation=relation,
        origin="explicit",
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
                Document(
                    workspace_id="ws",
                    path=BRD,
                    blob_sha="b" * 40,
                    commit_sha="c" * 40,
                    kind="concept",
                    doc_type="BRD",
                    title="Invitation expiry",
                    trust_tier="human_verified",
                    frontmatter={},
                    body=BODY,
                    findings=[],
                ),
                item(6, "Invitation lifecycle", "Epic."),
                item(7, "Default expiry", story(7, "R-01", "AC-01")),
                item(8, "Resend invalidates", story(8, "R-02", "AC-02")),
                item(
                    13,
                    "Duplicate expiry",
                    story(13, "R-01", "AC-09"),
                    state="closed",
                    reason="not_planned",
                ),
                item(30, "Other BRD", story(30, "R-01", "AC-01", brd="docs/specs/other/brd.md")),
                item(
                    19,
                    "Story #7: Default expiry",
                    "Closes #7\n\n| Criterion | Status | Evidence |\n"
                    "| --- | --- | --- |\n| AC-01: Given x, then y. | Not started | None yet |\n",
                    kind="pull_request",
                    draft=True,
                    head="a" * 40,
                ),
                item(
                    20,
                    "Resend",
                    "Closes #8\n\n| AC-02: Given x, then y. | Done | "
                    "tests/test_invitations.py::test_resend |\n",
                    kind="pull_request",
                    state="closed",
                    head="e" * 40,
                    merged=NOW,
                ),
                link(("issue", "7"), ("issue", "6"), "parent"),
                link(("issue", "8"), ("issue", "6"), "parent"),
                link(("pull_request", "19"), ("issue", "7"), "closes"),
                link(("pull_request", "20"), ("issue", "8"), "closes"),
                PullRequestCommit(workspace_id="ws", pr_number=19, sha="d" * 40),
                PullRequestFile(
                    workspace_id="ws",
                    pr_number=20,
                    path="tests/test_invitations.py",
                    status="modified",
                    additions=12,
                    deletions=0,
                ),
                CheckRun(
                    workspace_id="ws",
                    github_id=1,
                    head_sha="e" * 40,
                    pull_number=20,
                    name="pytest",
                    status="completed",
                    conclusion="success",
                    url="https://github.com/octo/quire/runs/1",
                ),
            ]
        )
        session.commit()
    return made


def trace(factory: sessionmaker[Session], path: str = BRD) -> Trace:
    with factory() as session:
        ws = session.get(Workspace, "ws")
        assert ws is not None
        return build_trace(session, ws, path)


def find(rows: list[TraceRow], level: str, key: str) -> TraceRow:
    for row in rows:
        if row.level == level and row.key == key:
            return row
        try:
            return find(row.children, level, key)
        except LookupError:
            continue
    raise LookupError(f"{level} {key}")


def test_a_draft_pull_request_is_traced_honestly(factory: sessionmaker[Session]) -> None:
    result = trace(factory)
    r1 = find(result.rows, "requirement", "R-01")
    assert (r1.status, r1.title) == ("approved", "Invitations expire after 7 days.")
    assert r1.url == f"https://github.com/octo/quire/blob/{'c' * 40}/{BRD}#r-01"
    epic = r1.children[0]
    assert (epic.key, epic.status, [s.key for s in epic.children]) == ("#6", "open", ["#7"])
    assert find(r1.children, "criterion", "AC-01").status == "not started"
    pr = find(r1.children, "pull_request", "PR #19")
    assert pr.status == "draft"
    assert [(c.level, c.key) for c in pr.children] == [("commit", "d" * 8)]  # no test, no check


def test_a_merged_pull_request_with_ci_is_traced_to_its_tests(
    factory: sessionmaker[Session],
) -> None:
    r2 = find(trace(factory).rows, "requirement", "R-02")
    criterion = find(r2.children, "criterion", "AC-02")
    assert criterion.status == "tested: passing"
    assert [(t.key, t.status) for t in criterion.children] == [
        ("tests/test_invitations.py::test_resend", "passing")
    ]
    pr = find(r2.children, "pull_request", "PR #20")
    assert pr.status == "merged"
    inferred = [c for c in pr.children if c.level == "test"]
    assert inferred[0].evidence[0].origin == "inferred"
    assert [(c.key, c.status) for c in pr.children if c.level == "check"] == [("pytest", "success")]


def test_only_this_brds_live_stories_are_traced(factory: sessionmaker[Session]) -> None:
    r1 = find(trace(factory).rows, "requirement", "R-01")
    keys = [s.key for s in r1.children[0].children]
    assert keys == ["#7"]  # not #13 (not planned) and not #30 (another BRD)


def test_rows_are_numbered_and_the_hash_is_stable(factory: sessionmaker[Session]) -> None:
    first, second = trace(factory), trace(factory)
    assert first.rows[0].id == "T1" and first.hash == second.hash and len(first.hash) == 64
    with pytest.raises(TraceError, match="not a synced BRD"):
        trace(factory, "docs/specs/missing/brd.md")
