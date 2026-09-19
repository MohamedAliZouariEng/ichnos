#!/usr/bin/env bash
# Publish the Quire demo repository to GitHub and seed it with Issues and a merged pull request.
# Usage: scripts/publish_demo.sh [owner/name]   (default: <your-login>/quire-demo)
# Run once per target repository. Requires: gh (authenticated), git, uv, python3.
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
LOGIN="$(gh api user --jq .login)"
REPO="${1:-$LOGIN/quire-demo}"
NOW="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
TODAY="$(date -u +%F)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

number() { basename "$1"; }  # gh prints the URL of what it created; the number is its last segment

if gh repo view "$REPO" >/dev/null 2>&1; then
  echo "Repository $REPO already exists; refusing to seed it twice." >&2
  exit 1
fi

echo "==> Creating $REPO from examples/demo-repository"
cp -R "$ROOT/examples/demo-repository/." "$WORK/"
cd "$WORK"
git init -q -b main
git add -A
git commit -q -m "Add Quire documentation"
gh repo create "$REPO" --public --source . --push \
  --description "Quire: fictional demo repository for Ichnos"

echo "==> Labels"
"$ROOT/scripts/sync_labels.sh" "$REPO" >/dev/null

echo "==> Issues"
EPIC=$(number "$(gh issue create -R "$REPO" --title "Invitation lifecycle hardening" \
  --label "type:epic" --label "status:approved" --body-file - <<'EOF'
## Summary
Invitations should stop working after a while, and people who open a link that no longer works should understand why.

## Source specification
- docs/meetings/2026-09-15-workspace-onboarding.md
EOF
)")

STORY=$(number "$(gh issue create -R "$REPO" --title "Explain invalid invitation links instead of showing Page not found" \
  --label "type:story" --label "status:draft" --body-file - <<EOF
## Parent
- Epic: #$EPIC

## Source specification
- docs/meetings/2026-09-15-workspace-onboarding.md

## Acceptance criteria
- [ ] AC-01: Given an invitation that was already accepted, when someone opens its link, then they see that the invitation was already used and how to ask for a new one.
- [ ] AC-02: Given a link with an unknown token, when someone opens it, then they see that the link is not valid.

## Scope exclusions
- Invitation expiry is covered by a separate Story.
EOF
)")

gh issue comment "$STORY" -R "$REPO" --body \
  "Support: two customers hit this last week and assumed Quire was down. Today's behaviour is described in docs/project/product-overview.md." >/dev/null

TASK=$(number "$(gh issue create -R "$REPO" --title "Add a glossary for onboarding terms" \
  --label "documentation" --body-file - <<EOF
While discussing #$STORY we used "invite", "invitation" and "invitation link" for different things. A short glossary next to the product overview would help.
EOF
)")

echo "==> Pull request"
git switch -q -c docs/glossary
cat > docs/project/glossary.md <<EOF
---
type: Reference
title: Onboarding glossary
description: Terms used when talking about workspace invitations.
tags: [glossary, onboarding]
status: stable
generated: { by: claude/opus-5, at: $NOW }
verified: { by: human:$LOGIN, at: $NOW }
---

# Terms

| Term | Meaning |
| --- | --- |
| Invitation | A pending offer for one email address to join one workspace. |
| Invitation link | The URL in the invitation email; it carries the invitation token. |
| Invitation token | The random single-use secret in the link, stored only as a hash ([ADR-0001](/adr/0001-invitation-tokens.md)). |
| Accepted invitation | An invitation whose token was used to join the workspace. |

See the [product overview](/project/product-overview.md) for how onboarding works today.
EOF
echo "* [Onboarding glossary](glossary.md) - Terms used when talking about workspace invitations." >> docs/project/index.md
python3 - "$TODAY" <<'EOF'
import sys
from pathlib import Path

log = Path("docs/log.md")
lines = log.read_text(encoding="utf-8").splitlines()
first = next(i for i, line in enumerate(lines) if line.startswith("## "))
lines[first:first] = [f"## {sys.argv[1]}", "* **Creation**: Added the [onboarding glossary](/project/glossary.md).", ""]
log.write_text("\n".join(lines) + "\n", encoding="utf-8")
EOF
uv run --no-project --with-requirements "$ROOT/scripts/requirements-docs.txt" \
  python "$ROOT/scripts/validate_okf.py" docs --strict

git add -A
git commit -q -m "Add onboarding glossary"
git push -q -u origin docs/glossary
PR=$(number "$(gh pr create -R "$REPO" --base main --head docs/glossary \
  --title "Add onboarding glossary" --body-file - <<EOF
Closes #$TASK

## Summary
Adds a glossary for the invitation terms that keep getting mixed up in #$STORY.

## Context used
- docs/project/product-overview.md
- docs/adr/0001-invitation-tokens.md
EOF
)")
gh pr review "$PR" -R "$REPO" --comment \
  --body "Glossary matches ADR-0001; the token row is the important one." >/dev/null
gh pr merge "$PR" -R "$REPO" --squash --delete-branch >/dev/null

echo
echo "Seeded https://github.com/$REPO"
echo "  Epic #$EPIC, Story #$STORY, Task #$TASK (closed by PR #$PR, merged)"
