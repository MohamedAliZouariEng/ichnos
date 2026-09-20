#!/usr/bin/env bash
# One command from a filled-in .env to a running, synced demo workspace (ADR-0026).
set -euo pipefail
cd "$(dirname "$0")/.."
env_file="${ICHNOS_ENV_FILE:-.env}"
fail() { echo "demo: $*" >&2; exit 1; }
value() { grep -E "^$1=" "$env_file" 2>/dev/null | tail -1 | cut -d= -f2- || true; }

command -v docker >/dev/null || fail "Docker is not installed: https://docs.docker.com/get-docker/"
docker compose version >/dev/null 2>&1 || fail "Docker Compose v2 is not available."
[ -f "$env_file" ] || fail "No $env_file yet. Run: make demo-repo (it creates one), then fill it in."

required="ICHNOS_GITHUB_TOKEN ICHNOS_LLM_PROVIDER ICHNOS_APPROVER_PASSWORD DEMO_REPO"
[ "$(value ICHNOS_LLM_PROVIDER)" = "ollama" ] || required="$required ICHNOS_LLM_API_KEY"
missing=""
for name in $required; do
  [ -n "$(value "$name")" ] || missing="$missing $name"
done
[ -z "$missing" ] || fail "Set these in $env_file first:$missing (see the README, Quick start)."

repo=$(value DEMO_REPO)
port=$(value ICHNOS_WEB_PORT)
port="${port:-8765}"
api="http://127.0.0.1:$port/api"

docker compose up --build --detach --wait
docker compose exec -T -e ICHNOS_CHECK_REPOSITORY="$repo" api /app/.venv/bin/python -m ichnos.doctor \
  || fail "Fix the failed checks above, then run make demo again."

id=$(curl -fsS "$api/workspaces" | python3 -c '
import json, sys
print(next((w["id"] for w in json.load(sys.stdin) if w["repository"] == sys.argv[1]), ""))
' "$repo")
if [ -z "$id" ]; then
  id=$(curl -fsS -X POST "$api/workspaces" -H 'Content-Type: application/json' \
    -d "{\"name\": \"quire\", \"repository\": \"$repo\"}" \
    | python3 -c 'import json, sys; print(json.load(sys.stdin)["id"])')
  echo "Created the workspace for $repo."
fi

curl -fsS -X POST "$api/workspaces/$id/sync" >/dev/null
status="running"
for _ in $(seq 1 90); do
  status=$(curl -fsS "$api/workspaces/$id/sync-runs" | python3 -c '
import json, sys
runs = json.load(sys.stdin)
print(runs[0].get("status", "unknown") if runs else "none")
')
  case "$status" in succeeded|completed|done|failed|error) break ;; esac
  sleep 2
done
echo "First sync: $status."

cat <<EOM

Ichnos is running at http://localhost:$port with the workspace "quire" for $repo.
  1. Inbox: the synced meeting note, glossary and ADR, each with its type and trust tier.
  2. Questions: ask "What did the onboarding meeting decide about invitation links?"
  3. Workflow runs: draft a BRD from the meeting note, then follow the self-hosting guide.
If anything looks wrong, run: make doctor
EOM
