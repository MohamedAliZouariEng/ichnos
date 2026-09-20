---
type: Decision
title: "ADR-0023: Trace validation flags gaps; people confirm inferred links in Ichnos"
description: The trace reports missing links, acceptance criteria without tests, unconfirmed inferred links, stale or unverified sources and failing checks; a person's confirmation of an inferred link is stored and audited in Ichnos only.
tags: [adr, traceability, validation, audit]
status: stable
generated: { by: claude/opus-5, at: 2026-09-20T09:39:28Z }
verified: { by: human:MohamedAliZouariEng, at: 2026-09-20T09:39:28Z }
sources:
  - id: adr-0010
    resource: /adr/0010-knowledge-links-provenance.md
    title: "ADR-0010: Knowledge links record origin, evidence and confidence"
  - id: adr-0015
    resource: /adr/0015-pending-actions-and-one-write-client.md
    title: "ADR-0015: Every GitHub write is an approved pending action, executed by one write client"
ichnos:
  adr_number: 23
---

# Context

Inferred links carry a confidence below one and the evidence that produced them.[^adr-0010] A trace that treats them like explicit links overstates what is known. Writing to GitHub needs an approved action,[^adr-0015] which is heavy for a reviewer's judgement about one link.

# Decision

- Validation reports, for each trace: requirements without a Story, Stories without a pull request, acceptance criteria without a test, inferred links nobody confirmed, stale or unverified sources, and failing checks. Each finding names the row and the missing or weak evidence.
- A signed-in person can confirm an inferred link, with an optional note. The confirmation records who and when, is written to the audit log, and can be withdrawn.
- Confirmations live in Ichnos only and are never written to GitHub. They are keyed by the link's identity (source, target and relation), so they survive a knowledge reset and resync.

# Consequences

- **Positive:** the trace separates what is written down from what is guessed, and a reviewer's judgement is kept without a repository write.
- **Negative:** confirmations are not visible on GitHub; people outside Ichnos see only the explicit links.

[^adr-0010]: ADR-0010: Knowledge links record origin, evidence and confidence
[^adr-0015]: ADR-0015: Every GitHub write is an approved pending action, executed by one write client
