from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from fake_github_writes import FakeGitRepo
from ichnos.approvals.decisions import proposed_decisions
from ichnos.context.pack import build_pack
from ichnos.db.models import Document, Workspace
from ichnos.workflows.implementation import (
    ImplementationDraft,
    enforce_implementation,
    render_plan,
    store_plan,
)
from ichnos.workflows.specification import findings_of
from test_context_api import CODE, seed

PASSPHRASE = "correct horse battery staple"
DEMO = Path(__file__).resolve().parents[3] / "examples/demo-repository/docs"
ADR1 = "docs/adr/0001-invitation-tokens.md"
PROPOSAL = {
    "title": "Invitation expiry is measured from creation",
    "context": "The BRD requires links to expire 7 days after they are sent.",
    "decision": "An invitation expires 7 days after it is created. Resending creates a new one.",
    "cites": ["P3"],
}


@pytest.fixture
def repo() -> FakeGitRepo:
    demo = {f"docs/{p.relative_to(DEMO).as_posix()}": p.read_text() for p in DEMO.rglob("*.md")}
    return FakeGitRepo(files={**demo, **CODE})


@pytest.fixture
def app(monkeypatch: pytest.MonkeyPatch, repo: FakeGitRepo) -> FastAPI:
    from ichnos.main import create_app
    from ichnos.settings import Settings

    monkeypatch.setenv("ICHNOS_GITHUB_TOKEN", "test-token-value")
    monkeypatch.setenv("ICHNOS_APPROVER_PASSWORD", PASSPHRASE)
    application = create_app(Settings())

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/user":
            return httpx.Response(200, json={"login": "octo"})
        return repo.handle(request)

    application.state.github_transport = httpx.MockTransport(handler)
    return application


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


def plan_with_decision(app: FastAPI, client: TestClient, repo: FakeGitRepo) -> str:
    ws = seed(app, client, repo)
    with app.state.session_factory() as session:
        session.add(
            Document(
                workspace_id=ws,
                path=ADR1,
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
        session.flush()
        workspace = session.get(Workspace, ws)
        assert workspace is not None
        pack = build_pack(session, workspace, 7).as_dict()
        draft = ImplementationDraft.model_validate(
            {
                "summary": "Expire invitations.",
                "steps": [{"text": "Refuse expired links.", "cites": ["P1"]}],
                "adr_proposals": [PROPOSAL],
            }
        )
        plan, _ = enforce_implementation(draft, pack)
        artifact = store_plan(
            session, workspace_id=ws, plan=plan, markdown=render_plan(plan), actor="ichnos/fake"
        )
        session.commit()
        return artifact.id


def test_the_plan_renders_decisions_that_can_be_read_back() -> None:
    markdown = (
        "# Implementation plan: Story #7, X\n\n## Proposed decisions\n\n"
        "### Expire from creation\n\n**Context.** Seven days.\n\n"
        "**Decision.** Expire after 7 days.\n\nSources: P3, p9\n"
    )
    assert proposed_decisions(markdown) == [
        {
            "title": "Expire from creation",
            "context": "Seven days.",
            "decision": "Expire after 7 days.",
            "cites": ["P3", "P9"],
        }
    ]


def test_a_proposed_decision_becomes_the_next_adr(
    app: FastAPI, client: TestClient, repo: FakeGitRepo
) -> None:
    plan_id = plan_with_decision(app, client, repo)
    assert client.post("/api/session", json={"password": PASSPHRASE}).status_code == 200
    response = client.post(f"/api/artifacts/{plan_id}/decisions", json={"index": 1})
    assert response.status_code == 201, response.text
    approval = response.json()
    files = {f["path"]: f["content"] for f in approval["payload"]["files"]}
    adr_path = "docs/adr/0002-invitation-expiry-is-measured-from-creation.md"
    assert set(files) == {adr_path, "docs/adr/index.md", "docs/log.md"}
    adr = files[adr_path]
    assert (
        "type: Decision" in adr and "ADR-0002: Invitation expiry is measured from creation" in adr
    )
    assert "by: human:octo" in adr and "resource: /specs/invitation-expiry/brd.md" in adr
    assert [f for f in findings_of(adr_path, adr) if f["level"] == "error"] == []
    assert "0002-invitation-expiry-is-measured-from-creation.md" in files["docs/adr/index.md"]
    assert repo.writes == []

    done = client.post(
        f"/api/approvals/{approval['id']}/approve", json={"payload_hash": approval["payload_hash"]}
    ).json()
    assert done["status"] == "executed", done["error"]
    assert adr_path in repo.files_at(approval["payload"]["branch"])
    assert client.get(f"/api/artifacts/{plan_id}").json()["status"] == "draft"  # still editable


def test_unknown_decisions_are_404(app: FastAPI, client: TestClient, repo: FakeGitRepo) -> None:
    plan_id = plan_with_decision(app, client, repo)
    assert client.post("/api/session", json={"password": PASSPHRASE}).status_code == 200
    assert client.post(f"/api/artifacts/{plan_id}/decisions", json={"index": 2}).status_code == 404
