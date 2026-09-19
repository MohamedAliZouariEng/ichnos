"""Documents stage: repository files into the documents table (ADR-0009)."""

import datetime as dt
from dataclasses import asdict
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ichnos.db.models import Document, Workspace
from ichnos.github.reader import GitHubReader
from ichnos.okf import ParsedDocument, parse_document
from ichnos.sync.cursors import get_cursor, set_cursor
from ichnos.sync.files import FILES_CURSOR, count_files, record_files

BUNDLE_ROOT = "docs"
TEXT_EXTENSIONS = (".md", ".txt")
MAX_FILE_BYTES = 1_000_000
CURSOR = "documents:commit"


def jsonable(value: Any) -> Any:
    """Make YAML values JSON-safe: dates and datetimes become ISO 8601 strings."""
    if isinstance(value, dt.date):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): jsonable(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [jsonable(item) for item in value]
    return value


def selected(path: str, index_paths: list[str]) -> bool:
    """Is this repository path a text file under one of the workspace's index paths?"""
    if not path.endswith(TEXT_EXTENSIONS):
        return False
    for prefix in index_paths:
        clean = prefix.strip().strip("/")
        if clean and (path == clean or path.startswith(f"{clean}/")):
            return True
    return False


def _apply(doc: Document, parsed: ParsedDocument, blob_sha: str, commit_sha: str) -> None:
    doc.blob_sha = blob_sha
    doc.commit_sha = commit_sha
    doc.kind = parsed.kind
    doc.concept_id = parsed.concept_id
    doc.doc_type = parsed.type
    doc.title = parsed.title
    doc.description = parsed.description
    doc.status = parsed.status
    doc.trust_tier = parsed.trust_tier
    doc.frontmatter = jsonable(parsed.frontmatter)
    doc.body = parsed.body
    doc.findings = [asdict(finding) for finding in parsed.findings]


def sync_documents(session: Session, reader: GitHubReader, workspace: Workspace) -> dict[str, int]:
    owner, repo = workspace.repo_owner, workspace.repo_name
    counts = {
        "documents_added": 0,
        "documents_updated": 0,
        "documents_deleted": 0,
        "documents_unchanged": 0,
        "documents_skipped": 0,
    }
    head = reader.branch_head(owner, repo, workspace.branch)
    files_current = get_cursor(session, workspace.id, FILES_CURSOR) == head
    if get_cursor(session, workspace.id, CURSOR) == head and files_current:
        total = session.scalar(
            select(func.count()).select_from(Document).where(Document.workspace_id == workspace.id)
        )
        counts["documents_unchanged"] = total or 0
        counts["files_unchanged"] = count_files(session, workspace.id)
        return counts

    existing = {
        doc.path: doc
        for doc in session.scalars(select(Document).where(Document.workspace_id == workspace.id))
    }
    seen: set[str] = set()
    entries = reader.tree(owner, repo, head)
    for entry in entries:
        if not selected(entry.path, workspace.index_paths):
            continue
        seen.add(entry.path)
        current = existing.get(entry.path)
        if current is not None and current.blob_sha == entry.sha:
            counts["documents_unchanged"] += 1
            continue
        if entry.size is not None and entry.size > MAX_FILE_BYTES:
            counts["documents_skipped"] += 1
            continue
        parsed = parse_document(entry.path, reader.blob_text(owner, repo, entry.sha), BUNDLE_ROOT)
        if current is None:
            current = Document(workspace_id=workspace.id, path=entry.path)
            session.add(current)
            counts["documents_added"] += 1
        else:
            counts["documents_updated"] += 1
        _apply(current, parsed, entry.sha, head)

    for path, doc in existing.items():
        if path not in seen:
            session.delete(doc)
            counts["documents_deleted"] += 1

    counts.update(record_files(session, workspace, head, entries))
    set_cursor(session, workspace.id, CURSOR, head)
    set_cursor(session, workspace.id, FILES_CURSOR, head)
    return counts
