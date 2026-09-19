---
type: Technical Specification
title: Ichnos MVP — Technical Specification
description: Information model, agent workflow, architecture, API, GitHub conventions and security design for the Ichnos MVP.
tags: [ichnos, mvp, architecture, langgraph, okf]
status: stable
generated: { by: claude/opus-5, at: 2026-09-19T21:22:44Z }
verified: { by: human:MohamedAliZouariEng, at: 2026-09-19T21:22:44Z }
sources:
  - id: prd
    resource: https://docs.sylergy.net/s/documentation/p/athar-XwmmVmIjhs
    title: Product Requirements Document v0.1 (written under the working name Athar)
  - id: brd
    resource: /specs/ichnos-mvp/brd.md
    title: Ichnos MVP — Business Requirements
  - id: okf-spec
    resource: https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md
    title: Open Knowledge Format specification v0.2
ichnos:
  artifact_id: techspec-ichnos-mvp
  implements: [FR-1, FR-2, FR-3, FR-4, FR-5, FR-6, FR-7, FR-8, FR-9, FR-10, FR-11, FR-12, FR-13, FR-14, FR-15]
---

# Overview

This specification describes how Ichnos implements the [business requirements](/specs/ichnos-mvp/brd.md).[^brd] It is derived from the original PRD.[^prd]

Key decisions are recorded as ADRs:

- [ADR-0001: Adopt OKF for repository documentation](/adr/0001-adopt-okf-for-documentation.md)
- [ADR-0002: GitHub is the canonical source of truth](/adr/0002-github-is-canonical.md)
- [ADR-0003: LangGraph for workflow orchestration](/adr/0003-langgraph-for-orchestration.md)
- [ADR-0004: GitHub access through a fine-grained PAT](/adr/0004-github-access-fine-grained-pat.md)
- [ADR-0005: One repository per workspace](/adr/0005-one-repository-per-workspace.md)
- [ADR-0006: Ollama as an optional Compose profile](/adr/0006-ollama-optional-compose-profile.md)
- [ADR-0007: Monorepo tooling with pnpm and uv](/adr/0007-monorepo-tooling-pnpm-uv.md)
- [ADR-0008: Retrieval store: SQLite full-text search now](/adr/0008-retrieval-store-sqlite-fts.md)
- [ADR-0009: GitHub sync strategy](/adr/0009-github-sync-strategy.md)
- [ADR-0010: Knowledge links record origin, evidence and confidence](/adr/0010-knowledge-links-provenance.md)
- [ADR-0011: Workflow engine](/adr/0011-workflow-engine.md)
- [ADR-0012: Model providers](/adr/0012-model-providers.md)
- [ADR-0013: Live run updates through Server-Sent Events](/adr/0013-live-run-updates.md)
- [ADR-0014: Drafts and versions live in SQLite until approved](/adr/0014-drafts-and-versions.md)
- [ADR-0015: Pending actions and one write client](/adr/0015-pending-actions-and-one-write-client.md)
- [ADR-0016: Approver session and identity](/adr/0016-approver-session-and-identity.md)
- [ADR-0017: How Ichnos writes to GitHub](/adr/0017-how-ichnos-writes-to-github.md)
- [ADR-0018: Slack deferred](/adr/0018-slack-deferred.md)

# Information model

## Canonical artifacts

| Artifact | Location | OKF type |
| --- | --- | --- |
| Initiative | GitHub Issue, label `type:initiative` | — (GitHub) |
| Epic | GitHub Issue, label `type:epic` | — (GitHub) |
| Story | GitHub Issue, label `type:story` | — (GitHub) |
| Acceptance criterion | Story body, `AC-NN` | — (GitHub) |
| BRD | `docs/specs/<slug>/brd.md` | `BRD` |
| Technical specification | `docs/specs/<slug>/techspec.md` | `Technical Specification` |
| ADR | `docs/adr/<NNNN>-<slug>.md` | `Decision` |
| Meeting note | `docs/meetings/<YYYY-MM-DD>-<slug>.md` | `Meeting Note` |
| Project guide | `docs/project/<slug>.md` | `Reference` or `Howto` |
| Pull request | GitHub | — (GitHub) |
| Commit | Git | — (Git) |
| Test | Repository and CI run | — (code) |

