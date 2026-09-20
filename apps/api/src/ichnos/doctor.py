"""Setup checks (Phase 7): what is wrong, and how to fix it, without revealing secrets.

The model check never calls the model; the GitHub checks make one request per repository.
Run inside the stack with make doctor, or read GET /api/health/checks.
"""

import os
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import httpx
from alembic.config import Config
from alembic.script import ScriptDirectory
from pydantic import SecretStr
from sqlalchemy import select, text
from sqlalchemy.orm import Session

import ichnos.db
from ichnos.db.models import Workspace
from ichnos.llm import provider_from_settings
from ichnos.settings import Settings

GITHUB = "https://api.github.com"
TOKEN_PREFIXES = ("github_pat_", "ghp_", "gho_", "ghu_", "ghs_", "ghr_")
TOKEN_FIX = (
    "Set ICHNOS_GITHUB_TOKEN in .env to a fine-grained token for your repository, with "
    "Contents, Issues and Pull requests set to read and write."
)


@dataclass
class Check:
    name: str
    status: str  # ok, warn or fail
    message: str
    fix: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _database(session: Session) -> list[Check]:
    try:
        session.execute(text("SELECT 1"))
    except Exception as exc:
        return [
            Check(
                "database",
                "fail",
                f"The database cannot be read: {type(exc).__name__}.",
                "Check that ICHNOS_DATA_DIR points at a folder the API can use.",
            )
        ]
    config = Config()
    config.set_main_option("script_location", str(Path(ichnos.db.__file__).parent / "migrations"))
    head = ScriptDirectory.from_config(config).get_current_head()
    try:
        current = session.execute(text("SELECT version_num FROM alembic_version")).scalar()
    except Exception:
        current = None
    checks = [Check("database", "ok", "Connected.")]
    if current == head:
        checks.append(Check("migrations", "ok", f"At the latest revision ({head})."))
    else:
        checks.append(
            Check(
                "migrations",
                "fail",
                f"The database is at {current or 'no revision'}; the code expects {head}.",
                "Restart the API so it upgrades the database, "
                "or run make api-migrate for a local one.",
            )
        )
    return checks


def _data_dir(settings: Settings) -> Check:
    folder = Path(settings.data_dir)
    if folder.is_dir() and os.access(folder, os.W_OK):
        return Check("data folder", "ok", f"{folder} is writable.")
    return Check(
        "data folder",
        "fail",
        f"{folder} is missing or not writable.",
        "Create it, or give the user running the API write access to it.",
    )


def _github(settings: Settings, repositories: list[str], transport: Any) -> list[Check]:
    token = settings.github_token
    if token is None or not token.get_secret_value():
        return [Check("GitHub token", "fail", "No GitHub token is configured.", TOKEN_FIX)]
    value = token.get_secret_value().strip()
    if not value.startswith(TOKEN_PREFIXES) or len(value) < 40:
        return [
            Check(
                "GitHub token",
                "fail",
                f"The value does not look like a GitHub token ({len(value)} characters, "
                "no known prefix such as github_pat_).",
                "Paste the token you created on GitHub; it starts with github_pat_. " + TOKEN_FIX,
            )
        ]
    headers = {
        "Authorization": f"Bearer {token.get_secret_value()}",
        "Accept": "application/vnd.github+json",
    }
    checks = []
    try:
        with httpx.Client(transport=transport, timeout=10) as client:
            user = client.get(f"{GITHUB}/user", headers=headers)
            if user.status_code == 401:
                return [
                    Check(
                        "GitHub token",
                        "fail",
                        "GitHub refused the token (401).",
                        "The token may have expired or been revoked. " + TOKEN_FIX,
                    )
                ]
            if user.status_code != 200:
                return [
                    Check(
                        "GitHub token",
                        "fail",
                        f"GitHub answered {user.status_code} to the token check.",
                        TOKEN_FIX,
                    )
                ]
            checks.append(Check("GitHub token", "ok", f"Accepted for {user.json().get('login')}."))
            for repository in repositories:
                name = f"repository {repository}"
                repo = client.get(f"{GITHUB}/repos/{repository}", headers=headers)
                if repo.status_code == 200:
                    checks.append(Check(name, "ok", "Reachable with this token."))
                else:
                    checks.append(
                        Check(
                            name,
                            "fail",
                            f"GitHub answered {repo.status_code} for this repository.",
                            "Give the token access to this repository, or correct its name in the "
                            "workspace settings.",
                        )
                    )
    except httpx.HTTPError as exc:
        checks.append(
            Check(
                "GitHub",
                "fail",
                f"GitHub could not be reached ({type(exc).__name__}).",
                "Check the network connection or proxy of the API container.",
            )
        )
    return checks


def _model(settings: Settings) -> Check:
    provider = provider_from_settings(settings, model_override=None, transport=None)
    if provider is None:
        return Check(
            "model",
            "warn",
            "No model is configured: drafting, planning and questions are unavailable.",
            "Set ICHNOS_LLM_PROVIDER and its API key in .env (see the self-hosting guide).",
        )
    return Check("model", "ok", f"{provider.model} is configured; this check does not call it.")


def _approvals(settings: Settings) -> Check:
    secret = getattr(settings, "approver_password", None)
    value = secret.get_secret_value() if isinstance(secret, SecretStr) else (secret or "")
    if value:
        return Check("approvals", "ok", "An approver passphrase is set.")
    return Check(
        "approvals",
        "warn",
        "No approver passphrase: nothing can be approved.",
        "Set ICHNOS_APPROVER_PASSWORD in .env.",
    )


def run_checks(
    settings: Settings, session: Session, transport: Any = None, extra: tuple[str, ...] = ()
) -> list[Check]:
    """extra: repositories to check before any workspace names them (make demo)."""
    repositories = [f"{w.repo_owner}/{w.repo_name}" for w in session.scalars(select(Workspace))]
    repositories += [r for r in extra if r and r not in repositories]
    return [
        *_database(session),
        _data_dir(settings),
        *_github(settings, repositories, transport),
        _model(settings),
        _approvals(settings),
    ]


def main() -> int:
    from ichnos.db.engine import make_engine, make_session_factory

    settings = Settings()
    with make_session_factory(make_engine(settings))() as session:
        extra = tuple(r for r in [os.environ.get("ICHNOS_CHECK_REPOSITORY", "")] if r)
        checks = run_checks(settings, session, extra=extra)
    for check in checks:
        print(f"  {check.status:<4}  {check.name:<32} {check.message}")
        if check.fix and check.status != "ok":
            print(f"        fix: {check.fix}")
    failed = sum(check.status == "fail" for check in checks)
    print(f"\n{len(checks)} checks, {failed} failed.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
