from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from fake_github import FakeGitHub, gh_comment, gh_issue
from ichnos.api.knowledge import fts_query
from ichnos.knowledge.chunks import chunk_markdown
from ichnos.main import create_app
from ichnos.settings import Settings

MEETING = (
    "---\ntype: Meeting Note\ntitle: Onboarding sync\n---\n"
    "# Context\n\nA contractor joined through an old link.\n\n"
    "# Decisions\n\n- Invitations expire after 7 days.\n- Resending invalidates the old link.\n"
)


def test_chunks_follow_headings_and_ignore_code() -> None:
    text = "Intro line.\n\n# One\nFirst.\n\n```\n# not a heading\n```\n\n## Two\nSecond.\n"
    chunks = chunk_markdown(text, default_heading="Title")
    assert [(c.heading, c.start_line) for c in chunks] == [("Title", 1), ("One", 3), ("Two", 10)]
    assert "# not a heading" in chunks[1].text


def test_long_sections_are_split_at_paragraphs() -> None:
    body = "\n\n".join(f"Paragraph {n} " + "word " * 60 for n in range(10))
    chunks = chunk_markdown(f"# Long\n{body}", max_chars=700)
    assert len(chunks) > 1
    assert all(len(chunk.text) <= 700 for chunk in chunks)
    assert {chunk.heading for chunk in chunks} == {"Long"}


def test_fts_query_is_always_safe() -> None:
    assert fts_query('expire AND "(') == '"expire" "AND"*'
    assert fts_query("invit") == '"invit"*'
    assert fts_query("  -- :: ") is None


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("ICHNOS_GITHUB_TOKEN", "test-token-value")
    github = FakeGitHub({"docs/meetings/sync.md": MEETING})
    github.issues = [gh_issue(2, "Explain invalid links", "2026-09-19T10:05:00Z")]
    github.comments = [
        gh_comment(70, 2, "Customers assumed Quire was down.", "2026-09-19T10:06:00Z")
    ]
    app = create_app(Settings())
    app.state.github_transport = github.transport
    with TestClient(app) as test_client:
        yield test_client


def _synced_workspace(client: TestClient) -> str:
    body = {"name": "quire", "repository": "octo-org/quire-demo"}
    workspace_id: str = client.post("/api/workspaces", json=body).json()["id"]
    run = client.post(f"/api/workspaces/{workspace_id}/sync").json()
    assert run["status"] == "succeeded", run
    assert run["counts"]["chunks_indexed"] >= 3
    return workspace_id


def test_search_finds_documents_by_stemmed_words(client: TestClient) -> None:
    workspace_id = _synced_workspace(client)
    hits = client.get(f"/api/workspaces/{workspace_id}/search", params={"q": "expiring"}).json()
    assert hits[0]["source_key"] == "docs/meetings/sync.md"
    assert hits[0]["heading"] == "Decisions"
    assert hits[0]["title"] == "Onboarding sync"
    assert "«" in hits[0]["snippet"]


def test_search_finds_comments_under_their_issue(client: TestClient) -> None:
    workspace_id = _synced_workspace(client)
    hits = client.get(f"/api/workspaces/{workspace_id}/search", params={"q": "down"}).json()
    assert (hits[0]["source_kind"], hits[0]["source_key"]) == ("issue", "2")
    assert hits[0]["title"] == "Explain invalid links"
    assert hits[0]["heading"] == "Comment by sara"


def test_search_handles_prefixes_and_odd_input(client: TestClient) -> None:
    workspace_id = _synced_workspace(client)
    url = f"/api/workspaces/{workspace_id}/search"
    assert client.get(url, params={"q": "invit"}).json() != []
    assert client.get(url, params={"q": '"( AND -'}).status_code == 200
    assert client.get(url, params={"q": "zebra"}).json() == []


def test_health_reports_search(client: TestClient) -> None:
    assert client.get("/healthz").json()["search"] == "ok"
