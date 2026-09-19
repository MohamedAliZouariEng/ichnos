from ichnos.knowledge.links import CommentText, DocText, ItemText, Snapshot, extract_links

Row = tuple[str, str, str, str, str, bool]

SNAPSHOT = Snapshot(
    documents={
        "docs/meetings/sync.md": DocText("# Sync\n\nSee [ADR-0001](/adr/0001-tokens.md).\n"),
        "docs/adr/0001-tokens.md": DocText("# Tokens\n", ["/meetings/sync.md"]),
    },
    items={
        1: ItemText(
            "issue", "## Summary\nHardening.\n\n## Source specification\n- docs/meetings/sync.md\n"
        ),
        2: ItemText("issue", "## Parent\n- Epic: #1\n\n## Notes\nRelated to #1 and #99.\n"),
        3: ItemText("issue", "While discussing #2 we mixed up terms.\n"),
        4: ItemText(
            "pull_request",
            "Closes #3\n\nTerms from #2.\n\n## Context used\n"
            "- docs/adr/0001-tokens.md\n- docs/missing.md\n",
        ),
    },
    comments=[
        CommentText(2, "sara", "issue_comment", "Described in docs/meetings/sync.md; see #2.")
    ],
    commits={"abc1234def": "Add glossary (#4)\n\nFixes #3"},
    pr_files={4: ["docs/adr/0001-tokens.md", "src/app.py"]},
)


def rows() -> set[Row]:
    return {
        (r.source.key, r.relation, r.target.kind, r.target.key, r.origin, r.resolved)
        for r in extract_links(SNAPSHOT)
    }


def test_document_links_and_sources_are_explicit() -> None:
    found = rows()
    assert (
        "docs/meetings/sync.md",
        "references",
        "document",
        "docs/adr/0001-tokens.md",
        "explicit",
        True,
    ) in found
    assert (
        "docs/adr/0001-tokens.md",
        "cites",
        "document",
        "docs/meetings/sync.md",
        "explicit",
        True,
    ) in found


def test_issue_conventions_are_explicit() -> None:
    found = rows()
    assert ("1", "references", "document", "docs/meetings/sync.md", "explicit", True) in found
    assert ("2", "parent", "issue", "1", "explicit", True) in found


def test_closing_keywords_in_pull_requests_and_commits() -> None:
    found = rows()
    assert ("4", "closes", "issue", "3", "explicit", True) in found
    assert ("abc1234def", "closes", "issue", "3", "explicit", True) in found


def test_mentions_are_inferred_with_lower_confidence() -> None:
    records = extract_links(SNAPSHOT)
    found = rows()
    assert ("3", "mentions", "issue", "2", "inferred", True) in found
    assert ("4", "mentions", "issue", "2", "inferred", True) in found
    assert ("abc1234def", "mentions", "pull_request", "4", "inferred", True) in found
    assert ("2", "mentions", "document", "docs/meetings/sync.md", "inferred", True) in found
    inferred = {r.confidence for r in records if r.origin == "inferred"}
    assert inferred == {0.6, 0.5}


def test_unresolved_targets_are_kept() -> None:
    found = rows()
    assert ("2", "mentions", "issue", "99", "inferred", False) in found
    assert ("4", "mentions", "file", "docs/missing.md", "inferred", False) in found


def test_pull_request_files_are_explicit_changes() -> None:
    found = rows()
    assert ("4", "changes", "document", "docs/adr/0001-tokens.md", "explicit", True) in found
    assert ("4", "changes", "file", "src/app.py", "explicit", True) in found


def test_explicit_links_suppress_redundant_inferences_and_self_links() -> None:
    found = rows()
    assert ("2", "mentions", "issue", "1", "inferred", True) not in found
    assert ("4", "mentions", "document", "docs/adr/0001-tokens.md", "inferred", True) not in found
    assert not any(row[0] == row[3] for row in found)


def test_evidence_says_where_the_link_was_found() -> None:
    parent = next(r for r in extract_links(SNAPSHOT) if r.relation == "parent")
    assert parent.evidence == "Issue #2 body: - Epic: #1"
