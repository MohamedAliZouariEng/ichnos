---
type: Decision
title: "ADR-0011: Workflow engine: LangGraph graphs of plain functions, run in the background"
description: Workflows are LangGraph state graphs whose nodes are plain Python functions, checkpointed to SQLite and executed in a background pool inside the API.
tags: [adr, workflow, langgraph, orchestration]
status: stable
generated: { by: claude/opus-5, at: 2026-09-19T19:42:04Z }
verified: { by: human:MohamedAliZouariEng, at: 2026-09-19T19:42:04Z }
sources:
  - id: adr-0003
    resource: /adr/0003-langgraph-for-orchestration.md
    title: "ADR-0003: LangGraph for workflow orchestration"
  - id: techspec
    resource: /specs/ichnos-mvp/techspec.md
    title: Ichnos MVP — Technical Specification
ichnos:
  adr_number: 11
---

# Context

ADR-0003 chose LangGraph and left open whether it should be mandatory or sit behind an adapter, to be settled in Phase 3.[^adr-0003] The requirements workflow calls a model several times and can take minutes, so it cannot run inside an HTTP request the way sync does, and it must survive a restart while it waits for a human in Phase 4.[^techspec]

# Options considered

1. **LangGraph behind a full adapter interface.** Swappable engine, but the adapter would re-describe graphs, state and interrupts for no current need.
2. **LangGraph as the engine, with nodes as plain functions.** Only the graph wiring depends on LangGraph; the logic is ordinary Python.
3. **A hand-written state machine.** No dependency, but interrupts, checkpoints and resumption must be rebuilt.

# Decision

- LangGraph is the workflow engine for the MVP. Each workflow is a state graph in `ichnos.workflows`; its nodes are plain functions that take and return typed state, so they are unit-tested without running a graph.
- Graph state is checkpointed with LangGraph's SQLite checkpointer in its own file in the data directory, so Alembic never manages its tables.
- Runs start through the API and execute in a small background pool inside the API process (two concurrent runs by default). Every stage change is written to the `run_events` table as it happens.
- A run left `running` when the API stops is marked `interrupted` at the next start; its checkpoint allows resuming it later.

# Consequences

- **Positive:** long model calls never block HTTP requests; the run view has a complete event history; logic stays testable and portable.
- **Negative:** LangGraph and its dependencies join the API image; one API process bounds throughput.
- **Revisit:** a separate worker container when runs outgrow one process.

[^adr-0003]: ADR-0003: LangGraph for workflow orchestration
[^techspec]: Ichnos MVP — Technical Specification
