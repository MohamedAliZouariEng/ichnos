from ichnos.evaluate.review import review
from ichnos.llm import FakeProvider

CRITERIA = [
    ("#7 AC-01", "Given a link sent 7 days ago, when opened, then it is refused."),
    ("#9 AC-04", "Given the page, when it loads, then it is fast."),
]


def test_the_review_returns_one_verdict_per_known_criterion() -> None:
    verdicts, usage = review(FakeProvider(), CRITERIA)
    assert set(verdicts) == {"#7 AC-01", "#9 AC-04"} and usage.calls == 1
    assert all(v.testable for v in verdicts.values())  # the fake says yes; the rules decide
