---
type: Decision
title: "ADR-0014: Drafts and versions live in SQLite until approved"
description: Intake sources are immutable, artifacts follow the specification lifecycle, and every edit creates a new validated version; the repository changes only after approval.
tags: [adr, artifacts, versioning, review]
status: stable
generated: { by: claude/opus-5, at: 2026-09-19T19:42:04Z }
verified: { by: human:MohamedAliZouariEng, at: 2026-09-19T19:42:04Z }
sources:
  - id: techspec
    resource: /specs/ichnos-mvp/techspec.md
    title: Ichnos MVP — Technical Specification
  - id: adr-0002
    resource: /adr/0002-github-is-canonical.md
    title: "ADR-0002: GitHub is the canonical source of truth"
ichnos:
  adr_number: 14
---

# Context

Generated artifacts start as drafts and only a human action approves them; drafts and rejected artifacts live in SQLite, and approved ones reach the repository as OKF.[^techspec] The technical specification left open how browser edits are stored before approval. GitHub stays the source of truth for approved knowledge (ADR-0002).[^adr-0002]

# Decision

- **Sources are immutable.** Every intake (pasted text, upload, or synced document) becomes a source record with its text, origin and SHA-256 hash. Workflows cite sources by ID; editing a note means creating a new source.
- **Artifacts follow the lifecycle** draft → needs-review → approved → deprecated, or rejected.
- **Versions are append-only.** Each version stores the full Markdown, its origin (`generated` or `edited`), the actor (`ichnos/<model>` or `human:<id>`), its parent version and its OKF findings. Diffs are computed between versions, never stored.
- **The repository changes only after approval** (Phase 4). A pasted meeting note is proposed as a new `docs/meetings/` concept and written together with the approved BRD.

# Consequences

- **Positive:** every draft can be traced to the exact text it came from; review shows who changed what; rejected work never touches the repository.
- **Negative:** drafts exist only in the Ichnos database until approved, so backups matter during review.

[^techspec]: Ichnos MVP — Technical Specification
[^adr-0002]: ADR-0002: GitHub is the canonical source of truth
