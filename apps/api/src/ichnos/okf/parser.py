"""Parse Open Knowledge Format (OKF v0.2) documents tolerantly.

Nothing here raises on document content: problems become findings, so one broken file never
stops a sync (ADR-0009). Paths are repository-relative POSIX strings such as
"docs/adr/0001-invitation-tokens.md"; the bundle root defaults to "docs".
"""

import datetime as dt
import posixpath
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Literal

import yaml

STATUSES = frozenset({"draft", "stable", "deprecated"})

FENCE_RE = re.compile(r"^\s*(`{3,}|~{3,})")
INLINE_CODE_RE = re.compile(r"`[^`\n]*`")
LINK_RE = re.compile(r"(?<!!)\[([^\]]*)\]\(([^)\s]+)[^)]*\)")
SCHEME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")
HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
FOOTNOTE_REF_RE = re.compile(r"\[\^([^\]\s]+)\](?!:)")
ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

DocumentKind = Literal["concept", "index", "log", "other"]
TrustTier = Literal["human_verified", "agent_verified", "generated", "unknown"]
Level = Literal["error", "warning"]


@dataclass(frozen=True)
class Finding:
    level: Level
    code: str
    message: str
    line: int | None = None


@dataclass(frozen=True)
class Heading:
    level: int
    text: str
    line: int


@dataclass(frozen=True)
class Link:
    text: str
    target: str
    line: int
    resolved_path: str | None  # repository-relative for internal links; None when external


@dataclass(frozen=True)
class Source:
    id: str | None
    resource: str
    title: str | None


@dataclass
class ParsedDocument:
    path: str
    kind: DocumentKind
    concept_id: str | None
    frontmatter: dict[str, Any]
    body: str
    body_start_line: int
    type: str | None = None
    title: str | None = None
    description: str | None = None
    status: str | None = None
    trust_tier: TrustTier = "unknown"
    headings: list[Heading] = field(default_factory=list)
    links: list[Link] = field(default_factory=list)
    sources: list[Source] = field(default_factory=list)
    footnotes: list[str] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)


@dataclass
class ParsedBundle:
    root: str
    okf_version: str | None
    documents: dict[str, ParsedDocument]
    findings: list[Finding]


def _text(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _actors(value: Any) -> list[str]:
    entries = value if isinstance(value, list) else [value]
    return [str(entry.get("by", "")) for entry in entries if isinstance(entry, dict)]


def trust_tier(frontmatter: Mapping[str, Any]) -> TrustTier:
    """Ichnos trust tier: who, if anyone, has confirmed this content."""
    verifiers = [actor for actor in _actors(frontmatter.get("verified")) if actor]
    if any(actor.startswith("human:") for actor in verifiers):
        return "human_verified"
    if verifiers:
        return "agent_verified"
    if any(_actors(frontmatter.get("generated"))):
        return "generated"
    return "unknown"


def resolve_link(doc_path: str, target: str, bundle_root: str = "docs") -> str | None:
    """Resolve a Markdown link target to a repository-relative path, or None if external."""
    if SCHEME_RE.match(target) or target.startswith("#"):
        return None
    clean = target.split("#", 1)[0].split("?", 1)[0]
    if not clean:
        return None
    base = bundle_root.strip("/") if clean.startswith("/") else posixpath.dirname(doc_path)
    resolved = posixpath.normpath(posixpath.join(base, clean.lstrip("/")))
    if clean.endswith("/"):
        resolved = posixpath.join(resolved, "index.md")
    return None if resolved == ".." or resolved.startswith("../") else resolved


def _split_frontmatter(text: str) -> tuple[str | None, str, int]:
    """Return (frontmatter, body, 1-based line where the body starts)."""
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].rstrip("\r\n") != "---":
        return None, text, 1
    for index in range(1, len(lines)):
        if lines[index].rstrip("\r\n") == "---":
            return "".join(lines[1:index]), "".join(lines[index + 1 :]), index + 2
    raise ValueError("Frontmatter starts with '---' but is never closed.")


def _sources(value: Any) -> list[Source]:
    if not isinstance(value, list):
        return []
    result: list[Source] = []
    for entry in value:
        if isinstance(entry, dict) and entry.get("resource"):
            ident = entry.get("id")
            result.append(
                Source(
                    id=None if ident is None else str(ident),
                    resource=str(entry["resource"]),
                    title=_text(entry.get("title")),
                )
            )
    return result


def _scan_body(doc: ParsedDocument, bundle_root: str) -> None:
    in_fence = False
    for offset, raw in enumerate(doc.body.splitlines()):
        line_no = doc.body_start_line + offset
        if FENCE_RE.match(raw):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        heading = HEADING_RE.match(raw)
        if heading:
            doc.headings.append(Heading(len(heading.group(1)), heading.group(2), line_no))
        text = INLINE_CODE_RE.sub("", raw)
        for match in LINK_RE.finditer(text):
            target = match.group(2)
            resolved = resolve_link(doc.path, target, bundle_root)
            doc.links.append(Link(match.group(1), target, line_no, resolved))
        for label in FOOTNOTE_REF_RE.findall(text):
            if label not in doc.footnotes:
                doc.footnotes.append(label)


