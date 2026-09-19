#!/usr/bin/env python3
"""Validate a docs/ directory as an Open Knowledge Format (OKF) v0.2 bundle.

Errors (OKF v0.2 conformance, section 11):
  1. Every non-reserved .md file has a parseable YAML frontmatter block.
  2. Every frontmatter block has a non-empty `type`.
  3. index.md and log.md follow sections 8 and 9.

Hygiene checks (warnings by default, errors with --strict):
  - status is draft, stable or deprecated
  - generated.by is present
  - stable concepts carry a human `verified` entry (Ichnos approval rule)
  - sources entries have a `resource`; footnotes match sources[].id
  - internal links resolve; every concept and section is listed in its index.md
"""
from __future__ import annotations

import argparse
import datetime as dt
import re
from pathlib import Path

import yaml

RESERVED = {"index.md", "log.md"}
STATUSES = {"draft", "stable", "deprecated"}

FENCE_RE = re.compile(r"^\s*(`{3,}|~{3,})")
INLINE_CODE_RE = re.compile(r"`[^`\n]*`")
HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.S)
LINK_RE = re.compile(r"(?<!!)\[[^\]]*\]\(([^)\s]+)[^)]*\)")
SCHEME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")
FOOTNOTE_REF_RE = re.compile(r"\[\^([^\]\s]+)\](?!:)")
FOOTNOTE_DEF_RE = re.compile(r"^\[\^([^\]\s]+)\]:", re.M)
LOG_HEADING_RE = re.compile(r"^##\s+(.+?)\s*$")
ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
INDEX_ENTRY_RE = re.compile(r"^[*-]\s+\[[^\]]+\]\([^)\s]+\)(\s+-\s+.+)?$")


class Report:
    def __init__(self, root: Path, strict: bool) -> None:
        self.root = root
        self.strict = strict
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def _rel(self, path: Path) -> str:
        try:
            return str(path.relative_to(self.root.parent))
        except ValueError:
            return str(path)

    def error(self, path: Path, msg: str) -> None:
        self.errors.append(f"ERROR {self._rel(path)}: {msg}")

    def warn(self, path: Path, msg: str) -> None:
        self.warnings.append(f"WARN  {self._rel(path)}: {msg}")

    def hygiene(self, path: Path, msg: str) -> None:
        (self.error if self.strict else self.warn)(path, msg)


def split_frontmatter(text: str) -> tuple[str | None, str]:
    """Return (frontmatter, body); frontmatter is None when absent."""
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].rstrip("\r\n") != "---":
        return None, text
    for i in range(1, len(lines)):
        if lines[i].rstrip("\r\n") == "---":
            return "".join(lines[1:i]), "".join(lines[i + 1:])
    raise ValueError("frontmatter opened with '---' but never closed")


def load_yaml(fm: str):
    return yaml.safe_load(fm) if fm.strip() else {}


def strip_code(body: str) -> str:
    """Remove fenced code blocks and inline code spans."""
    out, in_fence = [], False
    for line in body.splitlines():
        if FENCE_RE.match(line):
            in_fence = not in_fence
            continue
        if not in_fence:
            out.append(line)
    return INLINE_CODE_RE.sub("", "\n".join(out))


def resolve_target(path: Path, target: str, root: Path) -> Path | None:
    """Resolve an internal link target; None for external URLs and anchors."""
    if SCHEME_RE.match(target) or target.startswith("#"):
        return None
    target = target.split("#", 1)[0]
    if not target:
        return None
    base = root if target.startswith("/") else path.parent
    return (base / target.lstrip("/")).resolve()


def check_links(path: Path, text: str, rep: Report) -> None:
    for target in LINK_RE.findall(text):
        resolved = resolve_target(path, target, rep.root)
        if resolved is not None and not resolved.exists():
            rep.hygiene(path, f"broken link -> {target}")


def actors(value) -> list[str]:
    entries = value if isinstance(value, list) else [value]
    return [str(e.get("by", "")) for e in entries if isinstance(e, dict)]


def check_index(path: Path, text: str, rep: Report) -> None:
    try:
        fm, body = split_frontmatter(text)
    except ValueError as exc:
        rep.error(path, str(exc))
        return
    if fm is not None:
        if path.parent != rep.root:
            rep.error(path, "only the bundle-root index.md may carry frontmatter (OKF §8)")
        else:
            try:
                data = load_yaml(fm)
            except yaml.YAMLError as exc:
                rep.error(path, f"unparseable frontmatter: {exc}")
                data = {}
            if not isinstance(data, dict) or set(data) - {"okf_version"}:
                rep.error(path, "root index.md frontmatter may only contain okf_version (OKF §12)")

    body = strip_code(HTML_COMMENT_RE.sub("", body))
    lines = [line.strip() for line in body.splitlines() if line.strip()]
    if not any(line.startswith("#") for line in lines):
        rep.error(path, "index.md needs at least one section heading (OKF §8)")
    for line in lines:
        if not line.startswith("#") and not INDEX_ENTRY_RE.match(line):
            rep.hygiene(path, f"not a '* [Title](url) - description' entry: {line[:60]}")
    check_links(path, body, rep)

    listed = {resolve_target(path, t, rep.root) for t in LINK_RE.findall(body)}
    for child in sorted(path.parent.iterdir()):
        if child.name in RESERVED or child.name.startswith("."):
            continue
        is_concept = child.is_file() and child.suffix == ".md"
        is_section = child.is_dir() and any(child.rglob("*.md"))
        if (is_concept or is_section) and child.resolve() not in listed:
            rep.hygiene(path, f"'{child.name}' is not listed in this index")


