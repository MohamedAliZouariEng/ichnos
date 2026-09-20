---
type: Howto
title: Self-hosting Ichnos
description: Run Ichnos with Docker Compose, connect GitHub with a read-only token, and back up, upgrade and troubleshoot an installation.
tags: [self-hosting, docker, operations, security]
status: stable
generated: { by: claude/opus-5, at: 2026-09-19T21:11:24Z }
verified: { by: human:MohamedAliZouariEng, at: 2026-09-19T21:11:24Z }
sources:
  - id: adr-0004
    resource: /adr/0004-github-access-fine-grained-pat.md
    title: "ADR-0004: GitHub access through a fine-grained personal access token"
  - id: adr-0006
    resource: /adr/0006-ollama-optional-compose-profile.md
    title: "ADR-0006: Ollama as an optional Docker Compose profile"
---

# Requirements

- Docker with Compose v2.24 or later.
- About 1 GB of free memory for the default stack; local models need several more.
- A GitHub account that can read the repositories Ichnos should work on.

# Quick start

```bash
git clone https://github.com/MohamedAliZouariEng/ichnos.git
cd ichnos
cp .env.example .env
docker compose up --build --wait
```

Open http://localhost:8765, enter a workspace name and repository (`owner/name`), and save it.

# Connect GitHub

Ichnos reads GitHub with a fine-grained personal access token.[^adr-0004]

1. On GitHub, open Settings → Developer settings → Personal access tokens → Fine-grained tokens, and generate a new token.
2. Repository access: only the repositories Ichnos should read.
3. Repository permissions: Contents, Issues and Pull requests, all read-only. Metadata is added automatically.
4. Put the token in `.env` as `ICHNOS_GITHUB_TOKEN=…` and restart with `docker compose up --wait`.
5. In the UI, select **Check GitHub access**.

The token is read from the environment only. It is never stored in the database, returned by the API, or copied into an image.

# Sync a repository

1. Give the token read access to every repository you add as a workspace: edit the fine-grained token on GitHub and add the repository under **Repository access**.
2. In the UI, choose the workspace in the top bar, open **Inbox**, and select **Sync now**.

A sync reads the documents under the workspace's paths to index, plus Issues, pull requests, comments, reviews, changed files and commits (ADR-0009). The first sync of a small repository takes a few dozen requests; later syncs fetch only what changed, and an unchanged repository costs about four.

Everything a sync stores is derived from GitHub. To rebuild it from scratch, reset the workspace's knowledge and sync again:

```bash
curl -X DELETE http://127.0.0.1:8765/api/workspaces/<workspace-id>/knowledge
```

# Configure a model

Workflows call a language model through any OpenAI-compatible API (ADR-0012). Set these in `.env`, then restart with `make up`:

```bash
ICHNOS_LLM_PROVIDER=openai-compatible
ICHNOS_LLM_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai
ICHNOS_LLM_MODEL=gemini-3.8-flash
ICHNOS_LLM_API_KEY=your-key
```

The same settings point at OpenAI, OpenRouter, Groq or a local Ollama (`http://ollama:11434/v1` with `--profile ollama`, and no key). `ICHNOS_LLM_REASONING_EFFORT` defaults to `low`, which keeps hidden reasoning tokens down; set it to `off` for models that reject the parameter. A workspace can override the model name in its settings.

Open **Workspace** and select **Check model**: one small structured call proves the model answers in the expected format. Not every model a key lists supports chat completions.

When a workflow runs, the meeting note and the repository content it retrieves are sent to the model provider, and the UI says so whenever the provider is not on this machine. Check the provider's terms for your tier before using private repositories.

# Draft and review a BRD

1. Sync the workspace (**Inbox**, then **Sync now**) and open **Workflow runs**.
2. Choose a synced meeting note, paste text or upload a `.md` or `.txt` file, and select **Draft BRD**. The run shows its stages live: retrieval, requirements and specification.
3. Select **Review draft**. Every requirement cites its source; statements the sources do not support become assumptions or open questions.
4. Edit the draft in **Edit**, save it as a new version, and compare versions in **Changes**.

Drafts stay in the Ichnos database until they are approved, which arrives in Phase 4; nothing is written to GitHub before then (ADR-0014). Back up the data volume while drafts are under review.

# Configuration

