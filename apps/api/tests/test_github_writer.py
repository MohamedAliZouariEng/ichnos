import re
from pathlib import Path

import pytest
from pydantic import SecretStr

from fake_github_writes import FakeGitRepo
from ichnos.approvals.ticket import ExecutionTicket, issue_ticket
from ichnos.github.writer import FileChange, GitHubWriteError, GitHubWriter

SOURCE = Path(__file__).resolve().parents[1] / "src" / "ichnos"
TOKEN = SecretStr("test-token-value")


def writer(repo: FakeGitRepo) -> GitHubWriter:
    return GitHubWriter(
        issue_ticket("approval-1", "0" * 64),
        repository=f"{repo.owner}/{repo.name}",
        token=TOKEN,
        transport=repo.transport,
    )


def test_tickets_cannot_be_forged() -> None:
    with pytest.raises(PermissionError, match="approval service"):
        ExecutionTicket("approval-1", "0" * 64, object())
    with pytest.raises(PermissionError, match="execution ticket"):
        GitHubWriter("not a ticket", repository="octo/quire", token=TOKEN)  # type: ignore[arg-type]


def test_files_land_in_one_commit_on_a_new_branch(tmp_path: Path) -> None:
    repo = FakeGitRepo(files={"docs/index.md": "# Docs\n"})
    main_before = repo.refs["main"]
    with writer(repo) as client:
        sha = client.commit_files(
            base_branch="main",
            new_branch="ichnos/brd-1",
            message="docs: publish BRD",
            files=[
                FileChange("docs/specs/x/brd.md", "---\ntype: BRD\n---\n"),
                FileChange("docs/specs/x/index.md", "# X\n"),
            ],
        )
    assert repo.refs["ichnos/brd-1"] == sha
    assert repo.refs["main"] == main_before  # the default branch is never written
    assert repo.files_at("ichnos/brd-1") == {
        "docs/index.md": "# Docs\n",
        "docs/specs/x/brd.md": "---\ntype: BRD\n---\n",
        "docs/specs/x/index.md": "# X\n",
    }
    assert repo.commits[sha]["parents"] == [main_before]
    assert [route for _, route in repo.writes] == [
        "/git/blobs",
        "/git/blobs",
        "/git/trees",
        "/git/commits",
        "/git/refs",
    ]


def test_a_failed_write_leaves_no_branch_behind() -> None:
    repo = FakeGitRepo(files={"docs/index.md": "# Docs\n"})
    repo.refs["ichnos/taken"] = repo.refs["main"]
    with writer(repo) as client, pytest.raises(GitHubWriteError, match="Reference already exists"):
        client.commit_files(
            base_branch="main",
            new_branch="ichnos/taken",
            message="x",
            files=[FileChange("docs/a.md", "a")],
        )
    assert set(repo.refs) == {"main", "ichnos/taken"}


def test_pull_requests_issues_and_labels() -> None:
    repo = FakeGitRepo()
    with writer(repo) as client:
        pull = client.open_pull_request(head="ichnos/brd-1", base="main", title="BRD", body="…")
        client.ensure_labels({"type:epic": "5319e7", "agent:generated": "ededed"})
        client.ensure_labels({"type:epic": "5319e7"})  # already there: no second write
        issue = client.create_issue(title="Epic", body="…", labels=["type:epic"])
    assert (pull.number, pull.url) == (1, "https://github.com/octo/quire/pull/1")
    assert (issue.number, issue.url) == (2, "https://github.com/octo/quire/issues/2")
    assert repo.labels == {"type:epic", "agent:generated"}
    assert repo.issues[0]["labels"] == ["type:epic"]
    assert sum(1 for _, route in repo.writes if route == "/labels") == 2


def test_reads_report_missing_things_as_none() -> None:
    repo = FakeGitRepo(files={"docs/index.md": "# Docs\n"})
    with writer(repo) as client:
        assert client.branch_head("nope") is None
        assert client.file_sha("docs/missing.md", "main") is None
        assert client.file_sha("docs/index.md", "main") is not None
    assert repo.writes == []


IMPORTS_WRITER = re.compile(r"^\s*(from|import)\s+ichnos\.github\.writer\b", re.M)
ISSUES_TICKETS = re.compile(r"\bissue_ticket\s*\(")


def test_only_the_approvals_package_can_write() -> None:
    """ADR-0015: a new code path must not be able to write to GitHub without approval."""
    offenders = []
    for path in SOURCE.rglob("*.py"):
        relative = path.relative_to(SOURCE)
        if relative.parts[0] == "approvals":
            continue
        text = path.read_text(encoding="utf-8")
        if relative != Path("approvals/ticket.py") and ISSUES_TICKETS.search(text):
            offenders.append(f"{relative}: issues an execution ticket")
        if relative != Path("github/writer.py") and IMPORTS_WRITER.search(text):
            offenders.append(f"{relative}: imports the GitHub writer")
    assert offenders == []
