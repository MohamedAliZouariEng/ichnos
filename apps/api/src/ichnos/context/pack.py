"""Context packs (ADR-0019): everything needed to implement one Story, assembled by code.

No model is called. Every item says where it came from, how far to trust it, and why it was
included; missing parts are listed as absent; the pack's hash identifies exactly what it held.
"""

import datetime as dt
import hashlib
import json
import re
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from typing import Any

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from ichnos.db.models import Document, GitHubItem, Link, RepositoryFile, Workspace
from ichnos.workflows.retrieval import keywords

ITEM_KINDS = ("issue", "pull_request")
DOC_ROLES = {"BRD": "brd", "Technical Specification": "techspec", "Decision": "adr"}
RELATED = ("depends_on", "closes", "mentions", "parent")
EXPECTED = ("epic", "initiative", "brd", "techspec", "adr", "code")
CODE_LANGUAGES = frozenset(
    {
        "Python",
        "TypeScript",
        "JavaScript",
        "Go",
        "Rust",
        "Java",
        "Kotlin",
        "Ruby",
        "PHP",
        "C#",
        "SQL",
        "Shell",
        "HTML",
        "CSS",
    }
)
MAX_ADRS = 5
MAX_RELATED = 10
MAX_FILES = 20
MAX_FILE_BYTES = 40_000
MAX_EXCERPT = 4_000
MIN_ADR_MATCHES = 2
PATH_WORD_RE = re.compile(r"[a-z]+")

Fetch = Callable[[str], str]  # blob SHA -> file text


class PackError(Exception):
    """The pack cannot be built; the message is safe to show."""


@dataclass
class PackItem:
    id: str
    role: str
    title: str
    source: str
    url: str | None
    trust: str
    flags: list[str]
    reason: str
    excerpt: str


@dataclass
class ContextPack:
    story: int
    items: list[PackItem]
    absent: list[str]
    keywords: list[str]
    hash: str = ""
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def pack_hash(pack: ContextPack) -> str:
    content = {k: v for k, v in pack.as_dict().items() if k != "hash"}
    canonical = json.dumps(content, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode()).hexdigest()


def _stem(word: str) -> str:
    return word[:-1] if word.endswith("s") and len(word) > 4 else word


def _doc_flags(doc: Document, today: dt.date) -> list[str]:
    flags = [] if doc.trust_tier == "human_verified" else ["unverified"]
    stale_after = (doc.frontmatter or {}).get("stale_after")
    if stale_after:
        try:
            if dt.date.fromisoformat(str(stale_after)[:10]) < today:
                flags.append("stale")
        except ValueError:
            pass
    return flags


def _other_end(link: Link, key: str) -> str | None:
    """The Issue or pull request at the other end of a link between two items."""
    if link.source_kind not in ITEM_KINDS or link.target_kind not in ITEM_KINDS:
        return None
    if link.source_key == key:
        return link.target_key
    if link.target_key == key:
        return link.source_key
    return None


class _Builder:
    def __init__(self, session: Session, workspace: Workspace, today: dt.date) -> None:
        self.session, self.workspace, self.today = session, workspace, today
        self.items: list[PackItem] = []
        self.seen: set[str] = set()

    def _add(
        self,
        key: str,
        role: str,
        title: str,
        source: str,
        url: str | None,
        trust: str,
        flags: list[str],
        reason: str,
        excerpt: str,
        limit: int,
    ) -> bool:
        if key in self.seen:
            return False
        self.seen.add(key)
        self.items.append(
            PackItem(
                f"P{len(self.items) + 1}",
                role,
                title,
                source,
                url,
                trust,
                flags,
                reason,
                excerpt[:limit],
            )
        )
        return True

    def item(self, number: int) -> GitHubItem | None:
        return self.session.scalar(
            select(GitHubItem).where(
                GitHubItem.workspace_id == self.workspace.id, GitHubItem.number == number
            )
        )

    def document(self, path: str) -> Document | None:
        return self.session.scalar(
            select(Document).where(
                Document.workspace_id == self.workspace.id, Document.path == path
            )
        )

    def add_item(self, item: GitHubItem, role: str, reason: str) -> bool:
        kind = "Pull request" if item.item_type == "pull_request" else "Issue"
        flags = ["closed"] if item.state == "closed" else []
        return self._add(
            f"item:{item.number}",
            role,
            item.title,
            f"{kind} #{item.number}",
            item.url,
            "github",
            flags,
            reason,
            item.body or "",
            MAX_EXCERPT,
        )

    def add_doc(self, doc: Document, role: str, reason: str) -> bool:
        return self._add(
            f"doc:{doc.path}",
            role,
            doc.title or doc.path,
            f"{doc.path}@{doc.blob_sha[:8]}",
            None,
            doc.trust_tier,
            _doc_flags(doc, self.today),
            reason,
            doc.body,
            MAX_EXCERPT,
        )

    def add_file(self, file: RepositoryFile, reason: str, fetch: Fetch | None) -> bool:
        flags: list[str] = []
        text = ""
        if fetch is None:
            flags.append("not fetched")
        elif (file.size or 0) > MAX_FILE_BYTES:
            flags.append("not fetched")
            text = f"({file.size} bytes; larger than {MAX_FILE_BYTES})"
        else:
            text = fetch(file.blob_sha)
        return self._add(
            f"file:{file.path}",
            "code",
            file.path,
            f"{file.path}@{file.blob_sha[:8]}",
            None,
            "repository",
            flags,
            reason,
            text,
            MAX_FILE_BYTES,
        )

    def links(self, kind: str, key: str) -> list[Link]:
        """Links touching one node, in either direction."""
        kinds = ITEM_KINDS if kind in ITEM_KINDS else (kind,)
        return list(
            self.session.scalars(
                select(Link)
                .where(
                    Link.workspace_id == self.workspace.id,
                    or_(
                        and_(Link.source_kind.in_(kinds), Link.source_key == key),
                        and_(Link.target_kind.in_(kinds), Link.target_key == key),
                    ),
                )
                .order_by(Link.id)
            )
        )

    def parent_of(self, item: GitHubItem) -> GitHubItem | None:
        key = str(item.number)
        for link in self.links("issue", key):
            if link.relation == "parent" and link.source_key == key:
                other = _other_end(link, key)
                if other and other.isdigit():
                    return self.item(int(other))
        return None


