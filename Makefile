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
