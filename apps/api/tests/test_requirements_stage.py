from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from ichnos.db import models
from ichnos.db.engine import make_engine, make_session_factory
from ichnos.db.migrate import upgrade_to_head
from ichnos.llm import FakeProvider
from ichnos.settings import Settings
from ichnos.workflows.engine import StageContext, StageFailed
from ichnos.workflows.requirements import (
    Extraction,
    build_prompt,
    describe_requirements,
    enforce,
    fake_extraction,
    requirements_stage,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
MEETING = REPO_ROOT / "examples/demo-repository/docs/meetings/2026-09-15-workspace-onboarding.md"
SOURCES = [
    {"id": "S1", "title": "Onboarding sync", "kind": "upload", "text": "Invitations expire."}
]
CONTEXT = [
    {
        "id": "C1",
        "kind": "document",
        "key": "docs/adr/0001-tokens.md",
        "title": "ADR-0001: Tokens",
        "heading": "Decision",
        "excerpt": "Tokens are single-use.",
        "doc_type": "Decision",
        "trust_tier": "human_verified",
    }
]


@pytest.fixture
def context() -> StageContext:
    settings = Settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    upgrade_to_head(settings.sqlalchemy_url())
    factory: sessionmaker[Session] = make_session_factory(make_engine(settings))
    with factory() as session:
        workspace = models.Workspace(name="quire", repo_owner="octo", repo_name="quire")
        session.add(workspace)
        session.flush()
        session.add(models.Run(id="run-1", workspace_id=workspace.id, workflow_type="requirements"))
        session.commit()
        return StageContext(run_id="run-1", workspace_id=workspace.id, factory=factory)


def extraction(**overrides: object) -> Extraction:
    base: dict[str, object] = {"title": "Invitation expiry", "problem": "Links never expire."}
    return Extraction.model_validate({**base, **overrides})


def test_prompt_labels_sources_and_context() -> None:
    prompt = build_prompt(SOURCES, CONTEXT)
    assert "### [S1] Onboarding sync (upload)\nInvitations expire." in prompt
    assert "### [C1] document · ADR-0001: Tokens · Decision · human_verified" in prompt
    assert "Section: Decision" in prompt


def test_cited_requirements_are_kept_and_numbered() -> None:
    enforced = enforce(
        extraction(
            requirements=[
                {
                    "statement": "Invitations expire after 7 days.",
                    "citations": ["S1", "[c1]"],
                    "acceptance_criteria": [
                        "Given an invitation, when 7 days pass, then it fails."
                    ],
                },
                {
                    "statement": "Admins can resend invitations.",
                    "citations": ["S1"],
                    "acceptance_criteria": [
                        "Given an admin, when they resend, then a new link is sent."
                    ],
                },
            ]
        ),
        {"S1", "C1"},
    )
    reqs = enforced.brief.requirements
    assert [r.id for r in reqs] == ["R-01", "R-02"]
    assert reqs[0].citations == ["S1", "C1"]
    assert [c.id for r in reqs for c in r.acceptance_criteria] == ["AC-01", "AC-02"]
    assert enforced.demoted == []


def test_uncited_and_invented_citations_become_assumptions() -> None:
    enforced = enforce(
        extraction(
            requirements=[
                {"statement": "Invitations expire.", "citations": ["S1", "C9"]},
                {"statement": "Use Redis for tokens.", "citations": ["C42"]},
                {"statement": "Send reminder emails.", "citations": []},
            ]
        ),
        {"S1", "C1"},
    )
    assert [r.statement for r in enforced.brief.requirements] == ["Invitations expire."]
    assert enforced.brief.requirements[0].citations == ["S1"]
    assert enforced.demoted == ["Use Redis for tokens.", "Send reminder emails."]
    assert enforced.dropped_citations == 2
    texts = [a.text for a in enforced.brief.assumptions]
    assert "Not supported by the sources: Use Redis for tokens." in texts


def test_duplicates_and_blanks_are_dropped() -> None:
    enforced = enforce(
        extraction(
            requirements=[
                {"statement": "Invitations  expire.", "citations": ["S1"]},
                {"statement": "invitations expire.", "citations": ["S1"]},
                {"statement": "   ", "citations": ["S1"]},
            ],
            open_questions=[{"text": "Per workspace?"}, {"text": "per workspace?"}],
        ),
        {"S1"},
    )
    assert [r.statement for r in enforced.brief.requirements] == ["Invitations expire."]
    assert len(enforced.brief.open_questions) == 1


def test_fake_extraction_reads_the_quire_meeting_note() -> None:
    sources = [{"id": "S1", "title": "Onboarding", "kind": "upload", "text": MEETING.read_text()}]
    answer = Extraction.model_validate(fake_extraction("", build_prompt(sources, [])))
    statements = [r.statement for r in answer.requirements]
    assert any("expire" in s.lower() for s in statements)
    assert all(r.citations == ["S1"] for r in answer.requirements)
    assert len(answer.open_questions) == 3
    assert len(answer.out_of_scope) == 2


def test_stage_with_the_fake_provider(context: StageContext) -> None:
    sources = [{"id": "S1", "title": "Onboarding", "kind": "upload", "text": MEETING.read_text()}]
    context.services = {"provider": FakeProvider()}
    update = requirements_stage({"sources": sources, "context": CONTEXT}, context)
    assert update["model"] == "ichnos/fake"
    assert update["brief"]["requirements"][0]["id"] == "R-01"
    assert context.usage.calls == 1
    assert describe_requirements(update).endswith("3 open questions")


def test_stage_without_a_provider_fails(context: StageContext) -> None:
    with pytest.raises(StageFailed, match="no model provider"):
        requirements_stage({"sources": SOURCES, "context": []}, context)


def test_stage_fails_when_nothing_is_supported(context: StageContext) -> None:
    def unsupported(system: str, user: str) -> dict[str, object]:
        return {
            "title": "Guesswork",
            "problem": "Unknown.",
            "requirements": [{"statement": "Add dark mode.", "citations": ["C77"]}],
        }

    context.services = {"provider": FakeProvider(responders={"Extraction": unsupported})}
    with pytest.raises(StageFailed, match="no requirements supported"):
        requirements_stage({"sources": SOURCES, "context": []}, context)
    with context.factory() as session:
        notes = session.scalars(select(models.RunEvent).where(models.RunEvent.kind == "log")).all()
    assert notes[0].data["demoted"] == ["Add dark mode."]
