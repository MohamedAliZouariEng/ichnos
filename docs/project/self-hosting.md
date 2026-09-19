---
type: Howto
title: Self-hosting Ichnos
description: Run Ichnos with Docker Compose, connect GitHub with a read-only token, and back up, upgrade and troubleshoot an installation.
tags: [self-hosting, docker, operations, security]
status: stable
generated: { by: claude/opus-5, at: 2026-09-19T17:09:14Z }
verified: { by: human:MohamedAliZouariEng, at: 2026-09-19T17:09:14Z }
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

[^adr-0004]: ADR-0004: GitHub access through a fine-grained personal access token
[^adr-0006]: ADR-0006: Ollama as an optional Docker Compose profile
