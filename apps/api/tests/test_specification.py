import datetime as dt
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from ichnos.db import models
from ichnos.db.engine import make_engine, make_session_factory
from ichnos.db.migrate import upgrade_to_head
from ichnos.llm import FakeProvider
from ichnos.okf import parse_document
from ichnos.settings import Settings
from ichnos.workflows import brd
from ichnos.workflows.engine import StageContext, StageFailed, WorkflowRunner, start_run
from ichnos.workflows.requirements import Brief
from ichnos.workflows.specification import (
    Reference,
    findings_of,
    render_brd,
    specification_stage,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
MEETING = REPO_ROOT / "examples/demo-repository/docs/meetings/2026-09-15-workspace-onboarding.md"
AT = "2026-09-19T12:00:00Z"


def brief(**overrides: object) -> Brief:
    base: dict[str, object] = {
        "title": "Invitation expiry",
        "problem": "Invitation links never expire.",
        "goals": [],
        "requirements": [
            {
                "id": "R-01",
                "statement": "Invitations expire after 7 days.",
                "priority": "must",
                "rationale": "Decided in the meeting.",
                "citations": ["S1", "C1"],
                "acceptance_criteria": [{"id": "AC-01", "text": "Given ..., when ..., then ..."}],
            }
        ],
        "assumptions": [],
        "open_questions": [{"text": "Per workspace?", "citations": ["S1"]}],
        "risks": [],
        "out_of_scope": [],
    }
    return Brief.model_validate({**base, **overrides})


REFS = {
    "S1": Reference("S1", "Onboarding sync", "/meetings/2026-09-19-onboarding-sync.md"),
    "C1": Reference("C1", "Issue #2: Explain [invalid] links", "https://github.com/o/r/issues/2"),
    "C2": Reference("C2", "ADR-0001", "/adr/0001-tokens.md"),
}


def test_rendered_brd_is_valid_okf_with_footnotes() -> None:
    markdown, path = render_brd(brief(), REFS, model="ichnos/fake", at=AT)
    assert path == "docs/specs/invitation-expiry/brd.md"
    assert findings_of(path, markdown) == []
    parsed = parse_document(path, markdown)
    assert parsed.trust_tier == "generated"
    assert "**Must.** Invitations expire after 7 days.[^s1][^c1]" in markdown
    assert "[^c1]: [Issue #2: Explain (invalid) links](https://github.com/o/r/issues/2)" in markdown
    assert "[^c2]" not in markdown  # never cited, never defined
    assert "# Goals\n\nNone identified." in markdown
    assert "resource: /meetings/2026-09-19-onboarding-sync.md" in markdown
    assert "/adr/0001-tokens.md" not in markdown


def test_stage_without_a_brief_fails() -> None:
    context = StageContext(run_id="run-1", workspace_id="ws", factory=None)  # type: ignore[arg-type]
    with pytest.raises(StageFailed, match="no brief"):
        specification_stage({}, context)


@pytest.fixture
def factory() -> sessionmaker[Session]:
    settings = Settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    upgrade_to_head(settings.sqlalchemy_url())
    return make_session_factory(make_engine(settings))


def test_requirements_workflow_produces_a_cited_okf_brd(factory: sessionmaker[Session]) -> None:
    with factory() as session:
        workspace = models.Workspace(name="quire", repo_owner="octo", repo_name="quire")
        session.add(workspace)
        session.flush()
        source = models.Source(
            workspace_id=workspace.id,
            kind="pasted",
            title="Workspace onboarding sync",
            content=MEETING.read_text(encoding="utf-8"),
            content_sha256="0" * 64,
            created_by="human:local",
        )
        session.add(source)
        session.commit()
        workspace_id, source_id = workspace.id, source.id

    runner = WorkflowRunner()
    run_id = start_run(
        factory,
        runner,
        workspace_id=workspace_id,
        workflow_type=brd.WORKFLOW_TYPE,
        stages=brd.STAGES,
        initial={"source_ids": [source_id]},
        checkpoint_path=Settings().checkpoint_path(),
        services={"provider": FakeProvider()},
    )
    runner.wait(run_id, timeout=60)
    runner.shutdown()

    with factory() as session:
        run = session.get(models.Run, run_id)
        assert run is not None and run.status == "succeeded", run and run.error
        result = run.outputs["result"]
        artifact = session.get(models.Artifact, result["artifact_id"])
        assert artifact is not None
        version = session.scalar(
            select(models.ArtifactVersion).where(models.ArtifactVersion.artifact_id == artifact.id)
        )
        assert version is not None
        stages = [
            e.stage
            for e in session.scalars(
                select(models.RunEvent).where(models.RunEvent.run_id == run_id)
            )
            if e.kind == "stage.completed"
        ]

    assert stages == ["retrieval", "requirements", "specification"]
    assert (artifact.kind, artifact.status, artifact.run_id) == ("brd", "draft", run_id)
    assert (version.number, version.origin, version.actor) == (1, "generated", "ichnos/fake")
    assert version.findings == []
    assert parse_document(result["path"], version.content).trust_tier == "generated"

    requirement_sections = version.content.split("\n## R-")[1:]
    assert requirement_sections, "the BRD has no requirements"
    for section in requirement_sections:
        assert "[^s1]" in section.split("\n# ")[0], section[:80]
    today = dt.datetime.now(dt.UTC).date().isoformat()
    assert (
        f"[^s1]: [Workspace onboarding sync](/meetings/{today}-workspace-onboarding-sync.md)"
        in (version.content)
    )


def test_index_entries_list_the_brd_and_its_meeting_note() -> None:
    from ichnos.workflows.specification import index_entries

    entries = index_entries(
        "docs/specs/invitation-expiry/brd.md",
        "Invitation [expiry]",
        "Business requirements.",
        [("docs/meetings/2026-09-19-onboarding-sync.md", "Onboarding sync")],
    )
    assert entries == [
        {
            "index": "docs/specs/index.md",
            "entry": "* [Invitation (expiry)](invitation-expiry/) - Business requirements.",
        },
        {
            "index": "docs/specs/invitation-expiry/index.md",
            "heading": "Invitation (expiry)",
            "entry": "* [Business requirements](brd.md) - Business requirements.",
        },
        {
            "index": "docs/meetings/index.md",
            "entry": "* [Onboarding sync](2026-09-19-onboarding-sync.md) - Meeting note this "
            "BRD was drafted from.",
        },
    ]
