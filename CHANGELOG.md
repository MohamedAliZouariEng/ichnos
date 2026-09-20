# Changelog

All notable changes to Ichnos are recorded here. Versions follow semantic versioning.

## [0.1.0] - 2026-09-20

The first release: a self-hosted assistant that keeps a repository's knowledge as Open Knowledge Format (OKF) concepts, drafts requirements and plans with a model, and writes to GitHub only after a person approves the exact change.

### Added

- **Knowledge sync.** Documents, Issues, pull requests, commits, repository files and CI check runs are synced from GitHub into SQLite, validated as OKF, linked, and indexed for full-text search.
- **Requirements.** A business requirements document (BRD) is drafted from a meeting note, with every requirement citing its source, and edited as a versioned artifact.
- **Approvals.** Every GitHub write is a pending action: a person reviews the exact payload, and one write client executes it. BRDs are published as documentation pull requests; Epics and Stories are created as Issues.
- **Implementation.** A Story's context pack is built by code from synced knowledge; a plan is drafted and checked; a draft pull request starts from an empty commit and claims no code change.
- **Traceability.** Each requirement is followed to its Stories, acceptance criteria, pull requests, commits, tests and check runs, with a status and evidence on every row, and findings for what is missing. People confirm inferred links.
- **Questions.** Answers cite numbered sources in every statement, state their gaps, and carry an evidence trail built by code.
- **Running it.** `make demo-repo` and `make demo` start the demo; `make doctor` says what is wrong and how to fix it; images are published to GitHub Container Registry for each release.

### Measured

A new user reached the first answer in 11 minutes 59 seconds. Stories with parent and source links, answers with valid sources, and testable acceptance criteria were at 100%, with no unapproved writes. Link-expanded retrieval found 100% of expected sources, against 75% for full text. See the [v0.1.0 evaluation](docs/project/evaluation-v0.1.0.md).
