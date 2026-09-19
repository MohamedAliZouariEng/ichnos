---
type: BRD
title: Ichnos MVP — Business Requirements
description: Business context, scope, requirements and success measures for the Ichnos open-source MVP.
tags: [ichnos, mvp, sdlc, traceability]
status: stable
generated: { by: claude/opus-5, at: 2026-09-19T12:44:36Z }
verified: { by: human:MohamedAliZouariEng, at: 2026-09-19T12:44:36Z }
sources:
  - id: prd
    resource: https://docs.sylergy.net/s/documentation/p/athar-XwmmVmIjhs
    title: Product Requirements Document v0.1 (written under the working name Athar)
ichnos:
  artifact_id: brd-ichnos-mvp
  requirement_ids: [FR-1, FR-2, FR-3, FR-4, FR-5, FR-6, FR-7, FR-8, FR-9, FR-10, FR-11, FR-12, FR-13, FR-14, FR-15]
---

# Summary

Ichnos is a self-hosted web application that helps teams turn product requirements into traceable engineering work.[^prd] It connects meeting notes, product briefs, repository documentation, GitHub Issues, pull requests, commits and test evidence through an agent-assisted workflow.

Guiding principle: **AI may prepare and explain engineering work, but humans approve what becomes canonical and what is written to GitHub.**

The MVP does not replace GitHub or compete with hosted Jira. It is a focused, open-source, self-hosted tool that works without Jira, GCP, AWS or any proprietary platform. The technical design is in the [technical specification](/specs/ichnos-mvp/techspec.md).

# Positioning

Ichnos is a self-hosted, GitHub-native agentic SDLC workspace that turns requirements into reviewed, traceable engineering work. *Ichnos* (ἴχνος) is Greek for "footprint" or "trace".

Ichnos helps a team answer:

- What requirement led to this Story?
- Which acceptance criteria does this pull request implement?
- Where did this requirement originate?
- What evidence supports this generated specification?
- Which decisions, documents and tests are connected to this change?

# Problem

AI coding tools generate code quickly but lack reliable product and engineering context. Requirements are scattered across meeting notes, documents, Issues, pull requests, chat and code. As a result:

- Agents generate requirements or code from incomplete context.
- Product decisions disappear into conversations.
- Issues do not consistently link to durable specifications.
- Acceptance criteria are vague or not connected to tests.
- Reviewers cannot easily verify that a pull request satisfies the original intent.
- Teams must choose between complex enterprise platforms and fragmented manual workflows.
- Cloud-dependent AI tooling adds cost, lock-in and data-governance concerns.

# Goals

1. Provide a browser-based interface for a GitHub-native agentic SDLC workflow.
2. Convert a meeting note or product brief into a reviewable BRD/specification draft.
3. Convert an approved specification into proposed GitHub Epics and Stories.
4. Generate an implementation context pack and plan for an approved Story.
5. Link requirements, acceptance criteria, Issues, pull requests, commits and tests.
6. Require explicit human approval before any GitHub write.
7. Run locally or on a self-hosted machine with Docker Compose.
8. Keep GitHub and repository files as the canonical source of truth, with documentation in the Open Knowledge Format (OKF).
9. Let open-source users self-host with configurable model providers.
10. Produce a practical technical case study about agentic SDLC orchestration.

# Success criteria

The MVP succeeds when a user can:

- Connect one GitHub repository.
- Submit a meeting note through the web interface.
- Generate a BRD/spec draft with source references and assumptions.
- Review and edit the draft in the browser.
- Approve the draft through a human approval gate.
- Generate an Epic and three to five Story proposals.
- Review the exact proposed GitHub payloads and approve Issue creation.
- Generate an implementation plan for one Story.
- Create an optional draft pull request or PR payload.
- Inspect traceability from requirement to Story to PR and test evidence.
- Run the whole application locally with Docker Compose.

# Non-goals

The MVP will not:

