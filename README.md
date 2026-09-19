# Ichnos

A self-hosted, GitHub-native agentic SDLC workspace that turns requirements into reviewed, traceable engineering work.

*Ichnos* (ἴχνος) is Greek for "footprint" or "trace": every requirement should leave an inspectable trace from meeting note to specification, GitHub Issue, pull request and test.

## Status

Pre-alpha. Currently in **Phase 0: repository bootstrap**.

## Principles

- **GitHub is canonical.** Issues, pull requests, commits and repository files are the source of truth.
- **Humans approve every write.** AI prepares and explains work; people decide what becomes canonical.
- **Evidence over confidence.** Every generated claim points to its sources.
- **Local-first and provider-neutral.** Runs on your machine with Docker Compose and the model provider you choose.

## Documentation

All documentation in [`docs/`](docs/index.md) follows the [Open Knowledge Format (OKF)](https://okf.md/): Markdown files with typed YAML frontmatter, readable by humans and AI agents alike.

## License

[Apache-2.0](LICENSE)
