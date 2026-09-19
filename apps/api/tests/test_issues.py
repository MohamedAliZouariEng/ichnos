from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from fake_github_writes import FakeGitRepo
from ichnos.approvals.issues import build_issues
from ichnos.approvals.service import propose
from ichnos.db.models import Run, Workspace

PASSPHRASE = "correct horse battery staple"
BRD_PATH = "docs/specs/invitation-expiry/brd.md"
STATEMENTS = {
    "R-01": "Invitations expire after 7 days.",
    "R-02": "Resending invalidates the previous link.",
    "R-03": "An expired link explains why.",
}
PLAN: dict[str, Any] = {
    "epic_title": "Invitation lifecycle hardening",
    "epic_summary": "Stop old invitation links from working.",
    "exclusions": ["SSO and SCIM provisioning."],
    "uncovered": [],
    "stories": [
        {
            "key": "S-1",
            "title": "Expire invitations",
            "user_story": "As an admin, I want expiry.",
            "requirement_ids": ["R-01"],
            "priority": "must",
            "depends_on": [],
            "acceptance_criteria": [
                {"id": "AC-01", "text": "Given 7 days, when opened, then refused."}
            ],
        },
        {
            "key": "S-2",
            "title": "Resend invalidates",
            "user_story": "As an admin, I want resending.",
            "requirement_ids": ["R-02"],
            "priority": "must",
            "depends_on": ["S-1"],
            "acceptance_criteria": [
                {"id": "AC-02", "text": "Given a resend, when the old link opens, then refused."}
            ],
        },
        {
            "key": "S-3",
            "title": "Explain expired links",
            "user_story": "As an invitee, I want to know why.",
            "requirement_ids": ["R-03"],
            "priority": "should",
            "depends_on": ["S-1", "S-2"],
            "acceptance_criteria": [],
        },
    ],
}


def payload() -> dict[str, Any]:
    built, _ = build_issues(
        PLAN,
        approver="human:octo",
        repository="octo/quire",
        brd_path=BRD_PATH,
        statements=STATEMENTS,
    )
    return built


def test_bodies_follow_the_issue_convention() -> None:
    built = payload()
    epic = built["epic"]["body"]
    assert "## Source specification\n- docs/specs/invitation-expiry/brd.md" in epic
    assert "- R-02: Resending invalidates the previous link." in epic
    assert "## Out of scope\n- SSO and SCIM provisioning." in epic
    story = built["stories"][1]["body"]
    assert "## Parent\n- Epic: #{epic}" in story
    assert "- [ ] AC-02: Given a resend" in story
    assert "## Dependencies\n- Depends on #{S-1}" in story
    assert built["stories"][2]["labels"] == [
        "type:story",
        "status:draft",
        "agent:generated",
        "priority:should",
    ]
    assert "human:octo approved this exact text" in story


class Failing:
    """Refuses the nth Issue creation, to test partial results."""

    def __init__(self, repo: FakeGitRepo, fail_on: int | None) -> None:
        self.repo, self.fail_on, self.issues = repo, fail_on, 0

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if request.url.path == "/user":
            return httpx.Response(200, json={"login": "octo"})
        if request.method == "POST" and request.url.path.endswith("/issues"):
            self.issues += 1
            if self.issues == self.fail_on:
                return httpx.Response(502, json={"message": "Server Error"})
        return self.repo.handle(request)


def build(
    monkeypatch: pytest.MonkeyPatch, repo: FakeGitRepo, fail_on: int | None = None
) -> FastAPI:
    from ichnos.main import create_app
    from ichnos.settings import Settings

    monkeypatch.setenv("ICHNOS_GITHUB_TOKEN", "test-token-value")
    monkeypatch.setenv("ICHNOS_APPROVER_PASSWORD", PASSPHRASE)
    app = create_app(Settings())
    app.state.github_transport = httpx.MockTransport(Failing(repo, fail_on))
    return app


def propose_issues(app: FastAPI) -> str:
    with app.state.session_factory() as session:
        workspace = Workspace(name="quire", repo_owner="octo", repo_name="quire")
        session.add(workspace)
        session.flush()
        run = Run(workspace_id=workspace.id, workflow_type="issues-test")
        session.add(run)
        session.flush()
        approval = propose(
            session,
            run_id=run.id,
            workspace_id=workspace.id,
            action_type="create_issues",
            target="octo/quire",
            branch="main",
            payload=payload(),
            base={},
            summary="Create 1 Epic and 3 Stories",
            proposed_by="human:octo",
        )
        return approval.id


def decide(client: TestClient, approval_id: str) -> Any:
    assert client.post("/api/session", json={"password": PASSPHRASE}).status_code == 200
    shown = client.get(f"/api/approvals/{approval_id}").json()["payload_hash"]
    return client.post(f"/api/approvals/{approval_id}/approve", json={"payload_hash": shown}).json()


@pytest.fixture
def repo() -> FakeGitRepo:
    return FakeGitRepo()