def _check_concept(doc: ParsedDocument, has_frontmatter: bool) -> None:
    add = doc.findings.append
    if not has_frontmatter:
        add(Finding("error", "frontmatter-missing", "Concept has no YAML frontmatter.", 1))
    elif doc.type is None:
        add(Finding("error", "type-missing", "Frontmatter needs a non-empty 'type'.", 1))
    if doc.status is not None and doc.status not in STATUSES:
        add(Finding("warning", "status-unknown", f"Unknown status '{doc.status}'.", 1))
    if doc.status == "stable" and doc.trust_tier != "human_verified":
        message = "Status is stable but no human verified it."
        add(Finding("warning", "stable-unverified", message, 1))
    source_ids = {source.id for source in doc.sources if source.id}
    for label in doc.footnotes:
        if label not in source_ids:
            add(Finding("warning", "footnote-unsourced", f"Footnote [^{label}] has no source.", 1))


def _check_index(doc: ParsedDocument, bundle_root: str, has_frontmatter: bool) -> None:
    is_root = doc.path == f"{bundle_root}/index.md"
    if has_frontmatter and not is_root:
        doc.findings.append(
            Finding("error", "index-frontmatter", "Only the root index.md may have frontmatter.", 1)
        )
    if is_root and set(doc.frontmatter) - {"okf_version"}:
        doc.findings.append(
            Finding("error", "index-keys", "Root index.md may only declare okf_version.", 1)
        )
    if not doc.headings:
        doc.findings.append(Finding("error", "index-heading", "index.md needs a heading."))


def _check_log(doc: ParsedDocument, has_frontmatter: bool) -> None:
    if has_frontmatter:
        doc.findings.append(Finding("warning", "log-frontmatter", "log.md has frontmatter.", 1))
    dates: list[dt.date] = []
    for heading in doc.headings:
        if heading.level != 2:
            continue
        if not ISO_DATE_RE.match(heading.text):
            message = f"Log headings must be YYYY-MM-DD, found '{heading.text}'."
            doc.findings.append(Finding("error", "log-date", message, heading.line))
            continue
        try:
            dates.append(dt.date.fromisoformat(heading.text))
        except ValueError:
            doc.findings.append(Finding("error", "log-date", "Invalid date.", heading.line))
    if dates != sorted(dates, reverse=True):
        doc.findings.append(Finding("warning", "log-order", "Log entries are not newest first."))


def parse_document(path: str, text: str, bundle_root: str = "docs") -> ParsedDocument:
    """Parse one file. Files outside the bundle root, or not Markdown, get kind 'other'."""
    root = bundle_root.strip("/")
    name = posixpath.basename(path)
    kind: DocumentKind
    if not path.startswith(f"{root}/") or not path.endswith(".md"):
        kind = "other"
    elif name == "index.md":
        kind = "index"
    elif name == "log.md":
        kind = "log"
    else:
        kind = "concept"

    findings: list[Finding] = []
    raw: str | None
    try:
        raw, body, body_start = _split_frontmatter(text)
    except ValueError as exc:
        raw, body, body_start = None, text, 1
        findings.append(Finding("error", "frontmatter-unclosed", str(exc), 1))

    frontmatter: dict[str, Any] = {}
    if raw is not None:
        try:
            loaded = yaml.safe_load(raw) if raw.strip() else {}
        except yaml.YAMLError as exc:
            findings.append(Finding("error", "frontmatter-invalid", f"Invalid YAML: {exc}", 1))
            loaded = {}
        if isinstance(loaded, dict):
            frontmatter = {str(key): value for key, value in loaded.items()}
        else:
            message = "Frontmatter is not a mapping."
            findings.append(Finding("error", "frontmatter-shape", message, 1))

    doc = ParsedDocument(
        path=path,
        kind=kind,
        concept_id=path[len(root) + 1 : -3] if kind == "concept" else None,
        frontmatter=frontmatter,
        body=body,
        body_start_line=body_start,
        findings=findings,
    )
    doc.type = _text(frontmatter.get("type"))
    doc.title = _text(frontmatter.get("title"))
    doc.description = _text(frontmatter.get("description"))
    doc.status = _text(frontmatter.get("status"))
    doc.trust_tier = trust_tier(frontmatter)
    doc.sources = _sources(frontmatter.get("sources"))
    _scan_body(doc, root)
    if doc.title is None and doc.headings:
        doc.title = doc.headings[0].text

    already_flagged = any(f.code.startswith("frontmatter-") for f in findings)
    if kind == "concept":
        _check_concept(doc, raw is not None or already_flagged)
    elif kind == "index":
        _check_index(doc, root, raw is not None)
    elif kind == "log":
        _check_log(doc, raw is not None)
    return doc


def parse_bundle(files: Mapping[str, str], bundle_root: str = "docs") -> ParsedBundle:
    """Parse every file, then check links across the bundle."""
    root = bundle_root.strip("/")
    documents = {path: parse_document(path, files[path], root) for path in sorted(files)}
    findings: list[Finding] = []
    index = documents.get(f"{root}/index.md")
    version = None
    if index is None:
        findings.append(Finding("warning", "root-index-missing", f"No {root}/index.md found."))
    elif "okf_version" in index.frontmatter:
        version = str(index.frontmatter["okf_version"])
    for doc in documents.values():
        for link in doc.links:
            target = link.resolved_path or ""
            internal = target.startswith(f"{root}/") and target.endswith(".md")
            if internal and target not in documents:
                message = f"Link target '{link.target}' is not in the bundle."
                doc.findings.append(Finding("warning", "link-unresolved", message, link.line))
    return ParsedBundle(root=root, okf_version=version, documents=documents, findings=findings)


def render_document(frontmatter: Mapping[str, Any], body: str) -> str:
    """Write a document back, keeping every frontmatter key, including unknown ones."""
    if not frontmatter:
        return body
    dumped = yaml.safe_dump(
        dict(frontmatter), sort_keys=False, allow_unicode=True, default_flow_style=False
    )
    return f"---\n{dumped}---\n{body}"
