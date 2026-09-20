---
type: Howto
title: "Contributing to Ichnos"
description: "How to set up a development environment, the rules every change follows, and how contributions are licensed."
tags: [howto, contributing, development]
status: stable
generated: { by: claude/opus-5, at: 2026-09-20T15:17:52Z }
verified: { by: human:MohamedAliZouariEng, at: 2026-09-20T15:17:52Z }
sources:
  - id: development
    resource: /project/development.md
    title: "Developing Ichnos"
  - id: adr-0015
    resource: /adr/0015-pending-actions-and-one-write-client.md
    title: "ADR-0015: Every GitHub write is an approved pending action, executed by one write client"
  - id: adr-0025
    resource: /adr/0025-evaluation-metrics.md
    title: "ADR-0025: Evaluation metrics are computed by code from Ichnos's own data"
---

# Set up

You need Python 3.12 with `uv`, Node 22 with `pnpm`, and Docker. Clone the repository, then run `make check`: it validates the documentation, lints and type-checks the API, runs the API and web tests, and checks that the API contract and the generated client agree. The [development guide](/project/development.md) explains the layout.[^development]

# Rules every change follows

- **Decisions are ADRs.** A change of approach starts with an ADR in `docs/adr/`, written as an OKF `Decision`.
- **Documentation is OKF.** Everything in `docs/` must pass `make docs-check`, the strict validator CI runs.
- **Every GitHub write goes through the approval service.** Only `ichnos/approvals/` may import the write client; an architecture test fails otherwise, and an integration test proves no write happens without an approval.[^adr-0015]
- **Claims are measured.** Numbers in documentation or release notes come from code or a timer, and are recorded with the commit they were measured on.[^adr-0025]
- **Tests come with the change.** A bug fix adds the test that would have caught it.
- **Pull requests stay drafts until `make check` passes** and CI is green.

# Conventions

- The Makefile starts recipe lines with `>`, not a tab (`.RECIPEPREFIX`).
- Test helpers must not be named `test…`: pytest would collect them as tests.
- Lines stay under 100 characters; Ruff formats Python and splits nothing inside strings, so split long strings yourself.
- Commit messages use a type prefix, such as `feat:`, `fix:`, `docs:` or `test:`.

# License

Ichnos is licensed under the Apache License, Version 2.0. Contributions are accepted under the same license.

[^adr-0015]: ADR-0015: Every GitHub write is an approved pending action, executed by one write client
[^adr-0025]: ADR-0025: Evaluation metrics are computed by code from Ichnos's own data
[^development]: Developing Ichnos
