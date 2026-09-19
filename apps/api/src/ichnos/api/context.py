"""A Story's context pack (ADR-0019), built on request from synced knowledge."""

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request, status
from pydantic import BaseModel
from sqlalchemy import select

from ichnos.api.deps import SessionDep, SettingsDep
from ichnos.api.workspaces import get_workspace_or_404
from ichnos.context.pack import ContextPack, PackError, build_pack
from ichnos.db.models import RepositoryFile
from ichnos.github.contents import ContentsError, ContentsReader

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
    token = settings.github_token
    notes: list[str] = []
    if code and (token is None or not token.get_secret_value()):
        notes.append("Code contents were not fetched: no GitHub token is configured.")
    try:
        if code and token is not None and token.get_secret_value():
            files = {
                f.blob_sha: (f.path, f.commit_sha)
                for f in session.scalars(
                    select(RepositoryFile).where(RepositoryFile.workspace_id == workspace.id)
                )
            }
            repository = f"{workspace.repo_owner}/{workspace.repo_name}"
            with ContentsReader(repository, token, request.app.state.github_transport) as reader:

                def fetch(blob_sha: str) -> str:
                    path, commit = files[blob_sha]
                    found = reader.file(path, commit)
                    return found.text if found else ""

                pack = build_pack(session, workspace, number, fetch=fetch)
        else:
            pack = build_pack(session, workspace, number)
    except PackError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except ContentsError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc
    return _read(pack, notes)


def _read(pack: ContextPack, notes: list[str]) -> ContextPackRead:
    data = pack.as_dict()
    data["notes"] = [*data["notes"], *notes]
    return ContextPackRead.model_validate(data)
