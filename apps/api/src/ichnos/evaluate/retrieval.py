"""Retrieval evaluation (ADR-0025): full-text search alone, and with OKF links and traces.

Expected sources are written as kind:text and match paths and titles, not Issue numbers, so
the same question set works on anyone's copy of the demo repository.
"""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from ichnos.answers.retrieve import AnswerSource, retrieve_for_question
from ichnos.db.engine import make_engine, make_session_factory
from ichnos.db.models import Document, Workspace
from ichnos.settings import Settings

BRD = "docs/specs/workspace-invitation-lifecycle-hardening-expiry-resending/brd.md"
NOTE = "docs/meetings/2026-09-15-workspace-onboarding.md"
DEMO_CASES: list[tuple[str, list[str]]] = [
    (
        "What approved evidence shows that invitation links must expire, "
        "and where is that behavior tested?",
        [
            f"document:{NOTE}",
            f"document:{BRD}#r-01",
            "issue:Default Invitation Expiry",
            "pull_request:Default Invitation Expiry",
            "test:tests/test_invitations.py",
        ],
    ),
    (
        "How can an admin resend a pending invitation?",
        [f"document:{BRD}#r-02", "issue:Resend Pending Invitations"],
    ),
    (
        "What should an invitee see when opening an expired invitation link?",
        [f"document:{BRD}#r-03", "issue:Expired Invitation Error Handling"],
    ),
    (
        "Can workspace owners change how long invitation links last?",
        [f"document:{BRD}#r-05", "issue:Configurable Invitation Expiry Duration"],
    ),
    ("How are invitation tokens stored?", ["document:docs/adr/0001-invitation-tokens.md"]),
]


@dataclass
class CaseResult:
    question: str
    expected: list[str]
    basic: list[str]
    expanded: list[str]


def matches(expected: str, source: AnswerSource) -> bool:
    kind, _, text = expected.partition(":")
    return source.kind == kind and (source.locator.startswith(text) or text in source.title)


def found(expected: list[str], sources: list[AnswerSource]) -> list[str]:
    return [e for e in expected if any(matches(e, source) for source in sources)]


def compare(
    session: Session, workspace: Workspace, cases: list[tuple[str, list[str]]]
) -> list[CaseResult]:
    results = []
    for question, expected in cases:
        basic = retrieve_for_question(session, workspace, question, expand=False).sources
        full = retrieve_for_question(session, workspace, question).sources
        results.append(
            CaseResult(question, expected, found(expected, basic), found(expected, full))
        )
    return results


def recall(results: list[CaseResult], mode: str) -> float:
    total = sum(len(r.expected) for r in results)
    hits = sum(len(r.basic if mode == "basic" else r.expanded) for r in results)
    return hits / total if total else 0.0


def main() -> None:
    with make_session_factory(make_engine(Settings()))() as session:
        for workspace in session.scalars(select(Workspace)):
            has_demo = session.scalar(
                select(Document.path).where(
                    Document.workspace_id == workspace.id, Document.path == BRD
                )
            )
            if not has_demo:
                continue
            results = compare(session, workspace, DEMO_CASES)
            print(f"\n{workspace.name} ({workspace.repo_owner}/{workspace.repo_name})")
            for r in results:
                print(
                    f"  {len(r.basic)}/{len(r.expected)} -> {len(r.expanded)}/{len(r.expected)}"
                    f"  {r.question[:70]}"
                )
                for missing in sorted(set(r.expected) - set(r.expanded)):
                    print(f"      still missing: {missing}")
            print(
                f"  recall: basic {recall(results, 'basic'):.0%}, "
                f"link-expanded {recall(results, 'expanded'):.0%}"
            )


if __name__ == "__main__":
    main()
