# Groundwork — common tasks. Run `make help` for the list.
# On Windows without make, see README "Prerequisites" for the PowerShell equivalents.

PY      ?= python3
VENV    ?= .venv
BIN     := $(VENV)/bin
UV      := $(shell command -v uv 2>/dev/null)
API_PORT ?= 8000
WEB_PORT ?= 5173

.PHONY: help install install-api install-pipeline install-web data data-offline train api web test test-api test-scoring test-web lint clean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

$(BIN)/python:
ifdef UV
	uv venv $(VENV) --python 3.11
else
	$(PY) -m venv $(VENV)
endif

define pip_install
	$(if $(UV),uv pip install --python $(BIN)/python -r $(1),$(BIN)/python -m pip install -r $(1))
endef

install: install-api install-pipeline install-web ## Install everything

install-api: $(BIN)/python ## Install API dependencies
	$(call pip_install,backend/api/requirements.txt)

install-pipeline: $(BIN)/python ## Install data pipeline / scoring dependencies
	@if [ -f backend/pipeline/requirements.txt ]; then $(call pip_install,backend/pipeline/requirements.txt); else echo "backend/pipeline/requirements.txt not present yet — skipping"; fi

install-web: ## Install frontend dependencies
	cd frontend && npm install

data: ## Build data/processed/grid.parquet from real sources (LAYERS=a,b to limit)
	$(BIN)/python -m backend.pipeline.run $(if $(LAYERS),--layers $(LAYERS),)

data-offline: ## Build the grid using deterministic synthetic fallbacks only
	$(BIN)/python -m backend.pipeline.run --offline

train: ## Train presence-only ML models for profiles that declare one
	$(BIN)/python -m backend.scoring.train

api: ## Run the API on http://localhost:8000 (docs at /docs)
	$(BIN)/python -m uvicorn backend.api.main:app --reload --port $(API_PORT)

web: ## Run the frontend on http://localhost:5173
	cd frontend && npm run dev -- --port $(WEB_PORT)

test: test-api test-scoring test-web ## Run all tests

test-api: ## API + contract tests, against the stub and (if installed) the real scoring module
	GROUNDWORK_SCORING=stub $(BIN)/python -m pytest backend/tests_api -q
	@if $(BIN)/python -c "import backend.scoring" 2>/dev/null; then GROUNDWORK_SCORING=real $(BIN)/python -m pytest backend/tests_api -q; else echo "backend.scoring not importable — real-backend API tests skipped"; fi

test-scoring: ## Scoring tests (Person 1)
	@if [ -d backend/tests_scoring ]; then $(BIN)/python -m pytest backend/tests_scoring -q; else echo "backend/tests_scoring not present yet — skipping"; fi

test-web: ## Frontend typecheck, lint and fixture contract test
	cd frontend && npm run typecheck && npm run lint && npm test

lint: ## Lint Python (ruff) and frontend
	$(BIN)/python -m ruff check --config backend/api/ruff.toml backend/api backend/tests_api
	cd frontend && npm run lint

clean: ## Remove build outputs (keeps data caches)
	rm -rf frontend/dist .pytest_cache .ruff_cache
