---
type: Decision
title: "ADR-0016: Approvals need a local session; the approver is the token owner's GitHub login"
description: Approving requires signing in with a passphrase from the environment, which creates an HttpOnly session cookie; the approver identity written to verified is the GitHub login that owns the token.
tags: [adr, approvals, authentication, security]
status: stable
generated: { by: claude/opus-5, at: 2026-09-19T21:22:44Z }
verified: { by: human:MohamedAliZouariEng, at: 2026-09-19T21:22:44Z }
sources:
  - id: adr-0004
    resource: /adr/0004-github-fine-grained-pat.md
    title: "ADR-0004: GitHub access through a fine-grained personal access token"
ichnos:
  adr_number: 16
---

# Context

The delivery plan requires an authenticated local session for any approval, and OKF's `verified: { by: human:<login> }` is what "approved" means. Ichnos is self-hosted, often on one machine, and uses one fine-grained token per installation (ADR-0004).[^adr-0004] GitHub OAuth would give each person their own identity but needs a registered OAuth app and a reachable callback.

# Decision

- `ICHNOS_APPROVER_PASSWORD` enables approvals. Without it, Ichnos can draft and propose but never approve.
- Signing in with that passphrase creates a random session held in memory, sent as an `HttpOnly`, `SameSite=Strict` cookie that expires after eight hours of inactivity. Signing out or restarting the API ends every session.
- The approver's identity is the GitHub login that owns the token, read from `GET /user`. A payload that sets `verified` is built for that login, so the identity is part of what is approved.
- Every sign-in, failed sign-in, approval and rejection is an audit event.

# Consequences

- **Positive:** works offline and with no extra setup; the identity in `verified` is a real GitHub account.
- **Negative:** everyone who knows the passphrase approves as the token owner; per-person identity needs OAuth.
- **Revisit:** GitHub OAuth when Ichnos serves more than one person.

[^adr-0004]: ADR-0004: GitHub access through a fine-grained personal access token
