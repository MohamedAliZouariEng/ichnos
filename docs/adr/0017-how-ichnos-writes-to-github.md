---
type: Decision
title: "ADR-0017: Ichnos writes through pull requests and conventional Issues, and never merges"
description: Documentation is proposed as one atomic commit on a new branch with a pull request; Issues follow the body convention and labels; a human merges on GitHub.
tags: [adr, github, pull-requests, issues]
status: stable
generated: { by: claude/opus-5, at: 2026-09-19T21:22:44Z }
verified: { by: human:MohamedAliZouariEng, at: 2026-09-19T21:22:44Z }
sources:
  - id: adr-0015
    resource: /adr/0015-pending-actions-and-one-write-client.md
    title: "ADR-0015: Every GitHub write is an approved pending action, executed by one write client"
  - id: adr-0010
    resource: /adr/0010-knowledge-links-provenance.md
    title: "ADR-0010: Knowledge links record origin, evidence and confidence"
ichnos:
  adr_number: 17
---

# Context

Approved artifacts must reach the repository as OKF concepts, and approved plans as Issues, in forms that Ichnos's own sync and link extraction read back (ADR-0010).[^adr-0010] Writes happen only through approved pending actions (ADR-0015).[^adr-0015]

# Decision

- **Documentation** is written on a new branch `ichnos/<slug>-<short id>` as **one commit** built with the Git Data API (blobs, tree, commit, ref), so every file of a package lands together or not at all. A pull request against the default branch describes the change, lists the sources and requirements, and carries the AI disclosure line.
- **Ichnos never merges and never pushes to the default branch.** A human reviews and merges on GitHub; the repository's own checks run on the pull request.
- **Issues** use the body convention that sync already parses: `## Parent` with `- Epic: #N`, `## Source specification` with the BRD path, the requirement IDs they implement, and acceptance criteria as a checklist. Labels are `type:epic` or `type:story`, `status:draft` and `agent:generated`.
- The Epic is created first; Stories reference its number. Numbers and URLs are recorded on the action and the run, and written into the BRD's `ichnos` extension by a follow-up approved documentation change.
- A workspace that publishes needs a token with Contents, Pull requests and Issues write access to its repository only; reading stays possible with a read-only token.

# Consequences

- **Positive:** every change is reviewable on GitHub with its diff and checks; nothing lands half-written.
- **Negative:** a human must merge each documentation pull request.

[^adr-0010]: ADR-0010: Knowledge links record origin, evidence and confidence
[^adr-0015]: ADR-0015: Every GitHub write is an approved pending action, executed by one write client
