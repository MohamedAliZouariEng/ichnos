"""Approver sign-in (ADR-0016); require_approver guards every approval endpoint."""

import datetime as dt
from typing import Annotated, Any

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field

from ichnos.api.deps import SessionDep, SettingsDep
from ichnos.auth.session import COOKIE, ApproverSession, SessionStore
from ichnos.db.models import AuditEvent
from ichnos.github.identity import IdentityError, token_login

router = APIRouter(prefix="/api/session", tags=["session"])

CookieToken = Annotated[str | None, Cookie(alias=COOKIE)]
ERRORS: dict[int | str, dict[str, Any]] = {
    401: {"description": "Wrong passphrase"},
    403: {"description": "Approvals are disabled"},
    429: {"description": "Too many failed sign-ins"},
    502: {"description": "The token owner could not be identified"},
}


class SessionRead(BaseModel):
    approvals_enabled: bool
    signed_in: bool
    approver: str | None
    expires_at: dt.datetime | None


class SignIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    password: str = Field(min_length=1, max_length=500)


def _store(request: Request) -> SessionStore:
    store: SessionStore = request.app.state.sessions
    return store


def _read(store: SessionStore, session: ApproverSession | None) -> SessionRead:
    return SessionRead(
        approvals_enabled=store.enabled,
        signed_in=session is not None,
        approver=session.identity if session else None,
        expires_at=session.last_seen + store.idle if session else None,
    )


def require_approver(request: Request, token: CookieToken = None) -> ApproverSession:
    """Every approval endpoint depends on this: no live session, no approval."""
    session = _store(request).get(token)
    if session is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sign in to approve.")
    return session


ApproverDep = Annotated[ApproverSession, Depends(require_approver)]


@router.get("", response_model=SessionRead, operation_id="getSession")
def get_session(request: Request, token: CookieToken = None) -> SessionRead:
    store = _store(request)
    return _read(store, store.get(token))


@router.post("", response_model=SessionRead, operation_id="signIn", responses=ERRORS)
def sign_in(
    body: SignIn,
    request: Request,
    response: Response,
    settings: SettingsDep,
    session: SessionDep,
) -> SessionRead:
    store = _store(request)
    if not store.enabled:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Approvals are disabled; set ICHNOS_APPROVER_PASSWORD in .env and restart the API.",
        )
    if store.locked():
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS, "Too many failed sign-ins; wait five minutes."
        )
    if not store.check(body.password):
        session.add(AuditEvent(actor="unknown", event_type="session.failed", details={}))
        session.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Wrong passphrase.")
    try:
        login = token_login(settings, request.app.state.github_transport)
    except IdentityError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc
    approver = store.open(login)
    response.set_cookie(
        COOKIE,
        approver.token,
        max_age=int(store.idle.total_seconds()),
        path="/",
        httponly=True,
        samesite="strict",
        secure=request.url.scheme == "https",
    )
    session.add(AuditEvent(actor=approver.identity, event_type="session.signed_in", details={}))
    session.commit()
    return _read(store, approver)


@router.delete("", response_model=SessionRead, operation_id="signOut")
def sign_out(
    request: Request, response: Response, session: SessionDep, token: CookieToken = None
) -> SessionRead:
    store = _store(request)
    approver = store.get(token)
    store.close(token)
    response.delete_cookie(COOKIE, path="/")
    if approver is not None:
        session.add(
            AuditEvent(actor=approver.identity, event_type="session.signed_out", details={})
        )
        session.commit()
    return _read(store, None)
