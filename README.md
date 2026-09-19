# Ichnos

A self-hosted, GitHub-native agentic SDLC workspace that turns requirements into reviewed, traceable engineering work.

*Ichnos* (ἴχνος) is Greek for "footprint" or "trace": every requirement should leave an inspectable trace from meeting note to specification, GitHub Issue, pull request and test.

## Status

Pre-alpha. **Phase 1 (application foundation)** is complete: a workspace can be configured in the web UI, and its GitHub access checked with a read-only token.

## Quick start

```bash
git clone https://github.com/MohamedAliZouariEng/ichnos.git
cd ichnos
cp .env.example .env
docker compose up --build --wait
```

Open http://localhost:8765. See the [self-hosting guide](docs/project/self-hosting.md) to connect GitHub, and the [development guide](docs/project/development.md) to contribute.

## Principles

- **GitHub is canonical.** Issues, pull requests, commits and repository files are the source of truth.
- **Humans approve every write.** AI prepares and explains work; people decide what becomes canonical.
- **Evidence over confidence.** Every generated claim points to its sources.
- **Local-first and provider-neutral.** Runs on your machine with Docker Compose and the model provider you choose.

## Documentation

All documentation in [`docs/`](docs/index.md) follows the [Open Knowledge Format (OKF)](https://okf.md/): Markdown files with typed YAML frontmatter, readable by humans and AI agents alike.

## License

[Apache-2.0](LICENSE)