## Relationships

- Initiative contains Epic; Epic contains Story.
- BRD defines Requirement; Story implements Requirement.
- Story has Acceptance Criterion; Test verifies Acceptance Criterion.
- ADR constrains Technical Specification or Story.
- Pull Request implements Story and changes Code Module.
- Meeting Note supports Requirement or Decision.
- Artifact supersedes Artifact.

Explicit links (OKF Markdown links, `sources`, Issue parent sections, `Closes #N`) are authoritative. Inferred links carry evidence and confidence metadata and are shown as distinct from human-confirmed links.

## Artifact lifecycle

```text
draft → needs-review → approved → deprecated
            ↘ rejected
```

Generated content starts as `draft`. Only a human action moves it to `approved`.

| Ichnos state | Where it lives | OKF representation |
| --- | --- | --- |
| draft, needs-review | SQLite only | `status: draft`, `ichnos.review_state` |
| approved | Repository, via an approved PR | `status: stable` + `verified: { by: human:<login> }` |
| deprecated | Repository | `status: deprecated` + `ichnos.superseded_by` |
| rejected | Run audit log only | Never written to the repository |

# Documentation convention (OKF)

Every `docs/` directory Ichnos manages is an OKF v0.2 bundle.[^okf-spec]

- The root `index.md` declares `okf_version: "0.2"`; `index.md` and `log.md` are reserved at every level.
- Conformance: every non-reserved `.md` has parseable frontmatter with a non-empty `type`; reserved files follow the spec structure.
- `generated: { by, at }` records who wrote the content: `ichnos/<model>` for the agent, `human:<login>` for people.
- `verified` entries record confirmation; only the approval service writes `human:` entries on behalf of the approving user.
- `sources[]` entries have a stable `id`; claims cite them with footnotes `[^id]`.
- Links between concepts use bundle-relative paths (`/specs/<slug>/brd.md`).
- Ichnos-specific metadata lives under the `ichnos:` extension key; unknown keys are preserved on round-trip.
- Every approved write adds a dated entry to `log.md`.
- Ingestion is tolerant: unknown types, broken links and non-conformant files are warnings, never sync failures.

# Agent workflow

## Stages

1. Intake
2. Source indexing
3. Context retrieval
4. Requirements extraction
5. BRD/spec generation
6. Human review
7. Human approval
8. Epic/Story proposal
9. GitHub write approval
10. Context-pack assembly
11. Implementation-plan generation
12. Optional branch/PR action
13. Traceability validation

## Nodes

| Node | Responsibility |
| --- | --- |
| Intake | Normalise user input into an immutable source record |
| Retrieval | Find context: OKF `index.md` and `type` first, then vector search, then link expansion |
| Requirements | Extract requirements, assumptions and open questions |
| Specification | Produce a BRD/spec as an OKF concept |
| Planning | Propose Epic and Stories with acceptance criteria |
| Implementation | Build the context pack and implementation plan |
| Validation | Check links, acceptance criteria and source evidence |
| Approval | Interrupt and wait for a human decision |
| GitHub action | Execute only the approved, persisted payload |

## Run state

Each run retains: input artifact IDs, repository and branch, retrieved context references, generated outputs, user edits, approval decisions, pending action payloads, tool results, errors and retries, and final external identifiers.

# Architecture

## Stack

| Layer | Choice | Responsibility |
| --- | --- | --- |
| Web frontend | React + TypeScript + Vite | Workspace, review, approvals, traceability |
| API | FastAPI | HTTP API, sessions, validation, orchestration access |
| Orchestration | LangGraph | Stateful workflow, routing, interrupts, resumption |
| Metadata | SQLite | Runs, approvals, sync cursors, audit events |
| Knowledge | OKF bundle in `docs/` | Canonical documentation, typed and linked |
| Retrieval | SQLite FTS5 index + links table (ADR-0008, ADR-0010) | Context retrieval and relationship expansion |
| LLM | Configurable local or hosted model | Extraction, drafting, planning, validation |
| GitHub | REST/GraphQL API | Issues, PRs, commits, comments, metadata |
| Notifications | Optional Slack webhook | Status notifications |
| Packaging | Docker Compose | Local and self-hosted deployment |

