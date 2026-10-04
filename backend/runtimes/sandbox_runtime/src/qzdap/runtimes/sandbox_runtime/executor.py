"""Executors: gVisor (runsc) via Docker Engine API, plus an in-memory stub."""

from __future__ import annotations

import asyncio
import json
import tempfile
import time
from pathlib import Path
from typing import Protocol
from uuid import UUID

import httpx

from qzdap.runtimes.sandbox_runtime.jobs import JobResult, SandboxJob
from qzdap.runtimes.sandbox_runtime.settings import Settings

MAX_OUTPUT_DEFAULT = 64 * 1024


class JobExecutor(Protocol):
    runtime_name: str

    async def run(self, job: SandboxJob) -> JobResult: ...

    async def cancel(self, job_id: UUID) -> None: ...


def clip_output(text: str, *, limit: int = MAX_OUTPUT_DEFAULT) -> str:
    raw = text.encode("utf-8", "replace")
    if len(raw) <= limit:
        return text
    return raw[:limit].decode("utf-8", "ignore") + "\n...[truncated]"


def safe_relpath(name: str) -> str:
    cleaned = name.replace("\\", "/").lstrip("/")
    if not cleaned or ".." in Path(cleaned).parts:
        raise ValueError(f"illegal file path: {name}")
    return cleaned


class StubExecutor:
    """In-memory executor for unit tests. Never used as a production fallback."""

    runtime_name = "stub"

    def __init__(self) -> None:
        self.jobs: list[SandboxJob] = []
        self._cancelled: set[UUID] = set()
        self.force_status: str | None = None

    async def run(self, job: SandboxJob) -> JobResult:
        self.jobs.append(job)
        started = time.monotonic()
        if job.id in self._cancelled:
            return JobResult(
                id=job.id,
                status="cancelled",
                duration_ms=0,
                runtime=self.runtime_name,
                error_code="SANDBOX_CANCELLED",
            )
        if self.force_status == "timeout":
            return JobResult(
                id=job.id,
                status="timeout",
                duration_ms=job.timeout_ms,
                runtime=self.runtime_name,
                error_code="SANDBOX_TIMEOUT",
            )
        stdout = job.files.get("stdout.txt")
        if stdout is None:
            stdout = json.dumps(
                {"kind": job.kind, "files": sorted(job.files), "stdin": job.stdin},
                ensure_ascii=False,
            )
        ok = "SANDBOX_FAIL" not in job.stdin and self.force_status != "failed"
        duration_ms = int((time.monotonic() - started) * 1000)
        if not ok:
            return JobResult(
                id=job.id,
                status="failed",
                exit_code=1,
                stdout="",
                stderr="stub failure",
                duration_ms=duration_ms,
                runtime=self.runtime_name,
                error_code="SANDBOX_FAILED",
            )
        return JobResult(
            id=job.id,
            status="succeeded",
            exit_code=0,
            stdout=clip_output(stdout),
            stderr="",
            duration_ms=duration_ms,
            runtime=self.runtime_name,
        )

    async def cancel(self, job_id: UUID) -> None:
        self._cancelled.add(job_id)


