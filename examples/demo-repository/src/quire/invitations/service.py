"""Create and accept workspace invitations."""

import datetime as dt
from dataclasses import dataclass, field

from quire.invitations.tokens import hash_token, new_token


class InvitationError(Exception):
    """The invitation cannot be used; the message is shown to the invitee."""


@dataclass
class Invitation:
    workspace_id: str
    email: str
    token_hash: str
    created_at: dt.datetime
    accepted_at: dt.datetime | None = None
    revoked: bool = False


@dataclass
class InvitationStore:
    """In-memory store; the application keeps invitations in its database."""

    invitations: dict[str, Invitation] = field(default_factory=dict)

    def create(self, workspace_id: str, email: str, now: dt.datetime) -> tuple[Invitation, str]:
        """Store a new invitation and return it with the token for the link."""
        token = new_token()
        invitation = Invitation(workspace_id, email.strip().lower(), hash_token(token), now)
        self.invitations[invitation.token_hash] = invitation
        return invitation, token

    def accept(self, token: str, now: dt.datetime) -> Invitation:
        invitation = self.invitations.get(hash_token(token))
        if invitation is None or invitation.revoked:
            raise InvitationError("This invitation link is not valid.")
        if invitation.accepted_at is not None:
            raise InvitationError("This invitation has already been used.")
        invitation.accepted_at = now
        return invitation

    def revoke(self, invitation: Invitation) -> None:
        invitation.revoked = True
