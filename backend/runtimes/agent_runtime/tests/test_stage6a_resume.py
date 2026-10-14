"""Tests for Stage 6a PR C: governance node + resume_turn with ApprovalStore + AuditLogger."""

from __future__ import annotations

import time

import pytest
from langchain_core.tools import tool
from pydantic import BaseModel

from qzdap_agent_runtime import (
    ChannelGateway,
    ResumeRequest,
    SessionEngine,
)
from qzdap_agent_runtime.channels import ChannelMessage
from qzdap_agent_runtime.governance import (
    DEFAULT_APPROVAL_TTL_SECONDS,
    ApprovalExpiredError,
    ApprovalRecord,
    AuditEvent,
    AuditKind,
    InMemoryApprovalStore,
    InMemoryAuditLogger,
    InMemoryPolicyGuard,
)
from qzdap_agent_runtime.graph import nodes
from qzdap_agent_runtime.ports import ToolMeta
from qzdap_agent_runtime.tools import InMemoryToolRegistry, from_langchain_tool


@pytest.fixture(autouse=True)
def _reset_deps():
    yield
    nodes.reset_default_dependencies()


def _meta(name: str, risk: str, requires_approval: bool = False) -> ToolMeta:
    class _Args(BaseModel):
        query: str = "x"

    return ToolMeta(
        name=name, description=name, args_schema=_Args,
        risk=risk, requires_approval=requires_approval,
        timeout_ms=1000, max_retries=1, backoff_ms=100,
        idempotent=True, side_effect=False,
    )


# ---------------------------------------------------------------------------
# governance 节点: ApprovalStore 集成
# ---------------------------------------------------------------------------


class TestGovernanceWritesApprovalRecord:
    def test_approve_required_saves_approval_record(self) -> None:
        policy = InMemoryPolicyGuard()
        registry = InMemoryToolRegistry()
        meta = _meta("send_email", "high")
        def _send_email(query: str = "x") -> str:
            """send email"""
            return "sent"
        registry.register(meta, tool("send_email", args_schema=meta.args_schema)(_send_email))
        store = InMemoryApprovalStore()
        nodes.set_default_policy(policy)
        nodes.set_default_tool_registry(registry)
        nodes.set_default_approval_store(store)
        out = nodes.governance({
            "tenant_id": "t-1", "workspace_id": "w-1",
            "turn_id": "turn-1",
            "tool_calls": [
                {
                    "tool_call_id": "tc-1",
                    "tool_name": "send_email",
                    "status": "pending",
                    "arguments": {"query": "hi"},
                },
            ],
        })
        # 写入了 pending_approval
        assert "pending_approval" in out
        approval_id = out["pending_approval"]["approval_id"]
        # ApprovalStore 中能查到
        rec = store.get(approval_id)
        assert rec is not None
        assert rec.tool_name == "send_email"
        # TTL 默认 900s
        assert rec.expires_at - rec.created_at == DEFAULT_APPROVAL_TTL_SECONDS

    def test_audit_log_records_allow_event(self) -> None:
        policy = InMemoryPolicyGuard()
        registry = InMemoryToolRegistry()
        meta = _meta("search_kb", "low")
        def _search_kb(query: str = "x") -> str:
            """search kb"""
            return "ok"
        registry.register(meta, tool("search_kb", args_schema=meta.args_schema)(_search_kb))
        audit = InMemoryAuditLogger()
        nodes.set_default_policy(policy)
        nodes.set_default_tool_registry(registry)
        nodes.set_default_audit(audit)
        nodes.governance({
            "tenant_id": "t-1", "workspace_id": "w-1", "turn_id": "turn-1",
            "tool_calls": [
                {"tool_call_id": "tc-1", "tool_name": "search_kb", "status": "pending", "arguments": {}},
            ],
        })
        # 低风险直接 allow → 1 条 AUDIT
        events = audit.by_kind(AuditKind.ALLOW)
        assert len(events) == 1
        assert events[0].tool_name == "search_kb"


# ---------------------------------------------------------------------------
# engine.resume_turn: 完整流程
# ---------------------------------------------------------------------------


