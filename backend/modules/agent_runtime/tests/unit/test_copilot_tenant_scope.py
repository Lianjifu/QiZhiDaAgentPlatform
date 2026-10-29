"""会话列表的租户隔离（Gateway Stage 2 —— 补 ``/v1/sessions`` 的租户校验）。

租户过滤**必须显式写在查询里**：ORM 的自动过滤依赖请求上下文里绑定了租户，
没有绑定时它退化成 no-op —— 查询就会跨租户。
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from _ar_unit_in_memory import (
    InMemoryIdempotencyStore,
    InMemorySessionJournal,
    InMemorySessionRepository,
    make_dependencies,
)
from qzdap_agent_runtime.gateway.idempotency import IdempotencyGuard
from qzdap_schema.ids import AgentId, TenantId, UserId, WorkspaceId

from qzdap.modules.agent_runtime.application.copilot import CopilotSessionService
from qzdap.modules.agent_runtime.domain import Session, SessionStatus


def _session(tenant_id: UUID, owner_id: UUID, workspace_id: UUID) -> Session:
    return Session.create(
        id=uuid4(),
        tenant_id=TenantId(tenant_id),
        workspace_id=WorkspaceId(workspace_id),
        owner_id=UserId(owner_id),
        agent_id=AgentId(uuid4()),
        agent_version="v1",
        metadata={"title": "会话"},
    )


@pytest.mark.asyncio
async def test_listing_sessions_only_returns_the_requested_tenant() -> None:
    deps = make_dependencies()
    sessions: InMemorySessionRepository = deps["sessions"]
    owner_id = uuid4()
    workspace_id = uuid4()
    tenant_a, tenant_b = uuid4(), uuid4()

    await sessions.add(_session(tenant_a, owner_id, workspace_id))
    await sessions.add(_session(tenant_b, owner_id, workspace_id))

    svc = CopilotSessionService(
        sessions=sessions,
        turns=deps["turns"],
        messages=None,  # type: ignore[arg-type]
        catalog=None,  # type: ignore[arg-type]
        events=deps["events"],
        graph=None,  # type: ignore[arg-type]
        idempotency=IdempotencyGuard(InMemoryIdempotencyStore()),
        journal=InMemorySessionJournal(),
    )

    listed_a = await svc.list_sessions(tenant_id=tenant_a, owner_id=owner_id)
    listed_b = await svc.list_sessions(tenant_id=tenant_b, owner_id=owner_id)

    assert len(listed_a) == 1
    assert len(listed_b) == 1
    assert listed_a[0]["id"] != listed_b[0]["id"]


@pytest.mark.asyncio
async def test_listing_sessions_skips_closed_ones() -> None:
    deps = make_dependencies()
    sessions: InMemorySessionRepository = deps["sessions"]
    owner_id = uuid4()
    tenant_id = uuid4()

    open_session = _session(tenant_id, owner_id, uuid4())
    await sessions.add(open_session)
    closed = _session(tenant_id, owner_id, uuid4()).close()
    await sessions.add(closed)

    svc = CopilotSessionService(
        sessions=sessions,
        turns=deps["turns"],
        messages=None,  # type: ignore[arg-type]
        catalog=None,  # type: ignore[arg-type]
        events=deps["events"],
        graph=None,  # type: ignore[arg-type]
        idempotency=IdempotencyGuard(InMemoryIdempotencyStore()),
        journal=InMemorySessionJournal(),
    )

    listed = await svc.list_sessions(tenant_id=tenant_id, owner_id=owner_id)
    assert [item["id"] for item in listed] == [str(open_session.id)]
    assert closed.status is SessionStatus.CLOSED
