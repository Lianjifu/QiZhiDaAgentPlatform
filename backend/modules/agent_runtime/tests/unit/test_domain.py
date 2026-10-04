"""Unit tests for the agent runtime domain (no DB)."""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from qzdap_schema.ids import (
    AgentId,
    SessionId,
    TenantId,
    UserId,
    WorkspaceId,
)

from qzdap.modules.agent_runtime.domain import (
    Session,
    SessionStatus,
    Turn,
    TurnStatus,
)
from qzdap.modules.agent_runtime.domain.errors import SessionClosedError


def _make_session(**overrides: object) -> Session:
    defaults: dict[str, object] = {
        "id": SessionId(uuid4()),
        "tenant_id": TenantId(uuid4()),
        "workspace_id": WorkspaceId(uuid4()),
        "owner_id": UserId(uuid4()),
        "agent_id": AgentId(uuid4()),
        "agent_version": "1.0.0",
    }
    defaults.update(overrides)
    return Session.create(**defaults)  # type: ignore[arg-type]


def test_session_create_defaults_to_open() -> None:
    s = _make_session()
    assert s.status is SessionStatus.OPEN
    assert s.closed_at is None
    assert s.metadata == {}


def test_session_close_marks_closed() -> None:
    s = _make_session()
    closed = s.close()
    assert closed.status is SessionStatus.CLOSED
    assert closed.closed_at is not None
    assert closed.raise_closed_event().session_id == s.id


def test_session_close_is_not_idempotent() -> None:
    """Double-close raises SessionClosedError so audit events aren't dropped."""
    s = _make_session().close()
    with pytest.raises(SessionClosedError):
        s.close()


def test_session_create_validates_agent_version() -> None:
    with pytest.raises(ValueError, match="invalid agent_version"):
        _make_session(agent_version="")
    with pytest.raises(ValueError, match="invalid agent_version"):
        _make_session(agent_version="x" * 65)


def test_session_raise_opened_event_carries_ids() -> None:
    s = _make_session()
    e = s.raise_opened_event()
    assert e.session_id == s.id
    assert e.tenant_id == s.tenant_id
    assert e.workspace_id == s.workspace_id
    assert e.owner_id == s.owner_id
    assert e.agent_id == s.agent_id
    assert e.agent_version == s.agent_version


def test_turn_create_validates_user_input() -> None:
    with pytest.raises(ValueError, match="user_input"):
        Turn.create(
            id=__import__("uuid").UUID("00000000-0000-0000-0000-000000000001"),  # type: ignore[arg-type]
            tenant_id=TenantId(uuid4()),
            workspace_id=WorkspaceId(uuid4()),
            session_id=SessionId(uuid4()),
            user_input="",
        )
    with pytest.raises(ValueError, match="user_input"):
        Turn.create(
            id=__import__("uuid").UUID("00000000-0000-0000-0000-000000000001"),  # type: ignore[arg-type]
            tenant_id=TenantId(uuid4()),
            workspace_id=WorkspaceId(uuid4()),
            session_id=SessionId(uuid4()),
            user_input="   ",
        )


def test_turn_succeed_records_final_response() -> None:
    t = Turn.create(
        id=__import__("uuid").UUID(int=42),  # type: ignore[arg-type]
        tenant_id=TenantId(uuid4()),
        workspace_id=WorkspaceId(uuid4()),
        session_id=SessionId(uuid4()),
        user_input="hi",
    )
    assert t.status is TurnStatus.RUNNING
    done = t.succeed(final_response="hello", input_tokens=2, output_tokens=3)
    assert done.status is TurnStatus.SUCCEEDED
    assert done.final_response == "hello"
    assert done.input_tokens == 2
    assert done.output_tokens == 3


def test_turn_fail_records_error_code() -> None:
    t = Turn.create(
        id=__import__("uuid").UUID(int=43),  # type: ignore[arg-type]
        tenant_id=TenantId(uuid4()),
        workspace_id=WorkspaceId(uuid4()),
        session_id=SessionId(uuid4()),
        user_input="hi",
    )
    failed = t.fail(error_code="LLM_ALL_FAILED", error_message="all providers down")
    assert failed.status is TurnStatus.FAILED
    assert failed.error_code == "LLM_ALL_FAILED"
    assert failed.final_response == "all providers down"
    ev = failed.raise_failed_event()
    assert ev.code == "LLM_ALL_FAILED"
    assert ev.message == "all providers down"


def test_session_ids_have_branded_types() -> None:
    """Sanity: branded NewType checks still accept raw UUID for assignment."""
    s = _make_session()
    # These should type-check (SessionId wraps UUID, TenantId wraps UUID)
    sid: UUID = s.id
    tid: UUID = s.tenant_id
    assert isinstance(sid, UUID)
    assert isinstance(tid, UUID)