class TestResumeTurn:
    def _setup_engine_with_approval(self) -> tuple[SessionEngine, InMemoryApprovalStore]:
        store = InMemoryApprovalStore()
        audit = InMemoryAuditLogger()
        engine = SessionEngine(approval_store=store, audit=audit)
        return engine, store

    async def test_resume_approve_emits_done_and_audit(self) -> None:
        engine, store = self._setup_engine_with_approval()
        # 预存 approval
        now = time.time()
        rec = ApprovalRecord(
            approval_id="apr-tc-1",
            session_id="s-1", turn_id="t-1",
            tool_call_id="tc-1", tool_name="send_email",
            request_hash="hash-1", arguments={"to": "x@y"},
            policy_id="pol-1", requester="u-1",
            created_at=now, expires_at=now + 900,
        )
        store.save(rec)
        events = []
        async for ev in engine.resume_turn(ResumeRequest(
            turn_id="t-1", approval_id="apr-tc-1",
            decision="approve", actor_id="admin-1",
            tool_call_id="tc-1", request_hash="hash-1",
        )):
            events.append(ev)
        # emit done event
        from qzdap_agent_runtime.result.events import DoneEvent
        assert any(isinstance(e, DoneEvent) for e in events)
        # 审计记录 approve
        audit = engine.audit
        events = audit.by_kind(AuditKind.APPROVE)
        assert len(events) == 1
        assert events[0].approval_id == "apr-tc-1"

    async def test_resume_deny_emits_failed(self) -> None:
        engine, store = self._setup_engine_with_approval()
        now = time.time()
        rec = ApprovalRecord(
            approval_id="apr-tc-2",
            session_id="s-1", turn_id="t-1",
            tool_call_id="tc-2", tool_name="send_email",
            request_hash="hash-2", arguments={"to": "x@y"},
            policy_id="pol-1", requester="u-1",
            created_at=now, expires_at=now + 900,
        )
        store.save(rec)
        events = []
        async for ev in engine.resume_turn(ResumeRequest(
            turn_id="t-1", approval_id="apr-tc-2",
            decision="deny", actor_id="u-1",
            tool_call_id="tc-2", request_hash="hash-2",
        )):
            events.append(ev)
        from qzdap_agent_runtime.result.events import DoneEvent
        done_events = [e for e in events if isinstance(e, DoneEvent)]
        assert len(done_events) == 1
        assert done_events[0].status == "failed"
        # 审计记录 deny
        assert len(engine.audit.by_kind(AuditKind.DENY)) == 1

    async def test_resume_expired_emits_timeout_error_and_audit(self) -> None:
        """§5.7: 超 TTL 自动 deny + 写 audit TIMEOUT。"""
        engine, store = self._setup_engine_with_approval()
        now = time.time()
        rec = ApprovalRecord(
            approval_id="apr-tc-3",
            session_id="s-1", turn_id="t-1",
            tool_call_id="tc-3", tool_name="send_email",
            request_hash="hash-3", arguments={},
            policy_id="pol-1", requester="u-1",
            created_at=now - 1000,  # 1 秒前
            expires_at=now - 1,    # 已过期
        )
        store.save(rec)
        events = []
        async for ev in engine.resume_turn(ResumeRequest(
            turn_id="t-1", approval_id="apr-tc-3",
            decision="approve", actor_id="u-1",
            tool_call_id="tc-3", request_hash="hash-3",
        )):
            events.append(ev)
        from qzdap_agent_runtime.result.events import ErrorEvent
        err = [e for e in events if isinstance(e, ErrorEvent)]
        assert len(err) == 1
        assert err[0].error_code == "APPROVAL_EXPIRED"
        # 审计 TIMEOUT
        assert len(engine.audit.by_kind(AuditKind.TIMEOUT)) == 1

    async def test_resume_mismatch_emits_error(self) -> None:
        engine, store = self._setup_engine_with_approval()
        now = time.time()
        rec = ApprovalRecord(
            approval_id="apr-tc-4",
            session_id="s-1", turn_id="t-1",
            tool_call_id="tc-4", tool_name="send_email",
            request_hash="hash-4", arguments={},
            policy_id="pol-1", requester="u-1",
            created_at=now, expires_at=now + 900,
        )
        store.save(rec)
        events = []
        async for ev in engine.resume_turn(ResumeRequest(
            turn_id="t-1", approval_id="apr-tc-4",
            decision="approve", actor_id="u-1",
            tool_call_id="tc-other",  # 不匹配
            request_hash="hash-4",
        )):
            events.append(ev)
        from qzdap_agent_runtime.result.events import ErrorEvent
        err = [e for e in events if isinstance(e, ErrorEvent)]
        assert err[0].error_code == "APPROVAL_NOT_MATCH"

    async def test_resume_without_approval_store_emits_error(self) -> None:
        engine = SessionEngine()  # 无 approval_store
        events = []
        async for ev in engine.resume_turn(ResumeRequest(
            turn_id="t-1", approval_id="apr-x",
            decision="approve", actor_id="u-1",
        )):
            events.append(ev)
        from qzdap_agent_runtime.result.events import ErrorEvent
        err = [e for e in events if isinstance(e, ErrorEvent)]
        assert err[0].error_code == "APPROVAL_NOT_MATCH"