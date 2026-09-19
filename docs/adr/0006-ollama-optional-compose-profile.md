---
type: Decision
title: "ADR-0006: Ollama as an optional Docker Compose profile"
description: Local models run through an ollama service in an opt-in Compose profile; the default stack does not start it.
tags: [adr, llm, deployment, docker]
status: stable
generated: { by: claude/opus-5, at: 2026-09-19T13:13:45Z }
verified: { by: human:MohamedAliZouariEng, at: 2026-09-19T13:13:45Z }
sources:
  - id: techspec
    resource: /specs/ichnos-mvp/techspec.md
    title: Ichnos MVP — Technical Specification
ichnos:
  adr_number: 6
---

# Context

Ichnos is local-first and provider-neutral: it should support local models as well as hosted providers. The technical specification left open whether Docker Compose should include Ollama.[^techspec] Local models need several gigabytes of memory, while the default installation should start on a modest laptop.

# Options considered

1. **No Ollama in Compose.** Smallest stack; users install and wire a local runtime themselves.
2. **Ollama always on.** Local models work out of the box, but every installation pays the memory cost.
3. **Ollama in an opt-in Compose profile.** Default stack stays small; one flag enables local models.

# Decision

Docker Compose defines an `ollama` service under the profile `ollama`, started only with `docker compose --profile ollama up`. The model provider is configured through `ICHNOS_LLM_PROVIDER`, `ICHNOS_LLM_MODEL` and `ICHNOS_LLM_BASE_URL`, with matching `ICHNOS_EMBEDDING_*` variables. With the profile on, the base URL is `http://ollama:11434`. Phase 1 wires configuration only; model calls start in Phase 3.

# Consequences

- **Positive:** the default stack stays light; switching between local and hosted providers is a configuration change.
- **Negative:** local model quality may be weak, so hosted providers remain first-class; users must pull models themselves.
- **Follow-up:** from Phase 3, the UI shows the active provider and warns when repository content leaves the machine.

[^techspec]: Ichnos MVP — Technical Specification
