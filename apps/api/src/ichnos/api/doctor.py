"""Setup checks over HTTP: what is wrong and how to fix it, without secrets."""

from fastapi import APIRouter, Request
from pydantic import BaseModel

from ichnos.api.deps import SessionDep, SettingsDep
from ichnos.doctor import run_checks

router = APIRouter(tags=["health"])


class CheckRead(BaseModel):
    name: str
    status: str
    message: str
    fix: str


@router.get("/api/health/checks", response_model=list[CheckRead], operation_id="getSetupChecks")
def setup_checks(session: SessionDep, settings: SettingsDep, request: Request) -> list[CheckRead]:
    """Database, migrations, data folder, GitHub token and repositories, model, approvals."""
    checks = run_checks(settings, session, request.app.state.github_transport)
    return [CheckRead(**check.as_dict()) for check in checks]
