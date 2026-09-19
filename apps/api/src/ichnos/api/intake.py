"""Intake: immutable sources from pasted text, uploaded files or synced documents (ADR-0014)."""

import datetime as dt
import hashlib
import re
from typing import Annotated, Literal, Self

from fastapi import APIRouter, HTTPException, Query, Response, status
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from ichnos.api.deps import SessionDep
from ichnos.api.workspaces import LOCAL_ACTOR, NOT_FOUND, get_workspace_or_404
from ichnos.db.base import as_utc
from ichnos.db.models import AuditEvent, Document, Source
from ichnos.okf import parse_document, render_document

router = APIRouter(prefix="/api/workspaces/{workspace_id}/sources", tags=["intake"])

MAX_CHARS = 200_000
UPLOAD_TYPES = {".md": "text/markdown", ".markdown": "text/markdown", ".txt": "text/plain"}
SLUG_RE = re.compile(r"[^a-z0-9]+")


def slugify(text: str, limit: int = 60) -> str:
    slug = SLUG_RE.sub("-", text.lower()).strip("-")
    cut = slug[:limit]
    if len(slug) > limit and slug[limit] != "-" and "-" in cut:
        cut = cut.rsplit("-", 1)[0]  # never end on half a word
    return cut.strip("-") or "note"


def derive_title(content: str) -> str:
    """Frontmatter title, else the first heading, else the first non-empty line."""
    parsed = parse_document("docs/meetings/note.md", content)
    if parsed.title:
        return parsed.title[:300]
    for line in content.splitlines():
        if line.strip():
            return line.strip().lstrip("#").strip()[:80] or "Untitled note"
    return "Untitled note"


class SourceCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["pasted", "upload"] = "pasted"
    title: str | None = Field(default=None, max_length=300)
    filename: str | None = Field(default=None, max_length=300)
    content: str = Field(min_length=1, max_length=MAX_CHARS)

    @model_validator(mode="after")
    def _check(self) -> Self:
        if not self.content.strip():
            raise ValueError("content must not be empty")
        if self.kind == "upload" and not (
            self.filename and self.filename.lower().endswith(tuple(UPLOAD_TYPES))
        ):
            raise ValueError("uploads must be .md, .markdown or .txt files")
        return self


class DocumentSourceCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str = Field(min_length=1, max_length=500)


class SourceRead(BaseModel):
    id: str
    kind: str
    title: str
    filename: str | None
    document_path: str | None
    commit_sha: str | None
    media_type: str
    content_sha256: str
    size: int
    created_by: str
    created_at: dt.datetime
    proposed_path: str | None
    content: str | None = None
    reused: bool = False


def proposed_path(source: Source) -> str | None:
    """Where Phase 4 will write a pasted or uploaded note as an OKF meeting note."""
    if source.kind == "document":
        return None
    day = as_utc(source.created_at).date().isoformat()
    return f"docs/meetings/{day}-{slugify(source.title)}.md"


def _read(source: Source, *, with_content: bool, reused: bool = False) -> SourceRead:
    return SourceRead(
        id=source.id,
        kind=source.kind,
        title=source.title,
        filename=source.filename,
        document_path=source.document_path,
        commit_sha=source.commit_sha,
        media_type=source.media_type,
        content_sha256=source.content_sha256,
        size=len(source.content),
        created_by=source.created_by,
        created_at=as_utc(source.created_at),
        proposed_path=proposed_path(source),
        content=source.content if with_content else None,
        reused=reused,
    )


def _store(
    session: Session,
    workspace_id: str,
    *,
    kind: str,
    title: str,
    content: str,
    media_type: str,
    filename: str | None = None,
    document_path: str | None = None,
    commit_sha: str | None = None,
) -> tuple[Source, bool]:
    """Create a source, or return the existing one with identical content and kind."""
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
    existing = session.scalar(
        select(Source).where(
            Source.workspace_id == workspace_id,
            Source.content_sha256 == digest,
            Source.kind == kind,
        )
    )
    if existing is not None:
        return existing, True
    source = Source(
        workspace_id=workspace_id,
        kind=kind,
        title=title,
        filename=filename,
        document_path=document_path,
        commit_sha=commit_sha,
        media_type=media_type,
        content=content,
        content_sha256=digest,
        created_by=LOCAL_ACTOR,
    )
    session.add(source)
    session.flush()
    session.add(
        AuditEvent(
            actor=LOCAL_ACTOR,
            event_type="source.created",
            workspace_id=workspace_id,
            details={"source_id": source.id, "kind": kind, "sha256": digest},
        )
    )
    session.commit()
    return source, False


CREATED = {**NOT_FOUND, 200: {"description": "Identical content already exists; returned as is"}}


@router.post(
    "",
    response_model=SourceRead,
    status_code=status.HTTP_201_CREATED,
    operation_id="createSource",
    responses=CREATED,
)
def create_source(
    workspace_id: str, body: SourceCreate, session: SessionDep, response: Response
) -> SourceRead:
    """Pasted text or an uploaded file's text becomes an immutable source."""
    get_workspace_or_404(session, workspace_id)
    media_type = "text/markdown"
    if body.kind == "upload" and body.filename:
        extension = "." + body.filename.lower().rsplit(".", 1)[-1]
        media_type = UPLOAD_TYPES[extension]
    source, reused = _store(
        session,
        workspace_id,
        kind=body.kind,
        title=body.title or derive_title(body.content),
        content=body.content,
        media_type=media_type,
        filename=body.filename,
    )
    if reused:
        response.status_code = status.HTTP_200_OK
    return _read(source, with_content=True, reused=reused)


@router.post(
    "/from-document",
    response_model=SourceRead,
    status_code=status.HTTP_201_CREATED,
    operation_id="createSourceFromDocument",
    responses={**CREATED, 404: {"description": "Workspace or document not found"}},
)
def create_source_from_document(
    workspace_id: str, body: DocumentSourceCreate, session: SessionDep, response: Response
) -> SourceRead:
    """A synced repository document becomes a source, pinned to the commit it was read from."""
    get_workspace_or_404(session, workspace_id)
    doc = session.scalar(
        select(Document).where(Document.workspace_id == workspace_id, Document.path == body.path)
    )
    if doc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not synced; sync the workspace")
    source, reused = _store(
        session,
        workspace_id,
        kind="document",
        title=doc.title or doc.path,
        content=render_document(doc.frontmatter or {}, doc.body),
        media_type="text/markdown",
        document_path=doc.path,
        commit_sha=doc.commit_sha,
    )
    if reused:
        response.status_code = status.HTTP_200_OK
    return _read(source, with_content=True, reused=reused)


@router.get("", response_model=list[SourceRead], operation_id="listSources", responses=NOT_FOUND)
def list_sources(
    workspace_id: str,
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[SourceRead]:
    get_workspace_or_404(session, workspace_id)
    sources = session.scalars(
        select(Source)
        .where(Source.workspace_id == workspace_id)
        .order_by(Source.created_at.desc())
        .limit(limit)
    ).all()
    return [_read(source, with_content=False) for source in sources]


@router.get(
    "/{source_id}",
    response_model=SourceRead,
    operation_id="getSource",
    responses={404: {"description": "Workspace or source not found"}},
)
def get_source(workspace_id: str, source_id: str, session: SessionDep) -> SourceRead:
    get_workspace_or_404(session, workspace_id)
    source = session.get(Source, source_id)
    if source is None or source.workspace_id != workspace_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Source not found")
    return _read(source, with_content=True)
