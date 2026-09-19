import pytest
from sqlalchemy import inspect
from sqlalchemy.orm import Session, sessionmaker

from ichnos.approvals import PENDING, payload_hash, verify
from ichnos.db import models
from ichnos.db.engine import make_engine, make_session_factory
from ichnos.db.migrate import upgrade_to_head
from ichnos.settings import Settings

PAYLOAD = {
    "kind": "docs_pull_request",
    "files": [{"path": "docs/specs/x/brd.md", "content": "---\ntype: BRD\n---\n# Café\n"}],
    "title": "Publish BRD",
}


@pytest.fixture
def factory() -> sessionmaker[Session]:
    settings = Settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    upgrade_to_head(settings.sqlalchemy_url())
    return make_session_factory(make_engine(settings))


def _approval(session: Session) -> models.Approval:
    workspace = models.Workspace(name="quire", repo_owner="octo", repo_name="quire")
    session.add(workspace)
    session.flush()
    run = models.Run(workspace_id=workspace.id, workflow_type="publish")
    session.add(run)
    session.flush()
    approval = models.Approval(
        run_id=run.id,
        workspace_id=workspace.id,
        action_type="docs_pull_request",
        target="octo/quire",
        branch="main",
        summary="Publish BRD: Invitation expiry",
        payload=PAYLOAD,
        payload_hash=payload_hash(PAYLOAD),
        base={"artifact_version": 2, "head_sha": "c" * 40},
        proposed_by="human:octo",
    )
    session.add(approval)
    session.commit()
    return approval


def test_approvals_carry_the_pending_action_columns(factory: sessionmaker[Session]) -> None:
    with factory() as session:
        columns = {c["name"] for c in inspect(session.get_bind()).get_columns("approvals")}
    assert columns >= {
        "workspace_id",
        "artifact_id",
        "branch",
        "summary",
        "base",
        "proposed_by",
        "decision_note",
        "result",
        "error",
        "executed_at",
        "payload",
        "payload_hash",
    }


def test_the_hash_ignores_key_order_and_follows_content() -> None:
    reordered = {"title": PAYLOAD["title"], "files": PAYLOAD["files"], "kind": PAYLOAD["kind"]}
    assert payload_hash(reordered) == payload_hash(PAYLOAD)
    changed = {**PAYLOAD, "title": "Publish BRD!"}
    assert payload_hash(changed) != payload_hash(PAYLOAD)
    assert len(payload_hash(PAYLOAD)) == 64


def test_a_stored_payload_verifies_and_tampering_is_detected(
    factory: sessionmaker[Session],
) -> None:
    with factory() as session:
        approval_id = _approval(session).id
    with factory() as session:
        stored = session.get(models.Approval, approval_id)
        assert stored is not None
        assert stored.status == PENDING
        assert verify(stored)  # survives the JSON round trip, accents included
        stored.payload = {**stored.payload, "title": "Something else"}
        assert not verify(stored)


def test_approvals_go_with_their_run(factory: sessionmaker[Session]) -> None:
    with factory() as session:
        approval = _approval(session)
        run = session.get(models.Run, approval.run_id)
        session.delete(run)
        session.commit()
        assert session.query(models.Approval).count() == 0
