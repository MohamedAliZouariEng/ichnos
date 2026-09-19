---
type: Decision
title: "ADR-0020: Implementation plans are Ichnos artifacts; code enforces the acceptance-criteria mapping"
description: A model proposes the implementation plan from a context pack; code enforces that every acceptance criterion is mapped and every file is known or marked new; plans stay in Ichnos, and durable decisions become ADRs.
tags: [adr, planning, workflows, artifacts]
status: stable
generated: { by: claude/opus-5, at: 2026-09-19T23:34:26Z }
verified: { by: human:MohamedAliZouariEng, at: 2026-09-19T23:34:26Z }
sources:
  - id: adr-0012
    resource: /adr/0012-model-providers.md
    title: "ADR-0012: Model providers: one OpenAI-compatible adapter, structured output, Gemini by default"
  - id: adr-0014
    resource: /adr/0014-drafts-and-versions.md
    title: "ADR-0014: Drafts and versions live in SQLite until approved"
ichnos:
  adr_number: 20
---

# Context

A context pack says what exists; the engineer also needs a plan: files to change, data and API changes, steps, tests, risks and open questions. Ichnos already drafts BRDs with a model returning structured output that code then checks,[^adr-0012] and keeps drafts as versioned artifacts.[^adr-0014]

# Decision

- The model receives the Story and its context pack and returns a structured plan: files to change, data and API changes, ordered steps, test strategy, risks, open questions, and a mapping from each acceptance criterion to steps and tests.
- Code enforces the plan: every acceptance criterion of the Story maps to at least one step or test, and an unmapped one becomes an open question; every file to change is in the pack or marked `new`; every claim cites pack items (`P1`…), and claims citing unknown items are dropped with a note.
- The plan is an artifact of kind `implementation-plan`, rendered as Markdown with append-only versions, stored with the hash of the pack it used. It stays in Ichnos and is never committed to the repository.
- A decision that should outlive the Story is proposed as a new ADR, written as an OKF `Decision` concept and published through the usual approved documentation pull request.

# Consequences

- **Positive:** no acceptance criterion is silently skipped; the plan names only files that exist or says they are new.
- **Negative:** people outside Ichnos see only the plan's summary in the pull request, not the full plan.

[^adr-0012]: ADR-0012: Model providers: one OpenAI-compatible adapter, structured output, Gemini by default
[^adr-0014]: ADR-0014: Drafts and versions live in SQLite until approved
