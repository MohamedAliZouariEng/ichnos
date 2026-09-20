from collections.abc import Iterator
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from ichnos.honesty import claims
from ichnos.llm import FakeProvider
from ichnos.workflows.implementation import (
    HONESTY,
    PLAN_KIND,
    draft_implementation,
    plan_findings,
    render_plan,
    store_plan,
)
from test_implementation import PACK

PASSPHRASE = "correct horse battery staple"


@pytest.fixture
def app(monkeypatch: pytest.MonkeyPatch) -> FastAPI:
    from ichnos.main import create_app
    from ichnos.settings import Settings

    monkeypatch.setenv("ICHNOS_GITHUB_TOKEN", "test-token-value")
    monkeypatch.setenv("ICHNOS_APPROVER_PASSWORD", PASSPHRASE)
    application = create_app(Settings())
    application.state.github_transport = httpx.MockTransport(
        lambda request: httpx.Response(200, json={"login": "octo"})
    )
    return application


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


def stored(app: FastAPI, client: TestClient) -> tuple[str, str]:
    workspace = client.post(
        "/api/workspaces", json={"name": "quire", "repository": "octo/quire"}
    ).json()
    plan, _, _ = draft_implementation(FakeProvider(), PACK)
    markdown = render_plan(plan)
    with app.state.session_factory() as session:
        artifact = store_plan(
            session, workspace_id=workspace["id"], plan=plan, markdown=markdown, actor="ichnos/fake"
        )
        session.commit()
        return artifact.id, markdown


def test_a_stored_plan_is_a_clean_versioned_artifact(app: FastAPI, client: TestClient) -> None:
    artifact_id, markdown = stored(app, client)
    detail: dict[str, Any] = client.get(f"/api/artifacts/{artifact_id}").json()
    assert detail["kind"] == PLAN_KIND
    assert detail["slug"] == "story-7-default-invitation-expiry"
    assert detail["path"] == "ichnos/plans/story-7-default-invitation-expiry.md"
    assert detail["current"]["origin"] == "generated" and detail["current"]["findings"] == 0
    assert detail["source_ids"] == ["story:7", "pack:" + "a" * 64]

    edited = markdown.replace("## Risks", "## Risks\n\n- Reviewed by a person.")
    saved = client.post(
        f"/api/artifacts/{artifact_id}/versions", json={"content": edited, "base_version": 1}
    )
    assert saved.status_code == 201, saved.text
    assert client.get(f"/api/artifacts/{artifact_id}/versions/1").json()["content"] == markdown


def test_edits_cannot_remove_the_honesty_line_or_claim_finished_work(
    app: FastAPI, client: TestClient
) -> None:
    artifact_id, markdown = stored(app, client)
    for content, code in (
        (markdown.replace(HONESTY, ""), "plan-honesty"),
        (markdown + "\nAll tests pass now.\n", "plan-claim"),
    ):
        refused = client.post(
            f"/api/artifacts/{artifact_id}/versions", json={"content": content, "base_version": 1}
        )
        assert refused.status_code == 400 and "not saved" in refused.json()["detail"]
        live = client.post(
            f"/api/artifacts/{artifact_id}/validate", json={"content": content}
        ).json()
        assert code in [finding["code"] for finding in live]
    assert client.get(f"/api/artifacts/{artifact_id}").json()["current_version"] == 1


def test_plans_are_never_published(app: FastAPI, client: TestClient) -> None:
    artifact_id, _ = stored(app, client)
    assert client.post("/api/session", json={"password": PASSPHRASE}).status_code == 200
    response = client.post(f"/api/artifacts/{artifact_id}/publish")
    assert response.status_code == 409 and "stay in Ichnos" in response.json()["detail"]


def test_plan_checks_and_claims() -> None:
    plan, _, _ = draft_implementation(FakeProvider(), PACK)
    assert plan_findings(render_plan(plan)) == []
    assert [f["code"] for f in plan_findings("# Notes\n")] == [
        "plan-title",
        "plan-honesty",
        "plan-criteria",
    ]
    assert claims("The feature has been implemented.\nAll tests pass.") == [
        (1, "has been implemented"),
        (2, "All tests pass"),
    ]
    assert claims("Implement the check. Tests will verify expiry. No code has changed.") == []


def test_conditions_are_not_claims() -> None:
    real = (
        "- Story #9 (R-03) will later refine the exact error message on expired links; the current "
        "generic InvitationError message should be kept compatible until Story #9 is implemented."
    )
    assert claims(real) == []  # the first real Gemini plan's risk (line 43)
    assert claims("Verify that all tests pass on CI.") == []
    assert claims("Once expiry is implemented, remove the flag.") == []
    assert claims("The expiry check is implemented.") == [(1, "is implemented")]
    assert claims("Expiry works. All tests pass.") == [(1, "All tests pass")]
