---
type: Decision
title: "ADR-0024: Answers are grounded: every statement cites a retrieved source, and gaps are stated"
description: Questions are answered from retrieved documents, Issues, pull requests and trace rows; code drops statements without a valid source and every answer lists missing, conflicting or stale evidence.
tags: [adr, answers, retrieval, citations]
status: stable
generated: { by: claude/opus-5, at: 2026-09-20T09:39:28Z }
verified: { by: human:MohamedAliZouariEng, at: 2026-09-20T09:39:28Z }
sources:
  - id: adr-0012
    resource: /adr/0012-model-providers.md
    title: "ADR-0012: Model providers: one OpenAI-compatible adapter, structured output, Gemini by default"
  - id: adr-0019
    resource: /adr/0019-context-packs.md
    title: "ADR-0019: Context packs are assembled by code from synced knowledge, with provenance on every item"
ichnos:
  adr_number: 24
---

# Context

The delivery plan asks for answers that cite paths, Issue and pull request URLs and OKF sources, and that say when evidence is missing, conflicting or stale. Ichnos already asks models for structured output that code checks,[^adr-0012] and already numbers every piece of context it hands a model.[^adr-0019]

# Decision

- Retrieval gathers numbered sources for a question: document chunks with their heading, Issues and pull requests, and trace rows, each with its trust tier and flags.
- The model answers as a list of statements, each citing source numbers. Code drops a statement with no valid citation and notes it; an answer with no remaining statement says that no evidence was found.
- Every answer lists its gaps: parts of the question without evidence, sources that disagree, and sources that are stale, unverified or inferred.
- Citations are rendered as links: document paths with heading anchors at the synced commit, Issue and pull request URLs, and footnotes for OKF sources. Answers are kept in Ichnos; nothing is written to GitHub.

# Consequences

- **Positive:** every sentence of an answer can be followed to its source, and uncertainty is visible.
- **Negative:** answers are shorter than free text, and a question outside the synced knowledge gets a stated gap instead of a guess.

[^adr-0012]: ADR-0012: Model providers: one OpenAI-compatible adapter, structured output, Gemini by default
[^adr-0019]: ADR-0019: Context packs are assembled by code from synced knowledge, with provenance on every item
