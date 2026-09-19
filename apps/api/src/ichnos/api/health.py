"""Liveness and dependency check used by Docker health checks and the web shell."""

from typing import Literal

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel
from sqlalchemy import Engine, text
from sqlalchemy.exc import SQLAlchemyError

from ichnos import __version__

router = APIRouter(tags=["health"])

HealthState = Literal["ok", "degraded"]
DatabaseState = Literal["ok", "unavailable"]


class Health(BaseModel):
    status: HealthState
    version: str
    database: DatabaseState
    search: DatabaseState


@router.get(
    "/healthz",
    response_model=Health,
    operation_id="getHealth",
    responses={503: {"model": Health, "description": "A dependency is unavailable"}},
)
def get_health(request: Request, response: Response) -> Health:
    engine: Engine = request.app.state.engine
    database: DatabaseState = "ok"
    search: DatabaseState = "ok"
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
            try:  # the FTS5 index exists and is readable (ADR-0008)
                connection.execute(text("SELECT 1 FROM chunks_fts LIMIT 1"))
            except SQLAlchemyError:
                search = "unavailable"
    except SQLAlchemyError:
        database = "unavailable"
        search = "unavailable"
    healthy = database == "ok" and search == "ok"
    status: HealthState = "ok" if healthy else "degraded"
    if status != "ok":
        response.status_code = 503
    return Health(status=status, version=__version__, database=database, search=search)
