---
type: Reference
title: "Building Ichnos: an assistant that proposes, and people who approve"
description: "How Ichnos keeps requirements, plans, code and tests connected: its principles, its design, what real data taught it, and what its first release measured."
tags: [article, design, evaluation]
status: stable
generated: { by: claude/opus-5, at: 2026-09-20T16:02:48Z }
verified: { by: human:MohamedAliZouariEng, at: 2026-09-20T16:02:48Z }
sources:
  - id: adr-0015
    resource: /adr/0015-pending-actions-and-one-write-client.md
    title: "ADR-0015: Every GitHub write is an approved pending action, executed by one write client"
  - id: adr-0019
    resource: /adr/0019-context-packs.md
    title: "ADR-0019: Context packs are assembled by code from synced knowledge, with provenance on every item"
  - id: adr-0021
    resource: /adr/0021-draft-pull-requests-for-stories.md
    title: "ADR-0021: A Story's draft pull request starts with an empty commit and claims no code changes"
  - id: adr-0022
    resource: /adr/0022-traceability.md
    title: "ADR-0022: Traceability is assembled by code from recorded links, with status and evidence on every row"
  - id: adr-0024
    resource: /adr/0024-grounded-answers.md
    title: "ADR-0024: Answers are grounded: every statement cites a retrieved source, and gaps are stated"
  - id: adr-0025
    resource: /adr/0025-evaluation-metrics.md
    title: "ADR-0025: Evaluation metrics are computed by code from Ichnos's own data"
  - id: evaluation
    resource: /project/evaluation-v0.1.0.md
    title: "Ichnos v0.1.0 evaluation"
---

# The problem

Requirements start in meetings, become documents, turn into Stories, and end as pull requests and tests. Each step is written by someone else, somewhere else, and the links between them are kept in people's heads. AI assistants make each step faster, and make the drift faster too: a model can draft a requirement nobody agreed to, or describe code that does not exist.

Ichnos is a self-hosted assistant built around one question: can every artifact be followed back to the decision that caused it, and forward to the test that checks it?

# Five principles

**Knowledge lives in the repository.** Meeting notes, requirements and decisions are Markdown files in Open Knowledge Format (OKF), with typed frontmatter that records who generated each one, who verified it, and which sources it rests on. Ichnos syncs them; it never keeps a private copy of the truth.

**The model proposes, code enforces.** Every model output passes through code that checks it: requirements must cite their sources, plans must map every acceptance criterion, and answers must cite a retrieved source in every statement. Statements without a real source are dropped, not repaired.[^adr-0024]

**Every write waits for a person.** Publishing a document, creating Issues, opening a pull request: each is a pending action whose exact payload a person reviews. One write client executes approved actions, and only the approval service may call it; an architecture test fails the build otherwise.[^adr-0015]

**Ichnos never claims work that does not exist.** A Story's draft pull request starts from an empty commit and says so. A plan may say what should be built, never that it was.[^adr-0021]

**Numbers are measured.** Every figure in the release notes comes from code or a timer, and is recorded with the commit it was measured on.[^adr-0025]

# How it fits together

A sync reads documents, Issues, pull requests, commits, files and CI check runs into SQLite, validates the documents as OKF, records links between them with their origin and evidence, and indexes everything for full-text search. Workflows such as drafting a requirements document run as resumable graphs whose events stream to the browser. A Story's context pack is assembled by code, not by a model: its Epic, the requirements it implements, the decisions they cite, related work, and the code files it names, each with its provenance.[^adr-0019]

Traces follow each requirement to its Stories, acceptance criteria, pull requests, commits, tests and check runs, with a status and evidence on every row, and findings for whatever is missing.[^adr-0022] Answers draw on the same material: numbered sources, statements that cite them, stated gaps, and an evidence trail from the decision to the test, built by code so the model cannot drop a link from it.

# What real data taught it

Seeded tests passed long before real data did. Running on a real repository found problems no fixture had:

- A model wrote acceptance criterion identifiers in a different form, so every criterion looked unmapped. Identifiers are now normalised.
- "Keep the message compatible until Story #9 is implemented" was flagged as a false claim of finished work. Conditions are no longer claims; the first fix then let "the expiry check is implemented" through, because "check" is also a noun.
- An Epic that listed requirements was traced as a Story, doubling the warnings. Issues with children are Epics.
- Link-expanded retrieval first reached 83% of expected sources, not 100%: a retrieved trace was used as text, not as a way to reach its requirement and Story. The measurement found the gap before any user did.
- The first person to follow the README left a placeholder token in the configuration, and the setup check called it "expired". It now recognises a placeholder without sending it anywhere.

Each of these now has a test built from the words that exposed it.

# What the first release measured

A new user went from cloning the repository to a first answer in 11 minutes 59 seconds. On the demo repository, every Story had parent and source links, every stored answer cited valid sources, every acceptance criterion passed the testability rules and an independent model review, and no write happened without an approval. Link-expanded retrieval found every expected source; full-text search alone found 75%.[^evaluation]

These numbers have limits. The person who timed the setup was the project's author. Five questions and one demo repository are a small sample. The next steps are measuring on repositories Ichnos was not built against, and on people who have never read its code.

[^adr-0015]: ADR-0015: Every GitHub write is an approved pending action, executed by one write client
[^adr-0019]: ADR-0019: Context packs are assembled by code from synced knowledge, with provenance on every item
[^adr-0021]: ADR-0021: A Story's draft pull request starts with an empty commit and claims no code changes
[^adr-0022]: ADR-0022: Traceability is assembled by code from recorded links, with status and evidence on every row
[^adr-0024]: ADR-0024: Answers are grounded: every statement cites a retrieved source, and gaps are stated
[^adr-0025]: ADR-0025: Evaluation metrics are computed by code from Ichnos's own data
[^evaluation]: Ichnos v0.1.0 evaluation
