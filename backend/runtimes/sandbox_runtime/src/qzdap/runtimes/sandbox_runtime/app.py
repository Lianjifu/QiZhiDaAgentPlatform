"""FastAPI app factory for sandbox_runtime."""

from __future__ import annotations

from fastapi import FastAPI

from qzdap.runtimes.sandbox_runtime.executor import (
    GvisorExecutor,
    JobExecutor,
    StubExecutor,
)
from qzdap.runtimes.sandbox_runtime.routes import build_router
from qzdap.runtimes.sandbox_runtime.service import JobService
from qzdap.runtimes.sandbox_runtime.settings import Settings, get_settings


def build_executor(settings: Settings) -> JobExecutor:
    if settings.sandbox_executor == "stub":
        if settings.env == "production":
            raise RuntimeError("production refuses QZDAP_SANDBOX_EXECUTOR=stub")
        return StubExecutor()
    return GvisorExecutor(settings)


def create_app(
    *,
    settings: Settings | None = None,
    executor: JobExecutor | None = None,
) -> FastAPI:
    resolved = settings or get_settings()
    if resolved.sandbox_executor == "stub" and resolved.env == "production":
        raise RuntimeError("production refuses QZDAP_SANDBOX_EXECUTOR=stub")
    wired = executor or build_executor(resolved)
    app = FastAPI(title="qzdap-sandbox-runtime", version="0.1.0")
    app.state.settings = resolved
    app.state.executor = wired
    app.state.job_service = JobService(settings=resolved, executor=wired)
    app.include_router(build_router())
    return app


__all__ = ["build_executor", "create_app"]
