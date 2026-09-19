---
type: Decision
title: "ADR-0003: LangGraph for workflow orchestration"
description: The Ichnos agent workflow is a LangGraph state graph with persisted checkpoints and human-approval interrupts.
tags: [adr, orchestration, langgraph, agents]
status: stable
generated: { by: claude/opus-5, at: 2026-09-19T12:49:50Z }
verified: { by: human:MohamedAliZouariEng, at: 2026-09-19T12:49:50Z }
sources:
  - id: techspec
    resource: /specs/ichnos-mvp/techspec.md
    title: Ichnos MVP — Technical Specification
ichnos:
  adr_number: 3
---

# Context

The Ichnos workflow is not a single model call. It moves through intake, retrieval, generation, review and approval stages; it must pause for a human decision, survive restarts while paused, resume with the exact approved payload, and record every step for the run view.[^techspec]

# Options considered

1. **Custom state machine in FastAPI.** Full control, but interrupts, checkpointing and resumption must be built and tested from scratch.
2. **LangGraph.** Stateful graphs with conditional routing, interrupts for human input, and pluggable checkpoint persistence, including SQLite.
3. **Durable workflow engine (Temporal and similar).** Strong durability, but requires an extra server, which conflicts with a simple Docker Compose setup.
4. **Multi-agent frameworks (CrewAI, AutoGen and similar).** Optimised for autonomous agent conversations rather than explicit stages and approval gates.

# Decision

The workflow is implemented as a LangGraph state graph with a SQLite checkpointer. Stages are graph nodes, not autonomous agents. Approval is an interrupt: the graph persists the pending action and resumes only when the approval endpoint records a human decision.

Whether LangGraph is mandatory or sits behind a thin orchestration adapter will be settled by Phase 3 and recorded in a follow-up ADR.

# Consequences

- **Positive:** interrupts and resumption come built in; run state is inspectable; no extra infrastructure beyond SQLite.
- **Negative:** dependency on a fast-moving framework whose APIs may change; contributors must learn LangGraph concepts.
- **Mitigation:** keep node logic in plain Python functions that LangGraph only wires together, so business logic stays testable without the framework.

[^techspec]: Ichnos MVP — Technical Specification
