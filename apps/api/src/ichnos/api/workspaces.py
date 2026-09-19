"""Workspace configuration: one repository and branch per workspace (ADR-0005)."""

import datetime as dt
from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ichnos.api.deps import GitHubDep, SessionDep
from ichnos.db.base import new_id
from ichnos.db.models import AuditEvent, Workspace
from ichnos.github.client import GitHubAccess

router = APIRouter(prefix="/api/workspaces", tags=["workspaces"])

# Until authentication arrives (Phase 4), local actions use this OKF-style actor.
LOCAL_ACTOR = "human:local"
REPOSITORY_PATTERN = r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})/[A-Za-z0-9._-]{1,100}$"
CLEARABLE_FIELDS = {"llm_provider", "llm_model", "embedding_provider", "embedding_model"}
NOT_FOUND: dict[int | str, dict[str, Any]] = {404: {"description": "Workspace not found"}}
CONFLICT: dict[int | str, dict[str, Any]] = {
    409: {"description": "Name or repository and branch already used"}
}


def _check_paths(paths: list[str]) -> list[str]:
    for path in paths:
        if not path.strip() or path.startswith("/") or ".." in path.split("/"):
            raise ValueError(f"index paths must be relative and inside the repository: {path!r}")
    return paths


class WorkspaceFields(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    repository: str = Field(pattern=REPOSITORY_PATTERN, examples=["octo-org/demo"])
    branch: str = Field(default="main", min_length=1, max_length=255)
    index_paths: list[str] = Field(default_factory=lambda: ["docs/", ".github/"])
    llm_provider: str | None = Field(default=None, max_length=50)
    llm_model: str | None = Field(default=None, max_length=200)
    embedding_provider: str | None = Field(default=None, max_length=50)
    embedding_model: str | None = Field(default=None, max_length=200)


class WorkspaceCreate(WorkspaceFields):
    model_config = ConfigDict(extra="forbid")

    @field_validator("index_paths")
    @classmethod
    def _relative_paths(cls, paths: list[str]) -> list[str]:
        return _check_paths(paths)


class WorkspaceUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=100)
    repository: str | None = Field(default=None, pattern=REPOSITORY_PATTERN)
    branch: str | None = Field(default=None, min_length=1, max_length=255)
    index_paths: list[str] | None = None
    llm_provider: str | None = Field(default=None, max_length=50)
    llm_model: str | None = Field(default=None, max_length=200)
    embedding_provider: str | None = Field(default=None, max_length=50)
    embedding_model: str | None = Field(default=None, max_length=200)

    @field_validator("index_paths")
    @classmethod
    def _relative_paths(cls, paths: list[str] | None) -> list[str] | None:
        return None if paths is None else _check_paths(paths)


class WorkspaceRead(WorkspaceFields):
    id: str
    created_at: dt.datetime
    updated_at: dt.datetime


def _to_read(workspace: Workspace) -> WorkspaceRead:
    return WorkspaceRead(
        id=workspace.id,
        name=workspace.name,
        repository=f"{workspace.repo_owner}/{workspace.repo_name}",
        branch=workspace.branch,
        index_paths=list(workspace.index_paths),
        llm_provider=workspace.llm_provider,
        llm_model=workspace.llm_model,
        embedding_provider=workspace.embedding_provider,
        embedding_model=workspace.embedding_model,
        created_at=workspace.created_at,
        updated_at=workspace.updated_at,
    )


def get_workspace_or_404(session: Session, workspace_id: str) -> Workspace:
    workspace = session.get(Workspace, workspace_id)
    if workspace is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Workspace not found")
    return workspace


def _commit_or_409(session: Session) -> None:
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "A workspace with this name, or this repository and branch, already exists.",
        ) from exc


@router.get("", response_model=list[WorkspaceRead], operation_id="listWorkspaces")
def list_workspaces(session: SessionDep) -> list[WorkspaceRead]:
    rows = session.scalars(select(Workspace).order_by(Workspace.created_at)).all()
    return [_to_read(row) for row in rows]


@router.post(
    "",
    response_model=WorkspaceRead,
    status_code=status.HTTP_201_CREATED,
    operation_id="createWorkspace",
    responses=CONFLICT,
)
def create_workspace(body: WorkspaceCreate, session: SessionDep) -> WorkspaceRead:
    owner, repo = body.repository.split("/", 1)
    workspace = Workspace(
        id=new_id(),
        name=body.name,
        repo_owner=owner,
        repo_name=repo,
        branch=body.branch,
        index_paths=body.index_paths,
        llm_provider=body.llm_provider,
        llm_model=body.llm_model,
        embedding_provider=body.embedding_provider,
        embedding_model=body.embedding_model,
    )
    session.add(workspace)
    session.add(
        AuditEvent(
            actor=LOCAL_ACTOR,
            event_type="workspace.created",
            workspace_id=workspace.id,
            details={"repository": body.repository, "branch": body.branch},
        )
    )
    _commit_or_409(session)
    return _to_read(workspace)


@router.get(
    "/{workspace_id}",
    response_model=WorkspaceRead,
    operation_id="getWorkspace",
    responses=NOT_FOUND,
)
def get_workspace(workspace_id: str, session: SessionDep) -> WorkspaceRead:
    return _to_read(get_workspace_or_404(session, workspace_id))


@router.patch(
    "/{workspace_id}",
    response_model=WorkspaceRead,
    operation_id="updateWorkspace",
    responses={**NOT_FOUND, **CONFLICT},
)
def update_workspace(
    workspace_id: str, body: WorkspaceUpdate, session: SessionDep
) -> WorkspaceRead:
    workspace = get_workspace_or_404(session, workspace_id)
    changes = {
        field: value
        for field, value in body.model_dump(exclude_unset=True).items()
        if value is not None or field in CLEARABLE_FIELDS
    }
    repository = changes.pop("repository", None)
    if repository is not None:
        workspace.repo_owner, workspace.repo_name = repository.split("/", 1)
    for field, value in changes.items():
        setattr(workspace, field, value)
    session.add(
        AuditEvent(
            actor=LOCAL_ACTOR,
            event_type="workspace.updated",
            workspace_id=workspace.id,
            details={"fields": sorted(body.model_fields_set)},
        )
    )
    _commit_or_409(session)
    return _to_read(workspace)


@router.post(
    "/{workspace_id}/github-check",
    response_model=GitHubAccess,
    operation_id="checkWorkspaceGitHubAccess",
    responses=NOT_FOUND,
)
def check_github_access(workspace_id: str, session: SessionDep, github: GitHubDep) -> GitHubAccess:
    workspace = get_workspace_or_404(session, workspace_id)
    return github.check_access(workspace.repo_owner, workspace.repo_name, workspace.branch)
