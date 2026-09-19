from pathlib import Path
from typing import Any

import pytest

from ichnos.okf import (
    Heading,
    parse_bundle,
    parse_document,
    render_document,
    resolve_link,
    trust_tier,
)

REPO_ROOT = Path(__file__).resolve().parents[3]

CONCEPT = """---
type: Decision
title: Use tokens
status: stable
generated: { by: claude/opus-5, at: 2026-09-19T10:00:00Z }
verified: { by: human:alice, at: 2026-09-19T11:00:00Z }
sources:
  - id: note
    resource: /meetings/2026-09-15-sync.md
---

# Context

Decided in the sync.[^note]

[^note]: Sync notes
"""


def codes(text: str, path: str = "docs/adr/0001-x.md") -> list[str]:
    return [finding.code for finding in parse_document(path, text).findings]


def test_parses_concept_metadata() -> None:
    doc = parse_document("docs/adr/0001-use-tokens.md", CONCEPT)
    assert doc.kind == "concept"
    assert doc.concept_id == "adr/0001-use-tokens"
    assert (doc.type, doc.title, doc.status) == ("Decision", "Use tokens", "stable")
    assert doc.trust_tier == "human_verified"
    assert [source.id for source in doc.sources] == ["note"]
    assert doc.footnotes == ["note"]
    assert doc.findings == []


@pytest.mark.parametrize(
    ("frontmatter", "expected"),
    [
        ({"verified": [{"by": "claude/opus-5"}, {"by": "human:alice"}]}, "human_verified"),
        ({"verified": {"by": "ichnos/validator"}}, "agent_verified"),
        ({"generated": {"by": "claude/opus-5"}}, "generated"),
        ({}, "unknown"),
    ],
)
def test_trust_tiers(frontmatter: dict[str, Any], expected: str) -> None:
    assert trust_tier(frontmatter) == expected


def test_missing_frontmatter_is_a_finding_not_an_exception() -> None:
    doc = parse_document("docs/notes/plain.md", "# Plain title\n\nJust text.\n")
    assert [finding.code for finding in doc.findings] == ["frontmatter-missing"]
    assert doc.title == "Plain title"


def test_invalid_and_unclosed_frontmatter() -> None:
    assert "frontmatter-invalid" in codes("---\ntype: [unclosed\n---\nBody\n")
    unclosed = codes("---\ntype: Note\n")
    assert "frontmatter-unclosed" in unclosed
    assert "frontmatter-missing" not in unclosed


def test_conformance_warnings() -> None:
    unverified = "---\ntype: Note\nstatus: stable\n---\nText.\n"
    assert codes(unverified) == ["stable-unverified"]
    unsourced = "---\ntype: Note\nstatus: draft\n---\nClaim.[^ghost]\n"
    assert codes(unsourced) == ["footnote-unsourced"]
    assert codes("---\ntitle: No type\n---\nText.\n") == ["type-missing"]


@pytest.mark.parametrize(
    ("doc_path", "target", "expected"),
    [
        ("docs/specs/a/brd.md", "techspec.md", "docs/specs/a/techspec.md"),
        ("docs/specs/a/brd.md", "/adr/0001.md", "docs/adr/0001.md"),
        ("docs/index.md", "specs/", "docs/specs/index.md"),
        ("docs/a.md", "b.md#part", "docs/b.md"),
        ("docs/a.md", "../README.md", "README.md"),
        ("docs/a.md", "../../outside.md", None),
        ("docs/a.md", "https://okf.md/", None),
        ("docs/a.md", "#section", None),
    ],
)
def test_resolve_link(doc_path: str, target: str, expected: str | None) -> None:
    assert resolve_link(doc_path, target) == expected


def test_links_and_headings_outside_code_only() -> None:
    text = (
        "---\ntype: Note\n---\n"
        "# Title\n"
        "\n"
        "See [ADR](/adr/0001.md) but not `[inline](x.md)`.\n"
        "\n"
        "```\n"
        "[fake](nope.md)\n"
        "# not a heading\n"
        "```\n"
    )
    doc = parse_document("docs/notes/a.md", text)
    assert doc.headings == [Heading(1, "Title", 4)]
    assert [(link.resolved_path, link.line) for link in doc.links] == [("docs/adr/0001.md", 6)]


def test_index_rules() -> None:
    assert codes("---\ntype: X\n---\n# Section\n", "docs/adr/index.md") == ["index-frontmatter"]
    root = '---\nokf_version: "0.2"\nowner: me\n---\n# Docs\n'
    assert codes(root, "docs/index.md") == ["index-keys"]
    assert codes("* [A](a.md)\n", "docs/specs/index.md") == ["index-heading"]


def test_log_rules() -> None:
    assert codes("# Log\n\n## yesterday\n* x\n", "docs/log.md") == ["log-date"]
    out_of_order = "# Log\n\n## 2026-01-01\n* a\n\n## 2026-02-01\n* b\n"
    assert codes(out_of_order, "docs/log.md") == ["log-order"]


def test_bundle_checks() -> None:
    files = {
        "docs/index.md": '---\nokf_version: "0.2"\n---\n# Docs\n\n* [A](a.md) - A concept.\n',
        "docs/a.md": "---\ntype: Note\n---\nSee [missing](/missing.md).\n",
    }
    bundle = parse_bundle(files)
    assert bundle.okf_version == "0.2"
    assert [f.code for f in bundle.documents["docs/a.md"].findings] == ["link-unresolved"]
    without_root = parse_bundle({"docs/a.md": files["docs/a.md"]})
    assert [f.code for f in without_root.findings] == ["root-index-missing"]


def test_round_trip_keeps_unknown_keys() -> None:
    original = CONCEPT.replace("status: stable", "status: stable\nx-team: [core, docs]")
    first = parse_document("docs/adr/0001-x.md", original)
    written = render_document(first.frontmatter, first.body)
    second = parse_document("docs/adr/0001-x.md", written)
    assert second.frontmatter == first.frontmatter
    assert second.frontmatter["x-team"] == ["core", "docs"]
    assert second.body == first.body


def test_files_outside_the_bundle_are_other() -> None:
    doc = parse_document(".github/pull_request_template.md", "Closes #\n")
    assert doc.kind == "other"
    assert doc.findings == []


@pytest.mark.parametrize("repo", ["", "examples/demo-repository"])
def test_real_bundles_have_no_findings(repo: str) -> None:
    base = REPO_ROOT / repo
    files = {
        path.relative_to(base).as_posix(): path.read_text(encoding="utf-8")
        for path in (base / "docs").rglob("*.md")
    }
    bundle = parse_bundle(files)
    findings = bundle.findings + [f for d in bundle.documents.values() for f in d.findings]
    assert bundle.okf_version == "0.2"
    assert findings == []
