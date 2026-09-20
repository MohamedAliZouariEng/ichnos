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


def claims(text: str) -> list[tuple[int, str]]:
    """(line number, matched words) for each claim of completed work in the text."""
    found = []
    for number, line in enumerate(text.splitlines(), start=1):
        for match in CLAIM_RE.finditer(line):
            found.append((number, match.group(0)))
    return found
