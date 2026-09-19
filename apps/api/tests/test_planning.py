import pytest
from sqlalchemy.orm import Session, sessionmaker

from ichnos.db import models
from ichnos.db.engine import make_engine, make_session_factory
from ichnos.db.migrate import upgrade_to_head
from ichnos.llm import FakeProvider
from ichnos.settings import Settings
from ichnos.workflows.engine import StageContext, StageFailed
from ichnos.workflows.planning import (
    PlanDraft,
    build_plan_prompt,
    describe_planning,
    enforce_plan,
    fake_plan,
    planning_stage,
    requirements_of,
)

BRD = """---
type: BRD
title: Invitation expiry
status: stable
---

# Summary

Invitation links never expire.

# Requirements

## R-01

**Must.** Invitations expire after 7 days.[^s1]

Acceptance criteria:

- **AC-01**: Given an invitation, when 7 days pass, then it no longer works.

## R-02

**Must.** Resending invalidates the previous link.[^s1]

Acceptance criteria:

- **AC-02**: Given a pending invitation, when it is resent, then the old link stops working.

## R-03

**Must.** An expired link explains why.[^s1]

## R-04

**Should.** Invitees can ask for a new invitation.[^s1]

# Out of scope

- SSO and SCIM provisioning.[^s1]

[^s1]: [Onboarding sync](/meetings/x.md)
"""


def draft(**overrides: object) -> PlanDraft:
    base: dict[str, object] = {
        "epic_title": "Invitation lifecycle",
        "epic_summary": "Expire links.",
    }
    return PlanDraft.model_validate({**base, **overrides})


def story(title: str, *ids: str, **extra: object) -> dict[str, object]:
    return {"title": title, "requirement_ids": list(ids), **extra}


def test_requirements_are_read_from_the_brd() -> None:
    found = requirements_of(BRD)
    assert [r.id for r in found] == ["R-01", "R-02", "R-03", "R-04"]
    assert found[0].statement == "Invitations expire after 7 days."
    assert found[3].priority == "should"
    assert found[0].criteria == ("Given an invitation, when 7 days pass, then it no longer works.",)
    assert found[2].criteria == ()


def test_the_fake_planner_makes_one_linked_story_per_requirement() -> None:
    plan, notes = enforce_plan(
        PlanDraft.model_validate(fake_plan("", build_plan_prompt(BRD))), requirements_of(BRD)
    )
    assert plan.epic_title == "Invitation expiry"
    assert [s.requirement_ids for s in plan.stories] == [["R-01"], ["R-02"], ["R-03"], ["R-04"]]
    assert plan.exclusions == ["SSO and SCIM provisioning."]
    assert plan.uncovered == [] and notes == []


def test_enforcement_links_numbers_and_inherits() -> None:
    plan, notes = enforce_plan(
        draft(
            stories=[
                story(
                    "Expire invitations",
                    "r1",
                    "R-99",
                    acceptance_criteria=["Given x, when y, then z."],
                ),
                story("Resend", "R2", depends_on=[1, 2, 7]),
                story("Invented feature", "R-42"),
                story("Explain expired links", "R-03"),
            ]
        ),
        requirements_of(BRD),
    )
    assert [s.key for s in plan.stories] == ["S-1", "S-2", "S-3"]
    assert plan.stories[0].requirement_ids == ["R-01"]
    assert plan.stories[1].depends_on == ["S-1"]  # itself and unknown numbers dropped
    assert plan.stories[1].acceptance_criteria[0].text.startswith("Given a pending invitation")
    assert [c.id for s in plan.stories for c in s.acceptance_criteria] == ["AC-01", "AC-02"]
    assert plan.uncovered == ["R-04"]
    assert any("Invented feature" in note for note in notes)


def test_story_count_is_bounded() -> None:
    many = [story(f"Story {n}", "R-01") for n in range(7)]
    plan, notes = enforce_plan(draft(stories=many), requirements_of(BRD))
    assert len(plan.stories) == 5 and "Kept the first 5 of 7 stories." in notes
    with pytest.raises(StageFailed, match="at least 3"):
        enforce_plan(draft(stories=many[:2]), requirements_of(BRD))


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
        session.add(models.Run(id="run-1", workspace_id=workspace.id, workflow_type="planning"))
        for artifact_id, status in (("brd-approved", "approved"), ("brd-draft", "draft")):
            session.add(
                models.Artifact(
                    id=artifact_id,
                    workspace_id=workspace.id,
                    kind="brd",
                    title="Invitation expiry",
                    slug="invitation-expiry",
                    status=status,
                    current_version=1,
                )
            )
            session.add(
                models.ArtifactVersion(
                    artifact_id=artifact_id,
                    number=1,
                    content=BRD,
                    origin="generated",
                    actor="ichnos/fake",
                )
            )
        session.commit()
        return StageContext(
            run_id="run-1",
            workspace_id=workspace.id,
            factory=factory,
            services={"provider": FakeProvider()},
        )


def test_the_stage_plans_approved_brds_only(context: StageContext) -> None:
    with pytest.raises(StageFailed, match="only approved BRDs"):
        planning_stage({"artifact_id": "brd-draft"}, context)
    update = planning_stage({"artifact_id": "brd-approved"}, context)
    assert update["brd_path"] == "docs/specs/invitation-expiry/brd.md"
    assert update["model"] == "ichnos/fake"
    assert context.usage.calls == 1
    assert describe_planning(update) == "1 Epic and 4 Stories covering 4 of 4 requirements"
