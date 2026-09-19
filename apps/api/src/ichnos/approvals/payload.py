"""Canonical payloads and their hashes (ADR-0015)."""

import hashlib
import json
from typing import Any

from ichnos.db.models import Approval

PENDING = "pending"
APPROVED = "approved"
EXECUTED = "executed"
FAILED = "failed"
REJECTED = "rejected"
STALE = "stale"
FINAL = frozenset({EXECUTED, FAILED, REJECTED, STALE})


def canonical(payload: dict[str, Any]) -> bytes:
    """One byte representation per payload: sorted keys, no spaces, UTF-8."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )


def payload_hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(canonical(payload)).hexdigest()


def verify(approval: Approval) -> bool:
    """Does the stored payload still hash to the stored hash?"""
    return approval.payload_hash == payload_hash(approval.payload or {})
