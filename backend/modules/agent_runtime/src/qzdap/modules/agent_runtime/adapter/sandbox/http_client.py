"""HTTP client for sandbox_runtime internal jobs."""

from __future__ import annotations

from uuid import UUID

import httpx


class HttpSandboxRuntimeClient:
    def __init__(
        self,
        *,
        base_url: str,
        secret: str,
        timeout_seconds: float = 130.0,
        default_image: str = "qzdap/sandbox-python:latest",
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._secret = secret
        self._timeout = timeout_seconds
        self._default_image = default_image

    async def run_job(
        self,
        *,
        kind: str,
        tenant_id: UUID,
        workspace_id: UUID,
        call_id: UUID,
        image: str,
        command: list[str],
        files: dict[str, str],
        timeout_ms: int,
        network: str,
        memory_mb: int,
        stdin: str = "",
        env: dict[str, str] | None = None,
        agent_id: UUID | None = None,
    ) -> dict:
        if not self._base_url:
            return {
                "status": "failed",
                "error_code": "SANDBOX_UNAVAILABLE",
                "error_message": "sandbox_runtime_url is empty",
                "stdout": "",
                "stderr": "",
                "exit_code": None,
            }
        payload = {
            "kind": kind,
            "tenant_id": str(tenant_id),
            "workspace_id": str(workspace_id),
            "call_id": str(call_id),
            "agent_id": str(agent_id) if agent_id else "",
            "image": image or self._default_image,
            "command": command,
            "files": files,
            "stdin": stdin,
            "env": env or {},
            "timeout_ms": timeout_ms,
            "limits": {"memory_mb": memory_mb, "network": network},
        }
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(
                f"{self._base_url}/internal/jobs",
                json=payload,
                headers={"Authorization": f"Bearer {self._secret}"},
            )
        if response.status_code >= 400:
            detail = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
            code = "SANDBOX_HTTP_ERROR"
            if isinstance(detail, dict) and isinstance(detail.get("detail"), dict):
                code = str(detail["detail"].get("code") or code)
            return {
                "status": "failed",
                "error_code": code,
                "error_message": response.text[:500],
                "stdout": "",
                "stderr": "",
                "exit_code": None,
            }
        return response.json()


__all__ = ["HttpSandboxRuntimeClient"]
