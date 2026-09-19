---
type: Decision
title: "ADR-0007: Monorepo tooling with pnpm workspaces and uv"
description: TypeScript packages use pnpm workspaces, the Python API uses uv, and a root Makefile is the single entry point.
tags: [adr, tooling, monorepo]
status: stable
generated: { by: claude/opus-5, at: 2026-09-19T13:13:45Z }
verified: { by: human:MohamedAliZouariEng, at: 2026-09-19T13:13:45Z }
sources:
  - id: techspec
    resource: /specs/ichnos-mvp/techspec.md
    title: Ichnos MVP — Technical Specification
ichnos:
  adr_number: 7
---

# Context

The monorepo holds a TypeScript web app, shared TypeScript packages and a Python API.[^techspec] Installs must be fast and reproducible on developer machines, in CI and in Docker images, and must not pick up system-wide Python packages.

# Options considered

1. **JavaScript:** npm workspaces, Yarn, or pnpm workspaces; optionally Nx or Turborepo on top.
2. **Python:** pip with requirements files, Poetry, or uv.

# Decision

- **pnpm workspaces** for `apps/web` and `packages/*`. The pnpm version is pinned through `packageManager` in the root `package.json` and provided by Corepack.
- **uv** for `apps/api`, with `pyproject.toml` and a committed `uv.lock`.
- **No task-runner framework.** A root `Makefile` is the single entry point (`make dev`, `make lint`, `make test`, `make up`).
- **Pinned runtimes:** Node 22 in `.nvmrc`, Python 3.12 in `.python-version`.
- Make targets clear `PYTHONPATH`, so system-wide Python paths (for example ROS) cannot leak into the API environment.

# Consequences

- **Positive:** fast, lockfile-based installs everywhere; one command surface for contributors and CI.
- **Negative:** contributors need two package managers; lockfiles must change in the same PR as dependencies.
- **Revisit:** if build orchestration across packages becomes slow enough to justify Turborepo or Nx.

[^techspec]: Ichnos MVP — Technical Specification
