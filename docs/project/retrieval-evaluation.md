---
type: Reference
title: "Retrieval evaluation: full text and link-expanded"
description: "What OKF links and traces add to full-text search, measured on a portable question set against the demo repository."
tags: [reference, evaluation, retrieval]
status: stable
generated: { by: claude/opus-5, at: 2026-09-20T15:50:41Z }
verified: { by: human:MohamedAliZouariEng, at: 2026-09-20T15:50:41Z }
sources:
  - id: adr-0024
    resource: /adr/0024-grounded-answers.md
    title: "ADR-0024: Answers are grounded: every statement cites a retrieved source, and gaps are stated"
  - id: adr-0025
    resource: /adr/0025-evaluation-metrics.md
    title: "ADR-0025: Evaluation metrics are computed by code from Ichnos's own data"
---

# Method

Each question is retrieved twice: with full-text search over indexed chunks only, and with link expansion, which adds the documents a matching BRD cites, the traces of its matching requirements, and each trace's heading, Stories, pull requests and tests.[^adr-0024] A question's expected sources are written as `kind:text` and match paths and titles rather than Issue numbers, so the same set runs on any copy of the demo repository. Recall is the share of expected sources retrieved. `make retrieval-eval` runs it.[^adr-0025]

# Results

Measured on `MohamedAliZouariEng/quire-demo` on 2026-09-20.

| Question | Full text | First expansion | Final expansion |
| --- | --- | --- | --- |
| What approved evidence shows that invitation links must expire, and where is that behavior tested? | 2 of 5 | 3 of 5 | 5 of 5 |
| How can an admin resend a pending invitation? | 2 of 2 | 2 of 2 | 2 of 2 |
| What should an invitee see when opening an expired invitation link? | 2 of 2 | 2 of 2 | 2 of 2 |
| Can workspace owners change how long invitation links last? | 2 of 2 | 2 of 2 | 2 of 2 |
| How are invitation tokens stored? | 1 of 1 | 1 of 1 | 1 of 1 |
| **Recall** | **75%** | **83%** | **100%** |

# What the first measurement found

The demo question is long and uses common words, so its eight best full-text chunks went to other text, and neither the BRD heading R-01 nor Story #7 was retrieved. The first expansion added the test file, which full text cannot find, but used the trace of R-01 only as text. Adding each retrieved trace's heading, Stories and pull requests as sources in their own right closed the gap. Short questions whose words appear in headings and titles need no expansion.

# Limits

Five questions and one repository are a small sample. The question set was written by the project's author, who knew the documents. Recall counts whether a source was retrieved, not whether an answer cited it.

[^adr-0024]: ADR-0024: Answers are grounded: every statement cites a retrieved source, and gaps are stated
[^adr-0025]: ADR-0025: Evaluation metrics are computed by code from Ichnos's own data
