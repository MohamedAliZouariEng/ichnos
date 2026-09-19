---
type: Decision
title: "ADR-0018: No Slack in the first release; notifications come through a later adapter"
description: The first release notifies only in the Ichnos UI and on GitHub; Slack and other channels arrive later through one notification adapter.
tags: [adr, notifications, scope]
status: stable
generated: { by: claude/opus-5, at: 2026-09-19T21:22:44Z }
verified: { by: human:MohamedAliZouariEng, at: 2026-09-19T21:22:44Z }
sources:
  - id: techspec
    resource: /specs/ichnos-mvp/techspec.md
    title: Ichnos MVP — Technical Specification
ichnos:
  adr_number: 18
---

# Context

The technical specification left open whether Slack belongs in the first release, to be settled in Phase 4.[^techspec] Approvals happen in the Approval Center, and every write is visible on GitHub as a pull request or Issue.

# Decision

- The first release has no Slack integration. Pending approvals are shown in the Ichnos UI; GitHub notifies people about pull requests and Issues as usual.
- A later notification adapter will send the same events (approval requested, action executed, run failed) to Slack or other channels, without changing the approval flow.

# Consequences

- **Positive:** smaller release, no third-party app to register, no extra secret.
- **Negative:** approvers must open Ichnos to see pending actions.

[^techspec]: Ichnos MVP — Technical Specification
