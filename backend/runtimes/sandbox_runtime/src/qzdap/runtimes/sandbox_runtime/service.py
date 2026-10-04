"""Validate and run sandbox jobs."""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import UUID

from qzdap.runtimes.sandbox_runtime.executor import JobExecutor, safe_relpath
from qzdap.runtimes.sandbox_runtime.jobs import JobLimits, JobResult, SandboxJob
from qzdap.runtimes.sandbox_runtime.settings import Settings


class JobRejected(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class JobService:
    def __init__(self, *, settings: Settings, executor: JobExecutor) -> None:
        self._settings = settings
        self._executor = executor
        self._results: dict[UUID, JobResult] = {}
        self._running: dict[UUID, asyncio.Task[JobResult]] = {}

    def validate(self, payload: dict[str, Any]) -> SandboxJob:
        kind = payload.get("kind")
        if kind not in {"skill", "exec"}:
            raise JobRejected("SANDBOX_BAD_KIND", "kind must be skill or exec")
        image = str(payload.get("image") or self._settings.sandbox_default_image)
        if image not in self._settings.image_whitelist():
            raise JobRejected("SANDBOX_IMAGE_DENIED", f"image {image} is not allowed")
        command = payload.get("command")
        if not isinstance(command, list) or not command or not all(isinstance(x, str) for x in command):
            raise JobRejected("SANDBOX_BAD_COMMAND", "command must be a non-empty string list")
        timeout_ms = int(payload.get("timeout_ms") or 30_000)
        if timeout_ms < 1 or timeout_ms > self._settings.sandbox_max_timeout_ms:
            raise JobRejected("SANDBOX_BAD_TIMEOUT", "timeout_ms out of range")
        files_raw = payload.get("files") or {}
        if not isinstance(files_raw, dict):
            raise JobRejected("SANDBOX_BAD_FILES", "files must be an object")
        files: dict[str, str] = {}
        for name, content in files_raw.items():
            rel = safe_relpath(str(name))
            text = str(content)
            if len(text.encode("utf-8")) > self._settings.sandbox_max_file_bytes:
                raise JobRejected("SANDBOX_FILE_TOO_LARGE", f"{rel} exceeds max file size")
            files[rel] = text
        limits_raw = payload.get("limits") or {}
        network = str(limits_raw.get("network") or "none")
        if network not in {"none", "bridge"}:
            network = "none"
        if kind == "exec":
            network = "none"
        limits = JobLimits(
            memory_mb=int(limits_raw.get("memory_mb") or 256),
            cpu_millis=int(limits_raw.get("cpu_millis") or 500),
            pids=int(limits_raw.get("pids") or 64),
            network=network,  # type: ignore[arg-type]
        )
        env_raw = payload.get("env") or {}
        env = {str(k): str(v) for k, v in env_raw.items()} if isinstance(env_raw, dict) else {}
        job_id = payload.get("id")
        job = SandboxJob(
            kind=kind,
            image=image,
            command=list(command),
            tenant_id=str(payload.get("tenant_id") or ""),
            workspace_id=str(payload.get("workspace_id") or ""),
            call_id=str(payload.get("call_id") or ""),
            agent_id=str(payload.get("agent_id") or ""),
            stdin=str(payload.get("stdin") or ""),
            env=env,
            files=files,
            timeout_ms=timeout_ms,
            limits=limits,
        )
        if job_id:
            job.id = UUID(str(job_id))
        return job

    async def submit(self, payload: dict[str, Any]) -> JobResult:
        job = self.validate(payload)
        task = asyncio.create_task(self._executor.run(job))
        self._running[job.id] = task
        try:
            result = await task
        except asyncio.CancelledError:
            result = JobResult(
                id=job.id,
                status="cancelled",
                runtime=getattr(self._executor, "runtime_name", "runsc"),
                error_code="SANDBOX_CANCELLED",
            )
            raise
        finally:
            self._running.pop(job.id, None)
        self._results[job.id] = result
        return result

    async def get(self, job_id: UUID) -> JobResult | None:
        return self._results.get(job_id)

    async def cancel(self, job_id: UUID) -> bool:
        task = self._running.get(job_id)
        await self._executor.cancel(job_id)
        if task is None:
            return job_id in self._results
        task.cancel()
        return True


__all__ = ["JobRejected", "JobService"]
