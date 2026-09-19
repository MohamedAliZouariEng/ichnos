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
        env_ignore_empty=True,
    )

    env: Literal["development", "test", "production"] = "development"
    log_level: str = "INFO"
    data_dir: Path = Path("data")
    database_url: str | None = None
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])

    # GitHub access (ADR-0004): read from the environment only; never stored or returned.
    github_token: SecretStr | None = None

    # Model providers (ADR-0006): configuration only in Phase 1.
    llm_provider: str | None = None
    llm_model: str | None = None
    llm_base_url: str | None = None
    # ADR-0012: secret like the GitHub token; "off" stops sending reasoning_effort.
    llm_api_key: SecretStr | None = None
    llm_reasoning_effort: str = "low"
    llm_timeout: float = 120.0

    # Workflow engine (ADR-0011).
    workflow_workers: int = 2
    embedding_provider: str | None = None
    embedding_model: str | None = None
    embedding_base_url: str | None = None

    def checkpoint_path(self) -> Path:
        """LangGraph checkpoints live in their own file, outside Alembic (ADR-0011)."""
        return self.data_dir.resolve() / "checkpoints.db"

    def sqlalchemy_url(self) -> str:
        """Database URL; defaults to a SQLite file inside data_dir."""
        return self.database_url or f"sqlite:///{self.data_dir.resolve() / 'ichnos.db'}"


@lru_cache
def get_settings() -> Settings:
    return Settings()
