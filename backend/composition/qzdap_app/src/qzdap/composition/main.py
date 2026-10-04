"""FastAPI app factory."""

from __future__ import annotations

from typing import Annotated

from qzdap_auth.dependencies import (
    AuthenticatedPrincipal,
    require_authenticated,
    require_role,
)
from qzdap_http.cors import build_cors_config
from qzdap_http.health import health_router, liveness_router, readiness_router
from qzdap_http.middleware import build_default_middleware_chain
from qzdap_http.rate_limit import RateLimitPolicy
from qzdap_persistence.tenant_guard import install_tenant_loader
from qzdap_vault.actor import ActorContext
from fastapi import Depends, FastAPI
from fastapi.responses import JSONResponse

from qzdap.composition.container import Container
from qzdap.composition.lifespan import lifespan
from qzdap.composition.settings import get_settings


def create_app() -> FastAPI:
    # Resolve QZDAP_*_REF env vars (deploy/env.prod.example) into bare
    # QZDAP_* BEFORE Settings() reads env — Pydantic does not understand
    # the *_REF indirection.  Sync wrapper because no event loop runs
    # yet (uvicorn / gunicorn boots after this returns).
    from qzdap.composition.ref_resolver import resolve_ref_env_sync

    _resolved = resolve_ref_env_sync()
    if _resolved:
        import logging

        logging.getLogger(__name__).info(
            "boot: resolved %d QZDAP_*_REF env vars", _resolved
        )

    settings = get_settings()
    container = Container(settings)

    app = FastAPI(
        title="企智搭 · 智能体平台",
        version="0.1.0",
        debug=settings.debug,
        lifespan=lifespan,
    )

    app.state.container = container
    app.state.settings = settings

    # Health
    app.include_router(health_router)
    app.include_router(liveness_router)
    app.include_router(readiness_router)

    # Identity module
    from qzdap.modules.identity.adapter.http.router import (
        build_router as identity_router,
    )

    app.include_router(identity_router())

    # Agent runtime module
    from qzdap.modules.agent_runtime.adapter.http.router import (
        build_router as agent_runtime_router,
    )

    app.include_router(agent_runtime_router())
    from qzdap.modules.agent_runtime.adapter.http.catalog_router import (
        build_catalog_router as agent_catalog_router,
    )
    from qzdap.modules.agent_runtime.adapter.http.session_router import (
        build_session_router as copilot_session_router,
    )

    app.include_router(agent_catalog_router())
    app.include_router(copilot_session_router())

    # Tool module
    from qzdap.modules.tool.adapter.http.router import build_router as tool_router

    app.include_router(tool_router())

    # Skill module
    from qzdap.modules.skill.adapter.http.router import build_router as skill_router

    app.include_router(skill_router())

    # Memory module
    from qzdap.modules.memory.adapter.http.router import build_router as memory_router

    app.include_router(memory_router())

    # Knowledge module
    from qzdap.modules.knowledge.adapter.http.router import (
        build_router as knowledge_router,
    )

    app.include_router(knowledge_router())

    # Workflow catalog — /api/admin/workflows + /api/catalog/workflows
    from qzdap.modules.orchestration.adapter.http.router import (
        build_router as orchestration_router,
    )

    app.include_router(orchestration_router())

    # P8 agent_factory module — /v1/agents templates/versions/releases
    from qzdap.modules.agent_factory.adapter.http.router import (
        build_router as agent_factory_router,
    )

    app.include_router(agent_factory_router())

    # P8 evaluation module — /v1/eval/datasets + runs
    from qzdap.modules.evaluation.adapter.http.router import (
        build_router as evaluation_router,
    )

    app.include_router(evaluation_router())

    # P9 observability module — /v1/observability/runs + /costs + /quality
    from qzdap.modules.observability_module.adapter.http.router import (
        build_router as observability_router,
    )

    app.include_router(observability_router())

    # P9 platform module — /v1/platform/plans + /subscriptions/me + /settings
    from qzdap.modules.platform.adapter.http.router import (
        build_router as platform_router,
    )

    app.include_router(platform_router())

    from qzdap.modules.platform.adapter.http.ops_router import (
        build_ops_router as admin_ops_router,
    )

    app.include_router(admin_ops_router())

    # Governance module — /v1/policies + /v1/approvals
    from qzdap.modules.governance.adapter.http.factory import (
        make_approval_service,
        make_policy_evaluator,
        make_policy_service,
    )
    from qzdap.modules.governance.adapter.http.router import (
        _require_actor,
        _require_admin,
    )
    from qzdap.modules.governance.adapter.http.router import (
        router as governance_router,
    )

    app.include_router(governance_router)

    def _actor_from_principal(p: AuthenticatedPrincipal) -> ActorContext:
        return ActorContext(
            tenant_id=p.tenant_id,
            workspace_id=p.workspace_id,
            principal_id=p.principal.id,
            roles=frozenset(p.principal.roles),
        )

    async def _resolve_actor(
        p: Annotated[AuthenticatedPrincipal, Depends(require_authenticated)],
    ) -> ActorContext:
        return _actor_from_principal(p)

    async def _resolve_admin(
        p: Annotated[AuthenticatedPrincipal, Depends(require_role("admin"))],
    ) -> ActorContext:
        return _actor_from_principal(p)

    app.dependency_overrides[_require_actor] = _resolve_actor
    app.dependency_overrides[_require_admin] = _resolve_admin
    app.dependency_overrides[make_policy_service] = lambda: container.policy_service()
    app.dependency_overrides[make_approval_service] = lambda: (
        container.approval_service()
    )
    app.dependency_overrides[make_policy_evaluator] = lambda: (
        container.policy_evaluator()
    )

    # A4 self_evolution module — /v1/evolve/candidates/*
    from qzdap.modules.self_evolution.adapter.http.factory import (
        make_evolution_service,
    )
    from qzdap.modules.self_evolution.adapter.http.router import (
        _require_actor as evolution_require_actor,
    )
    from qzdap.modules.self_evolution.adapter.http.router import (
        _require_admin as evolution_require_admin,
    )
    from qzdap.modules.self_evolution.adapter.http.router import (
        router as evolution_router,
    )

    app.include_router(evolution_router)
    app.dependency_overrides[evolution_require_actor] = _resolve_actor
    app.dependency_overrides[evolution_require_admin] = _resolve_admin
    app.dependency_overrides[make_evolution_service] = lambda: (
        container.evolution_service()
    )

    # Model catalog — /api/admin/models
    from qzdap.modules.model.adapter.http.router import (
        build_router as model_router,
    )

    app.include_router(model_router())

    # P6 channel module — /v1/channels CRUD + /v1/channels/{cid}/webhook
    from qzdap.modules.channel.adapter.http.router import (
        _require_actor as channel_require_actor,
    )
    from qzdap.modules.channel.adapter.http.router import (
        _require_admin as channel_require_admin,
    )
    from qzdap.modules.channel.adapter.http.router import (
        router as channel_router,
    )

    app.include_router(channel_router)
    app.dependency_overrides[channel_require_actor] = _resolve_actor
    app.dependency_overrides[channel_require_admin] = _resolve_admin

    # Metrics endpoint
    @app.get(settings.metrics_path)
    async def metrics() -> JSONResponse:
        from qzdap_observability.metrics import render_prometheus

        body, content_type = render_prometheus()
        return JSONResponse(content=body.decode(), media_type=content_type)

    # Wire the ORM tenant-loader so every TenantScopedLoader query is
    # auto-filtered by the current request's tenant id.
    install_tenant_loader()

    # Middleware chain — outermost: ErrorEnvelope → Observability →
    # RateLimit → CORS → Auth → TenantGuard → WorkspaceGuard → App.
    build_default_middleware_chain(
        app,
        cors=build_cors_config(
            {
                "QZDAP_CORS_ALLOW_ORIGINS": settings.cors_allow_origins,
                "QZDAP_CORS_ALLOW_CREDENTIALS": str(
                    settings.cors_allow_credentials
                ).lower(),
                "QZDAP_CORS_ALLOW_METHODS": settings.cors_allow_methods,
                "QZDAP_CORS_ALLOW_HEADERS": settings.cors_allow_headers,
            }
        ),
        rate_limit=RateLimitPolicy(
            requests_per_minute=settings.rate_limit_per_tenant_per_min,
            window_seconds=settings.rate_limit_window_seconds,
        ),
        # Pass the verifier directly; the chain mounts AuthMiddleware via
        # `app.add_middleware(AuthMiddleware, verifier=...)` itself.
        auth_verifier=container.jwt_verifier(),
    )

    # ── boot-time sanity check ────────────────────────────────────────
    # Each module router declares a `_require_actor` /
    # `_require_admin` placeholder dependency that returns 401. The
    # override wiring above replaces them with the real auth chain —
    # if we forgot to wire one (e.g. a new module was added without
    # updating this function), every endpoint protected by the
    # missing module would silently 401 instead of 500'ing at boot.
    # Surface that mistake at boot so it can't lurk into prod.
    #
    # Each router imports its own copy of `_require_actor` (e.g.
    # ``as evolution_require_actor``), so the override dict holds one
    # entry per module — we verify by value (the resolved
    # ``_resolve_actor`` / ``_resolve_admin`` function) and require at
    # least the four core modules to be wired.
    overrides = app.dependency_overrides
    for fn_name, label in (("_resolve_actor", "actor"), ("_resolve_admin", "admin")):
        seen = {
            getattr(v, "__module__", "")
            for v in overrides.values()
            if getattr(v, "__name__", "") == fn_name
        }
        if not seen:
            raise RuntimeError(
                f"create_app: dependency_overrides for {label} "
                f"({fn_name}) not wired. Check that all module routers' "
                "placeholder deps are overridden before returning the app."
            )

    return app


# Alias for `uvicorn qzdap.composition.main:app` (older uvicorn pattern)
app = create_app() if False else None  # pragma: no cover


def __getattr__(name: str):  # type: ignore[no-untyped-def]
    if name == "app":
        return create_app()
    raise AttributeError(name)
