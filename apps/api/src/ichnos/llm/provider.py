"""Model providers (ADR-0012): one OpenAI-compatible adapter and a fake, schema-checked JSON."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol, TypeVar
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel, SecretStr, ValidationError

T = TypeVar("T", bound=BaseModel)
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "ollama", "host.docker.internal"}
MAX_ERROR = 2000


class ModelError(Exception):
    """The model could not be called or did not return valid structured output."""


@dataclass
class Usage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    calls: int = 0

    def add(self, data: Any) -> None:
        self.calls += 1
        if isinstance(data, dict):
            self.prompt_tokens += int(data.get("prompt_tokens") or 0)
            self.completion_tokens += int(data.get("completion_tokens") or 0)
            self.total_tokens += int(data.get("total_tokens") or 0)

    def merge(self, other: "Usage") -> None:
        self.prompt_tokens += other.prompt_tokens
        self.completion_tokens += other.completion_tokens
        self.total_tokens += other.total_tokens
        self.calls += other.calls

    def as_dict(self) -> dict[str, int]:
        return {
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "calls": self.calls,
        }


class ModelProvider(Protocol):
    name: str
    model: str
    local: bool

    def complete_json(self, system: str, user: str, schema: type[T]) -> tuple[T, Usage]: ...


def is_local(base_url: str) -> bool:
    """Does a call to this URL stay on this machine (or its Docker network)?"""
    host = urlparse(base_url).hostname or ""
    return host in LOCAL_HOSTS or host.endswith(".local")


def inline_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Replace $ref pointers with their $defs, since not every provider resolves them."""
    defs = schema.get("$defs", {})

    def resolve(node: Any) -> Any:
        if isinstance(node, dict):
            ref = node.get("$ref")
            if isinstance(ref, str) and ref.startswith("#/$defs/"):
                return resolve(defs[ref.removeprefix("#/$defs/")])
            return {key: resolve(value) for key, value in node.items() if key != "$defs"}
        if isinstance(node, list):
            return [resolve(item) for item in node]
        return node

    result = resolve(schema)
    assert isinstance(result, dict)
    return result


def _error_message(body: Any) -> str | None:
    """Gemini wraps errors in a list; OpenAI does not. Accept both."""
    if isinstance(body, list) and body:
        body = body[0]
    if isinstance(body, dict):
        error = body.get("error", body)
        if isinstance(error, dict) and error.get("message"):
            return str(error["message"]).strip()
    return None


def _content(body: dict[str, Any]) -> str:
    try:
        content = body["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ModelError("The model returned no answer.") from exc
    text = str(content or "").strip()
    if text.startswith("```"):  # tolerate a fenced answer
        text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    return text


class OpenAICompatibleProvider:
    """Gemini, OpenAI, OpenRouter, Groq or Ollama through the chat-completions format."""

    name = "openai-compatible"

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        api_key: SecretStr | None,
        reasoning_effort: str | None = "low",
        timeout: float = 120.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.local = is_local(base_url)
        self._reasoning_effort = None if reasoning_effort in (None, "", "off") else reasoning_effort
        self._timeout = timeout
        self._transport = transport
        self._headers = {"Content-Type": "application/json"}
        if api_key is not None and api_key.get_secret_value():
            self._headers["Authorization"] = f"Bearer {api_key.get_secret_value()}"

    @property
    def host(self) -> str:
        return urlparse(self.base_url).hostname or self.base_url

    def _post(self, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            with httpx.Client(
                headers=self._headers, timeout=self._timeout, transport=self._transport
            ) as client:
                response = client.post(f"{self.base_url}/chat/completions", json=payload)
        except httpx.HTTPError as exc:
            raise ModelError(f"Could not reach the model provider at {self.host}.") from exc
        try:
            body = response.json()
        except ValueError:
            body = None
        if response.status_code == 429:
            raise ModelError("The model provider's rate limit was reached; try again later.")
        if not response.is_success:
            detail = _error_message(body) or response.reason_phrase
            raise ModelError(f"The model provider returned HTTP {response.status_code}: {detail}")
        if not isinstance(body, dict):
            raise ModelError("The model provider returned an unreadable answer.")
        return body

    def complete_json(self, system: str, user: str, schema: type[T]) -> tuple[T, Usage]:
        usage = Usage()
        messages: list[dict[str, str]] = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        base: dict[str, Any] = {
            "model": self.model,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": schema.__name__,
                    "schema": inline_schema(schema.model_json_schema()),
                },
            },
        }
        if self._reasoning_effort:
            base["reasoning_effort"] = self._reasoning_effort
        problem = ""
        for _attempt in range(2):
            body = self._post({**base, "messages": messages})
            usage.add(body.get("usage"))
            content = _content(body)
            try:
                return schema.model_validate_json(content), usage
            except ValidationError as exc:
                problem = str(exc)[:MAX_ERROR]
            messages = [
                *messages,
                {"role": "assistant", "content": content},
                {
                    "role": "user",
                    "content": f"That answer did not match the JSON schema:\n{problem}\n"
                    "Answer again with only JSON that matches the schema.",
                },
            ]
        raise ModelError(f"The model did not return valid structured output: {problem[:300]}")


Responder = Callable[[str, str], dict[str, Any]]
FAKE_RESPONDERS: dict[str, Responder] = {}


def fake_responder(schema_name: str) -> Callable[[Responder], Responder]:
    """Register the fake provider's deterministic answer for one schema."""

    def register(function: Responder) -> Responder:
        FAKE_RESPONDERS[schema_name] = function
        return function

    return register


class FakeProvider:
    """Deterministic answers for tests, CI and offline demos; nothing leaves the machine."""

    name = "fake"
    local = True

    def __init__(self, model: str = "fake", responders: dict[str, Responder] | None = None) -> None:
        self.model = model
        self.responders = FAKE_RESPONDERS if responders is None else responders
        self.calls: list[tuple[str, str, str]] = []

    def complete_json(self, system: str, user: str, schema: type[T]) -> tuple[T, Usage]:
        self.calls.append((schema.__name__, system, user))
        responder = self.responders.get(schema.__name__)
        if responder is None:
            raise ModelError(f"The fake provider has no answer for {schema.__name__}.")
        usage = Usage()
        prompt = (len(system) + len(user)) // 4
        usage.add({"prompt_tokens": prompt, "completion_tokens": 10, "total_tokens": prompt + 10})
        return schema.model_validate(responder(system, user)), usage
