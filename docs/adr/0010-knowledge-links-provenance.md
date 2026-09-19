---
type: Decision
title: "ADR-0010: Knowledge links record origin, evidence and confidence"
description: All relationships live in one links table; each link is explicit or inferred and carries its evidence and a confidence value.
tags: [adr, traceability, graph]
status: stable
generated: { by: claude/opus-5, at: 2026-09-19T15:47:02Z }
verified: { by: human:MohamedAliZouariEng, at: 2026-09-19T15:47:02Z }
sources:
  - id: techspec
    resource: /specs/ichnos-mvp/techspec.md
    title: Ichnos MVP — Technical Specification
ichnos:
  adr_number: 10
---

# Context

Traceability depends on relationships between documents, Issues, pull requests, commits and files. The technical specification states that explicit links are authoritative, and that inferred links must carry evidence and confidence and stay distinguishable from confirmed ones.[^techspec]

# Decision

Every relationship is one row in a `links` table with:

- **source** and **target**: a node kind (`document`, `issue`, `pull_request`, `commit`, `file`) and its key (path, number or SHA);
- **relation**: `references`, `cites`, `parent`, `closes`, `changes` or `mentions`;
- **origin**: `explicit` or `inferred`;
- **evidence**: where the link was found, with a short excerpt;
- **confidence**: `1.0` for explicit links, lower for inferred ones;
- **resolved**: whether the target exists in the synced data.

Explicit links come from OKF Markdown links, OKF `sources`, GitHub closing keywords (`Closes #N`), the Issue body conventions (`## Parent`, `## Source specification`), and pull request changed files. Inferred links come from references found in prose, such as a bare `#12` or a repository path outside those conventions.

Links are derived data: they are extracted again from the source text on every sync and never edited in place. Unresolved targets are kept, because in OKF a missing target is knowledge not yet written.

# Consequences

- **Positive:** one query answers "what is connected to this?"; the UI can always show why a link exists.
- **Negative:** confidence values for inferred links are heuristic until humans confirm links (Phase 6).
- **Follow-up:** human confirmation turns an inferred link into an explicit one through the approval flow.

[^techspec]: Ichnos MVP — Technical Specification
