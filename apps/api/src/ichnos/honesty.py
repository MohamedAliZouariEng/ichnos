"""What Ichnos must never claim before a real repository action (ADR-0021).

Plans and pull request bodies are checked against these patterns: saying that code changed,
that something was implemented or fixed, or that tests pass is refused until a person pushes.
"""

import re

CLAIM_PATTERNS = [
    r"\b(?:has|have) been (?:changed|implemented|fixed|updated|added|completed|merged)\b",
    r"\b(?:was|were) (?:changed|implemented|fixed|updated|added|completed|merged)\b",
    r"\b(?:all )?tests? (?:now )?(?:pass|passes|passed|are passing|is passing)\b",
    r"\b(?:is|are) (?:now )?(?:done|complete|completed|implemented|fixed)\b",
    "\u2705",
]
CLAIM_RE = re.compile("|".join(CLAIM_PATTERNS), re.IGNORECASE)
# Words that turn what follows into a condition or a check, not a statement of fact:
# "until Story #9 is implemented", "verify that all tests pass".
CONDITION_RE = re.compile(
    r"\b(?:until|once|when|whenever|after|before|if|unless|whether|so that|"
    r"verify|verifies|verifying|ensure|ensures|checks? that|checks? whether|"
    r"confirm|confirms|assert|asserts)\b",
    re.IGNORECASE,
)
CLAUSE_BREAK = re.compile(r"[.;:!?]")


def claims(text: str) -> list[tuple[int, str]]:
    """(line number, matched words) for each claim of completed work in the text."""
    found = []
    for number, line in enumerate(text.splitlines(), start=1):
        for match in CLAIM_RE.finditer(line):
            clause = CLAUSE_BREAK.split(line[: match.start()])[-1]
            if CONDITION_RE.search(clause):
                continue
            found.append((number, match.group(0)))
    return found