class GvisorExecutor:
    """Run a one-shot container with Docker HostConfig.Runtime=runsc."""

    runtime_name = "runsc"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._containers: dict[UUID, str] = {}
        self._docker = httpx.AsyncClient(
            transport=httpx.AsyncHTTPTransport(uds=settings.sandbox_docker_socket),
            base_url="http://localhost",
            timeout=httpx.Timeout(60.0),
        )

    def _api(self, path: str) -> str:
        return f"/{self._settings.sandbox_docker_api}{path}"

    async def close(self) -> None:
        await self._docker.aclose()

    async def ensure_runsc(self) -> None:
        try:
            response = await self._docker.get(self._api("/info"))
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise RuntimeError("SANDBOX_DOCKER_UNAVAILABLE") from exc
        runtimes = (response.json() or {}).get("Runtimes") or {}
        if "runsc" not in runtimes:
            raise RuntimeError("SANDBOX_RUNSC_UNAVAILABLE")

    async def run(self, job: SandboxJob) -> JobResult:
        await self.ensure_runsc()
        started = time.monotonic()
        work = Path(tempfile.mkdtemp(prefix=f"qzdap-sandbox-{job.id.hex[:12]}-"))
        try:
            for name, content in job.files.items():
                rel = safe_relpath(name)
                dest = work / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_text(content, encoding="utf-8")
            if job.stdin:
                (work / "stdin.txt").write_text(job.stdin, encoding="utf-8")
            container_id = await self._create(job, work)
            self._containers[job.id] = container_id
            await self._docker.post(self._api(f"/containers/{container_id}/start"))
            wait = self._docker.post(self._api(f"/containers/{container_id}/wait"))
            try:
                waited = await asyncio.wait_for(wait, timeout=job.timeout_ms / 1000)
            except TimeoutError:
                await self.cancel(job.id)
                return JobResult(
                    id=job.id,
                    status="timeout",
                    duration_ms=int((time.monotonic() - started) * 1000),
                    runtime=self.runtime_name,
                    error_code="SANDBOX_TIMEOUT",
                    error_message="job exceeded timeout_ms",
                )
            payload = waited.json() if waited.status_code < 400 else {}
            exit_code = int(payload.get("StatusCode", 1))
            stdout = await self._logs(container_id, stderr=False)
            stderr = await self._logs(container_id, stderr=True)
            duration_ms = int((time.monotonic() - started) * 1000)
            ok = exit_code == 0
            return JobResult(
                id=job.id,
                status="succeeded" if ok else "failed",
                exit_code=exit_code,
                stdout=clip_output(stdout, limit=self._settings.sandbox_max_output_bytes),
                stderr=clip_output(stderr, limit=self._settings.sandbox_max_output_bytes),
                duration_ms=duration_ms,
                runtime=self.runtime_name,
                error_code=None if ok else "SANDBOX_FAILED",
            )
        except RuntimeError as exc:
            return JobResult(
                id=job.id,
                status="failed",
                duration_ms=int((time.monotonic() - started) * 1000),
                runtime=self.runtime_name,
                error_code=str(exc),
                error_message=str(exc),
            )
        finally:
            container_id = self._containers.pop(job.id, None)
            if container_id:
                await self._docker.delete(
                    self._api(f"/containers/{container_id}"),
                    params={"force": "true"},
                )
            _rmtree(work)

    async def cancel(self, job_id: UUID) -> None:
        container_id = self._containers.get(job_id)
        if not container_id:
            return
        try:
            await self._docker.post(self._api(f"/containers/{container_id}/kill"))
        except httpx.HTTPError:
            return

    async def _create(self, job: SandboxJob, work: Path) -> str:
        memory_bytes = max(32, job.limits.memory_mb) * 1024 * 1024
        nano_cpus = max(100, job.limits.cpu_millis) * 1_000_000
        network = "none" if job.limits.network != "bridge" else "bridge"
        body = {
            "Image": job.image,
            "Cmd": job.command,
            "Env": [f"{key}={value}" for key, value in job.env.items()],
            "WorkingDir": "/work",
            "Tty": True,
            "NetworkDisabled": network == "none",
            "HostConfig": {
                "Runtime": "runsc",
                "NetworkMode": network,
                "Memory": memory_bytes,
                "NanoCpus": nano_cpus,
                "PidsLimit": job.limits.pids,
                "ReadonlyRootfs": True,
                "CapDrop": ["ALL"],
                "SecurityOpt": ["no-new-privileges"],
                "Tmpfs": {"/tmp": "rw,nosuid,nodev,size=64m"},
                "Binds": [f"{work}:/work:rw"],
                "Privileged": False,
            },
        }
        response = await self._docker.post(self._api("/containers/create"), json=body)
        if response.status_code >= 400:
            raise RuntimeError(f"SANDBOX_CREATE_FAILED:{response.text[:200]}")
        container_id = response.json().get("Id")
        if not container_id:
            raise RuntimeError("SANDBOX_CREATE_FAILED")
        return str(container_id)

    async def _logs(self, container_id: str, *, stderr: bool) -> str:
        response = await self._docker.get(
            self._api(f"/containers/{container_id}/logs"),
            params={"stdout": "0" if stderr else "1", "stderr": "1" if stderr else "0"},
        )
        if response.status_code >= 400:
            return ""
        return response.text


def _rmtree(path: Path) -> None:
    import shutil

    shutil.rmtree(path, ignore_errors=True)


__all__ = [
    "GvisorExecutor",
    "JobExecutor",
    "StubExecutor",
    "clip_output",
    "safe_relpath",
]
