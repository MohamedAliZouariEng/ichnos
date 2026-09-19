"""Approver sessions (ADR-0016): a passphrase opens a short-lived, in-memory session."""

import datetime as dt
import hashlib
import hmac
import secrets
import threading
from dataclasses import dataclass

from ichnos.db.base import utc_now

COOKIE = "ichnos_session"


@dataclass
class ApproverSession:
    token: str
    login: str
    created_at: dt.datetime
    last_seen: dt.datetime

    @property
    def identity(self) -> str:
        return f"human:{self.login}"


class SessionStore:
    """Sessions live only in memory: restarting the API signs everyone out."""

    def __init__(
        self,
        password: str | None,
        *,
        idle_hours: float = 8.0,
        max_failures: int = 5,
        lockout_minutes: float = 5.0,
    ) -> None:
        self._digest = hashlib.sha256(password.encode()).digest() if password else None
        self.idle = dt.timedelta(hours=idle_hours)
        self._lockout = dt.timedelta(minutes=lockout_minutes)
        self._max_failures = max_failures
        self._sessions: dict[str, ApproverSession] = {}
        self._failures: list[dt.datetime] = []
        self._lock = threading.Lock()

    @property
    def enabled(self) -> bool:
        return self._digest is not None

    def locked(self) -> bool:
        cutoff = utc_now() - self._lockout
        with self._lock:
            self._failures = [when for when in self._failures if when > cutoff]
            return len(self._failures) >= self._max_failures

    def check(self, password: str) -> bool:
        """Constant-time comparison of digests; failures count towards the lockout."""
        if self._digest is None:
            return False
        ok = hmac.compare_digest(hashlib.sha256(password.encode()).digest(), self._digest)
        if not ok:
            with self._lock:
                self._failures.append(utc_now())
        return ok

    def open(self, login: str) -> ApproverSession:
        now = utc_now()
        session = ApproverSession(secrets.token_urlsafe(32), login, now, now)
        with self._lock:
            self._sessions[session.token] = session
            self._failures.clear()
        return session

    def get(self, token: str | None) -> ApproverSession | None:
        """The live session for a cookie value; idle sessions expire."""
        if not token:
            return None
        now = utc_now()
        with self._lock:
            session = self._sessions.get(token)
            if session is None:
                return None
            if now - session.last_seen >= self.idle:
                del self._sessions[token]
                return None
            session.last_seen = now
            return session

    def close(self, token: str | None) -> None:
        if token:
            with self._lock:
                self._sessions.pop(token, None)
