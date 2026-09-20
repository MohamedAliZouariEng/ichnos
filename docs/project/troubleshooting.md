---
type: Howto
title: "Troubleshooting Ichnos"
description: "What to do when the demo or a self-hosted Ichnos misbehaves: run make doctor, then find the symptom."
tags: [howto, troubleshooting, setup]
status: stable
generated: { by: claude/opus-5, at: 2026-09-20T15:17:52Z }
verified: { by: human:MohamedAliZouariEng, at: 2026-09-20T15:17:52Z }
sources:
  - id: self-hosting
    resource: /project/self-hosting.md
    title: "Self-hosting Ichnos"
  - id: adr-0015
    resource: /adr/0015-pending-actions-and-one-write-client.md
    title: "ADR-0015: Every GitHub write is an approved pending action, executed by one write client"
  - id: adr-0026
    resource: /adr/0026-releases.md
    title: "ADR-0026: Releases are tagged, and their images are built by GitHub Actions and published to GHCR"
---

# Start here

Run `make doctor`. It checks the database, migrations, data folder, GitHub token, each workspace's repository, the model and approvals, and prints how to fix anything that fails. It never prints a secret and never calls the model.

# Symptoms

**Approving an action fails with 403 or "Resource not accessible".** The token can read but not write. Create a fine-grained token with Contents, Issues and Pull requests set to read and write for your repository, put it in `ICHNOS_GITHUB_TOKEN`, and run `make up`. Ichnos still writes nothing without your approval.[^adr-0015]

**`make doctor` says GitHub refused the token (401).** The token expired or was revoked. Create a new one as above.

**`make doctor` fails for a repository (404 or 403).** The token was created before the repository existed, or for other repositories. Edit the token's repository access, or correct the repository name in the workspace.

**`make demo-repo` fails while pushing.** Your `gh` login may lack permission to push workflow files. Run `gh auth refresh -s workflow`, then `make demo-repo` again.

**`make demo` stops with "Set these in .env first".** It names each missing value; fill them in and run it again. With `ICHNOS_LLM_PROVIDER=ollama`, no API key is needed.

**The web page does not open.** Another program uses the port. Set `ICHNOS_WEB_PORT` in `.env` and run `make up`. Ichnos listens on 127.0.0.1 only.

**Drafting, planning or questions fail with a model error.** Check `ICHNOS_LLM_*` in `.env`. Some models reject the reasoning setting: set `ICHNOS_LLM_REASONING_EFFORT=off`.

**An answer says no evidence was found.** Run a sync, and check that the workspace's index paths include the folders your documents are in. Ichnos answers only from synced knowledge, and says so when it has none.

**Opening a draft pull request is refused as stale.** The Story's context changed since the plan was drafted, or its branch exists already. Plan the Story again and open the draft pull request from the new plan.

**The trace shows "linked by inference".** A changed test file was matched by name. Check it, then sign in and confirm it, or leave the warning if it is wrong.

# Developing locally

**pytest crashes before collecting, in a plugin of another Python installation** (for example ROS). Run tests through `make`, or remove that installation's path first: `env -u PYTHONPATH uv run pytest`.

**A test file errors with "fixture not found" for an imported function.** pytest collects every function named `test…`, including imported helpers. Name helpers without that prefix.

[^adr-0015]: ADR-0015: Every GitHub write is an approved pending action, executed by one write client
[^adr-0026]: ADR-0026: Releases are tagged, and their images are built by GitHub Actions and published to GHCR
[^self-hosting]: Self-hosting Ichnos
