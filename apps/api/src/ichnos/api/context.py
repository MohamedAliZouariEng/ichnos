"""A Story's context pack (ADR-0019), built on request from synced knowledge."""

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request, status
from pydantic import BaseModel

from ichnos.api.deps import SessionDep, SettingsDep
from ichnos.api.workspaces import get_workspace_or_404
from ichnos.context.code import pack_with_code
from ichnos.context.pack import PackError
from ichnos.github.contents import ContentsError

__all__ = ["pack_with_code", "router"]

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
    try:
        pack, notes = pack_with_code(
            session,
            workspace,
            number,
            settings.github_token,
            request.app.state.github_transport,
            code=code,
        )
    except PackError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except ContentsError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc
    data = pack.as_dict()
    data["notes"] = [*data["notes"], *notes]
    return ContextPackRead.model_validate(data)
