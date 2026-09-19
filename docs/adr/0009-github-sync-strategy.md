---
type: Decision
title: "ADR-0009: GitHub sync: on-demand, incremental and idempotent over REST"
description: Ichnos pulls repository files and GitHub history on demand over REST, compares files by blob hash, fetches history by cursors, and upserts idempotently.
tags: [adr, github, sync]
status: stable
generated: { by: claude/opus-5, at: 2026-09-19T15:47:02Z }
verified: { by: human:MohamedAliZouariEng, at: 2026-09-19T15:47:02Z }
sources:
  - id: brd
    resource: /specs/ichnos-mvp/brd.md
    title: Ichnos MVP — Business Requirements
ichnos:
  adr_number: 9
---

# Context

FR-2 requires synchronizing repository documents, Issues, comments, labels, milestones, pull requests, reviews, commits and changed files, incrementally and idempotently, while preserving URLs, paths, SHAs, authors and timestamps.[^brd] Ichnos typically runs on `127.0.0.1` with a read-only fine-grained token (ADR-0004).

# Options considered

1. **Webhooks.** Near real-time, but a local installation has no public URL to receive them.
2. **GraphQL bulk queries.** Fewer requests, but more complex pagination and cost accounting.
3. **REST polling on demand, with cursors and conditional requests.** Simple, well documented, and cheap when nothing changed.

# Decision

- **Trigger:** sync runs on demand (UI button or `POST /api/workspaces/{id}/sync`). Each run is recorded in `runs` with counts and errors, and audited.
- **Repository files:** read the branch head commit. If it matches the last synced commit, skip. Otherwise read the recursive tree, keep files under the workspace's index paths with a `.md` or `.txt` extension, fetch only blobs whose SHA changed, and delete documents that left the tree.
- **History:** Issues and pull requests are fetched with `state=all&since=<cursor>`; comments by their own cursor; for each changed pull request, its reviews, changed files and commits.
- **Idempotency:** every record is upserted by a stable key (path, Issue or pull request number, commit SHA, GitHub ID). A cursor advances only after the transaction that stored its data commits, and it overlaps the previous window slightly; re-reading overlap is harmless.
- **Rate limits:** requests use ETags where possible; the run stops cleanly with a clear message when the remaining quota runs out, instead of retrying blindly.

# Consequences

- **Positive:** works on any machine, including offline laptops between syncs; running a sync twice changes nothing.
- **Negative:** data is only as fresh as the last sync; the first sync of a large repository makes many requests.
- **Revisit:** scheduled sync, GraphQL, or webhooks when Ichnos runs on a reachable server.

[^brd]: Ichnos MVP — Business Requirements
