"""Extract relationships with origin, evidence and confidence (ADR-0010).

Pure functions over a Snapshot, so extraction is testable without a database.
"""

import re
from dataclasses import dataclass, field

from ichnos.okf import parse_document, resolve_link

EXPLICIT = 1.0
MENTION_CONFIDENCE = 0.6
PATH_CONFIDENCE = 0.5
BUNDLE_ROOT = "docs"
MAX_EVIDENCE = 300

CLOSING_RE = re.compile(
    r"\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s*:?\s+#(\d+)\b", re.IGNORECASE
)
MENTION_RE = re.compile(r"(?<![\w&/#])#(\d+)\b")
PARENT_RE = re.compile(r"^[-*]\s*(?:epic|initiative|parent)\s*:\s*#(\d+)", re.IGNORECASE)
PATH_RE = re.compile(r"(?<![\w/.-])((?:[\w.-]+/)+[\w.-]+\.(?:md|txt))\b")
HEADING_RE = re.compile(r"^#{1,6}\s+(.+?)\s*$")
COMMENT_LABELS = {
    "issue_comment": "Comment",
    "review": "Review",
    "review_comment": "Review comment",
}


@dataclass(frozen=True)
class Node:
    kind: str  # document, issue, pull_request, commit or file
    key: str


@dataclass(frozen=True)
class LinkRecord:
    source: Node
    target: Node
    relation: str
    origin: str
    evidence: str
    confidence: float
    resolved: bool


@dataclass(frozen=True)
class DocText:
    body: str
    sources: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ItemText:
    kind: str  # issue or pull_request
    body: str


@dataclass(frozen=True)
class CommentText:
    item_number: int
    author: str | None
    kind: str
    body: str


@dataclass
class Snapshot:
    """Everything link extraction reads, detached from the database."""

    documents: dict[str, DocText] = field(default_factory=dict)
    items: dict[int, ItemText] = field(default_factory=dict)
    comments: list[CommentText] = field(default_factory=list)
    commits: dict[str, str] = field(default_factory=dict)
    pr_files: dict[int, list[str]] = field(default_factory=dict)


class _Collector:
    def __init__(self, snapshot: Snapshot) -> None:
        self.snapshot = snapshot
        self.links: dict[tuple[Node, Node, str, str], LinkRecord] = {}

    def item_node(self, number: int) -> tuple[Node, bool]:
        item = self.snapshot.items.get(number)
        return Node(item.kind if item else "issue", str(number)), item is not None

    def path_node(self, path: str) -> tuple[Node, bool]:
        if path in self.snapshot.documents:
            return Node("document", path), True
        return Node("file", path), False

    def add(
        self,
        source: Node,
        target: tuple[Node, bool],
        relation: str,
        origin: str,
        evidence: str,
        confidence: float,
    ) -> None:
        node, resolved = target
        if node == source:
            return
        key = (source, node, relation, origin)
        if key not in self.links:
            self.links[key] = LinkRecord(
                source, node, relation, origin, evidence[:MAX_EVIDENCE], confidence, resolved
            )

    def scan_text(
        self, source: Node, text: str, where: str, *, conventions: bool, closing: bool
    ) -> None:
        heading: str | None = None
        for raw in text.splitlines():
            line = raw.strip()
            if not line:
                continue
            if match := HEADING_RE.match(line):
                heading = match.group(1).strip().lower()
                continue
            evidence = f"{where}: {line}"
            numbers: set[int] = set()
            paths: set[str] = set()
            if conventions and heading == "parent":
                for match in PARENT_RE.finditer(line):
                    numbers.add(int(match.group(1)))
                    target = self.item_node(int(match.group(1)))
                    self.add(source, target, "parent", "explicit", evidence, EXPLICIT)
            if conventions and heading == "source specification":
                for match in PATH_RE.finditer(line):
                    paths.add(match.group(1))
                    target = self.path_node(match.group(1))
                    self.add(source, target, "references", "explicit", evidence, EXPLICIT)
            if closing:
                for match in CLOSING_RE.finditer(line):
                    numbers.add(int(match.group(1)))
                    target = self.item_node(int(match.group(1)))
                    self.add(source, target, "closes", "explicit", evidence, EXPLICIT)
            for match in MENTION_RE.finditer(line):
                if int(match.group(1)) not in numbers:
                    target = self.item_node(int(match.group(1)))
                    self.add(source, target, "mentions", "inferred", evidence, MENTION_CONFIDENCE)
            for match in PATH_RE.finditer(line):
                if match.group(1) not in paths:
                    target = self.path_node(match.group(1))
                    self.add(source, target, "mentions", "inferred", evidence, PATH_CONFIDENCE)

    def scan_document(self, path: str, doc: DocText) -> None:
        source = Node("document", path)
        for link in parse_document(path, doc.body, BUNDLE_ROOT).links:
            if link.resolved_path is not None:
                evidence = f"{path}: [{link.text}]({link.target})"
                target = self.path_node(link.resolved_path)
                self.add(source, target, "references", "explicit", evidence, EXPLICIT)
        for resource in doc.sources:
            resolved = resolve_link(path, resource, BUNDLE_ROOT)
            if resolved is not None:
                evidence = f"{path}: sources -> {resource}"
                self.add(source, self.path_node(resolved), "cites", "explicit", evidence, EXPLICIT)

    def result(self) -> list[LinkRecord]:
        explicit = {(r.source, r.target) for r in self.links.values() if r.origin == "explicit"}
        return [
            record
            for record in self.links.values()
            if record.origin == "explicit" or (record.source, record.target) not in explicit
        ]


def extract_links(snapshot: Snapshot) -> list[LinkRecord]:
    collector = _Collector(snapshot)
    for path in sorted(snapshot.documents):
        collector.scan_document(path, snapshot.documents[path])
    for number in sorted(snapshot.items):
        item = snapshot.items[number]
        is_pull = item.kind == "pull_request"
        where = f"{'PR' if is_pull else 'Issue'} #{number} body"
        collector.scan_text(
            Node(item.kind, str(number)), item.body, where, conventions=True, closing=is_pull
        )
    for number in sorted(snapshot.pr_files):
        source = collector.item_node(number)[0]
        for path in snapshot.pr_files[number]:
            node = collector.path_node(path)[0]
            evidence = f"PR #{number} changed {path}"
            collector.add(source, (node, True), "changes", "explicit", evidence, EXPLICIT)
    for comment in snapshot.comments:
        label = COMMENT_LABELS.get(comment.kind, "Comment")
        where = f"{label} by {comment.author or 'unknown'} on #{comment.item_number}"
        source = collector.item_node(comment.item_number)[0]
        collector.scan_text(source, comment.body, where, conventions=False, closing=False)
    for sha in sorted(snapshot.commits):
        where = f"Commit {sha[:7]}"
        source = Node("commit", sha)
        collector.scan_text(source, snapshot.commits[sha], where, conventions=False, closing=True)
    return collector.result()
