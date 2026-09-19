---
type: Decision
title: "ADR-0001: Invitation links carry single-use opaque tokens"
description: Invitation links contain a random single-use token stored only as a hash.
tags: [adr, security, invitations]
status: stable
generated: { by: claude/opus-5, at: 2026-09-19T15:27:22Z }
verified: { by: human:MohamedAliZouariEng, at: 2026-09-19T15:27:22Z }
---

# Context

The first version of invitation links put the workspace ID and the invitee's email in the query string. Anyone who knew both could forge a working link, and a link could be used any number of times.

# Decision

- Each invitation gets a random 32-byte token, sent only in the invitation link.
- The database stores the SHA-256 hash of the token, never the token itself.
- A token is single-use: accepting the invitation marks it as used.
- Invitations are looked up by token hash.

# Consequences

- Leaked database rows cannot be turned into working links.
- Invitations now have a lifecycle (pending, accepted), which makes later features such as expiry or revocation a matter of adding state and checks.
- Resending an invitation requires creating a new token, because the original token cannot be recovered from its hash.

See the [product overview](/project/product-overview.md) for how invitations fit into onboarding.
