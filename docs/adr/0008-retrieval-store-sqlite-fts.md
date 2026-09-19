---
type: Decision
title: "ADR-0008: Retrieval store: SQLite full-text search now, embeddings in Phase 3"
description: Knowledge is indexed with SQLite FTS5 over heading-sized chunks in the metadata database; embeddings are added in Phase 3.
tags: [adr, retrieval, search, sqlite]
status: stable
generated: { by: claude/opus-5, at: 2026-09-19T15:47:02Z }
verified: { by: human:MohamedAliZouariEng, at: 2026-09-19T15:47:02Z }
sources:
  - id: techspec
    resource: /specs/ichnos-mvp/techspec.md
    title: Ichnos MVP — Technical Specification
ichnos:
  adr_number: 8
---

# Context

Phase 2 must make repository documents and GitHub history searchable. The technical specification left the default retrieval store open until Phase 2.[^techspec] The PRD rules out managed vector or graph databases, every index must be rebuildable from GitHub (ADR-0002), and model calls, including embeddings, only start in Phase 3 (ADR-0006).

# Options considered

1. **SQLite with embeddings now.** Semantic search from the start, but it forces an embedding provider into Phase 2 and blocks sync on model configuration.
2. **SQLite FTS5 now, embeddings added in Phase 3.** Lexical search that works offline with no model; semantic search joins it later in the same database.
3. **A local graph or RAG engine (LightRAG, Kuzu).** Rich retrieval, but a new dependency whose storage duplicates what OKF links already express.
4. **A separate vector database service.** Adds a container and operational work to a stack meant to stay small.

# Decision

- Documents and GitHub text are split into chunks at Markdown headings and indexed with SQLite **FTS5** (BM25 ranking) in the existing metadata database.
- The relationship graph is stored as rows in a `links` table (ADR-0010); graph queries are SQL joins, not a graph engine.
- In Phase 3, embeddings are added in the same database, and search combines both scores (hybrid retrieval). The chunk table is designed so that vectors attach to existing chunks.
- All knowledge tables are derived data. Resetting them and syncing again must rebuild the same index.

# Consequences

- **Positive:** no model or extra service needed in Phase 2; search works offline; one database file to back up.
- **Negative:** lexical search misses synonyms and paraphrases until embeddings arrive.
- **Requirement:** the Python `sqlite3` module must include FTS5; the API checks this at startup and reports it in `/healthz`.

[^techspec]: Ichnos MVP — Technical Specification