## Monorepo layout

```text
ichnos/
├── apps/
│   ├── api/                     # FastAPI service; Python package `ichnos` (uv)
│   │   ├── src/ichnos/
│   │   │   ├── api/             # routers: health, config, workspaces, sync, knowledge,
│   │   │   │                    #   intake, runs, artifacts
│   │   │   ├── db/              # SQLAlchemy models, engine, Alembic migrations
│   │   │   ├── github/          # read-only GitHub client and reader (ADR-0004, ADR-0009)
│   │   │   ├── knowledge/       # link extraction and chunking (ADR-0008, ADR-0010)
│   │   │   ├── llm/             # model providers, fake provider, preflight (ADR-0012)
│   │   │   ├── okf/             # tolerant OKF v0.2 parser (ADR-0001)
│   │   │   ├── sync/            # sync stages, cursors and reset (ADR-0009)
│   │   │   ├── workflows/       # engine, retrieval, requirements, specification (ADR-0011)
│   │   │   ├── main.py          # app factory; migrations run at startup
│   │   │   ├── openapi.py       # contract export
│   │   │   └── settings.py      # ICHNOS_* configuration
│   │   ├── tests/
│   │   ├── alembic.ini
│   │   ├── Dockerfile
│   │   ├── pyproject.toml
│   │   └── uv.lock
│   └── web/                     # React + TypeScript + Vite; served by nginx in Docker
├── packages/
│   ├── contracts/               # @ichnos/contracts: openapi.json and generated types
│   └── api-client/              # @ichnos/api-client: typed openapi-fetch client
├── docs/                        # OKF bundle
├── examples/demo-repository/    # Quire demo repository; published by scripts/publish_demo.sh
├── scripts/                     # OKF validator, rename check, labels, docs log, demo, e2e
├── .github/                     # CI, Dependabot, templates
├── docker-compose.yml
├── .env.example
├── Makefile                     # single entry point (ADR-0007)
├── package.json
└── pnpm-workspace.yaml
```

A shared `packages/ui` is added once a second app needs shared components.

## Deployment

```bash
git clone https://github.com/MohamedAliZouariEng/ichnos.git
cd ichnos
cp .env.example .env
docker compose up --build --wait
```

Compose runs `web` (nginx serving the UI and proxying `/api` and `/healthz`), published on `127.0.0.1:8765` by default, and `api` (uvicorn as a non-root user), reachable only inside the Compose network. SQLite lives in the `ichnos-data` volume, and migrations run when the API starts. An optional `ollama` service starts only with `--profile ollama` (ADR-0006). See the [self-hosting guide](/project/self-hosting.md).

# API scope

```text
POST  /api/workspaces                 GET  /api/workspaces
POST  /api/sync                       POST /api/ingest
GET   /api/runs                       POST /api/runs
GET   /api/runs/{run_id}              GET  /api/runs/{run_id}/events
GET   /api/artifacts/{artifact_id}    PATCH /api/artifacts/{artifact_id}
POST  /api/artifacts/{artifact_id}/approve
POST  /api/artifacts/{artifact_id}/reject
POST  /api/proposals/issues
GET   /api/approvals                  GET  /api/approvals/{approval_id}
POST  /api/approvals/{approval_id}/approve
POST  /api/approvals/{approval_id}/reject
GET   /api/context/issues/{issue_number}
POST  /api/query
GET   /api/traceability/{artifact_id}
```

