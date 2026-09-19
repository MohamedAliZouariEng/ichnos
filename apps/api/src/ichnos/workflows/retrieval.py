"""Retrieval stage: the synced knowledge a BRD should be grounded in (ADR-0008, ADR-0010).

Deterministic and model-free: keywords from the sources, full-text search, trust weighting
and link expansion. Every context item records why it was chosen.
"""

import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import and_, or_, select, text
from sqlalchemy.orm import Session

from ichnos.db.models import Chunk, Document, GitHubItem, Link, Source
from ichnos.okf import parse_document
from ichnos.workflows.engine import Data, StageContext, StageFailed

MAX_ITEMS = 8
MAX_KEYWORDS = 12
MAX_EXCERPT = 1200
EXPAND_TOP = 5
LINK_FACTOR = 0.5
TRUST_WEIGHT = {"human_verified": 1.5, "agent_verified": 1.2, "generated": 1.0, "unknown": 0.8}
TYPE_BOOST = {"Decision": 1.2, "Reference": 1.2, "Technical Specification": 1.2, "BRD": 1.2}
SKIPPED_KINDS = {"index", "log"}
WORD_RE = re.compile(r"[a-z][a-z'-]{3,}")
STOPWORDS = frozenset(
    [
        "about",
        "after",
        "also",
        "been",
        "before",
        "being",
        "both",
        "could",
        "does",
        "each",
        "from",
        "have",
        "into",
        "just",
        "more",
        "most",
        "must",
        "need",
        "other",
        "over",
        "same",
        "should",
        "some",
        "such",
        "than",
        "that",
        "their",
        "them",
        "then",
        "there",
        "these",
        "they",
        "this",
        "very",
        "what",
        "when",
        "where",
        "which",
        "while",
        "will",
        "with",
        "would",
        "your",
        "only",
        "when",
        "able",
        "like",
        "make",
    ]
)
SEARCH_SQL = text(
    """
    SELECT c.source_kind, c.source_key, c.heading, c.text, c.start_line,
           bm25(chunks_fts) AS rank
    FROM chunks_fts JOIN chunks AS c ON c.id = chunks_fts.rowid
    WHERE chunks_fts MATCH :query AND c.workspace_id = :workspace_id
    ORDER BY rank
    LIMIT 80
    """
)


@dataclass
class Candidate:
    kind: str
    key: str
    title: str | None
    heading: str | None
    excerpt: str
    score: float
    reason: str
    trust_tier: str | None = None
    doc_type: str | None = None
    url: str | None = None


@dataclass
class Retrieval:
    keywords: list[str]
    sources: list[dict[str, Any]]
    context: list[dict[str, Any]] = field(default_factory=list)


def keywords(texts: list[str], limit: int = MAX_KEYWORDS) -> list[str]:
    """The most frequent significant words of the sources' body text."""
    counts: Counter[str] = Counter()
    for content in texts:
        body = parse_document("docs/source.md", content).body
        for word in WORD_RE.findall(body.lower()):
            word = word.strip("'-")
            if len(word) >= 4 and word not in STOPWORDS:
                counts[word] += 1
    return [word for word, _ in counts.most_common(limit)]


def _matched(words: list[str], excerpt: str) -> list[str]:
    lowered = excerpt.lower()
    return [word for word in words if word[:5] in lowered][:4]


def _trim(value: str) -> str:
    value = value.strip()
    return value if len(value) <= MAX_EXCERPT else value[: MAX_EXCERPT - 1].rstrip() + "…"