All settings live in `.env`; empty values mean "not set".

| Variable | Purpose |
| --- | --- |
| `ICHNOS_GITHUB_TOKEN` | Read-only GitHub token |
| `ICHNOS_WEB_PORT` | Port for the UI on this machine (default 8765) |
| `ICHNOS_LLM_*`, `ICHNOS_EMBEDDING_*` | Model providers; used from Phase 3 |

# Security

Ichnos has no user authentication yet; it arrives with approvals in Phase 4. The UI is therefore published on `127.0.0.1` only. To use Ichnos on a remote server, keep it that way and connect through an SSH tunnel:

```bash
ssh -L 8765:127.0.0.1:8765 you@your-server
```

Do not publish the port on a public interface until authentication exists.

# Local models

Start the bundled Ollama service with `docker compose --profile ollama up --wait`, then set `ICHNOS_LLM_PROVIDER=ollama` and `ICHNOS_LLM_BASE_URL=http://ollama:11434` in `.env`.[^adr-0006]

# Data, backup and upgrade

Ichnos keeps its metadata in the Docker volume `ichnos_ichnos-data`. GitHub stays the source of truth; this volume holds workspaces, runs, approvals and the audit log.

Back up while the stack is stopped:

```bash
docker compose down
docker run --rm -v ichnos_ichnos-data:/data -v "$PWD":/backup alpine \
  tar czf /backup/ichnos-data.tgz -C /data .
docker compose up --wait
```

Upgrade by pulling and rebuilding; database migrations run automatically when the API starts:

```bash
git pull
docker compose up --build --wait
```

# Troubleshooting

| Symptom | Fix |
| --- | --- |
| `port is already allocated` or `address already in use` | Another program uses the port; set `ICHNOS_WEB_PORT` in `.env` |
| A service stays unhealthy | Run `docker compose logs api` and `docker compose ps` |
| The UI says "API unreachable" | Check that the `api` container is healthy |
| GitHub check: "token rejected" | The token expired or was revoked; create a new one |
| GitHub check: "repository not found" | The token does not include that repository, or the name is wrong |
| Sync failed: "Rate limit reached" | Wait until the time in the message; later syncs cost far fewer requests |
| Sync failed: "Not Found" | The token cannot read the repository, or the branch does not exist; select **Check GitHub access** |
| Model check: "only supports Interactions API" | That model does not offer chat completions; choose another from the provider's list |
| Run failed: "HTTP 429" | The provider's rate limit; wait, then start the run again |
| Run shows `interrupted` | The API stopped during the run; start it again |

[^adr-0004]: ADR-0004: GitHub access through a fine-grained personal access token
[^adr-0006]: ADR-0006: Ollama as an optional Docker Compose profile

## Approvals and writing to GitHub

Ichnos reads a repository freely, but it writes to GitHub only after a person approves the exact change ([ADR-0015](/adr/0015-pending-actions-and-one-write-client.md)).

**Token.** Give `ICHNOS_GITHUB_TOKEN` a fine-grained token for the one repository, with read and write access to Contents, Pull requests and Issues. The token's owner is the approver: publishing records `verified: human:<their login>` ([ADR-0016](/adr/0016-approver-session-and-identity.md)).

**Passphrase.** Set `ICHNOS_APPROVER_PASSWORD` in `.env` and restart. Without it, Ichnos can propose writes but nobody can approve them. Use **Sign in to approve** in the top bar. A session ends after `ICHNOS_SESSION_IDLE_HOURS` idle hours (8 by default) or when the API restarts. Five wrong passphrases in five minutes lock sign-in for five minutes.

**What approving checks.** The Approval Center shows the full payload: every file of a pull request, or every Issue with its body. Approving is refused, and nothing is written, when the action changed since you opened it, when it was prepared for another approver, or when the stored payload no longer matches its hash. An action becomes **stale**, again with nothing written, when the draft was edited after proposing or when a file it touches changed on GitHub. Propose it again to rebuild it on the current files.

**Publishing a BRD.** On a draft's page, **Publish…** proposes one pull request on an `ichnos/…` branch: the BRD as a `stable`, human-verified concept, any pasted meeting notes, index entries and a `log.md` line ([ADR-0017](/adr/0017-how-ichnos-writes-to-github.md)). Ichnos never merges. Review and merge the pull request on GitHub yourself.

