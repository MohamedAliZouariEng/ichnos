"""Server configuration the UI may display. Never includes secrets."""

from fastapi import APIRouter
from pydantic import BaseModel

from ichnos.api.deps import SettingsDep

router = APIRouter(prefix="/api/config", tags=["config"])


class ServerConfig(BaseModel):
    github_token_configured: bool
    llm_provider: str | None
    llm_model: str | None
    embedding_provider: str | None
    embedding_model: str | None


@router.get("", response_model=ServerConfig, operation_id="getServerConfig")
def get_server_config(settings: SettingsDep) -> ServerConfig:
    token = settings.github_token
    return ServerConfig(
        github_token_configured=token is not None and bool(token.get_secret_value()),
        llm_provider=settings.llm_provider,
        llm_model=settings.llm_model,
        embedding_provider=settings.embedding_provider,
        embedding_model=settings.embedding_model,
    )
