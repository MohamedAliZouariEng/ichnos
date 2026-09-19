"""Phase 4 exit criterion: zero GitHub writes without an approval record.

The whole Phase 4 flow runs through the public API against a recording fake GitHub: drafting,
a refused approval, a rejection, publishing, a human merge, planning, Issues and the follow-up.
Every write GitHub receives must carry the id of an approval that a human approved and that
was executed; refused and rejected actions must write nothing.
"""

from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from fake_github_writes import FakeGitRepo
from ichnos.db.models import Approval, AuditEvent

ROOT = Path(__file__).resolve().parents[3]
DEMO = ROOT / "examples/demo-repository/docs"
MEETING = DEMO / "meetings/2026-09-15-workspace-onboarding.md"
PASSPHRASE = "correct horse battery staple"


def approve(client: TestClient, approval: dict[str, Any]) -> dict[str, Any]:
    response = client.post(
        f"/api/approvals/{approval['id']}/approve", json={"payload_hash": approval["payload_hash"]}
    )
    assert response.status_code == 200, response.text
    result: dict[str, Any] = response.json()
    assert result["status"] == "executed", result["error"]
    return result


def test_every_github_write_has_an_approval_record(monkeypatch: pytest.MonkeyPatch) -> None:
    from ichnos.main import create_app
    from ichnos.settings import Settings

    repo = FakeGitRepo(
        files={f"docs/{p.relative_to(DEMO).as_posix()}": p.read_text() for p in DEMO.rglob("*.md")}
    )
    monkeypatch.setenv("ICHNOS_LLM_PROVIDER", "fake")
    monkeypatch.setenv("ICHNOS_GITHUB_TOKEN", "test-token-value")
    monkeypatch.setenv("ICHNOS_APPROVER_PASSWORD", PASSPHRASE)
    app = create_app(Settings())

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/user":
            return httpx.Response(200, json={"login": "octo"})
        return repo.handle(request)

    app.state.github_transport = httpx.MockTransport(handler)

    with TestClient(app) as client:
        workspace = client.post(
            "/api/workspaces", json={"name": "quire", "repository": "octo/quire"}
        ).json()
        source = client.post(
            f"/api/workspaces/{workspace['id']}/sources", json={"content": MEETING.read_text()}
        ).json()
        drafted = client.post(
            f"/api/workspaces/{workspace['id']}/runs", json={"source_ids": [source["id"]]}
        ).json()
        app.state.runner.wait(drafted["id"], timeout=60)
        artifact_id = client.get(f"/api/runs/{drafted['id']}").json()["artifact_id"]
        assert client.post("/api/session", json={"password": PASSPHRASE}).status_code == 200

        # A refused approval and a rejection write nothing.
        first = client.post(f"/api/artifacts/{artifact_id}/publish").json()
        refused = client.post(
            f"/api/approvals/{first['id']}/approve", json={"payload_hash": "f" * 64}
        )
        assert refused.status_code == 409
        client.post(f"/api/approvals/{first['id']}/reject", json={"note": "Not yet"})
        assert repo.writes == []

        # Publish for real; a pull request opens.
        published = approve(client, client.post(f"/api/artifacts/{artifact_id}/publish").json())

        # A human merges it on GitHub.
        branch = published["payload"]["branch"]
        main = repo.files_at("main")
        merged = {p: c for p, c in repo.files_at(branch).items() if main.get(p) != c}
        repo.push("main", merged, "Merge pull request #1")

        # Plan; the run waits; approve the Issues; the run resumes and proposes the follow-up.
        planning = client.post(f"/api/artifacts/{artifact_id}/plan").json()
        app.state.runner.wait(planning["id"], timeout=60)
        pending = client.get(
            f"/api/workspaces/{workspace['id']}/approvals", params={"status": "pending"}
        ).json()
        issues = next(a for a in pending if a["action_type"] == "create_issues")
        approve(client, client.get(f"/api/approvals/{issues['id']}").json())
        app.state.runner.wait(planning["id"], timeout=60)
        run = client.get(f"/api/runs/{planning['id']}").json()
        assert run["status"] == "succeeded", run["error"]
        follow_up = run["outputs"]["result"]["follow_up_approval_id"]
        approve(client, client.get(f"/api/approvals/{follow_up}").json())

    with app.state.session_factory() as session:
        approvals = {a.id: a for a in session.scalars(select(Approval))}
        approved = {
            e.approval_id
            for e in session.scalars(
                select(AuditEvent).where(AuditEvent.event_type == "approval.approved")
            )
        }

    assert repo.writes, "the scenario wrote nothing"
    assert None not in repo.write_approvals, "a write carried no approval id"
    writers = set(repo.write_approvals)
    executed = {approval_id for approval_id, a in approvals.items() if a.status == "executed"}
    assert writers == executed
    assert writers <= approved
    assert all(approvals[approval_id].decided_by == "human:octo" for approval_id in writers)
    assert {a.status for approval_id, a in approvals.items() if approval_id not in writers} == {
        "rejected"
    }
    assert len(repo.pulls) == 2 and len(repo.issues) == 5
