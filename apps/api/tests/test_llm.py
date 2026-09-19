import json
from collections.abc import Callable
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel, SecretStr

from ichnos.llm import (
    FakeProvider,
    ModelError,
    OpenAICompatibleProvider,
    inline_schema,
    is_local,
    provider_from_settings,
)
from ichnos.main import create_app
from ichnos.settings import Settings

GEMINI = "https://generativelanguage.googleapis.com/v1beta/openai"
Handler = Callable[[httpx.Request], httpx.Response]


class Requirement(BaseModel):
    id: str
    statement: str


class Extraction(BaseModel):
    requirements: list[Requirement]


def answer(content: str, total: int = 50) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "choices": [{"message": {"role": "assistant", "content": content}}],
            "usage": {"prompt_tokens": 20, "completion_tokens": 10, "total_tokens": total},
        },
    )


def provider(handler: Handler, effort: str = "low") -> OpenAICompatibleProvider:
    return OpenAICompatibleProvider(
        base_url=GEMINI,
        model="gemini-3.8-flash",
        api_key=SecretStr("test-key"),
        reasoning_effort=effort,
        transport=httpx.MockTransport(handler),
    )


VALID = json.dumps({"requirements": [{"id": "R-01", "statement": "Invitations expire."}]})


def test_structured_call_sends_schema_and_parses_answer() -> None:
    sent: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1beta/openai/chat/completions"
        assert request.headers["Authorization"] == "Bearer test-key"
        sent.append(json.loads(request.content))
        return answer(VALID)

    result, usage = provider(handler).complete_json("system", "user", Extraction)

    assert result.requirements[0].id == "R-01"
    assert usage.total_tokens == 50 and usage.calls == 1
    body = sent[0]
    assert body["model"] == "gemini-3.8-flash"
    assert body["reasoning_effort"] == "low"
    schema = body["response_format"]["json_schema"]["schema"]
    assert "$defs" not in json.dumps(schema) and "$ref" not in json.dumps(schema)


def test_invalid_answer_is_retried_once_with_the_errors() -> None:
    sent: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(json.loads(request.content))
        return answer('{"requirements": "oops"}' if len(sent) == 1 else VALID, total=40)

    result, usage = provider(handler).complete_json("system", "user", Extraction)

    assert result.requirements[0].statement == "Invitations expire."
    assert usage.calls == 2 and usage.total_tokens == 80
    assert "did not match the JSON schema" in sent[1]["messages"][-1]["content"]


def test_repeated_invalid_answers_raise() -> None:
    with pytest.raises(ModelError, match="valid structured output"):
        provider(lambda request: answer("not json")).complete_json("s", "u", Extraction)


@pytest.mark.parametrize(
    ("response", "expected"),
    [
        (
            httpx.Response(
                400,
                json=[
                    {
                        "error": {
                            "code": 400,
                            "message": "This model only supports Interactions API.",
                        }
                    }
                ],
            ),
            "only supports Interactions API",
        ),
        (
            httpx.Response(401, json={"error": {"message": "API key not valid."}}),
            "API key not valid",
        ),
        (httpx.Response(429, json={}), "rate limit"),
    ],
)
def test_provider_errors_are_readable(response: httpx.Response, expected: str) -> None:
    with pytest.raises(ModelError, match=expected):
        provider(lambda request: response).complete_json("s", "u", Extraction)


def test_reasoning_effort_can_be_turned_off() -> None:
    sent: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(json.loads(request.content))
        return answer(VALID)

    provider(handler, effort="off").complete_json("s", "u", Extraction)
    assert "reasoning_effort" not in sent[0]


def test_inline_schema_resolves_nested_definitions() -> None:
    inlined = inline_schema(Extraction.model_json_schema())
    item = inlined["properties"]["requirements"]["items"]
    assert item["properties"]["statement"]["type"] == "string"


@pytest.mark.parametrize(
    ("url", "local"),
    [
        (GEMINI, False),
        ("http://localhost:11434/v1", True),
        ("http://ollama:11434/v1", True),
        ("https://api.openai.com/v1", False),
    ],
)
def test_is_local(url: str, local: bool) -> None:
    assert is_local(url) is local


def test_factory(monkeypatch: pytest.MonkeyPatch) -> None:
    assert provider_from_settings(Settings()) is None
    monkeypatch.setenv("ICHNOS_LLM_PROVIDER", "fake")
    assert isinstance(provider_from_settings(Settings()), FakeProvider)
    monkeypatch.setenv("ICHNOS_LLM_PROVIDER", "openai-compatible")
    monkeypatch.setenv("ICHNOS_LLM_BASE_URL", GEMINI)
    assert provider_from_settings(Settings()) is None  # no model yet
    monkeypatch.setenv("ICHNOS_LLM_MODEL", "gemini-3.8-flash")
    built = provider_from_settings(Settings(), model_override="gemini-2.5-flash")
    assert isinstance(built, OpenAICompatibleProvider) and built.model == "gemini-2.5-flash"


def test_config_discloses_provider_but_never_the_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ICHNOS_LLM_PROVIDER", "openai-compatible")
    monkeypatch.setenv("ICHNOS_LLM_BASE_URL", GEMINI)
    monkeypatch.setenv("ICHNOS_LLM_MODEL", "gemini-3.8-flash")
    monkeypatch.setenv("ICHNOS_LLM_API_KEY", "secret-key-value")
    with TestClient(create_app(Settings())) as client:
        response = client.get("/api/config")
    config = response.json()
    assert config["llm_configured"] is True
    assert config["llm_host"] == "generativelanguage.googleapis.com"
    assert config["llm_local"] is False
    assert config["llm_reasoning_effort"] == "low"
    assert "secret-key-value" not in response.text


def test_model_check_uses_the_configured_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ICHNOS_LLM_PROVIDER", "openai-compatible")
    monkeypatch.setenv("ICHNOS_LLM_BASE_URL", GEMINI)
    monkeypatch.setenv("ICHNOS_LLM_MODEL", "gemini-3.8-flash")
    app = create_app(Settings())
    app.state.llm_transport = httpx.MockTransport(lambda request: answer('{"ok": true}', total=306))
    with TestClient(app) as client:
        check = client.post("/api/config/model-check").json()
    assert check["ok"] is True
    assert check["total_tokens"] == 306
    assert check["local"] is False


def test_model_check_without_configuration_explains_what_to_set() -> None:
    with TestClient(create_app(Settings())) as client:
        check = client.post("/api/config/model-check").json()
    assert check["ok"] is False
    assert "ICHNOS_LLM_PROVIDER" in check["message"]


def test_fake_provider_passes_the_model_check(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ICHNOS_LLM_PROVIDER", "fake")
    with TestClient(create_app(Settings())) as client:
        check = client.post("/api/config/model-check").json()
        config = client.get("/api/config").json()
    assert check["ok"] is True and check["provider"] == "fake"
    assert config["llm_local"] is True and config["llm_host"] is None
