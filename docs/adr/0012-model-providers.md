---
type: Decision
title: "ADR-0012: Model providers: one OpenAI-compatible adapter, structured output, Gemini by default"
description: Ichnos calls models through one OpenAI-compatible adapter with schema-checked JSON output, a preflight check and a fake provider for tests; this installation uses Gemini.
tags: [adr, llm, providers, privacy]
status: stable
generated: { by: claude/opus-5, at: 2026-09-19T19:42:04Z }
verified: { by: human:MohamedAliZouariEng, at: 2026-09-19T19:42:04Z }
sources:
  - id: adr-0006
    resource: /adr/0006-ollama-optional-compose-profile.md
    title: "ADR-0006: Ollama as an optional Docker Compose profile"
  - id: gemini-openai
    resource: https://ai.google.dev/gemini-api/docs/openai
    title: Gemini API — OpenAI compatibility
ichnos:
  adr_number: 12
---

# Context

Phase 3 makes the first model calls. Ichnos must stay provider-neutral and support local models (ADR-0006), and its workflows need structured data rather than free text.[^adr-0006] Gemini, OpenAI, OpenRouter, Groq and Ollama all offer the OpenAI chat-completions format; Gemini exposes it at `https://generativelanguage.googleapis.com/v1beta/openai/`, including JSON-schema output.[^gemini-openai]

A probe against Gemini showed two practical traps: a model listed for a key may not support chat completions (an "omni" model answered "only supports Interactions API"), and hidden reasoning tokens can dominate usage (306 tokens billed for 52 visible).

# Decision

- One adapter speaks the OpenAI chat-completions format; `ICHNOS_LLM_BASE_URL`, `ICHNOS_LLM_MODEL` and `ICHNOS_LLM_API_KEY` select the service. A workspace may override the model name, never the key or URL.
- The API key follows the GitHub token rules (ADR-0004): environment only, never stored, logged or returned.
- Workflows ask for JSON matching a schema, validate it with Pydantic, and retry once with the validation errors if it does not match.
- A preflight call checks the configured model before the first run and reports a clear error.
- `ICHNOS_LLM_REASONING_EFFORT` defaults to `low`; token usage, including reasoning, is recorded per run.
- A deterministic fake provider serves every test and CI run; real model calls happen only when a person starts a workflow.
- This installation uses Gemini (`gemini-3.8-flash`) through the OpenAI-compatible endpoint.

# Privacy

Running a workflow sends meeting notes and retrieved repository content to the provider. The UI shows the active provider and warns whenever the base URL is not on this machine. Provider terms differ by tier; on some free tiers, prompts may be used to improve the provider's products, so private repositories need a tier whose terms fit.

# Consequences

- **Positive:** switching provider is a configuration change; tests are fast, free and deterministic.
- **Negative:** provider-specific features beyond the OpenAI format are unavailable; output quality depends on the chosen model.
- **Revisit:** a native adapter when a needed feature is missing from the compatible format.

[^adr-0006]: ADR-0006: Ollama as an optional Docker Compose profile
[^gemini-openai]: Gemini API — OpenAI compatibility
