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


@router.get(
    "/healthz",
    response_model=Health,
    operation_id="getHealth",
    responses={503: {"model": Health, "description": "A dependency is unavailable"}},
)
def get_health(request: Request, response: Response) -> Health:
    engine: Engine = request.app.state.engine
    database: DatabaseState = "ok"
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except SQLAlchemyError:
        database = "unavailable"
    status: HealthState = "ok" if database == "ok" else "degraded"
    if status != "ok":
        response.status_code = 503
    return Health(status=status, version=__version__, database=database)