- Replace GitHub Issues, pull requests or repository workflows.
- Replace Jira, Confluence or enterprise portfolio tools.
- Automatically merge AI-generated code.
- Automatically approve requirements, Issues, PRs or code.
- Be a hosted multi-tenant SaaS.
- Require GCP, AWS or any specific cloud provider.
- Require a managed graph or vector database.
- Ingest all Slack history by default.
- Offer a general-purpose autonomous agent marketplace.
- Support every model provider in the first release.
- Include an ontology designer before the core workflow is validated.

# Target users

| User | Need |
| --- | --- |
| AI-enabled engineering team | Better requirements-to-code traceability while working in GitHub |
| Product owner or founder | Turn discussions into structured requirements and reviewable work |
| Engineer | Reliable context, clear acceptance criteria and a plan before coding |
| Reviewer or maintainer | Inspect generated artifacts, approve exact actions, verify PRs against requirements |
| Open-source self-hoster | Run independently, choose a model provider, keep control of repository data |

# Core user journey

1. Select a configured GitHub repository.
2. Paste or upload a meeting note, transcript or product brief.
3. Ichnos indexes the input and retrieves relevant docs, Issues, PRs and decisions.
4. The requirements workflow generates a draft BRD/spec.
5. The user reviews the draft, sources, assumptions and open questions.
6. The user edits or approves it.
7. Ichnos proposes Epic and Story payloads.
8. The user reviews exact Issue titles, bodies, labels, links and acceptance criteria.
9. The user approves Issue creation.
10. Ichnos creates the Issues and records their identifiers.
11. The user selects an approved Story.
12. Ichnos retrieves the Story, parent artifacts, relevant code, ADRs and related PRs.
13. Ichnos generates an implementation plan and traceability checklist.
14. The user optionally asks for a branch or draft PR.
15. Ichnos shows the exact proposed GitHub action.
16. The user approves or rejects it.
17. Ichnos displays the requirement-to-implementation trace.

# Product principles

- **GitHub is canonical.** Issues, PRs, commits, files and history are the source of truth; Ichnos indexes are rebuildable projections.
- **Human approval is a product feature.** Users inspect content, evidence, assumptions and exact external actions before anything becomes canonical.
- **Evidence over confidence.** Show the evidence behind a claim instead of an unsupported confidence score.
- **Local-first and provider-neutral.** Support local models and user-selected hosted providers.
- **Structured artifacts over chat.** The primary interface is artifact review, workflow status, approval and traceability.
- **Start narrow.** Validate one complete workflow before adding agents, databases or graph visualization.

# Functional requirements

## FR-1: Workspace setup
- Configure one or more GitHub repositories: access, repository and branch, paths to index, model provider, embedding provider, optional Slack webhook.
- Ship `.env.example` and a Docker Compose setup.

## FR-2: Repository and GitHub ingestion
- Ingest configurable Markdown and text files, prioritising `docs/` (an OKF bundle), `.github/`, ADRs, meeting notes and specifications.
- Retrieve Issues, comments, labels, milestones, PRs, reviews, commits and changed-file metadata.
- Preserve source URLs, paths, headings, commit SHAs, authors and timestamps.
- Synchronization is incremental and idempotent.

## FR-3: Requirements intake
- Paste text, upload a Markdown or text file, or select an existing repository document.
- Every intake item creates an immutable source record.

## FR-4: Requirements and BRD generation
- Generate a draft with: problem, users, goals, non-goals, functional and non-functional requirements, scope, assumptions, open questions, risks, proposed acceptance criteria and source traceability.
- Output is an OKF concept with `generated`, `status: draft` and `sources`.
- Unsupported statements become assumptions or open questions, never facts.

## FR-5: Artifact editing and review
- Edit generated Markdown before approval.
- Show citations, retrieved context, assumptions, open questions, generation status, version and generated-vs-edited diff.

## FR-6: Human approval gates
- Pause before: approving an artifact, creating or modifying Issues, applying labels or milestones, creating a branch, opening a PR, sending a Slack notification.
- Show the exact target and payload.
- Execute only the exact approved payload; never regenerate it after approval.
- Approval of a document records `verified: { by: human:<login> }` in its OKF frontmatter.

