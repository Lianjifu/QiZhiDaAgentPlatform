"""Unit tests for DelegateSubagentUseCase.

We don't hit Postgres — we patch ``SessionFactory.session`` to return a fake
AsyncSession that responds to a couple of SELECT/INSERT statements, and stub
``_AgentRuntimeFactory.for_session`` to skip the real LLM.

What we cover:
  1. happy path — stub agent + parent metadata OK → ok=True, final_response filled
  2. parent session not found → ok=False, error_code=PARENT_SESSION_NOT_FOUND
  3. cross-tenant parent → ok=False, error_code=CROSS_TENANT
  4. target agent not found → ok=False, error_code=AGENT_NOT_FOUND
  5. cross-tenant target → ok=False, error_code=CROSS_TENANT
  6. delegation depth exceeded → ok=False, error_code=DELEGATION_DEPTH_EXCEEDED
  7. sub-agent AppError → ok=False, error_code propagated
  8. sub-agent crash → ok=False, error_code=SUBAGENT_CRASHED
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any
from unittest.mock import MagicMock
from uuid import UUID, uuid4

import pytest


pytestmark = pytest.mark.asyncio


# ── fakes ──────────────────────────────────────────────────────────────


@dataclass
class _FakeRow:
    tenant_id: UUID
    workspace_id: UUID
    metadata: dict[str, Any] | None = None
    id: UUID | None = None
    version: str | None = "v1"
    status: str | None = "active"


class _FakeSession:
    """Stand-in for AsyncSession — returns the configured rows in order."""

    def __init__(self, results: list[Any] | None = None) -> None:
        self.executed: list[tuple[str, dict]] = []
        self._results = list(results or [])
        self.committed = False

    async def execute(self, statement, params=None):  # noqa: ANN001
        self.executed.append((str(statement), params or {}))
        m = MagicMock()
        if self._results:
            m.first = MagicMock(return_value=self._results.pop(0))
        else:
            m.first = MagicMock(return_value=None)
        return m

    async def commit(self) -> None:
        self.committed = True


def _async_cm(value):
    @asynccontextmanager
    async def _cm():
        yield value
    return _cm()


def _completion(final_message="sub-agent says hi"):
    from qzdap.modules.agent_runtime.application.use_cases.run_turn_to_completion import (
        RunTurnCompletionResult,
    )
    return RunTurnCompletionResult(
        final_message=final_message,
        turn_id=uuid4(),
        input_tokens=42,
        output_tokens=21,
    )


def _wire(*, ids, parent_row, target_row, subagent_result=None, raise_in_completion=False,
          app_error_to_raise=None, raw_error_to_raise=None):
    """Build a DelegateSubagentUseCase wired against in-memory fakes.

    Caller provides ``ids`` so the same uuid values can be reused when
    constructing test rows.

    Returns (usecase, parent_session_id, target_agent_id,
             fake_session, runtime_factory).
    """
    from qzdap.modules.agent_runtime.application.use_cases.delegate_subagent import (
        DelegateSubagentUseCase,
    )
    # Patch the source modules so the use case's deferred imports pick up
    # the stubs. The use case does
    #   from .run_turn import RunTurnUseCase
    # inside execute(), so we have to patch the *source* module, not the
    # delegate_subagent namespace.
    import qzdap.modules.agent_runtime.application.use_cases.run_turn as rt_mod
    import qzdap.modules.agent_runtime.application.use_cases.run_turn_to_completion as rtc_mod

    parent_sid = uuid4()
    target_aid = uuid4()

    fake_session = _FakeSession([parent_row, target_row])
    factory = MagicMock()
    # Each call to factory.session() must yield a fresh async context manager
    # — _AsyncGeneratorContextManager can't be re-entered after the first
    # `async with` exits, and the use case opens a session twice.
    factory.session = MagicMock(side_effect=lambda: _async_cm(fake_session))

    runtime_factory = MagicMock()
    runtime_factory.for_session = MagicMock(return_value=MagicMock())

    class _StubRun:
        def __init__(self, *_a, **_kw):  # noqa: ANN001
            pass

    class _StubCompletion:
        def __init__(self, *_a, **_kw):  # noqa: ANN001
            pass

        async def execute(self, **_):
            if app_error_to_raise is not None:
                raise app_error_to_raise
            if raw_error_to_raise is not None:
                raise raw_error_to_raise
            return subagent_result or _completion()

    _original_run = rt_mod.RunTurnUseCase
    _original_completion = rtc_mod.RunTurnCompletionUseCase
    rt_mod.RunTurnUseCase = _StubRun
    rtc_mod.RunTurnCompletionUseCase = _StubCompletion

    usecase = DelegateSubagentUseCase(
        agent_runtime_factory=runtime_factory,
        session_factory=factory,
    )
    # Return the originals so each test can restore if needed; for our tests
    # we just leave them patched — the next test re-patches.
    return (
        usecase, parent_sid, target_aid, fake_session, runtime_factory,
        _original_run, _original_completion,
    )


def _make_ids():
    return {
        "tenant_id": uuid4(),
        "workspace_id": uuid4(),
        "actor_id": uuid4(),
    }


# ── tests ──────────────────────────────────────────────────────────────


async def test_happy_path():
    ids = _make_ids()
    target_aid_uuid = uuid4()
    usecase, parent_sid, target_aid, session, factory, _, _ = _wire(
        ids=ids,
        parent_row=_FakeRow(
            tenant_id=ids["tenant_id"], workspace_id=ids["workspace_id"],
            metadata={"delegation_depth": 0, "agent_id": "parent-agent"},
        ),
        target_row=_FakeRow(
            tenant_id=ids["tenant_id"], workspace_id=ids["workspace_id"],
            id=target_aid_uuid, version="v1", status="active",
        ),
        subagent_result=_completion("sub-agent done"),
    )
    result = await usecase.execute(
        parent_session_id=parent_sid,
        target_agent_id=str(target_aid),
        task="do the thing",
        context={"k": "v"},
        **ids,
    )
    assert result.ok is True
    assert result.final_response == "sub-agent done"
    assert result.status == "succeeded"
    assert result.sub_session_id is not None
    assert result.delegation_depth == 1
    assert result.error_code is None
    assert session.committed is True
    assert factory.for_session.called


async def test_parent_session_not_found():
    ids = _make_ids()
    usecase, parent_sid, target_aid, _, _, _, _ = _wire(
        ids=ids,
        parent_row=None,  # missing
        target_row=_FakeRow(tenant_id=ids["tenant_id"], workspace_id=ids["workspace_id"]),
    )
    result = await usecase.execute(
        parent_session_id=parent_sid,
        target_agent_id=str(target_aid),
        task="x", context={}, **ids,
    )
    assert result.ok is False
    assert result.error_code == "PARENT_SESSION_NOT_FOUND"
    assert result.sub_session_id is None


async def test_cross_tenant_parent():
    ids = _make_ids()
    usecase, parent_sid, target_aid, _, _, _, _ = _wire(
        ids=ids,
        parent_row=_FakeRow(
            tenant_id=uuid4(),  # other tenant
            workspace_id=ids["workspace_id"],
            metadata={},
        ),
        target_row=_FakeRow(tenant_id=ids["tenant_id"], workspace_id=ids["workspace_id"]),
    )
    result = await usecase.execute(
        parent_session_id=parent_sid,
        target_agent_id=str(target_aid),
        task="x", context={}, **ids,
    )
    assert result.ok is False
    assert result.error_code == "CROSS_TENANT"


async def test_target_agent_not_found():
    ids = _make_ids()
    usecase, parent_sid, target_aid, _, _, _, _ = _wire(
        ids=ids,
        parent_row=_FakeRow(
            tenant_id=ids["tenant_id"], workspace_id=ids["workspace_id"],
            metadata={"delegation_depth": 0},
        ),
        target_row=None,  # missing
    )
    result = await usecase.execute(
        parent_session_id=parent_sid,
        target_agent_id=str(target_aid),
        task="x", context={}, **ids,
    )
    assert result.ok is False
    assert result.error_code == "AGENT_NOT_FOUND"


async def test_cross_tenant_target():
    ids = _make_ids()
    usecase, parent_sid, target_aid, _, _, _, _ = _wire(
        ids=ids,
        parent_row=_FakeRow(
            tenant_id=ids["tenant_id"], workspace_id=ids["workspace_id"],
            metadata={"delegation_depth": 0},
        ),
        target_row=_FakeRow(tenant_id=uuid4(), workspace_id=uuid4()),  # other tenant
    )
    result = await usecase.execute(
        parent_session_id=parent_sid,
        target_agent_id=str(target_aid),
        task="x", context={}, **ids,
    )
    assert result.ok is False
    assert result.error_code == "CROSS_TENANT"


async def test_delegation_depth_exceeded():
    ids = _make_ids()
    usecase, parent_sid, target_aid, _, _, _, _ = _wire(
        ids=ids,
        parent_row=_FakeRow(
            tenant_id=ids["tenant_id"], workspace_id=ids["workspace_id"],
            metadata={"delegation_depth": 3},  # already at max
        ),
        target_row=_FakeRow(tenant_id=ids["tenant_id"], workspace_id=ids["workspace_id"]),
    )
    result = await usecase.execute(
        parent_session_id=parent_sid,
        target_agent_id=str(target_aid),
        task="x", context={}, **ids,
    )
    assert result.ok is False
    assert result.error_code == "DELEGATION_DEPTH_EXCEEDED"
    assert "depth=3" in (result.error or "")


async def test_subagent_aperror():
    from qzdap_kernel.errors import AppError
    ids = _make_ids()
    usecase, parent_sid, target_aid, _, _, _, _ = _wire(
        ids=ids,
        parent_row=_FakeRow(
            tenant_id=ids["tenant_id"], workspace_id=ids["workspace_id"],
            metadata={"delegation_depth": 0},
        ),
        target_row=_FakeRow(tenant_id=ids["tenant_id"], workspace_id=ids["workspace_id"]),
        app_error_to_raise=AppError("LLM timed out", code="LLM_TIMEOUT", status=504),
    )
    result = await usecase.execute(
        parent_session_id=parent_sid,
        target_agent_id=str(target_aid),
        task="x", context={}, **ids,
    )
    assert result.ok is False
    assert result.error_code == "LLM_TIMEOUT"
    assert result.status == "failed"
    assert result.sub_session_id is not None  # sub_session was created


async def test_subagent_crash():
    ids = _make_ids()
    usecase, parent_sid, target_aid, _, _, _, _ = _wire(
        ids=ids,
        parent_row=_FakeRow(
            tenant_id=ids["tenant_id"], workspace_id=ids["workspace_id"],
            metadata={"delegation_depth": 0},
        ),
        target_row=_FakeRow(tenant_id=ids["tenant_id"], workspace_id=ids["workspace_id"]),
        raw_error_to_raise=RuntimeError("kaboom"),
    )
    result = await usecase.execute(
        parent_session_id=parent_sid,
        target_agent_id=str(target_aid),
        task="x", context={}, **ids,
    )
    assert result.ok is False
    assert result.error_code == "SUBAGENT_CRASHED"
    assert "kaboom" in (result.error or "")


async def test_format_task_with_context():
    from qzdap.modules.agent_runtime.application.use_cases.delegate_subagent import (
        DelegateSubagentUseCase,
    )

    uc = DelegateSubagentUseCase(
        agent_runtime_factory=MagicMock(),
        session_factory=MagicMock(),
    )
    out = uc._format_task("do X", {"a": 1, "b": "hi"})
    assert "do X" in out
    assert "- a: 1" in out
    assert "- b: hi" in out


async def test_format_task_empty_context():
    from qzdap.modules.agent_runtime.application.use_cases.delegate_subagent import (
        DelegateSubagentUseCase,
    )

    uc = DelegateSubagentUseCase(
        agent_runtime_factory=MagicMock(),
        session_factory=MagicMock(),
    )
    assert uc._format_task("do X", {}) == "do X"
