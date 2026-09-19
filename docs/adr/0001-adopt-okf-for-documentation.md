---
type: Decision
title: "ADR-0001: Adopt OKF for repository documentation"
description: All repository documentation is an Open Knowledge Format v0.2 bundle in docs/.
tags: [adr, documentation, okf]
status: stable
generated: { by: claude/opus-5, at: __NOW__ }
verified: { by: human:MohamedAliZouariEng, at: __NOW__ }
sources:
  - id: okf-site
    resource: https://okf.md/
    title: OKF — The Markdown Spec for Humans and AI Agents
  - id: okf-spec
    resource: https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md
    title: Open Knowledge Format specification v0.2
  - id: techspec
    resource: /specs/ichnos-mvp/techspec.md
    title: Ichnos MVP — Technical Specification
ichnos:
  adr_number: 1
---

# Context

Ichnos reads documentation to ground its agents and writes documentation after human approval. Plain Markdown gives no reliable way to tell a BRD from an ADR, to know where content came from, or whether a human approved it. Ichnos needs documentation that humans review in git and agents parse without custom adapters.

# Options considered

1. **Plain Markdown with path conventions only.** Zero overhead, but type, provenance and approval must be guessed from paths and prose.
2. **A docs-site framework (MkDocs, Docusaurus).** Good rendering, but its frontmatter is presentation-oriented and carries no provenance or trust model.
3. **An external knowledge store (wiki, Notion, Confluence).** Contradicts "GitHub is canonical" and adds lock-in.
4. **Open Knowledge Format (OKF).** Markdown with typed YAML frontmatter, reserved `index.md` and `log.md`, and optional provenance (`sources`), trust (`generated`, `verified`) and lifecycle (`status`) fields.[^okf-spec]

# Decision

`docs/` is an OKF v0.2 bundle, declared by `okf_version: "0.2"` in the root `index.md`.[^okf-site] Ichnos also reads v0.1 fallbacks (`timestamp`, `# Citations`). Conformance is validated in CI on every pull request. The concrete mapping of Ichnos artifacts to OKF fields is defined in the [technical specification](/specs/ichnos-mvp/techspec.md).[^techspec]

# Consequences

- **Positive:** the retrieval node routes by `type` without heuristics; `index.md` enables progressive disclosure; OKF links form the relationship graph without a graph database; "only a human can approve" becomes machine-checkable through `human:` actors in `verified`.
- **Negative:** every concept needs frontmatter, which adds authoring overhead; the spec is young (okf.md presents v0.1 while Google's spec is v0.2), so version drift must be tracked; GitHub renders `README.md`, not `index.md`, as a folder landing page.
- **Follow-up:** revisit this ADR when OKF publishes a new minor or major version.

[^okf-site]: OKF — The Markdown Spec for Humans and AI Agents
[^okf-spec]: Open Knowledge Format specification v0.2
[^techspec]: Ichnos MVP — Technical Specification
