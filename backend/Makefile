# 企智搭 · 智能体平台 — Makefile
# All commands assume cwd = backend/.

.PHONY: help install sync lock lint format import-lint type-check test test-unit test-contract smoke bench bench-turn-latency bench-obs-ingest db-upgrade db-downgrade db-stamp run-app run-app-debug clean verify

UV        ?= uv
PYTHON   ?= python3.12
APP      ?= qzdap.composition.main:create_app
HOST     ?= 0.0.0.0
PORT     ?= 8100

help:
	@echo "Targets:"
	@echo "  install         : uv sync (install all deps)"
	@echo "  sync            : uv sync (alias)"
	@echo "  lock            : uv lock"
	@echo "  lint            : ruff check + format check"
	@echo "  format          : ruff format (write)"
	@echo "  import-lint     : lint-imports (architecture contract)"
	@echo "  type-check      : mypy"
	@echo "  test            : pytest (unit + integration + contract)"
	@echo "  test-unit       : pytest (unit only)"
	@echo "  smoke           : tests/e2e/smoke.py"
	@echo "  bench           : turn-latency + observability-ingest benches"
	@echo "  bench-turn-latency : turn P95 bench (asyncio + httpx)"
	@echo "  bench-obs-ingest    : event-bus → recorder micro-bench"
	@echo "  db-upgrade      : alembic upgrade head"
	@echo "  db-downgrade    : alembic downgrade -1"
	@echo "  run-app         : uvicorn on :$(PORT)"
	@echo "  verify          : lint + import-lint + type-check + test"

install sync:
	$(UV) sync --all-extras --all-packages

lock:
	$(UV) lock

lint:
	$(UV) run ruff check .
	$(UV) run ruff format --check .

format:
	$(UV) run ruff format .

import-lint:
	$(UV) run lint-imports --config .importlinter.ini

type-check:
	$(UV) run mypy libs modules composition

test:
	$(UV) run pytest

test-unit:
	$(UV) run pytest -m "not integration and not contract and not smoke"

test-contract:
	$(UV) run pytest -m contract tests/contract

smoke:
	$(UV) run python tests/e2e/smoke.py

# ---------- P10 perf bench ----------

bench: bench-turn-latency bench-obs-ingest
	@echo "✓ all bench scripts passed"

bench-turn-latency:
	$(UV) run python -m tests.perf.bench_turn_latency --concurrency 10 --turns 5

bench-obs-ingest:
	$(UV) run python -m tests.perf.bench_observability_ingest --events 1000 --warmup 50

# ---------- Burn-in runner ----------
# Runs G5 (gitleaks) + G6 (promtool) + G7 (grafana JSON) locally.
# Set QZDAP_STABLE_URL + QZDAP_CANARY_URL to also run G2 / G3 / G8.
burn-in:
	$(UV) run python ../deploy/burn_in.py

db-upgrade:
	$(UV) run alembic -c migrations/alembic.ini upgrade head

db-downgrade:
	$(UV) run alembic -c migrations/alembic.ini downgrade -1

db-stamp:
	$(UV) run alembic -c migrations/alembic.ini stamp head

run-app:
	$(UV) run uvicorn $(APP) --host $(HOST) --port $(PORT) --factory

run-app-debug:
	$(UV) run uvicorn $(APP) --host $(HOST) --port $(PORT) --factory --reload --log-level debug

clean:
	rm -rf .pytest_cache .mypy_cache .ruff_cache .coverage htmlcov
	find . -type d -name __pycache__ -prune -exec rm -rf {} +

verify: lint import-lint type-check test
	@echo "✓ all green"