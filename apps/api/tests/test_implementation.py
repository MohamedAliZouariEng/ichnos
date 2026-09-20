from typing import Any

from ichnos.llm import FakeProvider
from ichnos.workflows.implementation import (
    HONESTY,
    ImplementationDraft,
    build_prompt,
    draft_implementation,
    enforce_implementation,
    render_plan,
)


def item(
    pid: str, role: str, title: str, excerpt: str = "", trust: str = "github"
) -> dict[str, Any]:
    return {
        "id": pid,
        "role": role,
        "title": title,
        "source": title,
        "url": None,
        "trust": trust,
        "flags": [],
        "reason": "test",
        "excerpt": excerpt,
    }


STORY = (
    "As an admin, I want invitations to expire.\n\n## Acceptance criteria\n"
    "- [ ] AC-01: Given a link older than 7 days, when opened, then it is refused.\n"
    "- [ ] AC-02: Given a fresh link, when opened, then it works.\n"
)
PACK: dict[str, Any] = {
    "story": 7,
    "hash": "a" * 64,
    "absent": ["initiative"],
    "keywords": [],
    "notes": [],
    "items": [
        item("P1", "story", "Default invitation expiry", STORY),
        item("P2", "adr", "ADR-0001", "Single-use tokens.", "human_verified"),
        item(
            "P3",
            "code",
            "src/quire/invitations/service.py",
            "def accept(token, now): ...",
            "repository",
        ),
        item("P4", "code", "tests/test_invitations.py", "def test_accept(): ...", "repository"),
    ],
}


def test_the_prompt_carries_criteria_and_the_pack() -> None:
    prompt = build_prompt(PACK)
    assert "- AC-01: Given a link older than 7 days, when opened, then it is refused." in prompt
    assert "[P3] code · repository · src/quire/invitations/service.py" in prompt
    assert "def accept(token, now): ..." in prompt
    assert "Absent from the pack: initiative." in prompt


def test_the_fake_plan_covers_every_criterion() -> None:
    plan, notes, usage = draft_implementation(FakeProvider(), PACK)
    assert notes == [] and usage.calls == 1
    assert [f.path for f in plan.files] == ["src/quire/invitations/service.py"]
    assert plan.files[0].cites == ["P3"] and plan.files[0].in_pack
    assert [(c.id, c.steps, c.tests) for c in plan.criteria] == [
        ("AC-01", ["S1"], ["T1"]),
        ("AC-02", ["S2"], ["T2"]),
    ]
    assert plan.tests[0].file == "tests/test_invitations.py"
    assert plan.open_questions == []


def test_enforcement_drops_inventions_and_raises_questions() -> None:
    draft = ImplementationDraft.model_validate(
        {
            "summary": "Expire invitations.",
            "files": [
                {"path": "./src/quire/invitations/service.py", "cites": ["p3", "P99"]},
                {"path": "src/quire/invitations/expiry.py", "change": "new", "cites": ["P2"]},
                {"path": "src/quire/mailer.py", "change": "modify"},
            ],
            "steps": [
                {"text": "Add expires_at to Invitation.", "cites": ["P3"]},
                {"text": "Call the imaginary audit service.", "cites": ["P42"]},
                {"text": "Refuse expired links in accept().", "cites": ["P3", "P2"]},
            ],
            "tests": [{"name": "test_expired_link_is_refused", "cites": ["P1"]}],
            "criteria": [
                {"criterion": "ac-01", "steps": [1, 2, 3], "tests": [1]},
                {"criterion": "AC-09", "steps": [1]},
            ],
        }
    )
    plan, notes = enforce_implementation(draft, PACK)
    assert plan.files[0].path == "src/quire/invitations/service.py" and plan.files[0].cites == [
        "P3"
    ]
    assert plan.files[1].change == "new" and not plan.files[1].in_pack
    assert [s.id for s in plan.steps] == ["S1", "S2"]  # the invented step is gone
    assert plan.steps[1].text == "Refuse expired links in accept()."
    assert plan.criteria[0].steps == ["S1", "S2"] and plan.criteria[0].tests == ["T1"]
    assert any("src/quire/mailer.py is not in the context pack" in q for q in plan.open_questions)
    assert any(q.startswith("AC-02") and "not covered" in q for q in plan.open_questions)
    assert any("P99" in n for n in notes) and any("Dropped step 2" in n for n in notes)


def test_the_rendered_plan_is_honest_and_complete() -> None:
    plan, _, _ = draft_implementation(FakeProvider(), PACK)
    text = render_plan(plan)
    assert text.startswith("# Implementation plan: Story #7, Default invitation expiry\n")
    assert HONESTY in text
    assert (
        "| AC-01: Given a link older than 7 days, when opened, then it is refused. | S1 | T1 |"
        in text
    )
    assert "| `src/quire/invitations/service.py` | modify | Implements the Story. | P3 |" in text
    assert "## Open questions\n\nNone." in text
