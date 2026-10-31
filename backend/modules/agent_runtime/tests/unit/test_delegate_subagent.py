"""Unit tests for DelegateSubagentUseCase（**端口版** ✓）。

⚠️ 旧版这套用例**在应用层写 SQL**（架构测试的豁免表里就有一条 ✓）—— 2026-10-30
（Session Stage 5b）改成走端口 ✓：会话读、agent 读、建会话、跑一轮全都走
注入的端口 ✓，豁免表因此少了一条 ✓。

覆盖：
  1. happy path —— 子代理跑完 → ok=True, final_response 有值 ✓
  2. parent session not found → ok=False, error_code=PARENT_SESSION_NOT_FOUND
  3. cross-tenant parent → ok=False, error_code=CROSS_TENANT
  4. target agent not found → ok=False, error_code=AGENT_NOT_FOUND
  5. cross-tenant target → ok=False, error_code=CROSS_TENANT
  6. delegation depth exceeded → ok=False, error_code=DELEGATION_DEPTH_EXCEEDED
  7. 这一轮报错 → ok=False, error_code 透传 ✓
  8. 崩溃 → ok=False, error_code=SUBAGENT_CRASHED
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any
from uuid import UUID, uuid4

import pytest

from qzdap_agent_runtime.session.completion import TurnCompletion, TurnFailedError
from qzdap_kernel.errors import AppError

pytestmark = pytest.mark.asyncio


class _FakeParentSession:
    """父会话（领域对象的那几个字段就够 ✓）。"""

    def __init__(
        self,
        *,
        tenant_id: UUID,
        workspace_id: UUID,
        owner_id: UUID,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.id = uuid4()
        self.tenant_id = tenant_id
        self.workspace_id = workspace_id
        self.owner_id = owner_id
        self.metadata = metadata or {}


class _FakeTargetAgent:
    def __init__(self, *, tenant_id: UUID, version: str = "v1") -> None:
        self.id = uuid4()
        self.tenant_id = tenant_id
        self.version = version


class _FakeSessions:
    def __init__(self, parent: _FakeParentSession | None) -> None:
        self._parent = parent
        self.added: list[Any] = []

    async def get(self, session_id: UUID) -> Any:  # type: ignore[no-untyped-def]
        return self._parent


class _FakeCatalog:
    def __init__(self, agent: _FakeTargetAgent | None) -> None:
        self._agent = agent

    async def get_published(self, agent_id: UUID) -> Any:  # type: ignore[no-untyped-def]
        if self._agent is None:
            from qzdap.modules.agent_runtime.domain.catalog_errors import (
                CatalogAgentNotFound,
            )

            raise CatalogAgentNotFound(f"agent {agent_id} not found")
        return self._agent


class _FakeCreateSession:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def execute(self, **kwargs: Any) -> Any:  # type: ignore[no-untyped-def]
        self.calls.append(kwargs)
        session = _FakeParentSession(
            tenant_id=kwargs["tenant_id"],
            workspace_id=kwargs["workspace_id"],
            owner_id=kwargs["owner_id"],
            metadata=kwargs.get("metadata") or {},
        )
        return session


class _FakeOneShot:
    def __init__(
        self,
        *,
        final_message: str = "sub-agent says hi",
        raise_exc: Exception | None = None,
    ) -> None:
        self._final_message = final_message
        self._raise = raise_exc
        self.calls: list[dict[str, Any]] = []

    async def run_on_session(self, **kwargs: Any) -> TurnCompletion:  # type: ignore[no-untyped-def]
        self.calls.append(kwargs)
        if self._raise is not None:
            raise self._raise
        return TurnCompletion(
            final_message=self._final_message,
            turn_id=uuid4(),
            input_tokens=42,
            output_tokens=21,
        )


class _FakeDbSession:
    """DB 会话的替身 —— 只需要 ``commit`` ✓。"""

    def __init__(self, factory: _FakeSessionFactory) -> None:
        self._factory = factory

    async def commit(self) -> None:
        self._factory.committed += 1


class _FakeSessionFactory:
    def __init__(self) -> None:
        self.committed = 0

    @asynccontextmanager
    async def session(self):  # type: ignore[no-untyped-def]
        yield _FakeDbSession(self)


def _wire(
    *,
    parent: _FakeParentSession | None,
    target: _FakeTargetAgent | None,
    one_shot: _FakeOneShot | None = None,
):
    """装配一个 DelegateSubagentUseCase（端口全是内存替身 ✓）。"""
    from qzdap.modules.agent_runtime.application.use_cases.delegate_subagent import (
        DelegateRuntime,
        DelegateSubagentUseCase,
    )

    sessions = _FakeSessions(parent)
    catalog = _FakeCatalog(target)
    create_session = _FakeCreateSession()
    one = one_shot or _FakeOneShot()
    factory = _FakeSessionFactory()

    runtime = DelegateRuntime(
        sessions=sessions,  # type: ignore[arg-type]
        catalog=catalog,  # type: ignore[arg-type]
        create_session=create_session,  # type: ignore[arg-type]
        one_shot=one,  # type: ignore[arg-type]
    )
    usecase = DelegateSubagentUseCase(
        runtime_factory=lambda _db_session: runtime,
        session_factory=factory,  # type: ignore[arg-type]
    )
    return usecase, create_session, one, factory


def _ids() -> tuple[UUID, UUID, UUID]:
    return uuid4(), uuid4(), uuid4()


async def test_happy_path() -> None:
    tid, wid, uid = _ids()
    parent = _FakeParentSession(
        tenant_id=tid, workspace_id=wid, owner_id=uid, metadata={"agent_id": "a1"}
    )
    target = _FakeTargetAgent(tenant_id=tid)
    usecase, create_session, one, factory = _wire(parent=parent, target=target)

    result = await usecase.execute(
        parent_session_id=parent.id,
        target_agent_id=str(target.id),
        task="做点事",
        context={},
        tenant_id=tid,
        workspace_id=wid,
        actor_id=uid,
    )
    assert result.ok is True
    assert result.final_response == "sub-agent says hi"
    assert result.status == "succeeded"
    assert result.sub_session_id is not None
    # 子会话带上了委派元数据 ✓（深度 +1 ✓）。
    meta = create_session.calls[0]["metadata"]
    assert meta["delegation_depth"] == 1
    assert meta["parent_session_id"] == str(parent.id)
    # 轮次跑在**刚建的那个子会话**上 ✓。
    assert one.calls[0]["session_id"] == UUID(result.sub_session_id)
    _ = factory


async def test_parent_session_not_found() -> None:
    tid, wid, uid = _ids()
    target = _FakeTargetAgent(tenant_id=tid)
    usecase, *_ = _wire(parent=None, target=target)
    result = await usecase.execute(
        parent_session_id=uuid4(),
        target_agent_id=str(target.id),
        task="t",
        context={},
        tenant_id=tid,
        workspace_id=wid,
        actor_id=uid,
    )
    assert result.ok is False
    assert result.error_code == "PARENT_SESSION_NOT_FOUND"


async def test_cross_tenant_parent() -> None:
    tid, wid, uid = _ids()
    parent = _FakeParentSession(tenant_id=uuid4(), workspace_id=wid, owner_id=uid)
    target = _FakeTargetAgent(tenant_id=tid)
    usecase, *_ = _wire(parent=parent, target=target)
    result = await usecase.execute(
        parent_session_id=parent.id,
        target_agent_id=str(target.id),
        task="t",
        context={},
        tenant_id=tid,
        workspace_id=wid,
        actor_id=uid,
    )
    assert result.ok is False
    assert result.error_code == "CROSS_TENANT"


async def test_target_agent_not_found() -> None:
    tid, wid, uid = _ids()
    parent = _FakeParentSession(tenant_id=tid, workspace_id=wid, owner_id=uid)
    usecase, *_ = _wire(parent=parent, target=None)
    result = await usecase.execute(
        parent_session_id=parent.id,
        target_agent_id=str(uuid4()),
        task="t",
        context={},
        tenant_id=tid,
        workspace_id=wid,
        actor_id=uid,
    )
    assert result.ok is False
    assert result.error_code == "AGENT_NOT_FOUND"


async def test_cross_tenant_target() -> None:
    tid, wid, uid = _ids()
    parent = _FakeParentSession(tenant_id=tid, workspace_id=wid, owner_id=uid)
    target = _FakeTargetAgent(tenant_id=uuid4())
    usecase, *_ = _wire(parent=parent, target=target)
    result = await usecase.execute(
        parent_session_id=parent.id,
        target_agent_id=str(target.id),
        task="t",
        context={},
        tenant_id=tid,
        workspace_id=wid,
        actor_id=uid,
    )
    assert result.ok is False
    assert result.error_code == "CROSS_TENANT"


async def test_delegation_depth_exceeded() -> None:
    tid, wid, uid = _ids()
    parent = _FakeParentSession(
        tenant_id=tid,
        workspace_id=wid,
        owner_id=uid,
        metadata={"delegation_depth": 3},
    )
    target = _FakeTargetAgent(tenant_id=tid)
    usecase, *_ = _wire(parent=parent, target=target)
    result = await usecase.execute(
        parent_session_id=parent.id,
        target_agent_id=str(target.id),
        task="t",
        context={},
        tenant_id=tid,
        workspace_id=wid,
        actor_id=uid,
    )
    assert result.ok is False
    assert result.error_code == "DELEGATION_DEPTH_EXCEEDED"


async def test_turn_failure_is_reported() -> None:
    tid, wid, uid = _ids()
    parent = _FakeParentSession(tenant_id=tid, workspace_id=wid, owner_id=uid)
    target = _FakeTargetAgent(tenant_id=tid)
    usecase, *_ = _wire(
        parent=parent,
        target=target,
        one_shot=_FakeOneShot(raise_exc=TurnFailedError("TURN_FAILED", "炸了")),
    )
    result = await usecase.execute(
        parent_session_id=parent.id,
        target_agent_id=str(target.id),
        task="t",
        context={},
        tenant_id=tid,
        workspace_id=wid,
        actor_id=uid,
    )
    assert result.ok is False
    assert result.error_code == "TURN_FAILED"


async def test_app_error_is_reported() -> None:
    tid, wid, uid = _ids()
    parent = _FakeParentSession(tenant_id=tid, workspace_id=wid, owner_id=uid)
    target = _FakeTargetAgent(tenant_id=tid)
    usecase, *_ = _wire(
        parent=parent,
        target=target,
        one_shot=_FakeOneShot(raise_exc=AppError("挂了", code="SOMETHING_BROKE", status=500)),
    )
    result = await usecase.execute(
        parent_session_id=parent.id,
        target_agent_id=str(target.id),
        task="t",
        context={},
        tenant_id=tid,
        workspace_id=wid,
        actor_id=uid,
    )
    assert result.ok is False
    assert result.error_code == "SOMETHING_BROKE"


async def test_subagent_crash() -> None:
    tid, wid, uid = _ids()
    parent = _FakeParentSession(tenant_id=tid, workspace_id=wid, owner_id=uid)
    target = _FakeTargetAgent(tenant_id=tid)
    usecase, *_ = _wire(
        parent=parent, target=target, one_shot=_FakeOneShot(raise_exc=RuntimeError("boom"))
    )
    result = await usecase.execute(
        parent_session_id=parent.id,
        target_agent_id=str(target.id),
        task="t",
        context={},
        tenant_id=tid,
        workspace_id=wid,
        actor_id=uid,
    )
    assert result.ok is False
    assert result.error_code == "SUBAGENT_CRASHED"


def test_format_task_with_context() -> None:
    from qzdap.modules.agent_runtime.application.use_cases.delegate_subagent import (
        DelegateSubagentUseCase,
    )

    usecase = DelegateSubagentUseCase(
        runtime_factory=lambda _s: None,  # type: ignore[arg-type,return-value]
        session_factory=None,  # type: ignore[arg-type]
    )
    text = usecase._format_task("做点事", {"k": "v"})
    assert "做点事" in text
    assert "k: v" in text


def test_format_task_empty_context() -> None:
    from qzdap.modules.agent_runtime.application.use_cases.delegate_subagent import (
        DelegateSubagentUseCase,
    )

    usecase = DelegateSubagentUseCase(
        runtime_factory=lambda _s: None,  # type: ignore[arg-type,return-value]
        session_factory=None,  # type: ignore[arg-type]
    )
    assert usecase._format_task("做点事", {}) == "做点事"


__all__ = []
