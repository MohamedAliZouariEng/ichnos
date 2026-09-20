"""Phase 5 exit criterion: after approval Ichnos opens a draft PR linked to the Story, and never
claims code changed before a real repository action.

The whole flow runs through the public API against a recording fake GitHub: a planning run, an
edited plan, a refused and a rejected proposal, the approved draft pull request and an approved
decision. Every write must belong to an executed approval, the draft must change no file, and
nothing that reached GitHub may claim finished work.
"""

from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from fake_github_writes import FakeGitRepo
from ichnos.db.models import Approval, AuditEvent, Document
from ichnos.honesty import claims
from ichnos.workflows.implementation import plan_findings
from test_context_api import CODE, seed
from test_zero_unapproved_writes import approve

DEMO = Path(__file__).resolve().parents[3] / "examples/demo-repository/docs"
PASSPHRASE = "correct horse battery staple"
DECISION = (
    "\n\n## Proposed decisions\n\n### Invitation expiry is measured from creation\n\n"
    "**Context.** The BRD asks for invitation links to expire after 7 days.\n\n"
    "**Decision.** An invitation expires 7 days after it is created.\n\nSources: P3\n"
)


def test_phase5_writes_are_approved_and_claim_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    from ichnos.main import create_app
    from ichnos.settings import Settings

    demo = {f"docs/{p.relative_to(DEMO).as_posix()}": p.read_text() for p in DEMO.rglob("*.md")}
    repo = FakeGitRepo(files={**demo, **CODE})
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
        ws = seed(app, client, repo)
        with app.state.session_factory() as session:
            session.add(
                Document(
                    workspace_id=ws,
                    path="docs/adr/0001-invitation-tokens.md",
                    blob_sha="d" * 40,
                    commit_sha="c" * 40,
                    kind="concept",
                    doc_type="Decision",
                    title="ADR-0001",
                    trust_tier="human_verified",
                    frontmatter={},
                    body="Tokens.",
                    findings=[],
                )
            )
            session.commit()

        # Plan Story #7 through a real run; nothing reaches GitHub.
        started = client.post(f"/api/workspaces/{ws}/stories/7/plan").json()
        app.state.runner.wait(started["id"], timeout=60)
        run = client.get(f"/api/runs/{started['id']}").json()
        assert run["status"] == "succeeded", run["error"]
        plan_id = run["outputs"]["result"]["artifact_id"]

        # A person edits the plan to propose a decision.
        edited = client.get(f"/api/artifacts/{plan_id}").json()["current"]["content"].rstrip("\n")
        edited += DECISION
        saved = client.post(
            f"/api/artifacts/{plan_id}/versions", json={"content": edited, "base_version": 1}
        )
        assert saved.status_code == 201, saved.text
        assert client.post("/api/session", json={"password": PASSPHRASE}).status_code == 200

        # A refused hash and a rejection write nothing.
        first = client.post(f"/api/artifacts/{plan_id}/draft-pull-request").json()
        refused = client.post(
            f"/api/approvals/{first['id']}/approve", json={"payload_hash": "f" * 64}
        )
        assert refused.status_code == 409
        client.post(f"/api/approvals/{first['id']}/reject", json={"note": "Not yet"})
        assert repo.writes == []

        # The approved draft pull request, then the approved decision.
        main_files = repo.files_at("main")
        draft = approve(client, client.post(f"/api/artifacts/{plan_id}/draft-pull-request").json())
        decision = approve(
            client, client.post(f"/api/artifacts/{plan_id}/decisions", json={"index": 1}).json()
        )

    with app.state.session_factory() as session:
        approvals = {a.id: a for a in session.scalars(select(Approval))}
        approved = {
            e.approval_id
            for e in session.scalars(
                select(AuditEvent).where(AuditEvent.event_type == "approval.approved")
            )
        }

    # Zero writes without an approval record.
    assert None not in repo.write_approvals
    writers = set(repo.write_approvals)
    assert writers == {draft["id"], decision["id"]}
    assert (
        writers == {i for i, a in approvals.items() if a.status == "executed"}
        and writers <= approved
    )
    assert {a.status for i, a in approvals.items() if i not in writers} == {"rejected"}

    # The draft pull request changes nothing and is a draft.
    draft_routes = [
        r for (_, r), a in zip(repo.writes, repo.write_approvals, strict=True) if a == draft["id"]
    ]
    assert draft_routes == ["/git/commits", "/git/refs", "/pulls"]
    assert repo.files_at(draft["payload"]["branch"]) == main_files
    assert repo.pulls[0]["draft"] is True and repo.pulls[0]["body"].startswith("Closes #7\n")

    # Nothing that reached GitHub claims finished work; the plan passes its own checks.
    for pull in repo.pulls:
        assert claims(pull["title"]) == [] and claims(pull["body"]) == [], pull["title"]
    assert plan_findings(edited) == []
