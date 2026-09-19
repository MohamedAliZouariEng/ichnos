---
type: Decision
title: "ADR-0015: Every GitHub write is an approved pending action, executed by one write client"
description: Writes are proposed as pending actions with a hashed payload and a recorded base; only the approval service can build the GitHub write client, and it executes exactly the approved payload.
tags: [adr, approvals, github, security]
status: stable
generated: { by: claude/opus-5, at: 2026-09-19T21:22:44Z }
verified: { by: human:MohamedAliZouariEng, at: 2026-09-19T21:22:44Z }
sources:
  - id: adr-0002
    resource: /adr/0002-github-is-canonical.md
    title: "ADR-0002: GitHub is the canonical source of truth"
  - id: techspec
    resource: /specs/ichnos-mvp/techspec.md
    title: Ichnos MVP — Technical Specification
ichnos:
  adr_number: 15
---

# Context

Humans approve every write to GitHub (ADR-0002).[^adr-0002] The delivery plan requires that the approval endpoint execute only the persisted payload, that stale approvals be rejected, and that CI fail on any unapproved write.[^techspec] A new code path must not be able to bypass the gate by calling GitHub directly.

# Decision

- **Pending actions.** A proposed write stores its workspace, repository, branch, action type, the full payload as JSON, the payload's SHA-256, the base it was built on (artifact version, branch head SHA, the blob SHA of every file it changes), who proposed it and when.
- **One write client.** Reads keep the existing read-only client. The write client can only be constructed from an approved action, inside the approval service; no other module imports it.
- **Approval checks before executing.** The stored hash must match the stored payload, the artifact must still be at the recorded version, and the branch head and touched files must be unchanged. Otherwise the action becomes `stale` and nothing is written.
- **Execution is recorded.** Each action moves from `pending` to `approved`, then `executed` or `failed`, or to `rejected` or `stale`. Results (commit SHA, pull request and Issue numbers and URLs) are stored on the action; re-running an executed action does nothing.
- **Proof in CI.** An integration test runs every write path against a fake GitHub that records writes and fails if any write happens without an approved action.

# Consequences

- **Positive:** the approval is a contract on exact bytes; a new feature cannot write without going through it.
- **Negative:** a busy default branch makes proposals go stale more often; they must be proposed again.

[^adr-0002]: ADR-0002: GitHub is the canonical source of truth
[^techspec]: Ichnos MVP — Technical Specification
