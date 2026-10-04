# ADR 0002 — Hexagonal (Ports & Adapters) layered modules

## Status

Accepted (2026-09-19).

## Context

`doc/backend/` prescribes 14 capability modules. Each one has a domain
model, application services, and external integrations (DB, HTTP,
LLM/MCP, etc.). Without a clear internal layout, modules either:

(a) Become anemic CRUD repos with no business logic, or
(b) Become a god-class with domain + SQL + HTTP all tangled.

Both styles rot within months.

## Decision

Every module follows the same four-layer split:

```
modules/<m>/src/qzdap/modules/<m>/
├── domain/                 ← pure business types + invariants
│   ├── <aggregate>.py      ← Tenant, Workspace, User, …
│   ├── events.py           ← DomainEvent subclasses (past tense)
│   └── errors.py           ← Module-specific AppError subclasses
├── application/
│   ├── services.py         ← Service that lazily creates use-cases
│   ├── use_cases/          ← one file per use case
│   └── ports/              ← abstract interfaces (Repos, Hashers, …)
└── adapter/
    ├── http/               ← FastAPI routers + DTOs + mappers
    ├── persistence/        ← SQLAlchemy ORM + repository impls
    └── events/             ← Publisher + subscriber registration
```

Strict rules enforced by `.importlinter.ini`:

1. `domain/` must NOT import any framework, ORM, transport, or any other
   module. Period. Only stdlib + `qzdap_kernel`.
2. `application/` may import `domain/` and `libs.*`, but never
   `adapter/`.
3. `adapter/` may import `application/ports/` and the framework
   (FastAPI / SQLAlchemy).
4. The composition root (`composition/qzdap_app/`) is the only place that
   wires concrete adapters into ports.

## Consequences

### Positive

- Pure domain code → fast unit tests, no mocks.
- Swapping an adapter (e.g. SQL → Postgres-Beta, REST → gRPC) requires
  changing one file, not refactoring 200.
- `import-linter` makes architectural drift visible at code-review time.

### Negative

- A bit more boilerplate per use case (port + impl + service wiring).
- Onboarding is steeper than a flat structure. Mitigated by the
  per-module README we generate in Week 2.

## Alternatives considered

- **Flat modules** (everything in one file per module): rejected.
  Mature modules routinely exceed 1000 lines; the layering pays for
  itself quickly.
- **Pure DDD tactical patterns everywhere** (entity base class,
  generic repository): rejected. We borrow what helps, not the whole
  textbook. Our `Base` is SQLAlchemy's; our Repository pattern is
  scoped to the few aggregates that need polymorphism.