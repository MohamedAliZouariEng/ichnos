---
type: Decision
title: "ADR-0013: Live run updates through Server-Sent Events"
description: The run view receives stage events through Server-Sent Events from a persisted event log, with polling as a fallback.
tags: [adr, api, realtime, ui]
status: stable
generated: { by: claude/opus-5, at: 2026-09-19T19:42:04Z }
verified: { by: human:MohamedAliZouariEng, at: 2026-09-19T19:42:04Z }
sources:
  - id: techspec
    resource: /specs/ichnos-mvp/techspec.md
    title: Ichnos MVP — Technical Specification
ichnos:
  adr_number: 13
---

# Context

The PRD requires workflow progress without a full page refresh. The technical specification left the choice between polling, Server-Sent Events and WebSockets to Phase 3.[^techspec] Updates flow one way, from server to browser.

# Options considered

1. **Polling.** Simplest, but delayed and chatty.
2. **Server-Sent Events.** One-way streaming over plain HTTP, with built-in reconnection and resume by event ID.
3. **WebSockets.** Two-way, but more moving parts and nothing to send upstream.

# Decision

- `GET /api/runs/{run_id}/events` streams run events as Server-Sent Events. Each event carries its `run_events` row ID, so a reconnecting browser sends `Last-Event-ID` and receives only what it missed.
- Events are persisted before they are streamed; the stream is a view of the log, never the only copy.
- `GET /api/runs/{run_id}` returns the full run, so clients can always fall back to polling.
- nginx disables response buffering for the stream path.

# Consequences

- **Positive:** live progress with no extra protocol; history survives reloads and restarts.
- **Negative:** each open run view holds one HTTP connection.

[^techspec]: Ichnos MVP — Technical Specification
