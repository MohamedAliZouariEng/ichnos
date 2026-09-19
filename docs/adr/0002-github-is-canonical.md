---
type: Decision
title: "ADR-0002: GitHub is the canonical source of truth"
description: Issues, pull requests, commits and repository files are canonical; Ichnos indexes are rebuildable projections.
tags: [adr, github, architecture]
status: stable
generated: { by: claude/opus-5, at: __NOW__ }
verified: { by: human:MohamedAliZouariEng, at: __NOW__ }
sources:
  - id: brd
    resource: /specs/ichnos-mvp/brd.md
    title: Ichnos MVP — Business Requirements
ichnos:
  adr_number: 2
---

# Context

Ichnos links requirements, Issues, pull requests, commits and tests. If Ichnos kept its own copy of these as the primary record, teams would face two sources of truth, lock-in, and drift between the tool and the repository.[^brd]

# Options considered

1. **Ichnos database as the primary record, synced to GitHub.** Richer modelling, but creates a competing source of truth.
2. **GitHub and repository files as canonical, Ichnos as a derived projection.** Less modelling freedom, but no lock-in and a single place to review changes.

# Decision

GitHub Issues, pull requests, commits, and the repository's files and history are canonical. Ichnos's SQLite data, vector index and link graph are projections that can be deleted and rebuilt from GitHub and the repository at any time.

Operational data that GitHub does not hold (workflow runs, drafts before approval, approval decisions and the audit log) is owned by Ichnos and persisted in SQLite. It is never treated as the record of a requirement or decision.

# Consequences

- **Positive:** no lock-in; teams keep their existing GitHub workflow; review happens where code review already happens; indexes can be rebuilt after corruption or upgrades.
- **Negative:** Ichnos depends on GitHub API availability and rate limits; sync must be incremental and idempotent; GitLab and other forges are out of scope for the MVP.
- **Rule:** every Ichnos feature must work if the local index is deleted and resynced.

[^brd]: Ichnos MVP — Business Requirements
