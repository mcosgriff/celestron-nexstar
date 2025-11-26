#!/usr/bin/env just --justfile
export PATH := join(justfile_directory(), ".env", "bin") + ":" + env_var('PATH')

# Dependency management
upgrade:
  uv lock --upgrade

sync:
  uv sync --all-extras

# Application commands
nexstar-gui:
  uv run nexstar-gui

nexstar *args:
  uv run nexstar {{args}}

# Testing
test:
  uv run pytest

test-verbose:
  uv run pytest -v

test-cov:
  uv run pytest --cov

test-cov-html:
  uv run pytest --cov --cov-report=html
  @echo "Coverage report generated at htmlcov/index.html"

test-file file:
  uv run pytest tests/{{file}}

# Code quality
format:
  uv run ruff format src

lint:
  uv run ruff check src

lint-fix:
  uv run ruff check --fix --unsafe-fixes src

typecheck:
  uv run mypy --config-file=pyproject.toml --show-error-codes src/

typecheck-strict:
  bash scripts/run_mypy_strict.sh

# Pre-commit
pre-commit-install:
  uv run pre-commit install

pre-commit-run:
  uv run pre-commit run

pre-commit-all:
  uv run pre-commit run --all-files

# All checks (format, lint, typecheck)
check:
  just format
  just lint
  just typecheck
  @echo "✓ All checks passed"

# Build
build:
  uv build

clean:
  rm -rf dist/ build/ *.egg-info .pytest_cache .mypy_cache .ruff_cache htmlcov/ .coverage coverage.xml

# Development utilities
coverage:
  uv run pytest --cov --cov-report=term-missing --cov-report=html
  @echo "Coverage report: htmlcov/index.html"

coverage-open:
  uv run pytest --cov --cov-report=html
  open htmlcov/index.html

# Database
db-upgrade:
  uv run nexstar data upgrade

db-downgrade:
  uv run nexstar data downgrade

# Quick development workflow
dev:
  just format
  just lint-fix
  just typecheck
  just test
  @echo "✓ Development checks complete"
