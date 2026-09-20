---
type: Decision
title: "ADR-0022: Traceability is assembled by code from recorded links, with status and evidence on every row"
description: Requirement, Epic, Story, acceptance criterion, pull request, commit and test are joined without a model from synced links, bodies and CI check runs; each row carries its status and evidence.
tags: [adr, traceability, links, testing]
status: stable
generated: { by: claude/opus-5, at: 2026-09-20T09:39:28Z }
verified: { by: human:MohamedAliZouariEng, at: 2026-09-20T09:39:28Z }
sources:
  - id: adr-0010
    resource: /adr/0010-knowledge-links-provenance.md
    title: "ADR-0010: Knowledge links record origin, evidence and confidence"
  - id: adr-0019
    resource: /adr/0019-context-packs.md
    title: "ADR-0019: Context packs are assembled by code from synced knowledge, with provenance on every item"
  - id: adr-0021
    resource: /adr/0021-draft-pull-requests-for-stories.md
    title: "ADR-0021: A Story's draft pull request starts with an empty commit and claims no code changes"
ichnos:
  adr_number: 22
---

# Context

Earlier phases record the pieces of a trace: links with their origin and evidence,[^adr-0010] Story context packs,[^adr-0019] and draft pull requests that close their Story and list its acceptance criteria.[^adr-0021] The delivery plan asks for Requirement, Epic, Story, acceptance criterion, pull request, commit and test in one view, with status and evidence per row.

# Decision

- The trace is built by code, with no model call, from synced knowledge, and hashed like a context pack.
- A requirement is a `## R-NN` heading of a BRD, identified as the BRD path with a heading anchor. A Story implements the requirements it lists under `## Requirements`; its parent link gives the Epic.
- Acceptance criteria are the `AC-NN` items of the Story body. A pull request belongs to the Story it closes; its commits come from the synced pull request commits.
- Test evidence has three sources, in decreasing strength: test paths named in the pull request's acceptance criteria evidence table (explicit), changed files that look like tests (inferred), and the pull request head's CI check runs (passing, failing or pending).
- Every row has a status (for example requirement approved, Story open, criterion not started or evidenced, pull request draft or merged, tests passing) and the evidence behind it, with its source.
- There is no graph explorer in the first release; no workflow depends on one.

# Consequences

- **Positive:** a trace is reproducible and free; every status can be checked against its source.
- **Negative:** a trace is only as complete as the conventions people follow; the validation in ADR-0023 makes gaps visible instead of hiding them.

[^adr-0010]: ADR-0010: Knowledge links record origin, evidence and confidence
[^adr-0019]: ADR-0019: Context packs are assembled by code from synced knowledge, with provenance on every item
[^adr-0021]: ADR-0021: A Story's draft pull request starts with an empty commit and claims no code changes
