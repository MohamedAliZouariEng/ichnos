"""Build the package that publishes a BRD as a human-verified OKF concept (ADR-0014, ADR-0017).

The payload is built for one approver against the repository's current files; its base records
the branch head and the blob SHA of every file it touches, so approval can detect changes.
"""

import datetime as dt
import re
from collections import defaultdict
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ichnos.api.intake import proposed_path
from ichnos.approvals.service import ApprovalError
from ichnos.db.models import Artifact, ArtifactVersion, Source
from ichnos.github.contents import ContentsReader
from ichnos.okf import parse_document, render_document
from ichnos.workflows.specification import findings_of, index_entries

LINK_TARGET = re.compile(r"\]\(([^)]+)\)")
REQUIREMENT = re.compile(r"^## (R-\d+)\b", re.M)
LOG = "docs/log.md"


def add_index_entry(text: str | None, heading: str | None, entry: str) -> str:
    """Append an index line unless its target is already listed; create the index if needed."""
    if text is None:
        return f"# {heading or 'Index'}\n\n{entry}\n"
    target = LINK_TARGET.search(entry)
    if target and f"]({target.group(1)})" in text:
        return text
    return text.rstrip("\n") + "\n" + entry + "\n"


def add_log_line(text: str, day: str, line: str) -> str:
    """Newest first: under today's heading, or a new heading above the latest one."""
    heading = f"## {day}"
    lines = text.rstrip("\n").splitlines()
    for index, current in enumerate(lines):
        if current.strip() == heading:
            lines.insert(index + 1, line)
            return "\n".join(lines) + "\n"
    for index, current in enumerate(lines):
        if current.startswith("## "):
            lines[index:index] = [heading, line, ""]
            return "\n".join(lines) + "\n"
    return "\n".join([*lines, "", heading, line]) + "\n"


def meeting_note(source: Source, approver: str, at: str) -> str:
    """A source as an OKF Meeting Note; notes that already are OKF concepts stay unchanged."""
    parsed = parse_document("docs/meetings/note.md", source.content)
    if parsed.frontmatter.get("type"):
        return source.content
    frontmatter = {
        "type": "Meeting Note",
        "title": source.title,
        "description": f"Notes captured in Ichnos as source {source.id}.",
        "status": "stable",
        "verified": {"by": approver, "at": at},
        "ichnos": {"source_id": source.id, "sha256": source.content_sha256},
    }
    return render_document(frontmatter, "\n" + source.content.strip() + "\n")


def build_publish(
    session: Session,
    artifact: Artifact,
    *,
    approver: str,
    reader: ContentsReader,
    repository: str,
    base_branch: str,
    now: dt.datetime,
) -> tuple[dict[str, Any], dict[str, Any], str]:
    """(payload, base, summary) for a docs_pull_request that publishes the artifact."""
    version = session.scalar(
        select(ArtifactVersion).where(
            ArtifactVersion.artifact_id == artifact.id,
            ArtifactVersion.number == artifact.current_version,
        )
    )
    if version is None:
        raise ApprovalError(409, "The artifact has no current version.")
    path = f"docs/specs/{artifact.slug}/{artifact.kind}.md"
    errors = sorted(
        {f["code"] for f in findings_of(path, version.content) if f["level"] == "error"}
    )
    if errors:
        raise ApprovalError(409, "Fix the OKF errors before publishing: " + ", ".join(errors))
    head = reader.head(base_branch)
    if head is None:
        raise ApprovalError(400, f"Branch {base_branch} does not exist in {repository}.")

    at = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    parsed = parse_document(path, version.content)
    title = parsed.title or artifact.title
    frontmatter = dict(parsed.frontmatter)
    frontmatter["status"] = "stable"
    frontmatter["verified"] = {"by": approver, "at": at}
    frontmatter["ichnos"] = {
        **(frontmatter.get("ichnos") or {}),
        "artifact_id": artifact.id,
        "run_id": artifact.run_id,
        "requirement_ids": REQUIREMENT.findall(version.content),
    }

    files: dict[str, str] = {}
    base_files: dict[str, str | None] = {}
    known: dict[str, str | None] = {}

    def current(file_path: str) -> str | None:
        if file_path not in known:
            found = reader.file(file_path, base_branch)
            base_files[file_path] = found.sha if found else None
            known[file_path] = found.text if found else None
        return known[file_path]

    current(path)
    files[path] = render_document(frontmatter, parsed.body)

    notes: list[tuple[str, str]] = []
    for source_id in artifact.source_ids or []:
        source = session.get(Source, source_id)
        if source is None or source.kind == "document":
            continue
        note_path = proposed_path(source)
        if note_path:
            current(note_path)
            files[note_path] = meeting_note(source, approver, at)
            notes.append((note_path, source.title))

    entries: dict[str, list[dict[str, str]]] = defaultdict(list)
    for entry in index_entries(path, title, parsed.description or title, notes):
        entries[entry["index"]].append(entry)
    for index_path, items in entries.items():
        text = current(index_path)
        for item in items:
            text = add_index_entry(text, item.get("heading"), item["entry"])
        files[index_path] = text or ""

    log = current(LOG)
    if log is not None:
        line = (
            f"* **Creation**: Added the [{title}](/specs/{artifact.slug}/{artifact.kind}.md) "
            f"BRD, approved by {approver}."
        )
        files[LOG] = add_log_line(log, now.date().isoformat(), line)

    requirement_ids = frontmatter["ichnos"]["requirement_ids"]
    generated_by = (frontmatter.get("generated") or {}).get("by", "unknown")
    body = "\n".join(
        [
            f"Publishes the BRD **{title}** as a human-verified OKF concept.",
            "",
            f"- Requirements: {', '.join(requirement_ids) or 'none'}",
            f"- Artifact: `{artifact.id}`, version {artifact.current_version}",
            "",
            "## Files",
            *[f"- `{file_path}`" for file_path in files],
            "",
            "## AI assistance",
            f"- Agent/framework: Ichnos workflow ({generated_by})",
            f"- Human review: {approver} approved this exact change in Ichnos",
        ]
    )
    payload: dict[str, Any] = {
        "kind": "docs_pull_request",
        "approver": approver,
        "repository": repository,
        "base_branch": base_branch,
        "branch": f"ichnos/{artifact.slug}-v{artifact.current_version}-{artifact.id[:8]}",
        "commit_message": f"docs: publish the {title} BRD",
        "title": f"Publish BRD: {title}",
        "body": body,
        "files": [{"path": file_path, "content": text} for file_path, text in files.items()],
    }
    base: dict[str, Any] = {
        "head_sha": head,
        "files": base_files,
        "artifact_id": artifact.id,
        "artifact_version": artifact.current_version,
    }
    return payload, base, f"Publish BRD: {title}"
