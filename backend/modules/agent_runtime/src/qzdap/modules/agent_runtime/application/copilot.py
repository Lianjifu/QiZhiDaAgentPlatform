"""Copilot session facade — list/create/history + LangGraph turn stream."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID, uuid4

from qzdap_kernel.contextvars import current_trace_id
from qzdap_schema.dtos.turn import ApprovalRequiredChunk, DoneChunk, TurnChunk
from qzdap_schema.ids import AgentId, SessionId, TenantId, TurnId, UserId, WorkspaceId

from qzdap.modules.agent_runtime.adapter.graph.runner import SessionGraphRunner
from qzdap.modules.agent_runtime.adapter.persistence.catalog_repositories import (
    SqlSessionMessageRepository,
)
from qzdap.modules.agent_runtime.application.catalog import AgentCatalogService
from qzdap.modules.agent_runtime.application.ports import (
    EventPublisher,
    SessionRepository,
    TurnRepository,
)
from qzdap.modules.agent_runtime.domain import Session, SessionStatus, Turn
from qzdap.modules.agent_runtime.domain.catalog import CatalogAgent
from qzdap.modules.agent_runtime.domain.errors import SessionClosedError, SessionNotFound


class CopilotSessionService:
    def __init__(
        self,
        *,
        sessions: SessionRepository,
        turns: TurnRepository,
        messages: SqlSessionMessageRepository,
        catalog: AgentCatalogService,
        events: EventPublisher,
        graph: SessionGraphRunner,
    ) -> None:
        self._sessions = sessions
        self._turns = turns
        self._messages = messages
        self._catalog = catalog
        self._events = events
        self._graph = graph

    async def list_sessions(self, *, owner_id: UUID, search: str = "") -> list[dict[str, Any]]:
        rows = await self._sessions.list_for_owner(owner_id, limit=80)
        query = search.strip().lower()
        out: list[dict[str, Any]] = []
        for session in rows:
            if session.status is SessionStatus.CLOSED:
                continue
            title = str(session.metadata.get("title") or "新对话")
            preview = str(session.metadata.get("preview") or "")
            hay = f"{title} {preview}".lower()
            if query and query not in hay:
                continue
            out.append(_session_card(session))
        return out

    async def create_session(
        self,
        *,
        tenant_id: UUID,
        workspace_id: UUID,
        owner_id: UUID,
        agent_id: UUID,
        title: str = "",
    ) -> dict[str, Any]:
        agent = await self._catalog.get_published(agent_id)
        session = Session.create(
            id=SessionId(uuid4()),
            tenant_id=TenantId(tenant_id),
            workspace_id=WorkspaceId(workspace_id),
            owner_id=UserId(owner_id),
            agent_id=AgentId(agent.id),
            agent_version=agent.version or "v1",
            metadata={
                "title": title.strip() or f"与{agent.name}对话",
                "preview": "",
                "agentName": agent.name,
                "model": agent.model,
                "rolling_summary": "",
            },
        )
        await self._sessions.add(session)
        await self._events.publish(
            session.raise_opened_event(),
            tenant_id=tenant_id,
            workspace_id=workspace_id,
        )
        return _session_detail(session, messages=[], pending=None, agent=agent)

    async def get_session(self, *, tenant_id: UUID, session_id: UUID) -> dict[str, Any]:
        session = await self._require_session(tenant_id, session_id)
        messages = await self._messages.list_for_session(session_id)
        pending = (session.graph_state or {}).get("pending_approval")
        agent = await self._catalog.get_admin(session.agent_id)
        return _session_detail(session, messages=messages, pending=pending, agent=None, agent_dict=agent)

    async def close_session(self, *, tenant_id: UUID, session_id: UUID) -> None:
        session = await self._require_session(tenant_id, session_id)
        if session.status is SessionStatus.CLOSED:
            return
        closed = session.close()
        await self._sessions.update(closed)
        await self._events.publish(
            closed.raise_closed_event(),
            tenant_id=tenant_id,
            workspace_id=session.workspace_id,
        )

    async def stream_turn(
        self,
        *,
        tenant_id: UUID,
        workspace_id: UUID,
        owner_id: UUID,
        session_id: UUID,
        user_input: str,
        model: str | None = None,
        resume: dict[str, Any] | None = None,
    ) -> AsyncIterator[TurnChunk]:
        session = await self._require_session(tenant_id, session_id)
        if session.status is SessionStatus.CLOSED:
            raise SessionClosedError(f"session {session_id} is closed", code="SESSION_CLOSED")
        agent_row = await self._catalog.get_published(session.agent_id)
        history = await self._messages.list_for_session(session_id)
        hist_msgs = [
            {"role": item["role"], "content": item["content"], "name": item.get("toolName") or None}
            for item in history
            if item.get("role") in {"user", "assistant", "tool", "system"}
        ]
        turn = Turn.create(
            id=TurnId(uuid4()),
            tenant_id=TenantId(tenant_id),
            workspace_id=WorkspaceId(workspace_id),
            session_id=session.id,
            user_input=user_input if not resume else (user_input or "继续"),
        )
        await self._turns.add(turn)
        await self._events.publish(
            turn.raise_started_event(),
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            trace_id=current_trace_id(),
        )
        seq = await self._next_seq(session_id)
        if not resume:
            await self._messages.append(
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                session_id=session_id,
                turn_id=turn.id,
                seq=seq,
                role="user",
                content=user_input,
            )
            seq += 1
        graph_resume = dict(session.graph_state or {})
        if resume:
            graph_resume = {**graph_resume, **resume}
        assistant_parts: list[str] = []
        async for chunk in self._graph.run_turn(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            owner_id=owner_id,
            turn_id=turn.id,
            user_input=user_input,
            history=hist_msgs,
            agent=agent_row,
            model=model or str(session.metadata.get("model") or agent_row.model or "default"),
            rolling_summary=str(session.metadata.get("rolling_summary") or ""),
            resume=graph_resume if graph_resume.get("pending_approval") or resume else None,
        ):
            yield chunk
            if getattr(chunk, "kind", None) == "message":
                assistant_parts.append(getattr(chunk, "content", "") or "")
            if isinstance(chunk, ApprovalRequiredChunk):
                meta = dict(session.metadata)
                meta["preview"] = "等待确认操作"
                updated = session.with_runtime(
                    metadata=meta,
                    graph_state=dict(self._graph.last_loop_state),
                    wait_status="waiting_approval",
                )
                await self._sessions.update(updated)
            if isinstance(chunk, DoneChunk):
                final = chunk.final_message or "".join(assistant_parts)
                await self._messages.append(
                    tenant_id=tenant_id,
                    workspace_id=workspace_id,
                    session_id=session_id,
                    turn_id=turn.id,
                    seq=seq,
                    role="assistant",
                    content=final,
                )
                meta = dict(session.metadata)
                meta["preview"] = final[:80]
                summary = str((self._graph.last_loop_state or {}).get("rolling_summary") or meta.get("rolling_summary") or "")
                meta["rolling_summary"] = summary
                updated = session.with_runtime(
                    metadata=meta,
                    graph_state=dict(self._graph.last_loop_state or {}),
                    wait_status="idle",
                )
                await self._sessions.update(updated)
                finished = turn.succeed(final_response=final)
                await self._turns.add(finished)

    async def decide_approval(
        self,
        *,
        tenant_id: UUID,
        workspace_id: UUID,
        owner_id: UUID,
        session_id: UUID,
        approval_id: UUID,
        approved: bool,
        approval_service: Any | None,
    ) -> AsyncIterator[TurnChunk]:
        session = await self._require_session(tenant_id, session_id)
        pending = dict((session.graph_state or {}).get("pending_approval") or {})
        if str(pending.get("approval_id")) != str(approval_id):
            pending["approval_id"] = str(approval_id)
        if approval_service is not None:
            from qzdap_schema.ids import ApprovalId, TenantId as TId, UserId as UId

            try:
                if approved:
                    await approval_service.approve(
                        tenant_id=TId(tenant_id),
                        approval_id=ApprovalId(approval_id),
                        approver_id=UId(UUID(int=1) if owner_id == UUID(int=0) else UUID(int=0)),
                    )
                else:
                    await approval_service.deny(
                        tenant_id=TId(tenant_id),
                        approval_id=ApprovalId(approval_id),
                        approver_id=UId(UUID(int=1) if owner_id == UUID(int=0) else UUID(int=0)),
                        reason="user denied",
                    )
            except Exception:  # noqa: BLE001
                pass
        pending["decision"] = "approved" if approved else "denied"
        async for chunk in self.stream_turn(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            owner_id=owner_id,
            session_id=session_id,
            user_input="继续",
            resume={"pending_approval": pending, "decision": pending["decision"], "messages": (session.graph_state or {}).get("messages")},
        ):
            yield chunk

    async def _require_session(self, tenant_id: UUID, session_id: UUID) -> Session:
        session = await self._sessions.get(session_id)
        if session is None or session.tenant_id != tenant_id:
            raise SessionNotFound(f"session {session_id} not found")
        return session

    async def _next_seq(self, session_id: UUID) -> int:
        rows = await self._messages.list_for_session(session_id)
        return (rows[-1]["seq"] + 1) if rows else 0


def _session_card(session: Session) -> dict[str, Any]:
    return {
        "id": str(session.id),
        "title": str(session.metadata.get("title") or "新对话"),
        "preview": str(session.metadata.get("preview") or ""),
        "updatedAt": session.created_at.isoformat(),
        "agentId": str(session.agent_id),
        "waitStatus": session.wait_status,
    }


def _session_detail(
    session: Session,
    *,
    messages: list[dict[str, Any]],
    pending: dict[str, Any] | None,
    agent: CatalogAgent | None,
    agent_dict: dict[str, Any] | None = None,
) -> dict[str, Any]:
    card = _session_card(session)
    card["messages"] = messages
    card["pendingApproval"] = pending
    card["agent"] = agent.to_catalog_dict() if agent is not None else agent_dict
    card["status"] = session.status.value
    return card


__all__ = ["CopilotSessionService"]
