# Architecture Decision Records

* [ADR-0001: Adopt OKF for repository documentation](0001-adopt-okf-for-documentation.md) - All repository documentation is an Open Knowledge Format v0.2 bundle in docs/.
* [ADR-0002: GitHub is the canonical source of truth](0002-github-is-canonical.md) - Issues, pull requests, commits and repository files are canonical; Ichnos indexes are rebuildable projections.
* [ADR-0003: LangGraph for workflow orchestration](0003-langgraph-for-orchestration.md) - The Ichnos agent workflow is a LangGraph state graph with persisted checkpoints and human-approval interrupts.
* [ADR-0004: GitHub access through a fine-grained personal access token](0004-github-access-fine-grained-pat.md) - The MVP authenticates to GitHub with one fine-grained PAT from the environment, read-only until approved writes need more.
* [ADR-0005: One repository per workspace](0005-one-repository-per-workspace.md) - A workspace is exactly one GitHub repository and branch; an installation may hold several workspaces.
* [ADR-0006: Ollama as an optional Docker Compose profile](0006-ollama-optional-compose-profile.md) - Local models run through an ollama service in an opt-in Compose profile; the default stack does not start it.
* [ADR-0007: Monorepo tooling with pnpm workspaces and uv](0007-monorepo-tooling-pnpm-uv.md) - TypeScript packages use pnpm workspaces, the Python API uses uv, and a root Makefile is the single entry point.
* [ADR-0008: Retrieval store: SQLite full-text search now, embeddings in Phase 3](0008-retrieval-store-sqlite-fts.md) - Knowledge is indexed with SQLite FTS5 over heading-sized chunks in the metadata database; embeddings are added in Phase 3.
* [ADR-0009: GitHub sync: on-demand, incremental and idempotent over REST](0009-github-sync-strategy.md) - Ichnos pulls repository files and GitHub history on demand over REST, compares files by blob hash, fetches history by cursors, and upserts idempotently.
* [ADR-0010: Knowledge links record origin, evidence and confidence](0010-knowledge-links-provenance.md) - All relationships live in one links table; each link is explicit or inferred and carries its evidence and a confidence value.