**Planning.** An approved BRD can be planned once: **Plan Epic and Stories** drafts one Epic and three to five Stories, then waits for your approval before creating any Issue. You can edit the Issues' titles and bodies before approving; the edited text is what gets written. Merge the BRD's pull request **before** planning, so Ichnos can propose recording the Issue numbers in the BRD. If you planned first, use **Link Issues into the BRD** on the planning run's page after merging.

**Working with two repositories.** Ichnos's own repository and the repository it writes to look alike on GitHub. When you merge from the command line, always name the repository: `gh pr merge <number> --repo <owner>/<name>`.

## Story context and implementation

**Code awareness.** Every sync also records the repository's files outside the documentation paths: path, blob SHA, size and language. File contents are not stored ([ADR-0019](/adr/0019-context-packs.md)).

**Context pack.** In **GitHub context**, **Context pack** on an Issue shows everything needed to implement that Story: its Epic, the BRD and techspec it references, the ADRs they cite or that match its words, related Issues and pull requests, and code files chosen by the paths and names it mentions. Every item has an identifier (`P1`, `P2`…), its source (a path at a blob SHA, or an Issue or pull request number), its trust tier, and flags such as *unverified*, *stale*, *merged* or *closed without merging*. Parts that do not exist are listed as not found. Code is read at the commit the last sync recorded, one request per file, at most 20 files of 40 KB.

**Planning a Story.** **Plan this Story** sends the Story and its context pack, including code, to the configured model, and stores the result as an implementation plan you can review, edit and version. Code checks the plan: every acceptance criterion maps to steps or tests or becomes an open question, files are in the pack or marked new, citations point at real pack items, and the plan keeps the line "Plan only: no code has changed." A plan never claims finished work; conditions such as "until Story #9 is implemented" are allowed ([ADR-0020](/adr/0020-implementation-plans.md)).

**Draft pull request.** On a plan without check errors, **Open draft PR…** proposes a branch `ichnos/story-<number>-…` with one empty commit and a draft pull request that closes the Story, lists every acceptance criterion as not started, summarises the plan, names the context it used and discloses AI assistance. Ichnos first rebuilds the context pack: if anything changed since the plan was drafted, it asks you to plan again. After your approval, the pull request changes 0 files; Ichnos never marks it ready or merges it ([ADR-0021](/adr/0021-draft-pull-requests-for-stories.md)).

**Decisions.** A plan may propose decisions under **Proposed decisions**. **Publish decision…** turns one into the next ADR, written as an OKF `Decision` concept, through the same approved documentation pull request as a BRD.

## Traceability and questions

**Traceability.** **Traceability** follows each requirement of a BRD to the Stories that list it, their acceptance criteria, the pull requests that close them, their commits, and their tests. Every row shows a status and the evidence behind it, with links ([ADR-0022](/adr/0022-traceability.md)). Test evidence comes from test paths named in a pull request's acceptance criteria table, from changed test files, and from CI check runs on the pull request's head commit; the sync reads check runs only while a head commit is new or its runs are unfinished.

**Findings.** Each trace lists what is missing or weak: requirements without a Story, Stories without a pull request, acceptance criteria without a test (an error once the pull request is merged), criteria marked done without a named test, failing checks, and unverified or stale BRDs. Evidence found by guessing, such as a changed test file, is marked inferred. A signed-in person can **Confirm…** it; the confirmation is audited, kept across knowledge resets, and never written to GitHub ([ADR-0023](/adr/0023-trace-validation-and-confirmation.md)).

**Questions.** **Questions** answers questions about the repository. The question and the retrieved sources go to the configured model; nothing is written to GitHub. Every statement cites numbered sources, statements without a valid source are dropped, and the answer lists its gaps: what the sources do not show, weak sources it relied on, and tests asked about but not found passing. When an answer cites a trace, its **Evidence trail** links the decision, the BRD heading, the Story, the pull request and the tests, built by code rather than by the model ([ADR-0024](/adr/0024-grounded-answers.md)). Answers are kept in Ichnos.

**Test evidence in your repository.** Traces are most useful when pull requests name the tests for each acceptance criterion, for example `| AC-01: … | Done | tests/test_invitations.py::test_expiry |`, and when CI runs on pull requests. Draft pull requests that Ichnos opens already contain this table.