def test_approval_creates_the_epic_then_linked_stories(
    monkeypatch: pytest.MonkeyPatch, repo: FakeGitRepo
) -> None:
    app = build(monkeypatch, repo)
    with TestClient(app) as client:
        approval_id = propose_issues(app)
        assert repo.writes == []
        detail = decide(client, approval_id)

    assert detail["status"] == "executed", detail["error"]
    epic, *stories = repo.issues
    assert epic["title"] == "Invitation lifecycle hardening" and epic["number"] == 1
    assert [s["number"] for s in stories] == [2, 3, 4]
    assert "- Epic: #1" in stories[0]["body"] and "#{" not in stories[0]["body"]
    assert "- Depends on #2" in stories[1]["body"]
    assert "- Depends on #2\n- Depends on #3" in stories[2]["body"]
    assert {"type:epic", "type:story", "priority:must", "agent:generated"} <= repo.labels
    assert detail["result"]["epic"]["url"] == "https://github.com/octo/quire/issues/1"
    assert [s["key"] for s in detail["result"]["stories"]] == ["S-1", "S-2", "S-3"]


def test_a_failure_halfway_records_what_was_created(
    monkeypatch: pytest.MonkeyPatch, repo: FakeGitRepo
) -> None:
    app = build(monkeypatch, repo, fail_on=3)  # the Epic and S-1 succeed, S-2 fails
    with TestClient(app) as client:
        detail = decide(client, propose_issues(app))
    assert detail["status"] == "failed"
    assert "HTTP 502" in detail["error"]
    assert detail["result"]["epic"]["number"] == 1
    assert [s["key"] for s in detail["result"]["stories"]] == ["S-1"]
    assert len(repo.issues) == 2


def test_rejected_plans_create_nothing(monkeypatch: pytest.MonkeyPatch, repo: FakeGitRepo) -> None:
    app = build(monkeypatch, repo)
    with TestClient(app) as client:
        approval_id = propose_issues(app)
        assert client.post("/api/session", json={"password": PASSPHRASE}).status_code == 200
        rejected = client.post(
            f"/api/approvals/{approval_id}/reject", json={"note": "Too big"}
        ).json()
    assert rejected["status"] == "rejected"
    assert repo.writes == [] and repo.issues == []


def test_a_revised_plan_is_approved_as_edited(
    monkeypatch: pytest.MonkeyPatch, repo: FakeGitRepo
) -> None:
    app = build(monkeypatch, repo)
    with TestClient(app) as client:
        approval_id = propose_issues(app)
        assert client.post("/api/session", json={"password": PASSPHRASE}).status_code == 200
        before = client.get(f"/api/approvals/{approval_id}").json()
        story = before["payload"]["stories"][0]
        revision = {
            "payload_hash": before["payload_hash"],
            "epic": {
                "title": "Invitation lifecycle, hardened",
                "body": before["payload"]["epic"]["body"],
            },
            "stories": [
                {"key": "S-1", "title": "Expire invitations after 7 days", "body": story["body"]}
            ],
        }
        revised = client.post(f"/api/approvals/{approval_id}/revise", json=revision).json()
        assert revised["payload_hash"] != before["payload_hash"] and revised["hash_ok"]
        stale = client.post(
            f"/api/approvals/{approval_id}/approve", json={"payload_hash": before["payload_hash"]}
        )
        assert stale.status_code == 409
        done = client.post(
            f"/api/approvals/{approval_id}/approve", json={"payload_hash": revised["payload_hash"]}
        ).json()
    assert done["status"] == "executed"
    assert repo.issues[0]["title"] == "Invitation lifecycle, hardened"
    assert repo.issues[1]["title"] == "Expire invitations after 7 days"


def test_revisions_keep_the_parent_line_and_apply_to_issues_only(
    monkeypatch: pytest.MonkeyPatch, repo: FakeGitRepo
) -> None:
    app = build(monkeypatch, repo)
    with TestClient(app) as client:
        approval_id = propose_issues(app)
        detail = client.get(f"/api/approvals/{approval_id}").json()
        revision = {
            "payload_hash": detail["payload_hash"],
            "epic": {"title": "Epic", "body": "Body"},
            "stories": [{"key": "S-1", "title": "Orphan", "body": "No parent here."}],
        }
        assert client.post(f"/api/approvals/{approval_id}/revise", json=revision).status_code == 401
        assert client.post("/api/session", json={"password": PASSPHRASE}).status_code == 200
        orphan = client.post(f"/api/approvals/{approval_id}/revise", json=revision)
        assert orphan.status_code == 400 and "## Parent" in orphan.json()["detail"]

        with app.state.session_factory() as session:
            run_id = detail["run_id"]
            docs = propose(
                session,
                run_id=run_id,
                workspace_id=detail["workspace_id"],
                action_type="docs_pull_request",
                target="octo/quire",
                branch="main",
                payload={"kind": "docs_pull_request"},
                base={},
                summary="Docs",
                proposed_by="human:octo",
            )
            docs_id, docs_hash = docs.id, docs.payload_hash
        refused = client.post(
            f"/api/approvals/{docs_id}/revise",
            json={**revision, "payload_hash": docs_hash, "stories": []},
        )
    assert refused.status_code == 409 and "edit it, then publish again" in refused.json()["detail"]
    assert repo.writes == []
