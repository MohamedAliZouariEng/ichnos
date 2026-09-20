from collections.abc import Iterator

import httpx
import pytest
from sqlalchemy.orm import Session, sessionmaker

from ichnos.db.engine import make_engine, make_session_factory
from ichnos.db.migrate import upgrade_to_head
from ichnos.db.models import Workspace
from ichnos.doctor import Check, run_checks
from ichnos.settings import Settings


@pytest.fixture
def factory() -> Iterator[sessionmaker[Session]]:
    settings = Settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    upgrade_to_head(settings.sqlalchemy_url())
    made = make_session_factory(make_engine(settings))
    with made() as session:
        session.add(
            Workspace(
                id="ws", name="quire", repo_owner="octo", repo_name="quire", index_paths=["docs/"]
            )
        )
        session.commit()
    yield made


def github(user: int = 200, repo: int = 200) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/user":
            return httpx.Response(user, json={"login": "octo"})
        return httpx.Response(repo, json={})

    return httpx.MockTransport(handler)


def checks(factory: sessionmaker[Session], transport: httpx.MockTransport) -> dict[str, Check]:
    with factory() as session:
        return {c.name: c for c in run_checks(Settings(), session, transport)}


def configure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ICHNOS_GITHUB_TOKEN", "test-token-value")
    monkeypatch.setenv("ICHNOS_LLM_PROVIDER", "fake")
    monkeypatch.setenv("ICHNOS_APPROVER_PASSWORD", "correct horse battery staple")


def test_a_good_setup_passes_every_check(
    monkeypatch: pytest.MonkeyPatch, factory: sessionmaker[Session]
) -> None:
    configure(monkeypatch)
    found = checks(factory, github())
    assert set(found) == {
        "database",
        "migrations",
        "data folder",
        "GitHub token",
        "repository octo/quire",
        "model",
        "approvals",
    }
    assert {c.status for c in found.values()} == {"ok"}
    assert "octo" in found["GitHub token"].message


def test_a_refused_token_and_an_unreachable_repository_say_how_to_fix_them(
    monkeypatch: pytest.MonkeyPatch, factory: sessionmaker[Session]
) -> None:
    configure(monkeypatch)
    refused = checks(factory, github(user=401))["GitHub token"]
    assert refused.status == "fail" and "401" in refused.message
    assert "ICHNOS_GITHUB_TOKEN" in refused.fix
    missing = checks(factory, github(repo=404))["repository octo/quire"]
    assert missing.status == "fail" and "access" in missing.fix


def test_missing_configuration_is_named_and_never_leaks_a_secret(
    monkeypatch: pytest.MonkeyPatch, factory: sessionmaker[Session]
) -> None:
    for name in ("ICHNOS_GITHUB_TOKEN", "ICHNOS_LLM_PROVIDER", "ICHNOS_APPROVER_PASSWORD"):
        monkeypatch.delenv(name, raising=False)
    found = checks(factory, github())
    assert found["GitHub token"].status == "fail"
    assert (found["model"].status, found["approvals"].status) == ("warn", "warn")
    configure(monkeypatch)
    text = " ".join(f"{c.message} {c.fix}" for c in checks(factory, github()).values())
    assert "test-token-value" not in text and "correct horse" not in text
