import datetime as dt
import hashlib
from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from ichnos.db.models import AuditEvent, Document
from ichnos.main import create_app
from ichnos.settings import Settings

NOTE = "# Workspace onboarding sync\n\nInvitations must expire after 7 days.\n"


@pytest.fixture
def app() -> FastAPI:
    return create_app(Settings())


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def workspace_id(client: TestClient) -> str:
    body = {"name": "quire", "repository": "octo-org/quire-demo"}
    value: str = client.post("/api/workspaces", json=body).json()["id"]
    return value


def _url(workspace_id: str, suffix: str = "") -> str:
    return f"/api/workspaces/{workspace_id}/sources{suffix}"


def test_pasted_text_becomes_an_immutable_source(client: TestClient, workspace_id: str) -> None:
    response = client.post(_url(workspace_id), json={"content": NOTE})
    assert response.status_code == 201
    source = response.json()
    today = dt.datetime.now(dt.UTC).date().isoformat()
    assert source["kind"] == "pasted"
    assert source["title"] == "Workspace onboarding sync"
    assert source["content_sha256"] == hashlib.sha256(NOTE.encode()).hexdigest()
    assert source["proposed_path"] == f"docs/meetings/{today}-workspace-onboarding-sync.md"
    assert source["content"] == NOTE

    listed = client.get(_url(workspace_id)).json()
    assert [item["id"] for item in listed] == [source["id"]]
    assert listed[0]["content"] is None  # the list never carries content


def test_identical_content_is_reused(client: TestClient, workspace_id: str) -> None:
    first = client.post(_url(workspace_id), json={"content": NOTE}).json()
    again = client.post(_url(workspace_id), json={"content": NOTE})
    assert again.status_code == 200
    assert again.json()["reused"] is True
    assert again.json()["id"] == first["id"]
    assert len(client.get(_url(workspace_id)).json()) == 1


def test_uploads_accept_text_files_only(client: TestClient, workspace_id: str) -> None:
    upload = {"kind": "upload", "filename": "notes.txt", "content": "Plain notes.\nMore."}
    created = client.post(_url(workspace_id), json=upload)
    assert created.status_code == 201
    assert created.json()["media_type"] == "text/plain"
    assert created.json()["title"] == "Plain notes."

    bad = client.post(_url(workspace_id), json={**upload, "filename": "slides.pdf"})
    assert bad.status_code == 422


@pytest.mark.parametrize("content", ["", "   \n  "])
def test_empty_content_is_rejected(client: TestClient, workspace_id: str, content: str) -> None:
    assert client.post(_url(workspace_id), json={"content": content}).status_code == 422


def test_synced_document_becomes_a_pinned_source(
    app: FastAPI, client: TestClient, workspace_id: str
) -> None:
    with app.state.session_factory() as session:
        session.add(
            Document(
                workspace_id=workspace_id,
                path="docs/meetings/2026-09-15-sync.md",
                blob_sha="a" * 40,
                commit_sha="c" * 40,
                kind="concept",
                title="Onboarding sync",
                doc_type="Meeting Note",
                trust_tier="human_verified",
                frontmatter={"type": "Meeting Note", "title": "Onboarding sync"},
                body="\n# Decisions\n\nInvitations expire.\n",
            )
        )
        session.commit()

    response = client.post(
        _url(workspace_id, "/from-document"), json={"path": "docs/meetings/2026-09-15-sync.md"}
    )
    assert response.status_code == 201
    source = response.json()
    assert (source["kind"], source["title"]) == ("document", "Onboarding sync")
    assert source["commit_sha"] == "c" * 40
    assert source["proposed_path"] is None
    assert source["content"].startswith("---\ntype: Meeting Note\n")

    missing = client.post(_url(workspace_id, "/from-document"), json={"path": "docs/nope.md"})
    assert missing.status_code == 404


def test_sources_cannot_be_changed_or_deleted(client: TestClient, workspace_id: str) -> None:
    source_id = client.post(_url(workspace_id), json={"content": NOTE}).json()["id"]
    assert (
        client.patch(_url(workspace_id, f"/{source_id}"), json={"content": "x"}).status_code == 405
    )
    assert client.delete(_url(workspace_id, f"/{source_id}")).status_code == 405
    assert client.get(_url(workspace_id, f"/{source_id}")).json()["content"] == NOTE


def test_new_sources_are_audited(app: FastAPI, client: TestClient, workspace_id: str) -> None:
    client.post(_url(workspace_id), json={"content": NOTE})
    client.post(_url(workspace_id), json={"content": NOTE})  # reused: not a new event
    with app.state.session_factory() as session:
        events = session.scalars(
            select(AuditEvent).where(AuditEvent.event_type == "source.created")
        ).all()
    assert len(events) == 1
