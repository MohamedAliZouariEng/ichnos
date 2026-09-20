# Ichnos

A self-hosted, GitHub-native agentic SDLC workspace that turns requirements into reviewed, traceable engineering work.

*Ichnos* (ἴχνος) is Greek for "footprint" or "trace": every requirement should leave an inspectable trace from meeting note to specification, GitHub Issue, pull request and test.

## Status

Pre-alpha. **Phase 3 (requirements workflow)** is complete: from a meeting note, Ichnos drafts an OKF BRD whose every requirement cites its source, and the draft is reviewed, edited and versioned in the browser.

## Quick start

You need Docker with Compose v2, the GitHub CLI signed in (`gh auth login`), and an API key for a model (Gemini works; the [self-hosting guide](docs/project/self-hosting.md) lists others). It takes about 20 minutes.

1. Clone Ichnos: `git clone https://github.com/MohamedAliZouariEng/ichnos && cd ichnos`
2. Create your own copy of the demo repository: `make demo-repo`. It prints which token to create next.
3. Create a fine-grained GitHub token for that repository only, with **Contents**, **Issues** and **Pull requests** set to read and write. In `.env`, set `ICHNOS_GITHUB_TOKEN`, the model settings (`ICHNOS_LLM_PROVIDER`, `ICHNOS_LLM_BASE_URL`, `ICHNOS_LLM_MODEL`, `ICHNOS_LLM_API_KEY`) and an `ICHNOS_APPROVER_PASSWORD` of your choice.
4. Start everything: `make demo`. It checks your setup, starts Ichnos, creates the workspace and runs the first sync.
5. Open http://localhost:8765, go to **Questions** and ask: *What did the onboarding meeting decide about invitation links?*

Ichnos writes to your repository only after you approve the exact change. If something fails, `make doctor` says what is wrong and how to fix it.

## Principles

- **GitHub is canonical.** Issues, pull requests, commits and repository files are the source of truth.
- **Humans approve every write.** AI prepares and explains work; people decide what becomes canonical.
- **Evidence over confidence.** Every generated claim points to its sources.
- **Local-first and provider-neutral.** Runs on your machine with Docker Compose and the model provider you choose.

## Documentation

All documentation in [`docs/`](docs/index.md) follows the [Open Knowledge Format (OKF)](https://okf.md/): Markdown files with typed YAML frontmatter, readable by humans and AI agents alike.

## License

[Apache-2.0](LICENSE)
