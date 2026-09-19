---
type: Decision
title: "ADR-0019: Context packs are assembled by code from synced knowledge, with provenance on every item"
description: A Story's context pack is built without a model from synced documents, GitHub history and the repository tree; every item carries its source, trust tier and flags.
tags: [adr, context, retrieval, code]
status: stable
generated: { by: claude/opus-5, at: 2026-09-19T23:34:26Z }
verified: { by: human:MohamedAliZouariEng, at: 2026-09-19T23:34:26Z }
sources:
  - id: adr-0009
    resource: /adr/0009-github-sync-strategy.md
    title: "ADR-0009: GitHub sync: on-demand, incremental and idempotent over REST"
  - id: adr-0010
    resource: /adr/0010-knowledge-links-provenance.md
    title: "ADR-0010: Knowledge links record origin, evidence and confidence"
ichnos:
  adr_number: 19
---

# Context

An engineer implementing one Story needs its Epic, requirements, decisions, related work and code in one place, and needs to know how far to trust each part. Ichnos already syncs documents and GitHub history incrementally[^adr-0009] and records every relationship with its evidence.[^adr-0010] It does not yet know the repository's code.

# Decision

- A context pack is assembled by code, with no model call, from what the last sync stored: the Story, its parent Epic, an Initiative if one exists, the BRD and techspec it references, ADRs (`type: Decision`) found by retrieval over the Story's text, related Issues and pull requests (parents, children, `Depends on` links and mentions), and code files.
- Sync also records the repository tree: path, blob SHA, size and language of each file outside `docs/`, compared by blob SHA like documents. File contents are fetched only for the files a pack selects, up to 20 files and 40 KB each.
- Code files are selected by paths that the Story, its documents or related pull requests mention, then by keyword matches on file names; each selection keeps its reason.
- Every item gets an identifier (`P1`, `P2`…), its source reference (path and blob SHA, or Issue or pull request number), its trust tier, and flags: `stale` when past `stale_after`, `unverified` when no human `verified` is present. Parts that do not exist are listed as absent, never invented.
- `Depends on #N` in an Issue body becomes an explicit `depends_on` link.
- A pack is stored with the SHA-256 of its canonical JSON, so later work can say exactly which pack it used.

# Consequences

- **Positive:** packs are reproducible and cost no tokens; every statement built on a pack can be traced to a file version or an Issue.
- **Negative:** selection by mentions and names can miss relevant code; the pack shows why each file was chosen so a person can add what is missing.
- Syncing the tree adds one recursive tree request per sync; contents are never stored for unselected files.

[^adr-0009]: ADR-0009: GitHub sync: on-demand, incremental and idempotent over REST
[^adr-0010]: ADR-0010: Knowledge links record origin, evidence and confidence
