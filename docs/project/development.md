---
type: Howto
title: Developing Ichnos
description: Set up a development machine, run Ichnos locally, and follow the checks and conventions every change must pass.
tags: [development, tooling, contributing]
status: stable
generated: { by: claude/opus-5, at: 2026-09-19T17:09:14Z }
verified: { by: human:MohamedAliZouariEng, at: 2026-09-19T17:09:14Z }
sources:
  - id: adr-0007
    resource: /adr/0007-monorepo-tooling-pnpm-uv.md
    title: "ADR-0007: Monorepo tooling with pnpm workspaces and uv"
  - id: techspec
    resource: /specs/ichnos-mvp/techspec.md
    title: Ichnos MVP — Technical Specification
---

# Prerequisites

- Node.js 22 (see `.nvmrc`) with Corepack, which provides the pinned pnpm version.
- Python 3.12 (see `.python-version`) and uv.
- Docker with Compose v2, for running the full stack.
- GNU make.

The tooling follows ADR-0007: pnpm workspaces for TypeScript, uv for the API, and the `Makefile` as the single entry point.[^adr-0007]

# First setup

```bash
git clone https://github.com/MohamedAliZouariEng/ichnos.git
cd ichnos
pnpm install
make api-install
cp .env.example .env    # optional: add a read-only GitHub token
make check
```

`make help` lists every target.

# Daily work

| Task | Command |
| --- | --- |
| Run API and web with reload | `make dev` (UI on http://localhost:5173) |
| Run the full stack in Docker | `make up`, then `make down` (UI on http://localhost:8765) |
| Run every check CI runs | `make check` |
| Format and auto-fix Python | `make api-format` |
| Regenerate the API contract after changing endpoints | `make contracts` |
| Create a migration after changing models | `make api-migration m="describe the change"` |
| Check the Phase 2 exit criteria against real GitHub | `make up`, then `make e2e` |
| Publish the Quire demo repository to your account | `scripts/publish_demo.sh` |

# Rules for every change

- Work on a branch and open a pull request; `main` is protected and requires all CI checks.
- Commit only when checks pass: `make check && git commit …`.
- API changes regenerate the contract in the same commit (`make contracts`); CI fails on drift.
- Model changes ship with their Alembic migration; a test compares migrations with models.
- Documentation in `docs/` stays a valid OKF bundle; add a `docs/log.md` entry with `scripts/docs_log.py`.

# Two databases

`make dev` and `make up` do not share data:

- `make dev` runs the API on your machine with the database `apps/api/data/ichnos.db`.
- `make up` runs the API in Docker with the volume `ichnos_ichnos-data`.

A workspace created in one is not visible in the other. Everything a sync stores is derived from GitHub (ADR-0002), so recreate the workspace in the UI and select **Sync now** to fill it again.

# Testing sync without GitHub

API tests never call GitHub. `tests/fake_github.py` serves repository files, Issues, pull requests, comments and commits from memory, honours `since` like GitHub does, and records every request, so tests can assert how many requests a sync made. `make e2e` is the only check that talks to real GitHub; CI runs it on every pull request with the workflow's own read-only token.

# Known pitfalls

- **TypeScript is pinned to 5.x.** TypeScript 7 (the native compiler) has no JavaScript compiler API yet, and `openapi-typescript` needs it. Dependabot ignores TypeScript major updates for this reason.
- **`PYTHONPATH` is cleared by make.** System-wide Python paths, such as ROS, would otherwise leak into the API environment and its tests.
- **Makefile recipes start with `>`** instead of a tab (`.RECIPEPREFIX`), so copied snippets keep working.
- **API tests never touch `apps/api/data`.** `tests/conftest.py` gives every test its own temporary directory and clears `ICHNOS_*` variables; if a test writes there, isolation is broken.
- **Warnings are errors in pytest.** Filter a warning only when it comes from a dependency and cannot be fixed on our side, and name it exactly.
- **pnpm may ask to approve build scripts.** Approve only packages you recognise, such as `esbuild`.
- **Requests appear twice in development.** React `StrictMode` runs effects twice in development builds only.
- **Ruff formats code, not strings.** A string literal over 100 characters must be split by hand, for example as two adjacent strings inside parentheses.
- **Ruff rejects `l` as a variable name** (E741, easily confused with `1`); use a word.

See the [technical specification](/specs/ichnos-mvp/techspec.md) for the architecture.[^techspec]

[^adr-0007]: ADR-0007: Monorepo tooling with pnpm workspaces and uv
[^techspec]: Ichnos MVP — Technical Specification