Every operation that writes to GitHub first creates a pending approval; the approval endpoint executes the exact persisted payload. Implemented so far: health and configuration (`GET /healthz`, `GET /api/config`); workspaces (`GET`/`POST /api/workspaces`, `GET`/`PATCH /api/workspaces/{workspace_id}`, `POST …/github-check`); sync (`POST …/sync`, `GET …/sync-runs`, `DELETE …/knowledge`); knowledge (`GET …/documents`, `GET …/documents/detail`, `GET …/github/items`, `GET …/links`, `GET …/search`); models (`POST /api/config/model-check`); intake (`POST …/sources`, `POST …/sources/from-document`, `GET …/sources`); runs (`POST …/runs`, `GET …/runs`, `GET /api/runs/{run_id}`, `GET /api/runs/{run_id}/events` as Server-Sent Events); artifacts (`GET …/artifacts`, `GET /api/artifacts/{artifact_id}`, `GET`/`POST …/versions`, `POST …/validate`). The committed contract is `packages/contracts/openapi.json`.

# GitHub conventions

## Labels

`type:initiative`, `type:epic`, `type:story`, `type:bug`, `status:draft`, `status:needs-review`, `status:approved`, `status:ready-for-implementation`, `status:in-progress`, `status:blocked`, `status:done`, `agent:generated`, `priority:p0`, `priority:p1`, `priority:p2`, `priority:p3`.

## Issue body

```markdown
## Parent
- Epic: #123
- Initiative: #120

## Source specification
- docs/specs/workspace-onboarding/brd.md#requirements

## Requirements
- R-03: Invitation links expire after a configurable period.

## Acceptance criteria
- [ ] AC-01: Given an invitation exists, when its expiry time is reached, then it cannot be accepted.
- [ ] AC-02: Given an expired invitation, when a user attempts to accept it, then the system displays an actionable error.

## Scope exclusions
- This Story does not include email provider configuration.
```

## Pull request body

```markdown
Closes #456

## Requirement traceability
| Acceptance criterion | Evidence |
|---|---|
| AC-01 | tests/test_invitation_expiry.py::test_expired_invitation |
| AC-02 | src/invitations/errors.py and integration test |

## Context used
- docs/specs/workspace-onboarding/brd.md
- #123

## AI assistance
- Agent/framework: Ichnos workflow
- Generated sections: <list>
- Human-edited sections: <list>
```

# Security and privacy

- **Tokens:** GitHub and Slack tokens live in environment variables or a local secrets store, are never committed, use least privilege, and default to read-only during setup.
- **External models:** external LLM use is explicit in configuration and shown in the UI; users are warned before repository content leaves their environment; local models are supported where practical.
- **Approvals:** an authenticated local session is required; the exact target and payload are persisted; approvals go stale if the underlying artifact changes; every approval event is audit-logged.
- **Repository boundaries:** the active repository, branch and target are displayed before any GitHub write.

# Open decisions

| Decision | Settle by | Current leaning |
| --- | --- | --- |
| LangGraph mandatory or behind an adapter | Phase 3 | Decided: LangGraph, nodes as plain functions ([ADR-0011](/adr/0011-workflow-engine.md)) |
| Default retrieval store | Phase 2 | Decided: SQLite FTS5 now, embeddings in Phase 3 ([ADR-0008](/adr/0008-retrieval-store-sqlite-fts.md)) |
| Run updates: polling, SSE or WebSockets | Phase 3 | Decided: SSE with a persisted event log ([ADR-0013](/adr/0013-live-run-updates.md)) |
| GitHub OAuth, PAT or both | Phase 1 | Decided: fine-grained PAT ([ADR-0004](/adr/0004-github-access-fine-grained-pat.md)) |
| Ollama in Docker Compose | Phase 1 | Decided: optional profile ([ADR-0006](/adr/0006-ollama-optional-compose-profile.md)) |
| Slack in first release | Phase 4 | Decided: later adapter ([ADR-0018](/adr/0018-slack-deferred.md)) |
| One or many repositories per workspace | Phase 1 | Decided: one ([ADR-0005](/adr/0005-one-repository-per-workspace.md)) |
| Format of browser-edited drafts | Phase 3 | Decided: versions in SQLite until approved ([ADR-0014](/adr/0014-drafts-and-versions.md)) |

[^brd]: Ichnos MVP — Business Requirements
[^prd]: Product Requirements Document v0.1
[^okf-spec]: Open Knowledge Format specification v0.2
