"""A Story's context pack (ADR-0019), built on request from synced knowledge."""

from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query, Request, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ichnos.api.deps import SessionDep, SettingsDep
from ichnos.api.workspaces import get_workspace_or_404
from ichnos.context.pack import ContextPack, PackError, build_pack
from ichnos.db.models import RepositoryFile, Workspace
from ichnos.github.contents import ContentsError, ContentsReader
from ichnos.settings import Settings

router = APIRouter(tags=["context"])


class PackItemRead(BaseModel):
    id: str
    role: str
    title: str
    source: str
    url: str | None
    trust: str
    flags: list[str]
    reason: str
    excerpt: str


class ContextPackRead(BaseModel):
    story: int
    items: list[PackItemRead]
    absent: list[str]
    keywords: list[str]
    hash: str
    notes: list[str]


def pack_with_code(
    session: Session,
    workspace: Workspace,
    number: int,
    settings: Settings,
    transport: Any,
    *,
    code: bool = True,
) -> tuple[ContextPack, list[str]]:
    """Build the pack; code files are read at the commit the sync recorded. Raises PackError."""
    token = settings.github_token
    has_token = token is not None and bool(token.get_secret_value())
    notes: list[str] = []
    if code and not has_token:
        notes.append("Code contents were not fetched: no GitHub token is configured.")
    if not code or not has_token or token is None:
        return build_pack(session, workspace, number), notes
    files = {
        f.blob_sha: (f.path, f.commit_sha)
        for f in session.scalars(
            select(RepositoryFile).where(RepositoryFile.workspace_id == workspace.id)
        )
    }
    repository = f"{workspace.repo_owner}/{workspace.repo_name}"
    with ContentsReader(repository, token, transport) as reader:

        def fetch(blob_sha: str) -> str:
            path, commit = files[blob_sha]
            found = reader.file(path, commit)
            return found.text if found else ""

        return build_pack(session, workspace, number, fetch=fetch), notes


@router.get(
    "/api/workspaces/{workspace_id}/stories/{number}/context",
    response_model=ContextPackRead,
    operation_id="getContextPack",
    responses={
        404: {"description": "Workspace or Issue not found"},
        502: {"description": "GitHub could not be read"},
    },
)
def get_context_pack(
    workspace_id: str,
    number: int,
    session: SessionDep,
    settings: SettingsDep,
    request: Request,
    code: Annotated[bool, Query(description="Fetch the selected code files' contents")] = True,
) -> ContextPackRead:
    """Everything needed to implement one Story, with provenance and trust on every item."""
    workspace = get_workspace_or_404(session, workspace_id)
    try:
        pack, notes = pack_with_code(
            session, workspace, number, settings, request.app.state.github_transport, code=code
        )
    except PackError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except ContentsError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc
    data = pack.as_dict()
    data["notes"] = [*data["notes"], *notes]
    return ContextPackRead.model_validate(data)
