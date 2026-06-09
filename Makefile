# Sigil Social Scraper - task runner.
#
# WHY THIS EXISTS: this project lives under ~/Documents, which iCloud Drive
# syncs. iCloud creates conflict copies inside a plain ".venv" (e.g.
# "python3.12 2") and corrupts uv's editable install, which breaks `import
# scraper` / the `sigil-scheduler` launcher. iCloud ignores any directory whose
# name ends in ".nosync", so we keep the virtualenv at ".venv.nosync" and force
# uv to use it via UV_PROJECT_ENVIRONMENT on EVERY command below. That makes
# these targets work in any terminal, even one that hasn't loaded ~/.zshenv.
#
# Usage: `make install`, `make scheduler`, `make api`, `make test`, etc.

export UV_PROJECT_ENVIRONMENT := .venv.nosync

# Editors (e.g. Cursor/VSCode) may export VIRTUAL_ENV=.venv pointing at a
# no-longer-existing venv, which makes uv print a "does not match" warning.
# Drop it so uv silently uses .venv.nosync.
unexport VIRTUAL_ENV

UV := uv

.DEFAULT_GOAL := help

.PHONY: help install scheduler api test typecheck lint clean reset

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

install: ## Create .venv.nosync and install all deps (incl. dev)
	$(UV) sync --extra dev

scheduler: ## Run the standalone scraper scheduler (the "cron" process)
	$(UV) run sigil-scheduler

api: ## Run the optional read-only status API on :8000
	$(UV) run uvicorn scraper.api.main:app --host 0.0.0.0 --port 8000

test: ## Run the test suite
	$(UV) run pytest -q

typecheck: ## Run mypy
	$(UV) run mypy scraper

lint: typecheck ## Alias for typecheck

clean: ## Remove caches and any stray iCloud-corrupted .venv artifacts
	rm -rf .venv ".venv 2" .pytest_cache .mypy_cache
	find . -name '__pycache__' -type d -prune -exec rm -rf '{}' +

reset: clean ## Full reset: delete the venv and reinstall from scratch
	rm -rf .venv.nosync ".venv.nosync 2"
	$(MAKE) install