def check_log(path: Path, text: str, rep: Report) -> None:
    try:
        fm, body = split_frontmatter(text)
    except ValueError as exc:
        rep.error(path, str(exc))
        return
    if fm is not None:
        rep.hygiene(path, "log.md should not carry frontmatter (OKF §9)")
    dates: list[dt.date] = []
    for line in body.splitlines():
        match = LOG_HEADING_RE.match(line)
        if not match:
            continue
        value = match.group(1)
        if not ISO_DATE_RE.match(value):
            rep.error(path, f"log date headings must be YYYY-MM-DD, found '{value}' (OKF §9)")
            continue
        try:
            dates.append(dt.date.fromisoformat(value))
        except ValueError:
            rep.error(path, f"invalid date '{value}'")
    if dates != sorted(dates, reverse=True):
        rep.hygiene(path, "log entries should be newest first (OKF §9)")
    check_links(path, strip_code(body), rep)


def check_concept(path: Path, text: str, rep: Report) -> None:
    try:
        fm, body = split_frontmatter(text)
    except ValueError as exc:
        rep.error(path, str(exc))
        return
    if fm is None:
        rep.error(path, "missing YAML frontmatter (OKF §11 rule 1)")
        return
    try:
        data = load_yaml(fm)
    except yaml.YAMLError as exc:
        rep.error(path, f"unparseable frontmatter: {exc}")
        return
    if not isinstance(data, dict):
        rep.error(path, "frontmatter must be a YAML mapping")
        return

    concept_type = data.get("type")
    if not isinstance(concept_type, str) or not concept_type.strip():
        rep.error(path, "frontmatter needs a non-empty 'type' (OKF §11 rule 2)")

    status = data.get("status", "stable")
    if status not in STATUSES:
        rep.hygiene(path, f"status must be one of {sorted(STATUSES)}, found '{status}'")
    generated = data.get("generated")
    if not (isinstance(generated, dict) and generated.get("by")):
        rep.hygiene(path, "missing 'generated: { by, at }'")
    if status == "stable" and not any(a.startswith("human:") for a in actors(data.get("verified"))):
        rep.hygiene(path, "status is stable but has no human 'verified' entry (Ichnos approval rule)")

    sources = data.get("sources") or []
    source_ids = set()
    for entry in sources if isinstance(sources, list) else []:
        if not (isinstance(entry, dict) and entry.get("resource")):
            rep.hygiene(path, "every sources entry needs a 'resource' (OKF §5.1)")
        elif entry.get("id"):
            source_ids.add(str(entry["id"]))

    clean = strip_code(body)
    refs = set(FOOTNOTE_REF_RE.findall(clean))
    defs = set(FOOTNOTE_DEF_RE.findall(clean))
    for label in sorted(refs - source_ids):
        rep.hygiene(path, f"footnote [^{label}] has no matching sources[].id")
    for label in sorted(refs - defs):
        rep.hygiene(path, f"footnote [^{label}] has no definition")
    check_links(path, clean, rep)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate an OKF v0.2 bundle.")
    parser.add_argument("bundle", nargs="?", default="docs", type=Path)
    parser.add_argument("--strict", action="store_true", help="treat hygiene warnings as errors")
    args = parser.parse_args(argv)

    root = args.bundle.resolve()
    if not root.is_dir():
        print(f"not a directory: {args.bundle}")
        return 2
    rep = Report(root, args.strict)
    if not (root / "index.md").exists():
        rep.warn(root, "no bundle-root index.md")

    files = sorted(root.rglob("*.md"))
    for path in files:
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            rep.error(path, "file is not valid UTF-8")
            continue
        if path.name == "index.md":
            check_index(path, text, rep)
        elif path.name == "log.md":
            check_log(path, text, rep)
        else:
            check_concept(path, text, rep)

    for line in rep.warnings + rep.errors:
        print(line)
    concepts = sum(1 for f in files if f.name not in RESERVED)
    mode = "strict" if args.strict else "default"
    print(f"\nOKF v0.2 ({mode}): {len(files)} files, {concepts} concepts, "
          f"{len(rep.errors)} errors, {len(rep.warnings)} warnings")
    return 1 if rep.errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
