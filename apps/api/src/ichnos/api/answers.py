"""Ask a question, get a grounded answer (ADR-0024); answers are kept in Ichnos."""

import datetime as dt

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from ichnos.answers.answer import draft_answer
from ichnos.answers.retrieve import retrieve_for_question
from ichnos.api.config import NOT_CONFIGURED
from ichnos.api.deps import SessionDep, SettingsDep
from ichnos.api.workspaces import get_workspace_or_404
from ichnos.db.base import as_utc
from ichnos.db.models import StoredAnswer
from ichnos.llm import ModelError, provider_from_settings

router = APIRouter(tags=["answers"])


class QuestionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=3, max_length=500)


class AnswerSourceRead(BaseModel):
    id: str
    kind: str
    title: str
    locator: str
    url: str | None
    trust: str
    flags: list[str]
    excerpt: str


class StatementRead(BaseModel):
    text: str
    cites: list[str]


class TrailLinkRead(BaseModel):
    label: str
    url: str


class AnswerRead(BaseModel):
    id: str
    question: str
    statements: list[StatementRead]
    gaps: list[str]
    cited: list[str]
    sources: list[AnswerSourceRead]
    trail: list[TrailLinkRead]
    model: str
    tokens: int
    created_at: dt.datetime


class AnswerSummary(BaseModel):
    id: str
    question: str
    statements: int
    gaps: int
    created_at: dt.datetime


def _read(row: StoredAnswer) -> AnswerRead:
    data = row.answer or {}
    return AnswerRead(
        id=row.id,
        question=row.question,
        statements=[StatementRead(**s) for s in data.get("statements", [])],
        gaps=list(data.get("gaps", [])),
        cited=list(data.get("cited", [])),
        trail=[TrailLinkRead(**t) for t in data.get("trail", [])],
        sources=[AnswerSourceRead(**s) for s in data.get("sources", [])],
        model=row.model,
        tokens=row.tokens,
        created_at=as_utc(row.created_at),
    )


@router.post(
    "/api/workspaces/{workspace_id}/questions",
    response_model=AnswerRead,
    status_code=status.HTTP_201_CREATED,
    operation_id="askQuestion",
    responses={
        400: {"description": "No model configured"},
        404: {"description": "Workspace not found"},
        502: {"description": "The model failed"},
    },
)
def ask_question(
    workspace_id: str,
    body: QuestionRequest,
    session: SessionDep,
    settings: SettingsDep,
    request: Request,
) -> AnswerRead:
    """Retrieve sources, answer with cited statements and stated gaps, and keep the answer."""
    workspace = get_workspace_or_404(session, workspace_id)
    provider = provider_from_settings(
        settings, model_override=workspace.llm_model, transport=request.app.state.llm_transport
    )
    if provider is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, NOT_CONFIGURED)
    retrieved = retrieve_for_question(session, workspace, body.question)
    try:
        answer, _, usage = draft_answer(provider, retrieved)
    except ModelError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc
    row = StoredAnswer(
        workspace_id=workspace.id,
        question=body.question.strip(),
        answer=answer.model_dump(),
        model=f"ichnos/{provider.model}" if retrieved.sources else "none",
        tokens=int(usage.as_dict().get("total_tokens", 0)),
    )
    session.add(row)
    session.commit()
    return _read(row)


@router.get(
    "/api/workspaces/{workspace_id}/questions",
    response_model=list[AnswerSummary],
    operation_id="listQuestions",
)
def list_questions(workspace_id: str, session: SessionDep) -> list[AnswerSummary]:
    workspace = get_workspace_or_404(session, workspace_id)
    rows = session.scalars(
        select(StoredAnswer)
        .where(StoredAnswer.workspace_id == workspace.id)
        .order_by(StoredAnswer.created_at.desc())
        .limit(20)
    )
    return [
        AnswerSummary(
            id=row.id,
            question=row.question,
            statements=len((row.answer or {}).get("statements", [])),
            gaps=len((row.answer or {}).get("gaps", [])),
            created_at=as_utc(row.created_at),
        )
        for row in rows
    ]


@router.get(
    "/api/answers/{answer_id}",
    response_model=AnswerRead,
    operation_id="getAnswer",
    responses={404: {"description": "Answer not found"}},
)
def get_answer(answer_id: str, session: SessionDep) -> AnswerRead:
    row = session.get(StoredAnswer, answer_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Answer not found.")
    return _read(row)
