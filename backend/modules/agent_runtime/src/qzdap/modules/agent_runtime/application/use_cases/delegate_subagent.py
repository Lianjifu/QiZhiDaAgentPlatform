"""Use case: delegate a task to a sub-agent (sync dispatch).

LLM 调 `delegate_to_agent(target_agent_id, task, context)` 时, 后端:
  1. 校验目标 agent 存在 + 同 tenant (防越权)
  2. 校验嵌套深度 (max_delegation_depth=3, 防止无限递归)
  3. 创建 sub_session, 标记 parent_session_id + delegation_depth
  4. 在 sub_session 上跑一个完整 turn (用 RunTurnCompletionUseCase 同步等)
  5. 收集 final_response 喂回父 agent

Returned to the LLM as a tool result:
  {ok, sub_session_id, agent_id, final_response, status, duration_ms,
   error_code?}

Nested delegation limit: enforced via session.metadata.delegation_depth.
Depth 0 = 顶层, depth 1 = 1 级 sub, depth >=3 = 拒绝.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from time import monotonic
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import text

from qzdap_kernel.errors import AppError

_log = logging.getLogger(__name__)

MAX_DELEGATION_DEPTH = 3
DEFAULT_TIMEOUT_SECONDS = 300


@dataclass(slots=True, frozen=True)
class DelegateSubagentResult:
    ok: bool
    sub_session_id: str | None
    agent_id: str
    final_response: str | None
    status: str
    duration_ms: int
    delegation_depth: int = 0
    error_code: str | None = None
    error: str | None = None


class DelegateSubagentUseCase:
    """Dispatch a single task to a sub-agent and synchronously collect the
    final response. Blocks until the sub-agent turn ends.
    """

    def __init__(
        self,
        *,
        agent_runtime_factory,        # _AgentRuntimeFactory from lifespan
        session_factory,             # container.session_factory()
        max_delegation_depth: int = MAX_DELEGATION_DEPTH,
    ) -> None:
        self._agent_runtime_factory = agent_runtime_factory
        self._session_factory = session_factory
        self._max_depth = max_delegation_depth

    async def execute(
        self,
        *,
        parent_session_id: UUID,
        target_agent_id: str,
        task: str,
        context: dict[str, Any],
        tenant_id: UUID,
        workspace_id: UUID,
        actor_id: UUID,
    ) -> DelegateSubagentResult:
        started = monotonic()

        # 阶段 1: 校验 + 创建 sub_session (短 session 拿完 metadata 就 commit)
        async with self._session_factory.session() as session:  # type: ignore[attr-defined]
            parent_row = (
                await session.execute(
                    text(
                        "SELECT tenant_id, workspace_id, metadata "
                        "FROM agent_sessions WHERE id = :sid"
                    ),
                    {"sid": str(parent_session_id)},
                )
            ).first()
            if parent_row is None:
                return _fail(
                    started, target_agent_id, "PARENT_SESSION_NOT_FOUND",
                    f"parent session {parent_session_id} not found",
                )
            if parent_row.tenant_id != tenant_id:
                return _fail(
                    started, target_agent_id, "CROSS_TENANT",
                    "parent session tenant mismatch",
                )
            if parent_row.workspace_id != workspace_id:
                return _fail(
                    started, target_agent_id, "CROSS_WORKSPACE",
                    "parent session workspace mismatch",
                )

            parent_meta = parent_row.metadata or {}
            parent_depth = int(parent_meta.get("delegation_depth") or 0)
            if parent_depth >= self._max_depth:
                return _fail(
                    started, target_agent_id, "DELEGATION_DEPTH_EXCEEDED",
                    (
                        f"delegation depth exceeded "
                        f"(parent depth={parent_depth}, max={self._max_depth})"
                    ),
                )

            target_row = (
                await session.execute(
                    text(
                        "SELECT id, tenant_id, status, version "
                        "FROM admin_agents WHERE id = :aid LIMIT 1"
                    ),
                    {"aid": target_agent_id},
                )
            ).first()
            if target_row is None:
                return _fail(
                    started, target_agent_id, "AGENT_NOT_FOUND",
                    f"agent {target_agent_id} not found",
                )
            if target_row.tenant_id != tenant_id:
                return _fail(
                    started, target_agent_id, "CROSS_TENANT",
                    "target agent tenant mismatch",
                )

            sub_session_id = uuid4()
            sub_meta = {
                "delegation_depth": parent_depth + 1,
                "parent_session_id": str(parent_session_id),
                "delegated_task_preview": task[:120],
                "delegated_from_agent_id": str(parent_meta.get("agent_id") or ""),
                "delegated_from_actor_id": str(actor_id),
            }
            await session.execute(
                text(
                    "INSERT INTO agent_sessions "
                    "(id, tenant_id, workspace_id, owner_id, agent_id, "
                    " agent_version, status, created_at, metadata) "
                    "VALUES (:id, :tid, :wid, :oid, :aid, :v, 'open', "
                    " now(), CAST(:meta AS jsonb))"
                ),
                {
                    "id": str(sub_session_id),
                    "tid": str(tenant_id),
                    "wid": str(workspace_id),
                    "oid": str(actor_id),
                    "aid": str(target_row.id),
                    "v": str(target_row.version or "v1"),
                    "meta": json.dumps(sub_meta, ensure_ascii=False, default=str),
                },
            )
            await session.commit()

        # 阶段 2: 跑 sub-agent turn (开一个 long-lived session 给 graph 用)
        user_input = self._format_task(task, context)
        depth = parent_depth + 1
        try:
            from qzdap.modules.agent_runtime.application.use_cases.run_turn import (
                RunTurnUseCase,
            )
            from qzdap.modules.agent_runtime.application.use_cases.run_turn_to_completion import (
                RunTurnCompletionUseCase,
            )

            async with self._session_factory.session() as session:  # type: ignore[attr-defined]
                sub_service = self._agent_runtime_factory.for_session(session)
                run_turn_uc = RunTurnUseCase(sub_service)
                completion_uc = RunTurnCompletionUseCase(run_turn_uc)
                completion = await completion_uc.execute(
                    tenant_id=tenant_id,
                    workspace_id=workspace_id,
                    owner_id=actor_id,
                    session_id=sub_session_id,
                    user_input=user_input,
                    model="",
                )
                await session.commit()
            return DelegateSubagentResult(
                ok=True,
                sub_session_id=str(sub_session_id),
                agent_id=target_agent_id,
                final_response=completion.final_message or "",
                status="succeeded",
                duration_ms=int((monotonic() - started) * 1000),
                delegation_depth=depth,
            )
        except AppError as exc:
            _log.warning(
                "delegate_to_agent sub-agent AppError agent=%s err=%s",
                target_agent_id, exc,
            )
            return DelegateSubagentResult(
                ok=False, sub_session_id=str(sub_session_id),
                agent_id=target_agent_id, final_response=None,
                status="failed",
                duration_ms=int((monotonic() - started) * 1000),
                delegation_depth=depth,
                error_code=exc.code,
                error=str(exc),
            )
        except Exception as exc:
            _log.exception(
                "delegate_to_agent sub-agent crashed agent=%s", target_agent_id,
            )
            return DelegateSubagentResult(
                ok=False, sub_session_id=str(sub_session_id),
                agent_id=target_agent_id, final_response=None,
                status="failed",
                duration_ms=int((monotonic() - started) * 1000),
                delegation_depth=depth,
                error_code="SUBAGENT_CRASHED",
                error=str(exc),
            )

    def _format_task(self, task: str, context: dict[str, Any]) -> str:
        if not context:
            return task
        ctx_lines = "\n".join(f"- {k}: {v}" for k, v in context.items())
        return f"{task}\n\n上下文:\n{ctx_lines}"


def _fail(
    started: float, agent_id: str, code: str, msg: str
) -> DelegateSubagentResult:
    return DelegateSubagentResult(
        ok=False, sub_session_id=None, agent_id=agent_id,
        final_response=None, status="failed",
        duration_ms=int((monotonic() - started) * 1000),
        error_code=code, error=msg,
    )


__all__ = [
    "DelegateSubagentResult",
    "DelegateSubagentUseCase",
    "MAX_DELEGATION_DEPTH",
]
