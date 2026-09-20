from sqlalchemy.orm import Session, sessionmaker

import test_answer_retrieval
import test_trace
from ichnos.db.models import Workspace
from ichnos.evaluate.retrieval import compare, recall

factory = test_trace.factory  # the Step 3 fixture, shared by name
BRD = test_trace.BRD
NOTE = test_answer_retrieval.NOTE
CASES = [
    (
        "What approved evidence shows that invitation links must expire?",
        [f"document:{NOTE}", f"document:{BRD}#r-01", "issue:Default expiry"],
    ),
    (
        "Where is resending tested?",
        [f"document:{BRD}#r-02", "test:tests/test_invitations.py"],
    ),
]


def test_links_and_traces_add_what_full_text_misses(factory: sessionmaker[Session]) -> None:
    test_answer_retrieval.seed(factory)
    with factory() as session:
        ws = session.get(Workspace, "ws")
        assert ws is not None
        results = compare(session, ws, CASES)
    demo, resending = results
    assert f"document:{NOTE}" not in demo.basic and f"document:{NOTE}" in demo.expanded
    assert "test:tests/test_invitations.py" in resending.expanded
    assert "test:tests/test_invitations.py" not in resending.basic
    assert recall(results, "basic") < recall(results, "expanded") == 1.0
