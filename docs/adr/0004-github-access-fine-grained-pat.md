---
type: Decision
title: "ADR-0004: GitHub access through a fine-grained personal access token"
description: The MVP authenticates to GitHub with one fine-grained PAT from the environment, read-only until approved writes need more.
tags: [adr, github, security]
status: stable
generated: { by: claude/opus-5, at: 2026-09-19T13:13:45Z }
verified: { by: human:MohamedAliZouariEng, at: 2026-09-19T13:13:45Z }
sources:
  - id: techspec
    resource: /specs/ichnos-mvp/techspec.md
    title: Ichnos MVP — Technical Specification
ichnos:
  adr_number: 4
---

# Context

Ichnos reads repository content, Issues and pull requests from Phase 2, and writes Issues, branches and pull requests from Phase 4. The technical specification left open whether to use GitHub OAuth, personal access tokens, or both, to be settled in Phase 1.[^techspec] A self-hosted MVP typically has one operator and no public callback URL.

# Options considered

1. **Classic PAT.** Simple, but scopes are coarse: `repo` grants access to every repository of the owner.
2. **Fine-grained PAT.** Limited to selected repositories and individual permissions, with an expiry date.
3. **OAuth app.** Per-user identity, but needs a registered app, a callback URL and session handling.
4. **GitHub App.** The best long-term model, with installation tokens per repository, but heavier setup for a first self-host.

# Decision

The MVP uses one fine-grained PAT, supplied as `ICHNOS_GITHUB_TOKEN` in `.env`.

- The token is read from the environment only. It is never stored in SQLite, never logged, and never returned by the API or sent to the browser. The UI shows only whether a token is configured and whether it can reach the workspace repository.
- Setup is read-only: Metadata, Contents, Issues and Pull requests with read access. Write access is added only when Phase 4 introduces approved writes, and the self-hosting guide documents that change.
- The GitHub client sits behind one interface, so OAuth or a GitHub App can replace the token later without touching callers.

# Consequences

- **Positive:** least-privilege access limited to one repository; no OAuth infrastructure; works fully offline from GitHub's auth flows.
- **Negative:** every GitHub write appears as the token owner, so the Ichnos audit log must record which local user approved each action; tokens expire and must be rotated by hand.
- **Revisit:** when one installation serves several human users.

[^techspec]: Ichnos MVP — Technical Specification
