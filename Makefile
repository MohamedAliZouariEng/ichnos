# Ichnos developer entry point. Run `make help` to list targets.
# Recipe lines start with '>' instead of a tab (see .RECIPEPREFIX).
SHELL := /bin/bash
.RECIPEPREFIX = >
.DEFAULT_GOAL := help

# Keep system-wide Python paths (for example ROS) out of Ichnos tooling. See ADR-0007.
unexport PYTHONPATH

.PHONY: help
help: ## List available targets
> @grep -E '^[a-zA-Z_-]+:.*## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

.PHONY: docs-check
docs-check: ## Validate docs/ as an OKF v0.2 bundle (strict)
> uv run --no-project --with-requirements scripts/requirements-docs.txt python scripts/validate_okf.py docs --strict

.PHONY: rename-check
rename-check: ## Fail on references to the old project name
> bash scripts/check_rename.sh

.PHONY: check
check: docs-check rename-check ## Run all repository checks

# ---- API (apps/api, managed by uv) ----
API_DIR := apps/api

.PHONY: api-install
api-install: ## Install API dependencies with uv
> cd $(API_DIR) && uv sync

.PHONY: api-dev
api-dev: ## Run the API with auto-reload on http://localhost:8000
> cd $(API_DIR) && uv run uvicorn ichnos.main:app --reload --host 127.0.0.1 --port 8000

.PHONY: api-format
api-format: ## Auto-format and auto-fix the API (ruff)
> cd $(API_DIR) && uv run ruff format . && uv run ruff check --fix .

.PHONY: api-lint
api-lint: ## Lint and format-check the API (ruff)
> cd $(API_DIR) && uv run ruff check . && uv run ruff format --check .

.PHONY: api-typecheck
api-typecheck: ## Type-check the API (mypy --strict)
> cd $(API_DIR) && uv run mypy

.PHONY: api-test
api-test: ## Run API tests (pytest)
> cd $(API_DIR) && uv run pytest

check: api-lint api-typecheck api-test

.PHONY: api-migrate
api-migrate: ## Apply database migrations to the local metadata database
> cd $(API_DIR) && uv run alembic upgrade head

.PHONY: api-migration
api-migration: ## Create a migration from model changes: make api-migration m="describe the change"
> cd $(API_DIR) && uv run alembic revision --autogenerate -m "$(m)"

# ---- Contracts (packages/contracts, packages/api-client) ----
.PHONY: contracts
contracts: ## Regenerate openapi.json and TypeScript types from the API
> cd $(API_DIR) && uv run python -m ichnos.openapi ../../packages/contracts/openapi.json
> pnpm --filter @ichnos/contracts run generate

.PHONY: contracts-check
contracts-check: ## Fail if the committed contract or generated types are out of date
> cd $(API_DIR) && uv run python -m ichnos.openapi > /tmp/ichnos-openapi.json
> diff -u packages/contracts/openapi.json /tmp/ichnos-openapi.json
> pnpm --filter @ichnos/contracts exec openapi-typescript openapi.json -o /tmp/ichnos-schema.ts
> diff -u packages/contracts/src/schema.ts /tmp/ichnos-schema.ts
> @echo "Contracts are up to date."

.PHONY: ts-typecheck
ts-typecheck: ## Type-check all TypeScript packages
> pnpm -r --if-present run typecheck

check: contracts-check ts-typecheck

# ---- Web (apps/web) ----
.PHONY: web-dev
web-dev: ## Run the web app on http://localhost:5173 (proxies /api to the API)
> pnpm --filter @ichnos/web dev

.PHONY: web-test
web-test: ## Run web tests (vitest)
> pnpm --filter @ichnos/web test

.PHONY: web-build
web-build: ## Build the web app into apps/web/dist
> pnpm --filter @ichnos/web build

.PHONY: dev
dev: ## Run API and web together; Ctrl+C stops both
> trap 'kill 0' EXIT; $(MAKE) api-dev & $(MAKE) web-dev & wait

check: web-test

# ---- Docker Compose ----
.PHONY: up
up: ## Build and start Ichnos with Docker Compose; returns when healthy
> docker compose up --build --detach --wait

.PHONY: down
down: ## Stop Ichnos (the data volume is kept)
> docker compose down

.PHONY: logs
logs: ## Follow the Docker Compose logs
> docker compose logs --follow

.PHONY: ps
ps: ## Show the status of the Ichnos services
> docker compose ps

# ---- Demo repository ----
.PHONY: demo-check
demo-check: ## Validate the demo repository's docs/ as an OKF v0.2 bundle (strict)
> uv run --no-project --with-requirements scripts/requirements-docs.txt python scripts/validate_okf.py examples/demo-repository/docs --strict

check: demo-check
