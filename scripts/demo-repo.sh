#!/usr/bin/env bash
# Create your own copy of the Quire demo repository from examples/demo-repository (ADR-0026).
# Uses your gh login; Ichnos itself writes nothing here.
set -euo pipefail
cd "$(dirname "$0")/.."
env_file="${ICHNOS_ENV_FILE:-.env}"

command -v gh >/dev/null || { echo "Install the GitHub CLI, then run: gh auth login"; exit 1; }
gh auth status >/dev/null 2>&1 || { echo "Sign in first: gh auth login"; exit 1; }
owner=$(gh api user --jq .login)
repo="$owner/${DEMO_REPO_NAME:-quire-demo}"

if gh repo view "$repo" >/dev/null 2>&1; then
  echo "$repo already exists; the demo will use it."
else
  work=$(mktemp -d)
  cp -r examples/demo-repository/. "$work/"
  (
    cd "$work"
    git init -q -b main
    git add .
    git -c user.name="$owner" -c user.email="$owner@users.noreply.github.com" \
      commit -q -m "Start the Quire demo from the Ichnos examples"
    gh repo create "$repo" --public --source . --push \
      --description "Quire: a demo repository for Ichnos" >/dev/null
  ) || {
    echo "Creating $repo failed. If the push was refused because of the workflow file,"
    echo "run: gh auth refresh -s workflow   and then make demo-repo again."
    rm -rf "$work"; exit 1
  }
  rm -rf "$work"
  echo "Created https://github.com/$repo"
fi

[ -f "$env_file" ] || cp .env.example "$env_file"
if grep -q '^DEMO_REPO=' "$env_file"; then
  sed -i "s|^DEMO_REPO=.*|DEMO_REPO=$repo|" "$env_file"
else
  printf '\nDEMO_REPO=%s\n' "$repo" >> "$env_file"
fi

cat <<EOM

Next, create a GitHub token for $repo:
  1. Open https://github.com/settings/personal-access-tokens/new
  2. Repository access: Only select repositories -> $repo
  3. Permissions: Contents, Issues and Pull requests -> Read and write
     (Metadata: read is added automatically; Ichnos writes only what you approve.)
  4. In $env_file set ICHNOS_GITHUB_TOKEN, the model settings (ICHNOS_LLM_*),
     and ICHNOS_APPROVER_PASSWORD. Then run: make demo
EOM
