"""Job models for sandbox_runtime."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal
from uuid import UUID, uuid4

JobKind = Literal["skill", "exec"]
JobStatus = Literal["running", "succeeded", "failed", "timeout", "cancelled"]
NetworkMode = Literal["none", "bridge"]


@dataclass(slots=True)
class JobLimits:
    memory_mb: int = 256
    cpu_millis: int = 500
    pids: int = 64
    network: NetworkMode = "none"


@dataclass(slots=True)
class SandboxJob:
    kind: JobKind
    image: str
    command: list[str]
    tenant_id: str
    workspace_id: str
    call_id: str
    id: UUID = field(default_factory=uuid4)
    agent_id: str = ""
    stdin: str = ""
    env: dict[str, str] = field(default_factory=dict)
    files: dict[str, str] = field(default_factory=dict)
    timeout_ms: int = 30_000
    limits: JobLimits = field(default_factory=JobLimits)


@dataclass(slots=True)
class JobResult:
    id: UUID
    status: JobStatus
    exit_code: int | None = None
    stdout: str = ""
    stderr: str = ""
    duration_ms: int = 0
    error_code: str | None = None
    error_message: str | None = None
    runtime: str = "runsc"

    def to_dict(self) -> dict[str, object]:
        return {
            "id": str(self.id),
            "status": self.status,
            "exit_code": self.exit_code,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "duration_ms": self.duration_ms,
            "error_code": self.error_code,
            "error_message": self.error_message,
            "runtime": self.runtime,
        }


__all__ = [
    "JobKind",
    "JobLimits",
    "JobResult",
    "JobStatus",
    "NetworkMode",
    "SandboxJob",
]
