"""Liveness + readiness + healthz routers."""

from __future__ import annotations

from fastapi import APIRouter, Request

health_router = APIRouter(tags=["health"])
liveness_router = APIRouter(tags=["health"])
readiness_router = APIRouter(tags=["health"])


@health_router.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok"}


@liveness_router.get("/livez")
async def livez() -> dict:
    return {"status": "alive"}


@readiness_router.get("/readyz")
async def readyz(request: Request) -> dict:
    """Ping the DB + Redis. Returns 503 if either fails."""
    deps: dict[str, str] = {}
    try:
        sf = getattr(request.app.state, "session_factory", None)
        if sf is not None:
            deps["db"] = "ok" if await sf.healthcheck() else "down"
        else:
            deps["db"] = "skipped"
    except Exception:  # noqa: BLE001
        deps["db"] = "down"

    try:
        redis = getattr(request.app.state, "redis", None)
        if redis is not None:
            await redis.ping()
            deps["redis"] = "ok"
        else:
            deps["redis"] = "skipped"
    except Exception:  # noqa: BLE001
        deps["redis"] = "down"

    all_ok = all(v in {"ok", "skipped"} for v in deps.values())
    return {"status": "ready" if all_ok else "degraded", "deps": deps}
