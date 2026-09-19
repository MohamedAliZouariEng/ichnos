"""Server configuration the UI may display, and the model check. Never includes secrets."""

from urllib.parse import urlparse

from fastapi import APIRouter, Request
from pydantic import BaseModel

from ichnos.api.deps import SettingsDep
from ichnos.llm import is_local, provider_from_settings
from ichnos.llm.preflight import preflight

router = APIRouter(prefix="/api/config", tags=["config"])

NOT_CONFIGURED = (
    "No model provider is configured; set ICHNOS_LLM_PROVIDER, ICHNOS_LLM_BASE_URL and "
    "ICHNOS_LLM_MODEL in .env (plus ICHNOS_LLM_API_KEY for hosted providers)."
)


class ServerConfig(BaseModel):
    github_token_configured: bool
    llm_provider: str | None
    llm_model: str | None
    llm_configured: bool
    llm_host: str | None
    llm_local: bool
    llm_reasoning_effort: str
    embedding_provider: str | None
    embedding_model: str | None


class ModelCheck(BaseModel):
    ok: bool
    provider: str | None
    model: str | None
    local: bool
    message: str
    total_tokens: int
    latency_ms: int


@router.get("", response_model=ServerConfig, operation_id="getServerConfig")
def get_server_config(settings: SettingsDep) -> ServerConfig:
    token = settings.github_token
    provider = provider_from_settings(settings)
    base_url = settings.llm_base_url or ""
    fake = provider is not None and provider.name == "fake"
    return ServerConfig(
        github_token_configured=token is not None and bool(token.get_secret_value()),
        llm_provider=settings.llm_provider,
        llm_model=settings.llm_model,
        llm_configured=provider is not None,
        llm_host=None if fake or not base_url else urlparse(base_url).hostname,
        llm_local=True if fake or not base_url else is_local(base_url),
        llm_reasoning_effort=settings.llm_reasoning_effort,
        embedding_provider=settings.embedding_provider,
        embedding_model=settings.embedding_model,
    )


@router.post("/model-check", response_model=ModelCheck, operation_id="checkModel")
def check_model(settings: SettingsDep, request: Request) -> ModelCheck:
    """One tiny structured call to the configured model. Costs a few tokens."""
    provider = provider_from_settings(settings, transport=request.app.state.llm_transport)
    if provider is None:
        return ModelCheck(
            ok=False,
            provider=settings.llm_provider,
            model=settings.llm_model,
            local=True,
            message=NOT_CONFIGURED,
            total_tokens=0,
            latency_ms=0,
        )
    result = preflight(provider)
    return ModelCheck(
        ok=result.ok,
        provider=provider.name,
        model=provider.model,
        local=provider.local,
        message=result.message,
        total_tokens=result.usage.total_tokens,
        latency_ms=result.latency_ms,
    )
