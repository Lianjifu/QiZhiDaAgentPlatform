"""``ChannelTurnService`` —— **真库**（会话粘性 ✓）。

覆盖 Session Stage 5b 的落点（IM 切到唯一 turn 实现）：

- 同一个 ``channel_session_key``（渠道 + 聊天）→ **同一个会话** ✓
  （台账 **R1**：IM 过去每条消息新建会话，跨消息没有上下文 ✗）；
- 不同的 key → 不同的会话 ✓；
- 会话上**跑的那一轮**用的是**粘住的那个会话** ✓。
"""

from __future__ import annotations

import os
import uuid
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from qzdap.modules.agent_runtime.adapter.persistence.session_store import (
    PostgresSessionStore,
)
from qzdap.modules.agent_runtime.application.channel_turn import ChannelTurnService
from qzdap_agent_runtime.gateway.types import ChannelType, IdempotencyKey, KeySource
from qzdap_agent_runtime.session.manager import SessionManager

_DDL = [
    """
CREATE TABLE "{schema}".agent_sessions (
    id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    owner_id uuid NOT NULL,
    agent_id uuid NOT NULL,
    agent_version varchar(64) NOT NULL,
    status varchar(16) NOT NULL DEFAULT 'open',
    closed_at timestamptz,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    graph_state jsonb NOT NULL DEFAULT '{}'::jsonb,
    -- ⚠️ **摘要是独立的一列** ✓（Context 方案 §5.1 ✓）—— ORM 现在映射它 ✓
    rolling_summary text NOT NULL DEFAULT '',
    current_revision integer NOT NULL DEFAULT 0,
    current_turn_id uuid,
    agent_version_pinned varchar(64),
    channel_session_key varchar(512),
    next_ingress_seq integer NOT NULL DEFAULT 0,
    next_message_seq integer NOT NULL DEFAULT 0,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
)
""",
    """
CREATE UNIQUE INDEX uq_agent_sessions_channel_key
    ON "{schema}".agent_sessions (tenant_id, channel_session_key)
    WHERE channel_session_key IS NOT NULL
""",
]


class _FakeCopilot:
    """``CopilotSessionService`` 的替身 —— 这一条只关心会话复用 ✓。"""

    def __init__(self) -> None:
        self.session_ids: list[UUID] = []

    def bind_ports(self, **ports: Any) -> None:
        return


class _FakeTurnEntry:
    """**跑一轮**的入口替身 ✓ —— 记下「这一轮跑在哪个会话上」✓。"""

    def __init__(self) -> None:
        self.session_ids: list[UUID] = []

    async def stream(self, **kwargs: Any):  # type: ignore[no-untyped-def]
        self.session_ids.append(kwargs["session_id"])
        from qzdap_schema.dtos.turn import DoneChunk

        yield DoneChunk(turn_id=uuid4(), seq=1, final_message="好的")


@pytest.fixture
async def store_ctx():
    url = os.environ.get("QZDAP_TEST_DATABASE_URL")
    if not url:
        pytest.skip("QZDAP_TEST_DATABASE_URL is not set")
    schema = "channel_turn_" + uuid.uuid4().hex
    admin = create_async_engine(url)
    async with admin.connect() as conn:
        await conn.execute(text(f'CREATE SCHEMA "{schema}"'))
        for statement in _DDL:
            await conn.execute(text(statement.replace("{schema}", schema)))
        await conn.commit()

    engine = create_async_engine(url, connect_args={"server_settings": {"search_path": schema}})
    from qzdap_persistence.session_factory import SessionFactory

    factory = SessionFactory(engine)
    try:
        yield factory
    finally:
        await engine.dispose()
        async with admin.connect() as conn:
            await conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
            await conn.commit()
        await admin.dispose()


def _request(*, key: str, tenant_id: UUID, workspace_id: UUID, owner_id: UUID) -> Any:
    from qzdap_agent_runtime.session.channel_turn import ChannelTurnRequest

    return ChannelTurnRequest(
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        owner_id=owner_id,
        agent_id=uuid4(),
        agent_version="v1",
        channel_session_key=key,
        channel_type=ChannelType.FEISHU,
        user_input="你好",
        idempotency=IdempotencyKey(
            value=f"platform|{uuid4()}",
            source=KeySource.PLATFORM_MESSAGE_ID,
            strength="strong",
            expires_at=None,  # type: ignore[arg-type]
        ),
        metadata={"channel_type": "feishu"},
    )


@pytest.mark.asyncio
async def test_the_same_channel_and_chat_reuse_one_session(store_ctx) -> None:  # type: ignore[no-untyped-def]
    copilot = _FakeCopilot()
    turn_entry = _FakeTurnEntry()
    async with store_ctx.session() as db_session:
        service = ChannelTurnService(
            sessions=SessionManager(store=PostgresSessionStore(db_session)),
            copilot=copilot,  # type: ignore[arg-type]
            turn_entry=turn_entry,  # type: ignore[arg-type]
        )
        tenant, workspace, owner = uuid4(), uuid4(), uuid4()
        first = await service.run(
            _request(
                key="channel-1:chat-1",
                tenant_id=tenant,
                workspace_id=workspace,
                owner_id=owner,
            )
        )
        second = await service.run(
            _request(
                key="channel-1:chat-1",
                tenant_id=tenant,
                workspace_id=workspace,
                owner_id=owner,
            )
        )
        await db_session.commit()

    assert first.session_id == second.session_id
    assert turn_entry.session_ids == [first.session_id, first.session_id]


@pytest.mark.asyncio
async def test_different_chats_get_different_sessions(store_ctx) -> None:  # type: ignore[no-untyped-def]
    copilot = _FakeCopilot()
    turn_entry = _FakeTurnEntry()
    async with store_ctx.session() as db_session:
        service = ChannelTurnService(
            sessions=SessionManager(store=PostgresSessionStore(db_session)),
            copilot=copilot,  # type: ignore[arg-type]
            turn_entry=turn_entry,  # type: ignore[arg-type]
        )
        tenant, workspace, owner = uuid4(), uuid4(), uuid4()
        first = await service.run(
            _request(
                key="channel-1:chat-a",
                tenant_id=tenant,
                workspace_id=workspace,
                owner_id=owner,
            )
        )
        second = await service.run(
            _request(
                key="channel-1:chat-b",
                tenant_id=tenant,
                workspace_id=workspace,
                owner_id=owner,
            )
        )
        await db_session.commit()

    assert first.session_id != second.session_id


__all__ = []
