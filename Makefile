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