def retrieve(
    session: Session, workspace_id: str, sources: list[Source], *, limit: int = MAX_ITEMS
) -> Retrieval:
    words = keywords([source.content for source in sources])
    labelled = [
        {
            "id": f"S{index}",
            "source_id": source.id,
            "title": source.title,
            "kind": source.kind,
            "document_path": source.document_path,
            "text": source.content,
        }
        for index, source in enumerate(sources, start=1)
    ]
    result = Retrieval(keywords=words, sources=labelled)
    if not words:
        return result
    excluded = {source.document_path for source in sources if source.document_path}

    documents = {
        doc.path: doc
        for doc in session.scalars(select(Document).where(Document.workspace_id == workspace_id))
    }
    items = {
        str(item.number): item
        for item in session.scalars(
            select(GitHubItem).where(GitHubItem.workspace_id == workspace_id)
        )
    }

    def candidate(
        kind: str, key: str, heading: str | None, body: str, base: float, reason: str
    ) -> Candidate | None:
        if kind == "document":
            doc = documents.get(key)
            if doc is None or doc.kind in SKIPPED_KINDS or key in excluded:
                return None
            weight = TRUST_WEIGHT.get(doc.trust_tier, 1.0) * TYPE_BOOST.get(doc.doc_type or "", 1.0)
            return Candidate(
                kind,
                key,
                doc.title,
                heading,
                _trim(body),
                base * weight,
                reason,
                trust_tier=doc.trust_tier,
                doc_type=doc.doc_type,
                url=key,
            )
        if kind in ("issue", "pull_request"):
            item = items.get(key)
            title = item.title if item else None
            url = item.url if item else None
            return Candidate(kind, key, title, heading, _trim(body), base, reason, url=url)
        if kind == "commit":
            return Candidate(kind, key, heading, heading, _trim(body), base * 0.5, reason)
        return None

    query = " OR ".join(f'"{word}"' for word in words)
    best: dict[tuple[str, str], Candidate] = {}
    for row in session.execute(SEARCH_SQL, {"query": query, "workspace_id": workspace_id}):
        reason = "matched: " + ", ".join(_matched(words, row.text) or words[:2])
        found = candidate(row.source_kind, row.source_key, row.heading, row.text, -row.rank, reason)
        if found is None:
            continue
        current = best.get((found.kind, found.key))
        if current is None or found.score > current.score:
            best[(found.kind, found.key)] = found

    ranked = sorted(best.values(), key=lambda c: c.score, reverse=True)
    for parent in ranked[:EXPAND_TOP]:
        links = session.scalars(
            select(Link).where(
                Link.workspace_id == workspace_id,
                Link.origin == "explicit",
                Link.resolved.is_(True),
                or_(
                    and_(Link.source_kind == parent.kind, Link.source_key == parent.key),
                    and_(Link.target_kind == parent.kind, Link.target_key == parent.key),
                ),
            )
        ).all()
        for link in links:
            outgoing = link.source_kind == parent.kind and link.source_key == parent.key
            kind = link.target_kind if outgoing else link.source_kind
            key = link.target_key if outgoing else link.source_key
            if (kind, key) in best:
                continue
            first = session.scalar(
                select(Chunk)
                .where(
                    Chunk.workspace_id == workspace_id,
                    Chunk.source_kind == kind,
                    Chunk.source_key == key,
                )
                .order_by(Chunk.ordinal)
            )
            if first is None:
                continue
            reason = f"linked {'from' if outgoing else 'to'} {parent.key} ({link.relation})"
            found = candidate(
                kind, key, first.heading, first.text, parent.score * LINK_FACTOR, reason
            )
            if found is not None:
                best[(kind, key)] = found

    chosen = sorted(best.values(), key=lambda c: c.score, reverse=True)[:limit]
    result.context = [
        {
            "id": f"C{index}",
            "kind": item.kind,
            "key": item.key,
            "title": item.title,
            "heading": item.heading,
            "excerpt": item.excerpt,
            "score": round(item.score, 3),
            "reason": item.reason,
            "trust_tier": item.trust_tier,
            "doc_type": item.doc_type,
            "url": item.url,
        }
        for index, item in enumerate(chosen, start=1)
    ]
    return result


def load_sources(session: Session, workspace_id: str, source_ids: list[str]) -> list[Source]:
    if not source_ids:
        raise StageFailed("no sources were given")
    sources: list[Source] = []
    for source_id in source_ids:
        source = session.get(Source, source_id)
        if source is None or source.workspace_id != workspace_id:
            raise StageFailed(f"source {source_id} was not found in this workspace")
        sources.append(source)
    return sources


def retrieval_stage(data: Data, context: StageContext) -> Data:
    with context.factory() as session:
        sources = load_sources(session, context.workspace_id, list(data.get("source_ids", [])))
        found = retrieve(session, context.workspace_id, sources)
    if not found.context:
        context.note("No synced knowledge matched; the BRD will rely on the sources alone.")
    return {"keywords": found.keywords, "sources": found.sources, "context": found.context}


def describe_retrieval(update: Data) -> str:
    items = update.get("context", [])
    kinds = Counter(item["kind"] for item in items)
    parts = ", ".join(f"{count} {kind.replace('_', ' ')}" for kind, count in sorted(kinds.items()))
    words = ", ".join(update.get("keywords", [])[:5])
    return f"{len(items)} context items ({parts or 'none'}); keywords: {words or 'none'}"
