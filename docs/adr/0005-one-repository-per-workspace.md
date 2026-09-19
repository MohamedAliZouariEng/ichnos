---
type: Decision
title: "ADR-0005: One repository per workspace"
description: A workspace is exactly one GitHub repository and branch; an installation may hold several workspaces.
tags: [adr, workspace, data-model]
status: stable
generated: { by: claude/opus-5, at: 2026-09-19T13:13:45Z }
verified: { by: human:MohamedAliZouariEng, at: 2026-09-19T13:13:45Z }
sources:
  - id: techspec
    resource: /specs/ichnos-mvp/techspec.md
    title: Ichnos MVP — Technical Specification
ichnos:
  adr_number: 5
---

# Context

FR-1 requires configuring one or more GitHub repositories. The technical specification left open whether a single workspace may span several repositories.[^techspec] That choice shapes the data model, sync cursors, permission checks and traceability queries from Phase 1 onward.

# Options considered

1. **Many repositories per workspace.** Enables cross-repository traceability, but multiplies sync state, permission checks and link-resolution rules.
2. **One repository per workspace, several workspaces per installation.** Simple model; FR-1 is met by adding more workspaces.

# Decision

A workspace is exactly one repository and one branch, plus its settings: paths to index, model provider and embedding provider. An installation can hold several workspaces. Traceability links resolve within one workspace; references to other repositories are kept as external links.

# Consequences

- **Positive:** one sync cursor set, one permission check and one OKF bundle per workspace; simple queries and UI.
- **Negative:** products split across several repositories cannot be traced end to end in the MVP.
- **Revisit:** if users need cross-repository traceability after the MVP evaluation.

[^techspec]: Ichnos MVP — Technical Specification
