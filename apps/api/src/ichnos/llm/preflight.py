"""Preflight: one tiny structured call proves the configured model works (ADR-0012)."""

import time
from dataclasses import dataclass

from pydantic import BaseModel

from ichnos.llm.provider import ModelError, ModelProvider, Usage, fake_responder


class Preflight(BaseModel):
    ok: bool


@fake_responder("Preflight")
def _fake_preflight(system: str, user: str) -> dict[str, bool]:
    return {"ok": True}


@dataclass
class PreflightResult:
    ok: bool
    message: str
    usage: Usage
    latency_ms: int


def preflight(provider: ModelProvider) -> PreflightResult:
    started = time.monotonic()
    try:
        answer, usage = provider.complete_json(
            "You check that structured output works. Answer only with JSON.",
            'Return {"ok": true}.',
            Preflight,
        )
    except ModelError as exc:
        elapsed = int((time.monotonic() - started) * 1000)
        return PreflightResult(False, str(exc), Usage(), elapsed)
    elapsed = int((time.monotonic() - started) * 1000)
    if not answer.ok:
        return PreflightResult(False, "The model answered, but not as expected.", usage, elapsed)
    return PreflightResult(True, "The model answered with valid structured output.", usage, elapsed)
