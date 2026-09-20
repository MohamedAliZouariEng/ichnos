"""Repository files outside the documentation bundle (ADR-0019).

Recorded from the tree the documents stage already fetched: path, blob SHA, size and language.
Contents are never stored; context packs fetch the few files they select.
"""

from collections.abc import Iterable
from pathlib import PurePosixPath

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ichnos.db.models import RepositoryFile, Workspace
from ichnos.github.reader import TreeEntry

FILES_CURSOR = "files:commit"
LANGUAGES = {
    ".py": "Python",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".js": "JavaScript",
    ".jsx": "JavaScript",
    ".go": "Go",
    ".rs": "Rust",
    ".java": "Java",
    ".kt": "Kotlin",
    ".rb": "Ruby",
    ".php": "PHP",
    ".cs": "C#",
    ".sql": "SQL",
    ".sh": "Shell",
    ".css": "CSS",
    ".html": "HTML",
    ".toml": "TOML",
    ".yaml": "YAML",
    ".yml": "YAML",
    ".json": "JSON",
    ".md": "Markdown",
}
NAMES = {"Dockerfile": "Dockerfile", "Makefile": "Makefile"}


def language_of(path: str) -> str | None:
    file = PurePosixPath(path)
    return NAMES.get(file.name) or LANGUAGES.get(file.suffix.lower())


def in_bundle(path: str, index_paths: list[str]) -> bool:
    """Everything under an index path belongs to the documents stage."""
    for prefix in index_paths:
        clean = prefix.strip().strip("/")
        if clean and (path == clean or path.startswith(f"{clean}/")):
            return True
    return False


def count_files(session: Session, workspace_id: str) -> int:
    total = session.scalar(
        select(func.count())
        .select_from(RepositoryFile)
        .where(RepositoryFile.workspace_id == workspace_id)
    )
    return total or 0


def record_files(
    session: Session, workspace: Workspace, head: str, entries: Iterable[TreeEntry]
) -> dict[str, int]:
    """Upsert files outside the bundle by blob SHA; delete the ones that disappeared."""
    counts = {"files_added": 0, "files_updated": 0, "files_deleted": 0, "files_unchanged": 0}
    existing = {
        file.path: file
        for file in session.scalars(
            select(RepositoryFile).where(RepositoryFile.workspace_id == workspace.id)
        )
    }
    seen: set[str] = set()
    for entry in entries:
        if in_bundle(entry.path, workspace.index_paths):
            continue
        seen.add(entry.path)
        current = existing.get(entry.path)
        if current is not None and current.blob_sha == entry.sha:
            counts["files_unchanged"] += 1
            continue
        if current is None:
            current = RepositoryFile(workspace_id=workspace.id, path=entry.path)
            session.add(current)
            counts["files_added"] += 1
        else:
            counts["files_updated"] += 1
        current.blob_sha = entry.sha
        current.commit_sha = head
        current.size = entry.size
        current.language = language_of(entry.path)
    for path, file in existing.items():
        if path not in seen:
            session.delete(file)
            counts["files_deleted"] += 1
    return counts
