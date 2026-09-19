"""FastAPI dependencies shared by routers."""

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session, sessionmaker

from ichnos.github.client import GitHubClient
from ichnos.settings import Settings


def get_app_settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def get_session(request: Request) -> Iterator[Session]:
    factory: sessionmaker[Session] = request.app.state.session_factory
    with factory() as session:
        yield session


def get_github_client(request: Request) -> GitHubClient:
    settings = get_app_settings(request)
    return GitHubClient(settings.github_token, transport=request.app.state.github_transport)


SettingsDep = Annotated[Settings, Depends(get_app_settings)]
SessionDep = Annotated[Session, Depends(get_session)]
GitHubDep = Annotated[GitHubClient, Depends(get_github_client)]
