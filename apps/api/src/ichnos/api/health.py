"""Liveness endpoint used by Docker health checks and the web shell."""

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

from ichnos import __version__

router = APIRouter(tags=["health"])


class Health(BaseModel):
    status: Literal["ok"]
    version: str


@router.get("/healthz", response_model=Health, operation_id="getHealth")
def get_health() -> Health:
    return Health(status="ok", version=__version__)
