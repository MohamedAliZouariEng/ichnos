"""Model access for workflows (ADR-0012)."""

from ichnos.llm import preflight as _preflight  # noqa: F401  (registers the fake preflight answer)
from ichnos.llm.factory import provider_from_settings
from ichnos.llm.provider import (
    FakeProvider,
    ModelError,
    ModelProvider,
    OpenAICompatibleProvider,
    Usage,
    fake_responder,
    inline_schema,
    is_local,
)

__all__ = [
    "FakeProvider",
    "ModelError",
    "ModelProvider",
    "OpenAICompatibleProvider",
    "Usage",
    "fake_responder",
    "inline_schema",
    "is_local",
    "provider_from_settings",
]
