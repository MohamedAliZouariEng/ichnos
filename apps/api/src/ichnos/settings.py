"""Runtime configuration read from ICHNOS_* environment variables and .env files."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="ICHNOS_",
        env_file=(".env", "../../.env"),
        extra="ignore",
    )

    env: Literal["development", "test", "production"] = "development"
    log_level: str = "INFO"
    data_dir: Path = Path("data")
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])

    # GitHub access (ADR-0004): read from the environment only; never stored or returned.
    github_token: SecretStr | None = None

    # Model providers (ADR-0006): configuration only in Phase 1.
    llm_provider: str | None = None
    llm_model: str | None = None
    llm_base_url: str | None = None
    embedding_provider: str | None = None
    embedding_model: str | None = None
    embedding_base_url: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
