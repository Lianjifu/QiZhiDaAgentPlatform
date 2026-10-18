"""Audit-log writer for built-in tools (bash / read_file / write_file /
edit_file / ls / glob / grep / web_search / http_fetch).

Writes one row to ``audit_log`` per tool invocation. Safe to fail: DB
errors are logged but never propagated, so a transient audit-log outage
cannot break the user's tool call.

Payload schema (event_type → payload shape):

  tool.bash_executed
    {command, cwd, exit_code, duration_ms,
     stdout_bytes, stderr_bytes, truncated}

  tool.fs_read       {tool, path, bytes_read, truncated}
  tool.fs_write      {tool, path, bytes_written, create_parents}
  tool.fs_edit       {tool, path, replacements}
  tool.fs_list       {tool, path, count, truncated}
  tool.fs_search     {tool, pattern, cwd, count, truncated}
  tool.network_egress {tool, url, status, duration_ms}

NOTE: file *content* is NEVER logged. For write/edit we log path + bytes;
for bash we log the full command (admins need it for IR) but only byte
counts for stdout/stderr. Payload always carries `_call_id` for joining
with the corresponding `tool_calls` row.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from qzdap.modules.governance.adapter.persistence.models import AuditLogORM

_log = logging.getLogger(__name__)


class ToolAuditRecorder:
    """Writes one ``audit_log`` row per tool invocation.

    Constructor takes a session factory whose ``session()`` returns an
    async context manager (the standard ``qzdap`` container shape).
    """

    def __init__(self, *, session_factory: Any) -> None:
        self._session_factory = session_factory

    async def record(
        self,
        *,
        tenant_id: UUID,
        actor_id: UUID,
        call_id: UUID,
        workspace_id: UUID | None,
        event_type: str,
        payload: dict[str, Any],
    ) -> None:
        """Insert one audit_log row. Never raises."""
        if not isinstance(payload, dict):
            payload = {"value": str(payload)}
        payload_with_ctx = {**payload, "_call_id": str(call_id)}
        try:
            # container.session_factory() returns a SessionFactory object;
            # the actual context manager is exposed via .session().
            factory = self._session_factory
            cm = factory() if callable(factory) else factory.session()
            async with cm as session:  # type: ignore[union-attr]
                session.add(AuditLogORM(
                    id=uuid4(),
                    tenant_id=tenant_id,
                    actor_id=actor_id,
                    event_type=event_type,
                    payload=payload_with_ctx,
                    created_at=datetime.now(UTC),
                ))
                await session.commit()
        except Exception:
            _log.exception(
                "tool_audit.record failed event=%s tenant=%s call=%s",
                event_type, tenant_id, call_id,
            )

    # ── Convenience helpers ────────────────────────────────────────

    async def bash(
        self,
        *,
        tenant_id: UUID,
        actor_id: UUID,
        call_id: UUID,
        workspace_id: UUID | None,
        command: str,
        cwd: str,
        exit_code: int,
        duration_ms: int,
        stdout_bytes: int,
        stderr_bytes: int,
        truncated: bool,
    ) -> None:
        await self.record(
            tenant_id=tenant_id, actor_id=actor_id, call_id=call_id,
            workspace_id=workspace_id,
            event_type="tool.bash_executed",
            payload={
                "command": command[:2000],
                "cwd": cwd,
                "exit_code": exit_code,
                "duration_ms": duration_ms,
                "stdout_bytes": stdout_bytes,
                "stderr_bytes": stderr_bytes,
                "truncated": truncated,
            },
        )

    async def fs_read(
        self,
        *,
        tenant_id: UUID,
        actor_id: UUID,
        call_id: UUID,
        workspace_id: UUID | None,
        tool: str,
        path: str,
        bytes_read: int,
        truncated: bool,
    ) -> None:
        await self.record(
            tenant_id=tenant_id, actor_id=actor_id, call_id=call_id,
            workspace_id=workspace_id,
            event_type="tool.fs_read",
            payload={"tool": tool, "path": path, "bytes_read": bytes_read, "truncated": truncated},
        )

    async def fs_write(
        self,
        *,
        tenant_id: UUID,
        actor_id: UUID,
        call_id: UUID,
        workspace_id: UUID | None,
        tool: str,
        path: str,
        bytes_written: int,
        create_parents: bool,
    ) -> None:
        await self.record(
            tenant_id=tenant_id, actor_id=actor_id, call_id=call_id,
            workspace_id=workspace_id,
            event_type="tool.fs_write",
            payload={
                "tool": tool, "path": path, "bytes_written": bytes_written,
                "create_parents": create_parents,
            },
        )

    async def fs_edit(
        self,
        *,
        tenant_id: UUID,
        actor_id: UUID,
        call_id: UUID,
        workspace_id: UUID | None,
        tool: str,
        path: str,
        replacements: int,
    ) -> None:
        await self.record(
            tenant_id=tenant_id, actor_id=actor_id, call_id=call_id,
            workspace_id=workspace_id,
            event_type="tool.fs_edit",
            payload={"tool": tool, "path": path, "replacements": replacements},
        )

    async def fs_list(
        self,
        *,
        tenant_id: UUID,
        actor_id: UUID,
        call_id: UUID,
        workspace_id: UUID | None,
        tool: str,
        path: str,
        count: int,
        truncated: bool,
    ) -> None:
        await self.record(
            tenant_id=tenant_id, actor_id=actor_id, call_id=call_id,
            workspace_id=workspace_id,
            event_type="tool.fs_list",
            payload={"tool": tool, "path": path, "count": count, "truncated": truncated},
        )

    async def fs_search(
        self,
        *,
        tenant_id: UUID,
        actor_id: UUID,
        call_id: UUID,
        workspace_id: UUID | None,
        tool: str,
        pattern: str,
        cwd: str,
        count: int,
        truncated: bool,
    ) -> None:
        await self.record(
            tenant_id=tenant_id, actor_id=actor_id, call_id=call_id,
            workspace_id=workspace_id,
            event_type="tool.fs_search",
            payload={
                "tool": tool, "pattern": pattern[:500], "cwd": cwd,
                "count": count, "truncated": truncated,
            },
        )

    async def network_egress(
        self,
        *,
        tenant_id: UUID,
        actor_id: UUID,
        call_id: UUID,
        workspace_id: UUID | None,
        tool: str,
        url: str,
        status: int,
        duration_ms: int,
    ) -> None:
        await self.record(
            tenant_id=tenant_id, actor_id=actor_id, call_id=call_id,
            workspace_id=workspace_id,
            event_type="tool.network_egress",
            payload={
                "tool": tool, "url": url[:2000], "status": status,
                "duration_ms": duration_ms,
            },
        )


__all__ = ["ToolAuditRecorder"]