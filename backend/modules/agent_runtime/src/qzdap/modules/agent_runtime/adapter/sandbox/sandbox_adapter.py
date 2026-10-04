"""SandboxPort adapter over sandbox_runtime."""

from __future__ import annotations

from uuid import UUID

from qzdap.modules.agent_runtime.adapter.sandbox.http_client import (
    HttpSandboxRuntimeClient,
)
from qzdap.modules.agent_runtime.application.ports import SandboxPort

SANDBOX_EXEC_NAME = "sandbox_exec"
DEFAULT_IMAGE = "qzdap/sandbox-python:latest"


class SandboxRuntimeAdapter(SandboxPort):
    def __init__(
        self,
        client: HttpSandboxRuntimeClient,
        *,
        tenant_id: UUID,
        workspace_id: UUID,
        agent_id: UUID | None = None,
        default_image: str = DEFAULT_IMAGE,
    ) -> None:
        self._client = client
        self._tenant_id = tenant_id
        self._workspace_id = workspace_id
        self._agent_id = agent_id
        self._default_image = default_image

    async def exec(
        self,
        *,
        call_id: UUID,
        language: str,
        code: str,
        timeout_ms: int = 30_000,
    ) -> dict:
        if language not in {"python", "shell"}:
            return {
                "ok": False,
                "error_code": "SANDBOX_BAD_LANGUAGE",
                "error_message": "language must be python or shell",
                "call_id": str(call_id),
            }
        if language == "python":
            files = {"main.py": code}
            command = ["python", "/work/main.py"]
        else:
            files = {"run.sh": code}
            command = ["sh", "/work/run.sh"]
        result = await self._client.run_job(
            kind="exec",
            tenant_id=self._tenant_id,
            workspace_id=self._workspace_id,
            call_id=call_id,
            image=self._default_image,
            command=command,
            files=files,
            timeout_ms=timeout_ms,
            network="none",
            memory_mb=256,
            agent_id=self._agent_id,
        )
        ok = result.get("status") == "succeeded"
        return {
            "ok": ok,
            "call_id": str(call_id),
            "stdout": result.get("stdout") or "",
            "stderr": result.get("stderr") or "",
            "exit_code": result.get("exit_code"),
            "status": result.get("status"),
            "error_code": result.get("error_code"),
        }


__all__ = ["DEFAULT_IMAGE", "SANDBOX_EXEC_NAME", "SandboxRuntimeAdapter"]
