"""Metadata tables for workspaces, sync state, runs, approvals and the audit log."""

import datetime as dt
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from ichnos.db.base import Base, new_id, utc_now


class TimestampMixin:
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class Workspace(TimestampMixin, Base):
    """One GitHub repository and branch plus its settings (ADR-0005)."""

    __tablename__ = "workspaces"
    __table_args__ = (UniqueConstraint("repo_owner", "repo_name", "branch"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    repo_owner: Mapped[str] = mapped_column(String(100))
    repo_name: Mapped[str] = mapped_column(String(100))
    branch: Mapped[str] = mapped_column(String(255), default="main")
    index_paths: Mapped[list[str]] = mapped_column(JSON, default=list)
    llm_provider: Mapped[str | None] = mapped_column(String(50))
    llm_model: Mapped[str | None] = mapped_column(String(200))
    embedding_provider: Mapped[str | None] = mapped_column(String(50))
    embedding_model: Mapped[str | None] = mapped_column(String(200))


class SyncCursor(Base):
    """Incremental sync position per workspace and source (FR-2)."""

    __tablename__ = "sync_cursors"
    __table_args__ = (UniqueConstraint("workspace_id", "source"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    source: Mapped[str] = mapped_column(String(50))
    cursor: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class Run(TimestampMixin, Base):
    """One execution of a workflow (FR-14)."""

    __tablename__ = "runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    workflow_type: Mapped[str] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(String(20), default="pending")
    stage: Mapped[str | None] = mapped_column(String(50))
    inputs: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    outputs: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    error: Mapped[str | None] = mapped_column(Text)
    finished_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))


class Approval(Base):
    """A pending GitHub write and the human decision on it (FR-6, ADR-0015)."""

    __tablename__ = "approvals"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), index=True)
    action_type: Mapped[str] = mapped_column(String(50))
    target: Mapped[str] = mapped_column(String(500))  # owner/name
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    payload_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(20), default="pending")
    decided_by: Mapped[str | None] = mapped_column(String(100))
    decided_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    # Phase 4 (ADR-0015): where the write goes, what it was built on, what it did.
    workspace_id: Mapped[str | None] = mapped_column(String(36), index=True)
    artifact_id: Mapped[str | None] = mapped_column(String(36), index=True)
    branch: Mapped[str | None] = mapped_column(String(200))
    summary: Mapped[str | None] = mapped_column(String(300))
    base: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    proposed_by: Mapped[str | None] = mapped_column(String(100))
    decision_note: Mapped[str | None] = mapped_column(Text)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    error: Mapped[str | None] = mapped_column(Text)
    executed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))


class AuditEvent(Base):
    """Append-only record of significant actions. No foreign keys, so events outlive rows."""

    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    occurred_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, index=True
    )
    actor: Mapped[str] = mapped_column(String(100))
    event_type: Mapped[str] = mapped_column(String(50), index=True)
    workspace_id: Mapped[str | None] = mapped_column(String(36))
    run_id: Mapped[str | None] = mapped_column(String(36))
    approval_id: Mapped[str | None] = mapped_column(String(36))
    details: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


# ---- Knowledge: derived from GitHub and rebuildable at any time (ADR-0002) ----


def _workspace_fk() -> Mapped[str]:
    return mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), index=True)


