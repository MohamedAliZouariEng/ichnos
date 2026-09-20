"""One recorded model review of acceptance criteria, beside the code rules (ADR-0025).

The model's verdicts are reported next to the rules and their agreement is counted; they never
replace the rules. Run with make ac-review; it makes one model call per workspace.
"""

from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import select

from ichnos.db.engine import make_engine, make_session_factory
from ichnos.db.models import Workspace
from ichnos.evaluate.metrics import is_testable, stories
from ichnos.llm import ModelProvider, Usage, fake_responder, provider_from_settings
from ichnos.settings import Settings
from ichnos.trace.build import CRITERION_RE

REVIEW_PROMPT = """\
You judge whether acceptance criteria are testable: a person could write an automated or manual
test with a clear pass or fail. Judge each criterion by its id, with a one-sentence reason.
"""


class Verdict(BaseModel):
    id: str
    testable: bool
    reason: str = ""


class ReviewDraft(BaseModel):
    verdicts: list[Verdict] = Field(default_factory=list)


def review(
    provider: ModelProvider, criteria: list[tuple[str, str]]
) -> tuple[dict[str, Verdict], Usage]:
    lines = "\n".join(f"- {cid}: {text}" for cid, text in criteria)
    draft, usage = provider.complete_json(REVIEW_PROMPT, f"## Criteria\n\n{lines}", ReviewDraft)
    known = {cid for cid, _ in criteria}
    return {v.id: v for v in draft.verdicts if v.id in known}, usage


@fake_responder("ReviewDraft")
def fake_review(system: str, user: str) -> dict[str, Any]:
    ids = [line[2:].split(":", 1)[0] for line in user.splitlines() if line.startswith("- ")]
    return {"verdicts": [{"id": cid, "testable": True, "reason": "fake"} for cid in ids]}


def main() -> None:
    settings = Settings()
    provider = provider_from_settings(settings, model_override=None, transport=None)
    if provider is None:
        print("No model is configured; the review needs one.")
        return
    with make_session_factory(make_engine(settings))() as session:
        for workspace in session.scalars(select(Workspace)):
            criteria = [
                (f"#{s.number} {ac}", text)
                for s in stories(session, workspace.id)
                for _, ac, text in CRITERION_RE.findall(s.body or "")
            ]
            if not criteria:
                continue
            verdicts, usage = review(provider, criteria)
            agree = 0
            print(f"\n{workspace.name} ({workspace.repo_owner}/{workspace.repo_name})")
            for cid, text in criteria:
                rule, _ = is_testable(text)
                model = verdicts.get(cid)
                shown = "no verdict" if model is None else ("testable" if model.testable else "not")
                agree += int(model is not None and model.testable == rule)
                print(
                    f"  {cid:<12} rules: {'testable' if rule else 'not':<9} model: {shown:<10}"
                    f" {model.reason[:60] if model else ''}"
                )
            print(
                f"  agreement: {agree} of {len(criteria)}; "
                f"tokens: {usage.as_dict()['total_tokens']}"
            )


if __name__ == "__main__":
    main()
