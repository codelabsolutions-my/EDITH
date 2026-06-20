# EDITH — developer task runner
# Usage: make <target>   (run `make help` to list targets)

.DEFAULT_GOAL := help
SHELL := /bin/bash

# Resolve uv if present, else fall back to python -m
UV := $(shell command -v uv 2>/dev/null)

.PHONY: help setup dev down lint fmt test test-server test-connectors test-app \
        typecheck migrate hooks

help: ## List available targets
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

setup: ## Install dev tooling (server + app) and git hooks
	cd server && $(if $(UV),uv sync --all-extras,pip install -e ".[dev]")
	-cd app && flutter pub get
	$(MAKE) hooks

hooks: ## Install pre-commit hooks
	-pre-commit install

dev: ## Run server + postgres locally (docker-compose)
	docker compose up --build

down: ## Stop local stack
	docker compose down

migrate: ## Apply database migrations (yoyo)
	cd server && yoyo apply

lint: ## Lint everything (ruff + mypy + flutter analyze)
	cd server && ruff check . && mypy app
	-cd app && flutter analyze

fmt: ## Auto-format (ruff format + dart format)
	cd server && ruff format . && ruff check --fix .
	-cd app && dart format .

typecheck: ## Type-check the server
	cd server && mypy app

test: test-server test-app ## Run all tests

test-server: ## Run server tests
	cd server && pytest

cov: ## Run server tests with a coverage report
	cd server && pytest --cov=app --cov-report=term-missing

test-connectors: ## Run the connector conformance suite
	cd server && pytest tests/test_connectors.py -v

test-app: ## Run Flutter tests
	-cd app && flutter test
