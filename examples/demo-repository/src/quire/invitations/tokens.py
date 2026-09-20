"""Invitation tokens (ADR-0001): single-use, opaque, and stored only as a hash."""

import hashlib
import secrets

TOKEN_BYTES = 32


def new_token() -> str:
    """A random token for the invitation link; only its hash is stored."""
    return secrets.token_urlsafe(TOKEN_BYTES)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()