class Document(Base):
    """A repository file parsed as OKF (ADR-0001)."""

    __tablename__ = "documents"
    __table_args__ = (UniqueConstraint("workspace_id", "path"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace_id: Mapped[str] = _workspace_fk()
    path: Mapped[str] = mapped_column(String(500))
    blob_sha: Mapped[str] = mapped_column(String(40))
    commit_sha: Mapped[str] = mapped_column(String(40))
    kind: Mapped[str] = mapped_column(String(20))
    concept_id: Mapped[str | None] = mapped_column(String(500))
    doc_type: Mapped[str | None] = mapped_column(String(100))
    title: Mapped[str | None] = mapped_column(String(500))
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str | None] = mapped_column(String(20))
    trust_tier: Mapped[str] = mapped_column(String(20))
    frontmatter: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    body: Mapped[str] = mapped_column(Text)
    findings: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    synced_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class GitHubItem(Base):
    """An Issue or pull request; they share one number space on GitHub."""

    __tablename__ = "github_items"
    __table_args__ = (UniqueConstraint("workspace_id", "number"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace_id: Mapped[str] = _workspace_fk()
    number: Mapped[int] = mapped_column(Integer)
    item_type: Mapped[str] = mapped_column(String(20))
    github_id: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(1000))
    body: Mapped[str | None] = mapped_column(Text)
    state: Mapped[str] = mapped_column(String(20))
    state_reason: Mapped[str | None] = mapped_column(String(30))
    author: Mapped[str | None] = mapped_column(String(100))
    labels: Mapped[list[str]] = mapped_column(JSON, default=list)
    milestone: Mapped[str | None] = mapped_column(String(200))
    url: Mapped[str] = mapped_column(String(500))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    merged_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    draft: Mapped[bool | None] = mapped_column(Boolean)
    head_ref: Mapped[str | None] = mapped_column(String(255))
    base_ref: Mapped[str | None] = mapped_column(String(255))
    head_sha: Mapped[str | None] = mapped_column(String(40))


class GitHubComment(Base):
    """An Issue comment, a pull request review, or a review comment."""

    __tablename__ = "github_comments"
    __table_args__ = (UniqueConstraint("workspace_id", "kind", "github_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace_id: Mapped[str] = _workspace_fk()
    github_id: Mapped[int] = mapped_column(Integer)
    item_number: Mapped[int] = mapped_column(Integer, index=True)
    kind: Mapped[str] = mapped_column(String(20))
    author: Mapped[str | None] = mapped_column(String(100))
    body: Mapped[str] = mapped_column(Text)
    review_state: Mapped[str | None] = mapped_column(String(30))
    path: Mapped[str | None] = mapped_column(String(500))
    url: Mapped[str] = mapped_column(String(500))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))


class Commit(Base):
    """A commit on the workspace branch or in a pull request."""

    __tablename__ = "commits"
    __table_args__ = (UniqueConstraint("workspace_id", "sha"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace_id: Mapped[str] = _workspace_fk()
    sha: Mapped[str] = mapped_column(String(40))
    message: Mapped[str] = mapped_column(Text)
    author_name: Mapped[str | None] = mapped_column(String(200))
    author_login: Mapped[str | None] = mapped_column(String(100))
    authored_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    url: Mapped[str] = mapped_column(String(500))


class PullRequestFile(Base):
    """A file changed by a pull request."""

    __tablename__ = "pull_request_files"
    __table_args__ = (UniqueConstraint("workspace_id", "pr_number", "path"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace_id: Mapped[str] = _workspace_fk()
    pr_number: Mapped[int] = mapped_column(Integer)
    path: Mapped[str] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(20))
    additions: Mapped[int] = mapped_column(Integer, default=0)
    deletions: Mapped[int] = mapped_column(Integer, default=0)
    previous_path: Mapped[str | None] = mapped_column(String(500))


class PullRequestCommit(Base):
    """Membership of a commit in a pull request."""

    __tablename__ = "pull_request_commits"
    __table_args__ = (UniqueConstraint("workspace_id", "pr_number", "sha"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace_id: Mapped[str] = _workspace_fk()
    pr_number: Mapped[int] = mapped_column(Integer)
    sha: Mapped[str] = mapped_column(String(40))


class Link(Base):
    """A relationship with its origin, evidence and confidence (ADR-0010)."""

    __tablename__ = "links"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "source_kind",
            "source_key",
            "target_kind",
            "target_key",
            "relation",
            "origin",
        ),
        Index("ix_links_target", "workspace_id", "target_kind", "target_key"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace_id: Mapped[str] = _workspace_fk()
    source_kind: Mapped[str] = mapped_column(String(20))
    source_key: Mapped[str] = mapped_column(String(500))
    target_kind: Mapped[str] = mapped_column(String(20))
    target_key: Mapped[str] = mapped_column(String(500))
    relation: Mapped[str] = mapped_column(String(20))
    origin: Mapped[str] = mapped_column(String(10))
    evidence: Mapped[str] = mapped_column(Text)
    confidence: Mapped[float] = mapped_column(Float)
    resolved: Mapped[bool] = mapped_column(Boolean, default=False)
    extracted_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class Chunk(Base):
    """A heading-sized piece of text, indexed by the chunks_fts FTS5 table (ADR-0008)."""

    __tablename__ = "chunks"
    __table_args__ = (Index("ix_chunks_source", "workspace_id", "source_kind", "source_key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace_id: Mapped[str] = _workspace_fk()
    source_kind: Mapped[str] = mapped_column(String(20))
    source_key: Mapped[str] = mapped_column(String(500))
    ordinal: Mapped[int] = mapped_column(Integer)
    heading: Mapped[str | None] = mapped_column(String(500))
    text: Mapped[str] = mapped_column(Text)
    start_line: Mapped[int | None] = mapped_column(Integer)


# ---- Requirements workflow: operational data, never touched by a knowledge reset (ADR-0014) ----


class Source(Base):
    """An immutable intake record: pasted text, an uploaded file or a synced document."""

    __tablename__ = "sources"
    __table_args__ = (Index("ix_sources_content", "workspace_id", "content_sha256"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = _workspace_fk()
    kind: Mapped[str] = mapped_column(String(20))  # pasted, upload or document
    title: Mapped[str] = mapped_column(String(300))
    filename: Mapped[str | None] = mapped_column(String(300))
    document_path: Mapped[str | None] = mapped_column(String(500))
    commit_sha: Mapped[str | None] = mapped_column(String(40))
    media_type: Mapped[str] = mapped_column(String(50), default="text/markdown")
    content: Mapped[str] = mapped_column(Text)
    content_sha256: Mapped[str] = mapped_column(String(64))
    created_by: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class Artifact(TimestampMixin, Base):
    """A generated deliverable such as a BRD, reviewed before it reaches the repository."""

    __tablename__ = "artifacts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = _workspace_fk()
    kind: Mapped[str] = mapped_column(String(30))  # brd
    title: Mapped[str] = mapped_column(String(300))
    slug: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(20), default="draft")
    run_id: Mapped[str | None] = mapped_column(ForeignKey("runs.id", ondelete="SET NULL"))
    source_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    current_version: Mapped[int] = mapped_column(Integer, default=0)


class ArtifactVersion(Base):
    """One append-only version of an artifact's Markdown."""

    __tablename__ = "artifact_versions"
    __table_args__ = (UniqueConstraint("artifact_id", "number"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    artifact_id: Mapped[str] = mapped_column(
        ForeignKey("artifacts.id", ondelete="CASCADE"), index=True
    )
    number: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
    origin: Mapped[str] = mapped_column(String(20))  # generated or edited
    actor: Mapped[str] = mapped_column(String(100))
    parent_number: Mapped[int | None] = mapped_column(Integer)
    findings: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class RunEvent(Base):
    """One entry in a run's event log; its id is the Server-Sent Events id (ADR-0013)."""

    __tablename__ = "run_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), index=True)
    stage: Mapped[str | None] = mapped_column(String(50))
    kind: Mapped[str] = mapped_column(String(30))
    message: Mapped[str] = mapped_column(Text)
    data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
