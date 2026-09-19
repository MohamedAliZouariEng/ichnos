"""Build the configured model provider (ADR-0012)."""

import httpx

from ichnos.llm.provider import FakeProvider, ModelProvider, OpenAICompatibleProvider
from ichnos.settings import Settings

COMPATIBLE = {"openai-compatible", "openai", "gemini", "ollama", "openrouter", "groq"}


def provider_from_settings(
    settings: Settings,
    *,
    model_override: str | None = None,
    transport: httpx.BaseTransport | None = None,
) -> ModelProvider | None:
    """The provider to use, or None when no model is configured."""
    kind = (settings.llm_provider or "").strip().lower()
    model = model_override or settings.llm_model
    if kind == "fake":
        return FakeProvider(model=model or "fake")
    if kind in COMPATIBLE and settings.llm_base_url and model:
        return OpenAICompatibleProvider(
            base_url=settings.llm_base_url,
            model=model,
            api_key=settings.llm_api_key,
            reasoning_effort=settings.llm_reasoning_effort,
            timeout=settings.llm_timeout,
            transport=transport,
        )
    return None
