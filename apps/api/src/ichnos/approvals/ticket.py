"""Execution tickets (ADR-0015): the only way to obtain a GitHub write client.

Only the approval service calls issue_ticket; an architecture test fails the build if any
module outside ichnos.approvals imports the writer or issues a ticket.
"""

from dataclasses import dataclass, field

_ISSUER = object()


@dataclass(frozen=True)
class ExecutionTicket:
    approval_id: str
    payload_hash: str
    issuer: object = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        if self.issuer is not _ISSUER:
            raise PermissionError("Only the approval service issues execution tickets (ADR-0015).")


def issue_ticket(approval_id: str, payload_hash: str) -> ExecutionTicket:
    return ExecutionTicket(approval_id, payload_hash, _ISSUER)