## FR-7: Planning generation
- From an approved BRD/spec, propose: Epic, Stories, acceptance criteria, dependencies, scope exclusions, priorities with rationale, links to source requirements.
- Proposals are editable before GitHub creation.

## FR-8: GitHub Issue creation
- After approval, create Issues with title, body, labels, milestone, parent links, source specification links and acceptance criteria.
- Record Issue numbers and URLs in the workflow run.

## FR-9: Story context pack
- Assemble: Story, parent Epic, Initiative, linked BRD and techspec, relevant ADRs, related Issues and PRs, relevant files, acceptance criteria, known constraints.
- Every item exposes its source reference and OKF trust tier.

## FR-10: Implementation planning
- Generate: files to change, data and API changes, steps, testing strategy, risks, unresolved questions, acceptance-criteria mapping.
- Never claim code has changed before a real repository action.

## FR-11: Draft branch or pull request
- After approval, optionally create a branch or draft PR.
- A PR includes: linked Story, summary, acceptance-criteria mapping, test plan, context sources, AI-assistance disclosure, risk notes.

## FR-12: Traceability
- Display Requirement → Epic → Story → Acceptance Criterion → PR → Commit → Test.
- Identify missing links and unsupported traceability claims.

## FR-13: Grounded Q&A
- Answer natural-language questions over indexed repository and GitHub content, with source links or paths.
- State when evidence is insufficient, conflicting or stale.

## FR-14: Workflow runs
- Show run ID, workflow type, stage, status, inputs, outputs, sources, pending approvals, errors and timestamps.

## FR-15: Optional Slack notifications
- Notify on: draft ready, approval requested, GitHub action completed, CI failure, PR ready.
- Slack is a notification channel only, never canonical storage.

# Non-functional requirements

- **Portability:** Linux, macOS and Windows via Docker; local machine or single VPS; no mandatory cloud provider.
- **Reliability:** idempotent sync; indexes rebuildable from GitHub and files; failed runs keep state and allow retry; approval payloads stable until approved, rejected or expired.
- **Performance** (up to 1,000 indexed artifacts): incremental sync normally under 5 minutes; context queries normally under 15 seconds excluding model latency; live progress without page refresh.
- **Observability:** record stages, tool calls, retrieval sources, artifacts, edits, approvals, GitHub actions, errors and retries.
- **Accessibility:** keyboard-accessible approvals; clear status and errors; readable Markdown and code; laptop-friendly layout; no critical step depends only on a graph view.
- **Documentation:** every repository `docs/` directory Ichnos writes to stays a conformant OKF bundle.

# Evaluation targets

- At least 90% of generated Stories include parent and source links.
- At least 90% of generated answers include valid source references.
- At least 80% of generated acceptance criteria are judged clear and testable after review.
- Zero unapproved GitHub writes.
- A new user starts the demo in under 30 minutes after cloning and configuring credentials.

# Business risks

| Risk | Mitigation |
| --- | --- |
| Product becomes a generic chat interface | Prioritise artifacts, approvals, runs and traceability screens |
| Agent hallucination | Require sources, assumptions, open questions and human approval |
| Slack becomes the real source of truth | Store decisions in GitHub docs or Issues; Slack only notifies |
| Self-hosting is hard | Simple Docker Compose, `.env.example`, health checks, troubleshooting docs |
| Unclear setup for open-source users | Complete demo repository and one-command startup |
| UI work delays workflow validation | Build only the screens needed for the vertical slice |

# Definition of done

The MVP is done when the Docker Compose setup runs the full demo scenario (meeting note → BRD → Epic and Stories → context pack and plan → draft PR → trace) with no GitHub write made without explicit approval, no dependency on GCP, AWS, Jira or a managed database, and all documentation in a conformant OKF bundle.

[^prd]: Product Requirements Document v0.1
