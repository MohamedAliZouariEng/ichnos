#!/usr/bin/env bash
# Fail if the old project name appears in any tracked file,
# except for the allow-listed provenance strings.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"

ALLOWLIST=".github/rename-allowlist.txt"

hits=$(git grep -niI "athar" -- . \
  ":(exclude)scripts/check_rename.sh" \
  ":(exclude)$ALLOWLIST" || true)

if [[ -n "$hits" && -f "$ALLOWLIST" ]]; then
  patterns=$(grep -v '^#' "$ALLOWLIST" | sed '/^[[:space:]]*$/d' || true)
  if [[ -n "$patterns" ]]; then
    hits=$(printf '%s\n' "$hits" | grep -vF -- "$patterns" || true)
  fi
fi

if [[ -n "$hits" ]]; then
  echo "Found references to the old project name:"
  printf '%s\n' "$hits"
  exit 1
fi

echo "Rename check passed: no references to the old project name."
