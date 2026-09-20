---
type: Decision
title: "ADR-0026: Releases are tagged, and their images are built by GitHub Actions and published to GHCR"
description: A semantic version tag builds the API and web images in GitHub Actions and publishes them to GitHub Container Registry; Compose builds from source or pulls a release, and make demo is the one-command path.
tags: [adr, release, docker, distribution]
status: stable
generated: { by: claude/opus-5, at: 2026-09-20T13:10:26Z }
verified: { by: human:MohamedAliZouariEng, at: 2026-09-20T13:10:26Z }
sources:
  - id: adr-0012
    resource: /adr/0012-model-providers.md
    title: "ADR-0012: Model providers: one OpenAI-compatible adapter, structured output, Gemini by default"
  - id: adr-0015
    resource: /adr/0015-pending-actions-and-one-write-client.md
    title: "ADR-0015: Every GitHub write is an approved pending action, executed by one write client"
ichnos:
  adr_number: 26
---

# Context

A stranger must be able to self-host Ichnos and reproduce the demo. Building from source works but is slow, and a release needs a fixed, inspectable artifact. The demo needs a GitHub token and a model key,[^adr-0012] and every write it makes still waits for approval.[^adr-0015]

# Decision

- Releases use semantic version tags, starting with `v0.1.0`.
- Pushing a tag runs a GitHub Actions workflow that builds the API and web images and publishes them to GitHub Container Registry as `ghcr.io/mohamedalizouarieng/ichnos-api` and `ghcr.io/mohamedalizouarieng/ichnos-web`, tagged with the version, with OCI labels for the source repository and version.
- Docker Compose builds from source by default and can pull a published version instead.
- Release notes are taken from `CHANGELOG.md`.
- `make demo` is the one-command path: it checks the configuration, creates the person's own copy of the demo repository from `examples/demo-repository`, and starts Ichnos.
- The technical article is an OKF concept under `docs/articles/`.
- Publishing a release never writes to a user's repository.

# Consequences

- **Positive:** a release is a fixed pair of images anyone can pull, and the demo starts with one command.
- **Negative:** images are built by CI on each tag, so a broken release needs a new tag rather than a rebuild.

[^adr-0012]: ADR-0012: Model providers: one OpenAI-compatible adapter, structured output, Gemini by default
[^adr-0015]: ADR-0015: Every GitHub write is an approved pending action, executed by one write client
