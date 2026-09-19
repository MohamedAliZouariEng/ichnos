import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from fake_github_writes import FakeGitRepo
from ichnos.approvals.publish import add_index_entry, add_log_line, meeting_note
from ichnos.db.models import Source
from ichnos.okf import parse_document

ROOT = Path(__file__).resolve().parents[3]
DEMO = ROOT / "examples/demo-repository/docs"
MEETING = DEMO / "meetings/2026-09-15-workspace-onboarding.md"
PASSPHRASE = "correct horse battery staple"


def demo_files() -> dict[str, str]:
    return {
        f"docs/{p.relative_to(DEMO).as_posix()}": p.read_text(encoding="utf-8")
        for p in DEMO.rglob("*.md")
    }


@pytest.fixture
def repo() -> FakeGitRepo:
    return FakeGitRepo(files=demo_files())


@pytest.fixture
def app(monkeypatch: pytest.MonkeyPatch, repo: FakeGitRepo) -> FastAPI:
    from ichnos.main import create_app
    from ichnos.settings import Settings

    monkeypatch.setenv("ICHNOS_LLM_PROVIDER", "fake")
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


@pytest.fixture
def artifact_id(app: FastAPI, client: TestClient) -> str:
    """A BRD drafted by a real run (fake model) from the demo meeting note, pasted."""
    workspace = client.post(
        "/api/workspaces", json={"name": "quire", "repository": "octo/quire"}
    ).json()
    source = client.post(
        f"/api/workspaces/{workspace['id']}/sources",
        json={"content": MEETING.read_text(encoding="utf-8")},
    ).json()
    run = client.post(
        f"/api/workspaces/{workspace['id']}/runs", json={"source_ids": [source["id"]]}
    ).json()
    app.state.runner.wait(run["id"], timeout=60)
    value: str = client.get(f"/api/runs/{run['id']}").json()["artifact_id"]
    return value


def publish(client: TestClient, artifact_id: str) -> Any:
    assert client.post("/api/session", json={"password": PASSPHRASE}).status_code == 200
    return client.post(f"/api/artifacts/{artifact_id}/publish")


def test_publishing_proposes_the_full_package_and_writes_nothing(
    client: TestClient, repo: FakeGitRepo, artifact_id: str
) -> None:
    response = publish(client, artifact_id)
    assert response.status_code == 201, response.text
    approval = response.json()
    assert approval["status"] == "pending" and approval["hash_ok"]
    assert repo.writes == []

    paths = [f["path"] for f in approval["payload"]["files"]]
    slug = client.get(f"/api/artifacts/{artifact_id}").json()["slug"]
    assert paths[0] == f"docs/specs/{slug}/brd.md"
    assert {"docs/specs/index.md", f"docs/specs/{slug}/index.md", "docs/meetings/index.md"} <= set(
        paths
    )
    assert "docs/log.md" in paths
    assert any(
        p.startswith("docs/meetings/") and p.endswith("-workspace-onboarding-sync.md")
        for p in paths
    )
    brd = approval["payload"]["files"][0]["content"]
    assert "status: stable" in brd and "by: human:octo" in brd and "requirement_ids:" in brd
    assert approval["base"]["files"][paths[0]] is None  # a new file
    assert client.get(f"/api/artifacts/{artifact_id}").json()["status"] == "needs-review"
    assert client.post(f"/api/artifacts/{artifact_id}/publish").status_code == 409


def test_approval_opens_a_pull_request_with_a_valid_human_verified_bundle(
    client: TestClient, repo: FakeGitRepo, artifact_id: str, tmp_path: Path
) -> None:
    approval = publish(client, artifact_id).json()
    detail = client.post(
        f"/api/approvals/{approval['id']}/approve", json={"payload_hash": approval["payload_hash"]}
    ).json()
    assert detail["status"] == "executed", detail["error"]
    assert detail["result"]["pull_request"]["number"] == 1
    assert client.get(f"/api/artifacts/{artifact_id}").json()["status"] == "approved"
    assert client.get(f"/api/runs/{detail['run_id']}").json()["status"] == "succeeded"

    branch = approval["payload"]["branch"]
    for path, text in repo.files_at(branch).items():
        target = tmp_path / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    checked = subprocess.run(
        [sys.executable, str(ROOT / "scripts/validate_okf.py"), str(tmp_path / "docs"), "--strict"],
        capture_output=True,
        text=True,
    )
    assert checked.returncode == 0, checked.stdout + checked.stderr
    brd_path = approval["payload"]["files"][0]["path"]
    brd = parse_document(brd_path, repo.files_at(branch)[brd_path])
    assert brd.trust_tier == "human_verified"


def test_rejecting_returns_the_artifact_to_draft(
    client: TestClient, repo: FakeGitRepo, artifact_id: str
) -> None:
    approval = publish(client, artifact_id).json()
    rejected = client.post(f"/api/approvals/{approval['id']}/reject", json={"note": "Later"}).json()
    assert rejected["status"] == "rejected"
    assert client.get(f"/api/artifacts/{artifact_id}").json()["status"] == "draft"
    assert client.get(f"/api/runs/{rejected['run_id']}").json()["status"] == "rejected"
    assert repo.writes == []


def test_a_draft_with_okf_errors_is_not_published(client: TestClient, artifact_id: str) -> None:
    client.post(
        f"/api/artifacts/{artifact_id}/versions",
        json={"content": "# No frontmatter\n", "base_version": 1},
    )
    response = publish(client, artifact_id)
    assert response.status_code == 409 and "OKF errors" in response.json()["detail"]


def test_publishing_needs_a_session(client: TestClient, artifact_id: str) -> None:
    assert client.post(f"/api/artifacts/{artifact_id}/publish").status_code == 401


def test_index_entries_are_added_once() -> None:
    entry = "* [X](x/) - X"
    assert add_index_entry(None, "Specs", entry) == "# Specs\n\n* [X](x/) - X\n"
    once = add_index_entry("# Specs\n", None, entry)
    assert add_index_entry(once, None, entry) == once


def test_log_lines_go_under_today_newest_first() -> None:
    log = "# Log\n\n## 2026-09-15\n* **Creation**: old\n"
    updated = add_log_line(log, "2026-09-19", "* new")
    assert updated == "# Log\n\n## 2026-09-19\n* new\n\n## 2026-09-15\n* **Creation**: old\n"
    assert add_log_line(updated, "2026-09-19", "* newer").count("## 2026-09-19") == 1


def test_plain_notes_are_wrapped_as_okf_meeting_notes() -> None:
    source = Source(
        id="src-1",
        workspace_id="ws",
        kind="pasted",
        title="Kickoff",
        content="We agreed that invitations expire.",
        content_sha256="0" * 64,
        created_by="human:octo",
    )
    note = meeting_note(source, "human:octo", "2026-09-19T12:00:00Z")
    parsed = parse_document("docs/meetings/kickoff.md", note)
    assert parsed.frontmatter["type"] == "Meeting Note"
    assert parsed.trust_tier == "human_verified"
    assert "invitations expire" in parsed.body
