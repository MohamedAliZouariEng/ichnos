import pytest

from ichnos.settings import Settings


def test_defaults() -> None:
    settings = Settings()
    assert settings.env == "development"
    assert settings.github_token is None
    assert settings.llm_provider is None


def test_github_token_never_leaks(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ICHNOS_GITHUB_TOKEN", "test-token-value")
    settings = Settings()
    assert settings.github_token is not None
    assert settings.github_token.get_secret_value() == "test-token-value"
    assert "test-token-value" not in repr(settings)
    assert "test-token-value" not in settings.model_dump_json()


def test_empty_values_count_as_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ICHNOS_GITHUB_TOKEN", "")
    monkeypatch.setenv("ICHNOS_LLM_PROVIDER", "")
    settings = Settings()
    assert settings.github_token is None
    assert settings.llm_provider is None
