import datetime as dt

import pytest

from quire.invitations.service import InvitationError, InvitationStore

NOW = dt.datetime(2026, 9, 20, 9, 0, tzinfo=dt.UTC)


def test_an_invitation_is_accepted_once() -> None:
    store = InvitationStore()
    _, token = store.create("ws-1", "Ada@Example.com", NOW)
    assert store.accept(token, NOW).email == "ada@example.com"
    with pytest.raises(InvitationError, match="already been used"):
        store.accept(token, NOW)


def test_unknown_and_revoked_links_are_refused() -> None:
    store = InvitationStore()
    invitation, token = store.create("ws-1", "ada@example.com", NOW)
    with pytest.raises(InvitationError, match="not valid"):
        store.accept("not-a-token", NOW)
    store.revoke(invitation)
    with pytest.raises(InvitationError, match="not valid"):
        store.accept(token, NOW)


def test_tokens_are_stored_only_as_hashes() -> None:
    store = InvitationStore()
    invitation, token = store.create("ws-1", "ada@example.com", NOW)
    assert token not in invitation.token_hash
    assert list(store.invitations) == [invitation.token_hash]
