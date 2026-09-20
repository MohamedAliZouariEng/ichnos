---
type: Reference
title: "Ichnos v0.1.0 evaluation"
description: "The release exit criteria, each with its measured result, the commit it was measured on, and the limits of the measurement."
tags: [reference, evaluation, release, metrics]
status: stable
generated: { by: claude/opus-5, at: 2026-09-20T15:50:41Z }
verified: { by: human:MohamedAliZouariEng, at: 2026-09-20T15:50:41Z }
sources:
  - id: adr-0025
    resource: /adr/0025-evaluation-metrics.md
    title: "ADR-0025: Evaluation metrics are computed by code from Ichnos's own data"
  - id: self-hosting
    resource: /project/self-hosting.md
    title: "Self-hosting Ichnos"
  - id: troubleshooting
    resource: /project/troubleshooting.md
    title: "Troubleshooting Ichnos"
---

# Exit criteria

Every number below was measured by code or a timer, as ADR-0025 requires.[^adr-0025] The metrics were read from the demo workspace (`MohamedAliZouariEng/quire-demo`) on 2026-09-20, at commit `5f2c5fe`.

| Criterion | Threshold | Measured | Result |
| --- | --- | --- | --- |
| A new user starts the demo | under 30 minutes | 11 min 59 s, from clone to first answer | Met |
| Stories with parent and source links | ≥ 90% | 5 of 5 (100%) | Met |
| Answers with valid sources | ≥ 90% | 5 of 5 (100%) | Met |
| Acceptance criteria judged testable | ≥ 80% | 7 of 7 (100%) | Met |
| Writes without a human approval | 0 | 0 unapproved of 6 executed | Met |
| `docs/` passes OKF validation | strict, 0 errors | 0 errors, 0 warnings | Met |

The linked Stories include #2, an Issue from an earlier demo step with its own acceptance criteria; the rule counts every live Story, so it is counted too.

# The stranger run

A fresh clone of `phase-7/release`, a fresh demo repository (`quire-stranger`) created by `make demo-repo`, a new fine-grained token for that repository only, and a separate, empty database. Only the README was followed.

| Leg | Time |
| --- | --- |
| Clone | 4 s |
| `make demo-repo` | 12 s |
| `make demo` run before `.env` was complete: it named four missing values and started nothing | 1 s |
| Token created and `.env` filled in, with the token left as a placeholder | about 4 min |
| `make demo` failed on a DNS timeout on the machine, outside Ichnos | 11 s |
| `make demo` refused the placeholder token (401); diagnosed and fixed | about 6.5 min |
| `make demo` succeeded: checks passed, workspace created, first sync succeeded | at 11 min 0 s |
| First answer in Questions | 59 s later |
| **Total** | **11 min 59 s** |

**Limits.** The person was the project's author, so the README's wording was not tested on a newcomer. The Docker build cache was warm. The clone used the release branch, before it reached `main`.

**What it changed.** The setup check now names a placeholder token without sending it to GitHub, and `make demo` checks the demo repository before creating anything. The README says `make demo` refuses to start until `.env` is filled in, and the troubleshooting guide covers DNS timeouts, placeholder tokens and tokens for another repository.[^troubleshooting]

# Acceptance criteria: rules and model

The code rules and one recorded review by `gemini-3.8-flash` judged the same seven criteria. They agreed on 7 of 7, for 708 tokens. The review is reported beside the rules and never replaces them.

# Retrieval

Full-text search alone found 75% of the expected sources on the demo question set; with the documents BRDs cite and the traces of matching requirements, 100%. The [retrieval evaluation](/project/retrieval-evaluation.md) has the details.

[^adr-0025]: ADR-0025: Evaluation metrics are computed by code from Ichnos's own data
[^self-hosting]: Self-hosting Ichnos
[^troubleshooting]: Troubleshooting Ichnos
