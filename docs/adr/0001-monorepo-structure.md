# ADR 0001 — Monorepo structure (libs + modules + composition)

## Status

Accepted (2026-09-19).

## Context

We are building a 14-module enterprise agent platform. Each module is a
hexagonal bounded context with its own domain, application, and adapter
layers. Shared infrastructure (kernel, persistence, auth, observability,
LLM, sandbox, vector, messaging, schema, http) lives in `libs/*` and is
imported by multiple modules.

The question is: should `libs/*` and `modules/*` live in separate repos,
a mono-repo, or a hybrid?

## Decision

A single uv workspace at the repo root, with three package roots:

```
libs/        ← 10 kernel packages (`qzdap-kernel`, `qzdap-persistence`, …)
modules/     ← 14 capability modules (`qzdap-identity`, `qzdap-agent-runtime`, …)
composition/ ← composition root (`qzdap-app`)
```

Each package is a separately-installable Python project with its own
`pyproject.toml`. They share lock state via the root `uv.lock`.

## Consequences

### Positive

- Atomic PRs across a module + its dependent `libs.*` change. No
  `git submodule` ceremony.
- One CI pipeline. One test run. One import-linter pass.
- One migration stream. One `docker-compose.yml`.
- Single deploy artifact: the `qzdap-app` container.

### Negative

- Build the world on every CI run. Mitigated by per-package
  test selection (`pytest modules/identity/tests/...`).
- Library boundary drift risk if anyone bypasses `import-linter`. The
  pre-commit hook + CI lint-imports job catch this.
- Larger binary footprint. Acceptable for now (a single process at
  current scale).

## Alternatives considered

- **Polyrepo**: rejected. Cross-cutting changes (e.g. adding
  `tenant_id` to every aggregate) become a 14-PR effort.
- **Hybrid (libs in their own repo, modules in this one)**: rejected.
  Same drift problem with worse ergonomics — would need to publish
  every libs/* change to PyPI before modules could import it.

## Enforcement

- `.importlinter.ini` has the `no-business-in-libs` contract that
  forbids `libs.* → modules.*` imports in either direction.
- The composition root is the only place that wires concrete adapters.