def build_pack(
    session: Session,
    workspace: Workspace,
    number: int,
    *,
    fetch: Fetch | None = None,
    today: dt.date | None = None,
) -> ContextPack:
    b = _Builder(session, workspace, today or dt.date.today())
    story = b.item(number)
    if story is None:
        raise PackError(f"Issue #{number} is not synced in this workspace.")
    if story.item_type == "pull_request":
        raise PackError(f"#{number} is a pull request; context packs are built for Issues.")
    b.add_item(story, "story", "the Story being implemented")

    # Parent Epic, then its Initiative.
    chain = [story]
    for role in ("epic", "initiative"):
        parent = b.parent_of(chain[-1])
        if parent is None:
            break
        b.add_item(parent, role, f"parent of #{chain[-1].number}")
        chain.append(parent)

    # BRD and techspec referenced by the Story or its parents, then the ADRs they cite.
    documents: list[Document] = []
    for item in chain:
        key = str(item.number)
        for link in b.links("issue", key):
            if (
                link.source_key != key
                or link.target_kind != "document"
                or link.relation not in ("references", "cites")
            ):
                continue
            doc = b.document(link.target_key)
            doc_role = DOC_ROLES.get(doc.doc_type or "") if doc else None
            if doc and doc_role and b.add_doc(doc, doc_role, f"referenced by #{item.number}"):
                documents.append(doc)
    for doc in list(documents):
        for link in b.links("document", doc.path):
            if link.source_key != doc.path or link.target_kind != "document":
                continue
            cited = b.document(link.target_key)
            if cited and DOC_ROLES.get(cited.doc_type or "") == "adr":
                b.add_doc(cited, "adr", f"cited by {doc.path}")

    # More ADRs by keywords shared with the Story and its BRD.
    words = keywords(
        [story.title, story.body or ""] + [d.body for d in documents if d.doc_type == "BRD"]
    )
    stems = {_stem(word) for word in words}
    room = MAX_ADRS - sum(1 for i in b.items if i.role == "adr")
    scored = []
    for doc in session.scalars(
        select(Document).where(
            Document.workspace_id == workspace.id, Document.doc_type == "Decision"
        )
    ):
        text = f"{doc.title or ''} {doc.body}".lower()
        matched = sorted(word for word in words if word in text)
        if len(matched) >= MIN_ADR_MATCHES:
            scored.append((-len(matched), doc.path, doc, matched))
    for _, _, doc, matched in sorted(scored, key=lambda s: (s[0], s[1]))[: max(0, room)]:
        b.add_doc(doc, "adr", "matches " + ", ".join(matched[:4]))

    # Related Issues and pull requests: direct links first, then siblings under the Epic.
    candidates: list[tuple[str, str]] = []
    story_key = str(number)
    for link in b.links("issue", story_key):
        other = _other_end(link, story_key)
        if other and link.relation in RELATED:
            relation = link.relation.replace("_", " ")
            candidates.append((other, f"#{link.source_key} {relation} #{link.target_key}"))
    if len(chain) > 1:
        epic_key = str(chain[1].number)
        for link in b.links("issue", epic_key):
            other = _other_end(link, epic_key)
            if other and link.relation == "parent" and link.target_key == epic_key:
                candidates.append((other, f"sibling Story under #{epic_key}"))
    added = 0
    for other, why in candidates:
        if added >= MAX_RELATED:
            break
        found = b.item(int(other)) if other.isdigit() else None
        if found is None or found.state_reason == "not_planned":
            continue
        if b.add_item(found, "related", why):
            added += 1

    # Code files: paths the Story, its parents or its documents mention, then name matches.
    texts = " ".join(
        [story.body or ""] + [i.body or "" for i in chain[1:]] + [d.body for d in documents]
    )
    picks: list[tuple[int, int, str, RepositoryFile, str]] = []
    for file in session.scalars(
        select(RepositoryFile).where(RepositoryFile.workspace_id == workspace.id)
    ):
        mentioned = file.path in texts
        if file.path.endswith("__init__.py") and not mentioned:
            continue
        matched = sorted(stems & {_stem(w) for w in PATH_WORD_RE.findall(file.path.lower())})
        if mentioned:
            picks.append((0, 0, file.path, file, "mentioned in the Story, Epic or BRD"))
        elif matched and file.language in CODE_LANGUAGES:
            picks.append((1, -len(matched), file.path, file, "name matches " + ", ".join(matched)))
    for _, _, _, file, reason in sorted(picks, key=lambda p: (p[0], p[1], p[2]))[:MAX_FILES]:
        b.add_file(file, reason, fetch)

    roles = {i.role for i in b.items}
    pack = ContextPack(number, b.items, [r for r in EXPECTED if r not in roles], words)
    pack.hash = pack_hash(pack)
    return pack
