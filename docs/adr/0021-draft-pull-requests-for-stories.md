---
type: Decision
title: "ADR-0021: A Story's draft pull request starts with an empty commit and claims no code changes"
description: Ichnos opens a Story's draft pull request only after approval, from an empty first commit, with an evidence table where every acceptance criterion is not started; it never marks the pull request ready or merges it.
tags: [adr, github, pull-requests, honesty]
status: stable
generated: { by: claude/opus-5, at: 2026-09-19T23:34:26Z }
verified: { by: human:MohamedAliZouariEng, at: 2026-09-19T23:34:26Z }
sources:
  - id: adr-0015
    resource: /adr/0015-pending-actions-and-one-write-client.md
    title: "ADR-0015: Every GitHub write is an approved pending action, executed by one write client"
  - id: adr-0017
    resource: /adr/0017-how-ichnos-writes-to-github.md
    title: "ADR-0017: Ichnos writes through pull requests and conventional Issues, and never merges"
ichnos:
  adr_number: 21
---

# Context

The delivery plan's Phase 5 exit criterion is that Ichnos opens a draft pull request linked to the Story after approval, and never claims code changed before a real repository action. GitHub needs a commit on a branch to open a pull request. Every write is an approved pending action[^adr-0015] and Ichnos never merges.[^adr-0017]

# Decision

- A new action type, `draft_pull_request`, creates a branch `ichnos/story-<number>-<slug>` from the default branch, adds one empty commit whose tree equals the base tree ("Start Story #<number>; no code changes yet"), and opens a draft pull request.
- The body follows the convention: `Closes #<number>`, an acceptance-criteria evidence table where every row is *Not started*, the context used (pack items with their trust tiers), a summary of the plan with its version and hash, and AI disclosure.
- Honesty rule: nothing Ichnos writes may state or imply that code changed. The executor checks that the commit's tree equals the base tree before opening the pull request, and a test rejects bodies that claim changes, completed criteria or passing tests.
- Ichnos never marks the pull request ready for review and never merges it; the engineer pushes the code.

# Consequences

- **Positive:** the pull request links the Story, its context and its plan from the first minute, and shows 0 files changed until a person pushes code.
- **Negative:** the pull request carries an empty commit, which a squash merge removes.

[^adr-0015]: ADR-0015: Every GitHub write is an approved pending action, executed by one write client
[^adr-0017]: ADR-0017: Ichnos writes through pull requests and conventional Issues, and never merges
