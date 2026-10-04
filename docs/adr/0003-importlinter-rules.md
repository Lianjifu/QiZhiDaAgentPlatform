# ADR 0003 — import-linter architecture contracts

## Status

Accepted (2026-09-19).

## Context

`doc/backend/` 13 节 prescribed strict layering. Without a tool enforcing
it, every PR is a chance to import the wrong thing in the wrong
direction. The prompt's "工程纪律" mandate calls this out explicitly.

## Decision

Use `grimp` + `lint-imports` to codify five contracts in
`.importlinter.ini`:

1. **`no-business-in-libs`** — `libs.*` must NOT import `modules.*`.
   `libs.*` is the kernel; it must remain general-purpose.
2. **`domain-purity`** — every `modules/*/domain/` must NOT import any
   framework (FastAPI, SQLAlchemy, asyncpg, redis, httpx, pydantic),
   nor any other `qzdap_*` library. Domain code is pure.
3. **`layered-modules`** — the 14 modules have an explicit
   dependency order. Higher layers may depend on lower; never the
   reverse.
4. **`peer-modules-isolation`** — `tool`, `skill`, and `memory` are
   peers; they may NOT import each other directly. They communicate
   via the EventBus only.
5. **`agent-runtime-can-call-peers-via-ports`** — `agent_runtime` may
   import `modules/<peer>/application/ports/`, but NOT the concrete
   service. This forces usecase composition through ports, which is
   what lets us swap mocks for real implementations between Week 2 and
   Week 5 without changing agent_runtime.

The CI job `import-lint` runs `lint-imports` on every PR and blocks on
violations.

## Consequences

### Positive

- Architectural drift is caught at PR time, not in code review.
- New contributors discover the rules by reading one file.
- The contracts double as documentation: each `contract:` block in
  `.importlinter.ini` reads like a sentence.

### Negative

- A change to layering (e.g. adding a new module) requires updating
  both the contract and the rationale. This is intentional friction.
- `lint-imports` adds ~5 s to CI. Acceptable.

## Alternatives considered

- **dependency-cruiser (JS)**: rejected. We're Python-first.
- **Manual grep in CI**: rejected. False positives + missed cases.
- **Enforce only the most important contract** (no-business-in-libs):
  rejected. The peer-isolation rule is the one that has bitten us
  before in similar projects; cutting it would mean re-discovering the
  problem.