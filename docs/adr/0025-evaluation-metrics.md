---
type: Decision
title: "ADR-0025: Evaluation metrics are computed by code from Ichnos's own data"
description: The release metrics (linked Stories, answers with valid sources, testable acceptance criteria, unapproved writes, demo time and retrieval recall) are measured by code or a timer and recorded with their commit, never estimated.
tags: [adr, evaluation, metrics, testing]
status: stable
generated: { by: claude/opus-5, at: 2026-09-20T13:10:26Z }
verified: { by: human:MohamedAliZouariEng, at: 2026-09-20T13:10:26Z }
sources:
  - id: adr-0015
    resource: /adr/0015-pending-actions-and-one-write-client.md
    title: "ADR-0015: Every GitHub write is an approved pending action, executed by one write client"
  - id: adr-0022
    resource: /adr/0022-traceability.md
    title: "ADR-0022: Traceability is assembled by code from recorded links, with status and evidence on every row"
  - id: adr-0024
    resource: /adr/0024-grounded-answers.md
    title: "ADR-0024: Answers are grounded: every statement cites a retrieved source, and gaps are stated"
ichnos:
  adr_number: 25
---

# Context

The delivery plan's release criteria are measurable: at least 90% of Stories with parent and source links, at least 90% of answers with valid sources, at least 80% of acceptance criteria judged testable, zero unapproved writes, and a new user starting the demo in under 30 minutes. Ichnos already records the data these need: links, traces,[^adr-0022] stored answers with their sources,[^adr-0024] and approvals with their audit events.[^adr-0015]

# Decision

- A Story counts as linked when it is a live Story Issue (not an Epic, not closed as not planned) with an explicit parent link and a link to the BRD it implements.
- An answer counts as valid when every statement cites a source the answer retrieved, and an answer without statements states at least one gap.
- An acceptance criterion counts as testable by code rules: it has Given, When and Then, and no vague word such as fast, easy, intuitive or appropriate without a number. One model review of the same criteria is recorded beside the rules; it is reported, never substituted for them.
- Unapproved writes are counted from the audit log: every executed action must have a human approval of its exact payload hash. The integration test from Phase 4 stays in CI.
- Demo time is measured by a person with a timer, from a fresh clone to the first answered question, following only the README.
- Retrieval is compared on a fixed question set: the recall of expected sources with full-text search alone, and with the documents BRDs cite and the traces of matching requirements added.
- Results are recorded as an OKF `Reference` with the date and the commit they were measured on.

# Consequences

- **Positive:** every number in the release notes can be reproduced by running the same code on the same data.
- **Negative:** code rules for testability are strict and simple; they can reject a testable criterion written in an unusual form, which the recorded model review makes visible.

[^adr-0015]: ADR-0015: Every GitHub write is an approved pending action, executed by one write client
[^adr-0022]: ADR-0022: Traceability is assembled by code from recorded links, with status and evidence on every row
[^adr-0024]: ADR-0024: Answers are grounded: every statement cites a retrieved source, and gaps are stated
