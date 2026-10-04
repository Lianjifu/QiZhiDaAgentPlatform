"""Internal HTTP API for sandbox_runtime."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request

from qzdap.runtimes.sandbox_runtime.service import JobRejected, JobService
from qzdap.runtimes.sandbox_runtime.settings import Settings


def _service(request: Request) -> JobService:
    service = getattr(request.app.state, "job_service", None)
    if service is None:
        raise HTTPException(status_code=500, detail="job service not wired")
    return service


def _settings(request: Request) -> Settings:
    settings = getattr(request.app.state, "settings", None)
    if settings is None:
        raise HTTPException(status_code=500, detail="settings not wired")
    return settings


def require_internal(
    request: Request,
    authorization: str | None = Header(default=None),
) -> None:
    secret = _settings(request).sandbox_runtime_secret
    expected = f"Bearer {secret}"
    if not secret or authorization != expected:
        raise HTTPException(status_code=401, detail="SANDBOX_UNAUTHORIZED")


def build_router() -> APIRouter:
    router = APIRouter()

    @router.get("/healthz")
    async def healthz(request: Request) -> dict[str, str]:
        settings = _settings(request)
        return {
            "status": "ok",
            "executor": settings.sandbox_executor,
            "runtime": "runsc" if settings.sandbox_executor == "gvisor" else "stub",
        }

    @router.post("/internal/jobs")
    async def create_job(
        body: dict[str, Any],
        service: JobService = Depends(_service),  # noqa: B008
        _: None = Depends(require_internal),
    ) -> dict[str, Any]:
        try:
            result = await service.submit(body)
        except JobRejected as exc:
            raise HTTPException(status_code=400, detail={"code": exc.code, "message": exc.message}) from exc
        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                detail={"code": "SANDBOX_BAD_PATH", "message": str(exc)},
            ) from exc
        return result.to_dict()

    @router.get("/internal/jobs/{job_id}")
    async def get_job(
        job_id: UUID,
        service: JobService = Depends(_service),  # noqa: B008
        _: None = Depends(require_internal),
    ) -> dict[str, Any]:
        result = await service.get(job_id)
        if result is None:
            raise HTTPException(status_code=404, detail="SANDBOX_JOB_NOT_FOUND")
        return result.to_dict()

    @router.post("/internal/jobs/{job_id}/cancel")
    async def cancel_job(
        job_id: UUID,
        service: JobService = Depends(_service),  # noqa: B008
        _: None = Depends(require_internal),
    ) -> dict[str, Any]:
        ok = await service.cancel(job_id)
        if not ok:
            raise HTTPException(status_code=404, detail="SANDBOX_JOB_NOT_FOUND")
        return {"ok": True, "id": str(job_id)}

    return router


__all__ = ["build_router"]
