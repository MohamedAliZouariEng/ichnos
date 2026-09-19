# Quire demo repository

Sample repository used to demonstrate Ichnos end to end. Quire is a fictional shared-notebook app for small teams.

- `docs/` is an [OKF v0.2](https://okf.md/) bundle: product context, one architecture decision, and the meeting note that starts the demo.
- The demo follows one feature, **invitation expiry**, from the meeting note to a BRD, GitHub Stories, a pull request and its tests.
- In Phase 2 this folder is published as its own GitHub repository, so Ichnos can sync it like any other project.
- Publish it with `scripts/publish_demo.sh` from the Ichnos repository. It creates `<your-login>/quire-demo` with labels, an Epic, a Story, a task and a merged pull request.
