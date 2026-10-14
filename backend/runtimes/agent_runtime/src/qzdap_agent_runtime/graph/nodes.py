"""19 节点 stub 实现（§2.5 阻塞 3 权威命名表）。

每个 stub 是一个 LangGraph 节点函数：接受 `SessionState`，返回状态更新字典。
Stage 1 范围内：stub 只做"过路"——保留消息、初始化空字段、确保图可编译。
Stage 2 PR C：acquire_turn_lock / release_turn_lock 接入 LockManager。
真实逻辑（治理、执行、recall 等）由后续 Stage 2/3/4/6a/6b 填充。

节点 ID 与 §13.2 表 19 行一一对应；编号 = 执行顺序。
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from ..context.budget import (
    Compactor,
    ContextAssembler,
    InMemorySummaryModel,
    estimate_tokens,
)
from ..execution.executor import InMemoryToolExecutor
from ..execution.lock import (
    LockManager,
    LockToken,
    RevisionConflictError,
    SessionBusyError,
)
from ..governance.approval import (
    DEFAULT_APPROVAL_TTL_SECONDS,
    ApprovalRecord,
    InMemoryApprovalStore,
    _request_hash,
)
from ..governance.audit import AuditEvent, AuditKind, InMemoryAuditLogger
from ..governance.policy import InMemoryPolicyGuard
from ..memory.layered import InMemoryLayeredMemory, L1Source
from ..graph.deep_agent import (
    DEEP_AGENT_BUDGET_EXCEEDED_ERROR_CODE,
    DEEP_AGENT_FAILED_ERROR_CODE,
    DeepAgentBudgetExceeded,
    DeepAgentConfig,
    InMemoryDeepAgent,
    InMemoryDeepAgentFactory,
    SubAgentSpec,
)
from .routing import AgentRouteConfig, TaskKind, classify_task_kind_heuristic
from .state import SessionState

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Stage 2 PR C 注入点：LockManager 由 composition root 注入（lifespan）。
# 进程内全局单例（仅单测 / dev 兜底使用）；生产用 PostgresLockManager。
# ---------------------------------------------------------------------------

_default_lock_manager: Optional[LockManager] = None
_default_memory: Optional[InMemoryLayeredMemory] = None
_default_compactor: Optional[Compactor] = None
_default_assembler: Optional[ContextAssembler] = None
_default_policy: Optional[Any] = None  # PolicyGuard
_default_executor: Optional[InMemoryToolExecutor] = None
_default_tool_registry: Optional[Any] = None  # ToolRegistry
_default_agent_config: Optional[AgentRouteConfig] = None
_default_approval_store: Optional[InMemoryApprovalStore] = None
_default_audit: Optional[InMemoryAuditLogger] = None
_default_deep_agent_factory: Optional[Any] = None  # DeepAgentFactory (Stage 6b)


def set_default_lock_manager(manager: LockManager) -> None:
    """composition root 注入入口（lifespan 启动时调用一次）。"""
    global _default_lock_manager
    _default_lock_manager = manager


def get_default_lock_manager() -> LockManager | None:
    """节点运行时的 LockManager 解析（注入优先，否则 None = Stage 1 fake 行为）。"""
    return _default_lock_manager


def set_default_memory(memory: InMemoryLayeredMemory) -> None:
    """composition root 注入 LayeredMemory。"""
    global _default_memory
    _default_memory = memory


def get_default_memory() -> InMemoryLayeredMemory | None:
    return _default_memory


def set_default_compactor(compactor: Compactor) -> None:
    global _default_compactor
    _default_compactor = compactor


def get_default_compactor() -> Compactor | None:
    if _default_compactor is None:
        return Compactor()
    return _default_compactor


def set_default_assembler(assembler: ContextAssembler) -> None:
    global _default_assembler
    _default_assembler = assembler


def get_default_assembler() -> ContextAssembler | None:
    return _default_assembler


def set_default_policy(policy: Any) -> None:
    global _default_policy
    _default_policy = policy


def get_default_policy() -> Any | None:
    return _default_policy


def set_default_executor(executor: InMemoryToolExecutor) -> None:
    global _default_executor
    _default_executor = executor


def get_default_executor() -> InMemoryToolExecutor | None:
    return _default_executor


def set_default_tool_registry(registry: Any) -> None:
    global _default_tool_registry
    _default_tool_registry = registry


def get_default_tool_registry() -> Any | None:
    return _default_tool_registry


def set_default_agent_config(config: AgentRouteConfig) -> None:
    global _default_agent_config
    _default_agent_config = config


def get_default_agent_config() -> AgentRouteConfig | None:
    return _default_agent_config


def set_default_approval_store(store: InMemoryApprovalStore) -> None:
    """composition root 注入 ApprovalStore (§5.7 / Stage 6a)."""
    global _default_approval_store
    _default_approval_store = store


def get_default_approval_store() -> InMemoryApprovalStore | None:
    return _default_approval_store


def set_default_audit(audit: InMemoryAuditLogger) -> None:
    """composition root 注入 AuditLogger (§5.7 / Stage 6a)."""
    global _default_audit
    _default_audit = audit


def get_default_audit() -> InMemoryAuditLogger | None:
    return _default_audit


def set_default_deep_agent_factory(factory: Any) -> None:
    """composition root 注入 DeepAgentFactory (§5.5 / Stage 6b)."""
    global _default_deep_agent_factory
    _default_deep_agent_factory = factory


def get_default_deep_agent_factory() -> Any | None:
    return _default_deep_agent_factory


def reset_default_dependencies() -> None:
    """测试辅助：清空所有默认依赖。"""
    global _default_lock_manager, _default_memory, _default_compactor, _default_assembler
    global _default_policy, _default_executor, _default_tool_registry, _default_agent_config
    global _default_approval_store, _default_audit, _default_deep_agent_factory
    _default_lock_manager = None
    _default_memory = None
    _default_compactor = None
    _default_assembler = None
    _default_policy = None
    _default_executor = None
    _default_tool_registry = None
    _default_agent_config = None
    _default_approval_store = None
    _default_audit = None
    _default_deep_agent_factory = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _passthrough(state: SessionState) -> dict[str, Any]:
    """通用 passthrough：保留原 state 不变；供未实现节点使用。"""
    return {}


# ---------------------------------------------------------------------------
# 1-9: 外层线性段
# ---------------------------------------------------------------------------


def normalize_input(state: SessionState) -> dict[str, Any]:
    """1 normalize_input: §13.2 节点 1。Stage 1 仅初始化 trace_id。"""
    return {}


def acquire_turn_lock(state: SessionState) -> dict[str, Any]:
    """2 acquire_turn_lock: §13.2 节点 2。

    Stage 2 PR C：advisory lock + revision 乐观并发（§4.2 / §4.3）。

    行为：

    - 从 state 读取 session_id / turn_id / expected_revision / revision
    - 调用 LockManager.acquire()，成功则把 token 写入 state
    - 失败：

        * `SessionBusyError` → 在 state.errors 写入 `SESSION_BUSY` 错误码
        * `RevisionConflictError` → 在 state.errors 写入 `REVISION_CONFLICT`

    Stage 1 行为：未注入 LockManager 时保持 passthrough（向后兼容）。
    """
    manager = get_default_lock_manager()
    if manager is None:
        # Stage 1 fake：未注入 LockManager，跳过锁逻辑
        return {}

    session_id = str(state.get("session_id", ""))
    turn_id = str(state.get("turn_id", ""))
    # 注意：必须用 `is None` 判空，因为 expected_revision=0 是合法值，
    # 不能用 `or` 否则会把 0 当 falsy 而错误地回退。
    raw_expected = state.get("expected_revision")
    expected_revision = int(raw_expected) if raw_expected is not None else int(
        state.get("revision") or 0
    )
    current_revision = int(state.get("revision") or 0)

    try:
        token = manager.acquire(
            session_id=session_id,
            turn_id=turn_id,
            expected_revision=expected_revision,
            current_revision=current_revision,
        )
    except SessionBusyError as exc:
        # SESSION_BUSY: 已有活动 turn
        return {
            "errors": [
                {
                    "node": "acquire_turn_lock",
                    "error_code": "SESSION_BUSY",
                    "message": str(exc),
                    "trace_id": state.get("trace_id"),
                    "retriable": True,
                    "occurred_at": "",
                }
            ]
        }
    except RevisionConflictError as exc:
        # REVISION_CONFLICT: revision 不匹配
        return {
            "errors": [
                {
                    "node": "acquire_turn_lock",
                    "error_code": "REVISION_CONFLICT",
                    "message": str(exc),
                    "trace_id": state.get("trace_id"),
                    "retriable": True,
                    "occurred_at": "",
                }
            ]
        }

    # 成功：把 token 信息写入 state
    return {
        "pending_approval": {
            # 注意：lock token 复用 pending_approval 字段存 session-scoped 数据。
            # 真实数据存在 session_turns 表的 idempotency_key / current_turn_id 列。
            "approval_id": token.holder_id,
            "tool_call_id": "",
            "tool_name": f"turn_lock:{turn_id}",
            "arguments_hash": "",
            "policy_id": "turn_lock",
            "requester": str(state.get("agent_id", "")),
            "requested_at": "",
            "expires_at": "",
        }
    }


def load_checkpoint(state: SessionState) -> dict[str, Any]:
    """3 load_checkpoint: §13.2 节点 3。Stage 1 passthrough。"""
    return {}


def write_turn_record(state: SessionState) -> dict[str, Any]:
    """4 write_turn_record: §13.2 节点 4。Stage 1 passthrough。"""
    return {}


def recall_memory_and_knowledge(state: SessionState) -> dict[str, Any]:
    """6 recall_memory_and_knowledge: §13.2 节点 6。

    Stage 3 PR B：调用 LayeredMemory.recall_memory + recall_knowledge。

    行为：

    - 从 state 取 query / tenant_id / workspace_id / user_id / session_id
    - 调用 memory.recall_memory() → memory_hits (L1+L2)
    - 调用 memory.recall_knowledge() → knowledge_hits (L3)
    - 召回失败 → state.degraded.recall_degraded=true

    L1 source 注入由 load_agent_context 节点在更早阶段完成（避免
    节点互相耦合）。本节点只做 recall。

    InMemoryLayeredMemory 是同步实现（无 I/O）；async 节点 (例如
    PostgresLayeredMemory) 通过 run_async_from_sync 适配。
    """
    memory = get_default_memory()
    if memory is None:
        return {
            "memory_hits": [],
            "knowledge_hits": [],
        }

    msgs = state.get("messages") or []
    # 兼容 LangChain BaseMessage 和 dict 两种输入
    if msgs:
        last = msgs[-1]
        if hasattr(last, "content"):
            text = str(last.content)  # type: ignore[union-attr]
        elif isinstance(last, dict):
            text = str(last.get("content", ""))
        else:
            text = str(last)
    else:
        text = ""
    tenant_id = str(state.get("tenant_id", ""))
    workspace_id = str(state.get("workspace_id", ""))
    user_id = ""  # 从 authenticated actor 注入 (Stage 5)
    session_id = str(state.get("session_id", ""))

    try:
        # 始终调用方法（duck typing）；不依赖 isinstance 检查
        mem_hits = _call_memory_recall(memory, "recall_memory",
            query=text, tenant_id=tenant_id, workspace_id=workspace_id,
            user_id=user_id or "*", session_id=session_id,
            policy={"top_k": 5, "threshold": 0.05})
        knowledge_hits = _call_memory_recall(memory, "recall_knowledge",
            query=text, tenant_id=tenant_id, workspace_id=workspace_id)
    except Exception as exc:  # noqa: BLE001
        # §5.4 召回失败: 主回答继续, 标记 degraded
        logger.warning("recall failed: %s", exc)
        return {
            "memory_hits": [],
            "knowledge_hits": [],
            "degraded": {**(state.get("degraded") or {}), "recall_degraded": True},
        }

    # dataclass → dict
    def _to_dict(h: Any) -> dict[str, Any]:
        if hasattr(h, "__dataclass_fields__"):
            from dataclasses import asdict
            return asdict(h)
        return h

    return {
        "memory_hits": [_to_dict(h) for h in mem_hits],
        "knowledge_hits": [_to_dict(h) for h in knowledge_hits],
        "degraded": {**(state.get("degraded") or {}), "recall_degraded": False},
    }


def _call_memory_recall(memory: Any, method_name: str, **kwargs: Any) -> list[Any]:
    """调用 memory 上的方法，兼容 sync/async 实现。"""
    method = getattr(memory, method_name)
    result = method(**kwargs)
    import asyncio
    if asyncio.iscoroutine(result):
        from ..memory import run_async_from_sync
        return run_async_from_sync(result)
    return result


def assemble_context(state: SessionState) -> dict[str, Any]:
    """7 assemble_context: §13.2 节点 7。

    Stage 3 PR B：用 ContextAssembler 拼装 system / agent / tenant /
    summary / memory / knowledge / recent，按固定优先级 (§5.3)。
    """
    assembler = get_default_assembler()
    if assembler is None:
        # Stage 1 兼容: 未注入 assembler → passthrough
        return {}

    memory_hits = state.get("memory_hits") or []
    knowledge_hits = state.get("knowledge_hits") or []

    try:
        ctx = assembler.assemble(
            system_prompt="You are a helpful assistant.",  # 实际从 agent catalog 注入 (Stage 4)
            agent_config={
                "agent_id": state.get("agent_id", ""),
                "version": state.get("agent_version", ""),
            },
            tenant_context={
                "tenant_id": state.get("tenant_id", ""),
                "workspace_id": state.get("workspace_id", ""),
                "user_id": "",  # Stage 5 注入
            },
            rolling_summary=str(state.get("rolling_summary", "")),
            memory_hits=memory_hits,
            knowledge_hits=knowledge_hits,
            recent_messages=list(state.get("messages", []) or []),
        )
        return {
            "context_manifest": ctx.manifest.to_dict(),
            "degraded": {**(state.get("degraded") or {}), **ctx.degraded_flags},
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning("assemble_context failed: %s", exc)
        return {
            "degraded": {**(state.get("degraded") or {}), "compaction_degraded": True},
        }


def compact_if_needed(state: SessionState) -> dict[str, Any]:
    """8 compact_if_needed: §13.2 节点 8。

    Stage 3 PR B：用 Compactor 压缩 messages (§5.3)。
    - 优先 LLM 摘要
    - 失败降级为确定性窗口压缩
    - 标记 compaction_degraded
    """
    compactor = get_default_compactor()
    if compactor is None:
        return {}

    messages = list(state.get("messages", []) or [])
    if not messages:
        return {}

    target_tokens = 4000  # Stage 4 由 ContextAssembler.max_tokens 决定
    existing_summary = str(state.get("rolling_summary", ""))

    try:
        result = compactor.compact(messages, existing_summary, target_tokens)
        return {
            "messages": _result_to_messages(result, messages),
            "rolling_summary": result.rolling_summary,
            "context_manifest": {
                **(state.get("context_manifest") or {}),
                "compaction": {
                    "tokens_before": result.tokens_before,
                    "tokens_after": result.tokens_after,
                    "removed_ids": result.removed_message_ids,
                },
            },
            "degraded": {
                **(state.get("degraded") or {}),
                "compaction_degraded": result.degraded,
            },
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning("compact_if_needed failed: %s", exc)
        return {
            "degraded": {**(state.get("degraded") or {}), "compaction_degraded": True},
        }


def _result_to_messages(result: CompactionResult, original: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Compactor 压缩后: 摘要 + tail 消息。"""
    kept = original[len(result.removed_message_ids):]
    summary_msg = {
        "role": "system",
        "content": f"[compaction summary] {result.rolling_summary}",
    }
    return [summary_msg, *kept]


def load_agent_context(state: SessionState) -> dict[str, Any]:
    """5 load_agent_context: §13.2 节点 5。

    Stage 3 PR B 范围：注入 L1 source (当前 messages + rolling_summary) 到
    LayeredMemory，使后续 recall_memory_and_knowledge 节点能命中。

    Stage 4 扩展：实际加载 agent catalog, 写 system_prompt / tool policy / agent_version。
    """
    memory = get_default_memory()
    if memory is not None and hasattr(memory, "set_l1"):
        memory.set_l1(L1Source(
            session_id=str(state.get("session_id", "")),
            messages=tuple(state.get("messages", []) or []),
            rolling_summary=str(state.get("rolling_summary", "")),
        ))
    # Stage 1 兼容: passthrough（除 L1 注入外）
    return {}


# ---------------------------------------------------------------------------
# 9 route（节点 ID = 9，但需特殊：返回 deep_task 标志供条件路由）
# ---------------------------------------------------------------------------


def route(state: SessionState) -> dict[str, Any]:
    """9 route: §13.2 节点 9。

    Stage 4 PR C: 接入真实 `classify_task_kind_heuristic` (不再是 fake)。

    行为：
    - 取 state.messages 末尾作为 user query
    - 调 classify_task_kind_heuristic 算 TaskKind
    - 计算 route.deep_task
    - 写 state.route 字段
    """
    cfg = get_default_agent_config() or AgentRouteConfig(
        agent_id=str(state.get("agent_id", "")),
        deep_research=False,
    )
    msgs = state.get("messages") or []
    if msgs:
        last = msgs[-1]
        if hasattr(last, "content"):
            text = str(last.content)  # type: ignore[union-attr]
        elif isinstance(last, dict):
            text = str(last.get("content", ""))
        else:
            text = str(last)
    else:
        text = ""
    message_count = len(msgs)
    registry = get_default_tool_registry()
    tools_count = len(registry.list_by_risk("low")) + len(registry.list_by_risk("medium")) + len(registry.list_by_risk("high")) if registry else 0

    kind = classify_task_kind_heuristic(
        message_count=message_count,
        tools_count=tools_count,
        message_text=text,
        agent_config=cfg,
    )

    return {
        "route": {
            "deep_task": kind != TaskKind.SIMPLE_QA,
            "task_kind": kind.value,
            "rule_version": "stage-4-classifier",
            "classifier": "heuristic",
            "confidence": 1.0,
            "candidates": [kind.value],
            "reason": f"task_kind={kind.value}",
        }
    }


def should_take_deep_branch(state: SessionState) -> str:
    """条件路由函数：route 节点后的边选择。"""
    route = state.get("route") or {}
    return "deep" if route.get("deep_task") else "simple"


# ---------------------------------------------------------------------------
# 10 agent / 11 governance / 12 execute（Agent Loop 内循环）
# ---------------------------------------------------------------------------


def agent(state: SessionState) -> dict[str, Any]:
    """10 agent: §13.2 节点 10。Stage 1 passthrough。"""
    return {}


def governance(state: SessionState) -> dict[str, Any]:
    """11 governance: §13.2 节点 11。

    Stage 6a PR C: 接入 PolicyGuard + ApprovalStore + AuditLogger。

    行为：
    - 遍历 state.tool_calls 中 pending 的 tool_call
    - 调 PolicyGuard.decide() 拿 ApprovalDecision
    - approve_required → 写 state.pending_approval + ApprovalStore.save()
      + AuditLogger.log(AUDIT 不留, 等 resume_turn 时记 approve/deny)
    - deny → 写 state.errors (ErrorCode.APPROVAL_EXPIRED 等) + 记 audit
    - allow → 记 audit (immediately)
    """
    policy = get_default_policy()
    registry = get_default_tool_registry()
    audit = get_default_audit()
    store = get_default_approval_store()
    if policy is None or registry is None:
        return {}  # Stage 1 兼容: 未注入 policy/registry → passthrough

    from ..ports import ActorContext
    actor = ActorContext(
        actor_id="u-1",  # Stage 5 注入
        tenant_id=str(state.get("tenant_id", "")),
        workspace_id=str(state.get("workspace_id", "")),
        roles=(),
    )

    tool_calls = list(state.get("tool_calls") or [])
    pending = list(state.get("pending_approval") or [])
    new_errors = []
    now = time.time()

    for tc in tool_calls:
        if tc.get("status") not in (None, "pending", "approved"):
            continue
        tool_name = tc.get("tool_name", "")
        try:
            meta, _ = registry.get(tool_name)
        except KeyError:
            continue

        decision, approval_id = _call_policy(policy, actor=actor,
            tool_call_id=str(tc.get("tool_call_id", "")),
            tool_meta=meta,
            arguments=tc.get("arguments", {}))

        if decision == "approve_required":
            approval_id = approval_id or f"apr-{tc.get('tool_call_id', '')}"
            arguments = tc.get("arguments", {})
            request_hash = _request_hash(arguments)
            # §5.7 TTL: 写入 ApprovalStore
            if store is not None:
                from ..governance.approval import ApprovalRecord
                rec = ApprovalRecord(
                    approval_id=approval_id,
                    session_id=str(state.get("session_id", "")),
                    turn_id=str(state.get("turn_id", "")),
                    tool_call_id=str(tc.get("tool_call_id", "")),
                    tool_name=tool_name,
                    request_hash=request_hash,
                    arguments=arguments,
                    policy_id=meta.policy_id,
                    requester=actor.actor_id,
                    created_at=now,
                    expires_at=now + DEFAULT_APPROVAL_TTL_SECONDS,
                )
                store.save(rec)
            pending.append({
                "approval_id": approval_id,
                "tool_call_id": str(tc.get("tool_call_id", "")),
                "tool_name": tool_name,
                "arguments_hash": request_hash,
                "policy_id": meta.policy_id or "",
                "requester": actor.actor_id,
                "requested_at": "",
                "expires_at": "",
            })
        elif decision == "deny":
            new_errors.append({
                "node": "governance",
                "error_code": "APPROVAL_EXPIRED",
                "message": f"tool {tool_name} denied by policy",
                "trace_id": state.get("trace_id"),
                "retriable": False,
                "occurred_at": "",
            })
            if audit is not None:
                audit.log(AuditEvent(
                    kind=AuditKind.DENY,
                    actor_id=actor.actor_id,
                    session_id=str(state.get("session_id", "")),
                    turn_id=str(state.get("turn_id", "")),
                    tool_call_id=str(tc.get("tool_call_id", "")),
                    tool_name=tool_name,
                    policy_id=meta.policy_id,
                    request_hash=_request_hash(tc.get("arguments", {})),
                    trace_id=state.get("trace_id"),
                    reason="policy deny",
                ))
        elif decision == "allow" and audit is not None:
            audit.log(AuditEvent(
                kind=AuditKind.ALLOW,
                actor_id=actor.actor_id,
                session_id=str(state.get("session_id", "")),
                turn_id=str(state.get("turn_id", "")),
                tool_call_id=str(tc.get("tool_call_id", "")),
                tool_name=tool_name,
                policy_id=meta.policy_id,
                request_hash=_request_hash(tc.get("arguments", {})),
                trace_id=state.get("trace_id"),
            ))

    out: dict[str, Any] = {}
    if pending:
        out["pending_approval"] = pending[-1]  # 取最后一个 pending 写 state
    if new_errors:
        out["errors"] = list(state.get("errors") or []) + new_errors
    return out


import time  # noqa: E402  # 延迟到模块末尾使用


def _call_policy(policy: Any, *, actor: Any, tool_call_id: str, tool_meta: Any, arguments: dict[str, Any]) -> tuple[Any, str | None]:
    """调 PolicyGuard.decide 兼容 sync/async。"""
    import asyncio
    decision_coro = policy.decide(
        actor=actor, tool_call_id=tool_call_id,
        tool_meta=tool_meta, arguments=arguments,
    )
    if asyncio.iscoroutine(decision_coro):
        from ..memory import run_async_from_sync
        result = run_async_from_sync(decision_coro)
    else:
        result = decision_coro
    return result


def execute(state: SessionState) -> dict[str, Any]:
    """12 execute: §13.2 节点 12。

    Stage 4 PR C: 接入 ToolExecutor (with timeout/retry/idempotency)。

    行为：
    - 遍历 pending tool_calls (status=pending 且 governance.allow)
    - 调 ToolExecutor.execute() 跑工具
    - 写 state.tool_results
    - is_error=true 时写 state.errors (ErrorCode 映射)
    """
    executor = get_default_executor()
    registry = get_default_tool_registry()
    if executor is None or registry is None:
        return {}

    import asyncio
    from ..memory import run_async_from_sync
    tool_calls = list(state.get("tool_calls") or [])
    tool_results = list(state.get("tool_results") or [])
    new_errors = []

    for tc in tool_calls:
        if tc.get("status") != "pending":
            continue
        tool_name = tc.get("tool_name", "")
        tool_call_id = str(tc.get("tool_call_id", ""))
        try:
            meta, tool = registry.get(tool_name)
        except KeyError:
            continue

        try:
            result = run_async_from_sync(executor.execute(
                tool_call_id=tool_call_id,
                tool=tool,
                arguments=tc.get("arguments", {}),
                meta=meta,
                turn_id=str(state.get("turn_id", "")),
                idempotency_key=str(tc.get("idempotency_key", tool_call_id)),
            ))
        except Exception as exc:  # noqa: BLE001
            new_errors.append({
                "node": "execute",
                "error_code": "TOOL_TIMEOUT",
                "message": str(exc),
                "trace_id": state.get("trace_id"),
                "retriable": True,
                "occurred_at": "",
            })
            continue

        tool_results.append({
            "tool_call_id": tool_call_id,
            "content": result.get("result"),
            "is_error": result.get("is_error", False),
            "raw_size_bytes": 0,
            "pointer": None,
        })
        if result.get("is_error"):
            new_errors.append({
                "node": "execute",
                "error_code": result.get("error_code", "INTERNAL_ERROR"),
                "message": result.get("error_message", ""),
                "trace_id": state.get("trace_id"),
                "retriable": True,
                "occurred_at": "",
            })

    out: dict[str, Any] = {"tool_results": tool_results}
    if new_errors:
        out["errors"] = list(state.get("errors") or []) + new_errors
    return out


# ---------------------------------------------------------------------------
# 13 / 14 Deep Agents 条件分支
# ---------------------------------------------------------------------------


def deep_agent_plan(state: SessionState) -> dict[str, Any]:
    """13 deep_agent_plan: §13.2 节点 13。

    Stage 6b PR B: 接入 DeepAgentFactory (§5.5)。

    行为：
    - 调 factory.create() 拿到 DeepAgent 实例
    - emit todos via emit_plan (Stage 6b 退出条件: todos 推到 SSE)
    - budget 超限 → state.errors DEEP_AGENT_BUDGET_EXCEEDED
    - 其他异常 → state.errors DEEP_AGENT_FAILED
    """
    factory = get_default_deep_agent_factory()
    if factory is None:
        return {}  # Stage 1 兼容: 未注入 factory → passthrough

    import asyncio
    cfg = DeepAgentConfig(
        agent_id=str(state.get("agent_id", "")),
        deep_research=True,
        max_steps=20,
        max_cost_usd=1.0,
        system_prompt=str(state.get("route", {}).get("reason", "")),
    )
    try:
        agent = asyncio.run(factory.create(cfg))
    except DeepAgentBudgetExceeded as exc:
        return {
            "errors": list(state.get("errors") or []) + [{
                "node": "deep_agent_plan",
                "error_code": DEEP_AGENT_BUDGET_EXCEEDED_ERROR_CODE,
                "message": exc.message,
                "trace_id": state.get("trace_id"),
                "retriable": False,
                "occurred_at": "",
            }]
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "errors": list(state.get("errors") or []) + [{
                "node": "deep_agent_plan",
                "error_code": DEEP_AGENT_FAILED_ERROR_CODE,
                "message": str(exc),
                "trace_id": state.get("trace_id"),
                "retriable": False,
                "occurred_at": "",
            }]
        }

    # emit todos
    if hasattr(agent, "emit_plan"):
        plan = [
            {"id": f"todo-{i}", "status": "pending",
             "content": f"step {i+1}: investigate {q}",
             "assigned_subagent": "research-1"}
            for i, q in enumerate(_extract_questions(state))
        ]
        agent.emit_plan(plan)

    return {
        "todos": getattr(agent, "todos", []),
    }


def subagent(state: SessionState) -> dict[str, Any]:
    """14 subagent: §13.2 节点 14。

    Stage 6b PR B: 摘要 sub-agent 执行结果回主 agent。

    行为：
    - 调 factory.create() 拿到 DeepAgent (sub-agent 委派)
    - 模拟 sub-agent 跑 1 step + 累加 cost
    - 失败时把 sub-agent 错误码写进 state.errors
    - 成功时把 sub-agent 输出合并到 state.context_manifest
    - todos 全部 mark done
    """
    factory = get_default_deep_agent_factory()
    if factory is None:
        return {}

    import asyncio
    cfg = DeepAgentConfig(
        agent_id=f"{state.get('agent_id', '')}-sub",
        deep_research=True,
        max_steps=10,
        max_cost_usd=0.5,
    )
    try:
        agent = asyncio.run(factory.create(cfg))
        if hasattr(agent, "step"):
            agent.step(cost=0.05)
    except DeepAgentBudgetExceeded as exc:
        return {
            "errors": list(state.get("errors") or []) + [{
                "node": "subagent",
                "error_code": DEEP_AGENT_BUDGET_EXCEEDED_ERROR_CODE,
                "message": exc.message,
                "trace_id": state.get("trace_id"),
                "retriable": False,
                "occurred_at": "",
            }],
            "todos": _mark_todos_done(state.get("todos") or []),
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "errors": list(state.get("errors") or []) + [{
                "node": "subagent",
                "error_code": DEEP_AGENT_FAILED_ERROR_CODE,
                "message": str(exc),
                "trace_id": state.get("trace_id"),
                "retriable": True,
                "occurred_at": "",
            }],
        }

    return {
        "todos": _mark_todos_done(state.get("todos") or []),
        "context_manifest": {
            **(state.get("context_manifest") or {}),
            "subagent": {
                "agent": agent.name,
                "steps": agent.steps,
                "cost_usd": agent.cost,
            },
        },
    }


def _extract_questions(state: SessionState) -> list[str]:
    """从 messages 末尾提取 N 个问题作为 plan 的子任务。"""
    msgs = state.get("messages") or []
    if not msgs:
        return ["未知子任务"]
    last = msgs[-1]
    if hasattr(last, "content"):
        text = str(last.content)  # type: ignore[union-attr]
    elif isinstance(last, dict):
        text = str(last.get("content", ""))
    else:
        text = str(last)
    return [text[:30] + "...", "文献调研", "总结输出"]


def _mark_todos_done(todos: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """§5.5: sub-agent 完成后 todos 标记为 done。"""
    return [{**t, "status": "done"} for t in todos]


def agent(state: SessionState) -> dict[str, Any]:
    """10 agent: §13.2 节点 10。Stage 1 passthrough。"""
    return {}
# ---------------------------------------------------------------------------


def remember(state: SessionState) -> dict[str, Any]:
    """15 remember: §13.2 节点 15。

    Stage 3 PR C：从 final answer + 显式事实 + provenance 提取 L2 长期事实，
    写入 LayeredMemory.write_l2。

    行为：

    - 提取 L2 事实：从 state.context_manifest 的 memory hits 中提取高置信度 hit
    - 去重：write_l2 同 content_hash 幂等（§5.4）
    - 提升：低置信度只作为候选，不进入长期事实（§11 风险）
    - 失败不回滚答案，进入 outbox 重试（§5.4）
    """
    memory = get_default_memory()
    if memory is None:
        return {}

    tenant_id = str(state.get("tenant_id", ""))
    workspace_id = str(state.get("workspace_id", ""))
    user_id = ""  # Stage 5 注入

    # 从 L2 hits 中提取事实（高置信度门槛：§11 风险决议）
    min_confidence = 0.7
    memory_hits = state.get("memory_hits") or []
    candidates: list[dict[str, Any]] = []

    for hit in memory_hits:
        if hit.get("layer") != "l2":
            continue
        confidence = float(hit.get("metadata", {}).get("confidence", 1.0))
        if confidence < min_confidence:
            continue  # 提升门：低置信度不进长期事实
        content = str(hit.get("content", ""))
        if not content:
            continue
        candidates.append({
            "fact_id": hit.get("source_id", f"unknown-{len(candidates)}"),
            "tenant_id": tenant_id,
            "workspace_id": workspace_id,
            "user_id": user_id or "*",
            "content": content,
            "confidence": confidence,
            "source_turn_id": state.get("turn_id"),
            "content_hash": _content_hash(content),
            "policy_version": "v1",
        })

    if not candidates:
        return {}

    # 写入（write_l2 自带 content_hash 幂等去重）
    for cand in candidates:
        try:
            memory.write_l2(cand)
        except Exception as exc:  # noqa: BLE001
            # §5.4 记忆写失败不回滚答案, 进入 outbox 重试
            logger.warning("remember.write_l2 failed: %s", exc)

    return {}


def _content_hash(content: str) -> str:
    """§5.4 content_hash 幂等: sha256 截前 16 字符。"""
    import hashlib
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]


def persist_result(state: SessionState) -> dict[str, Any]:
    """16 persist_result: §13.2 节点 16。Stage 1 passthrough。"""
    return {}


def emit_result(state: SessionState) -> dict[str, Any]:
    """17 emit_result: §13.2 节点 17。Stage 1 passthrough。"""
    return {}


def compact_tool_result(state: SessionState) -> dict[str, Any]:
    """18 compact_tool_result: §13.2 节点 18。Stage 1 passthrough。"""
    return {}


def release_turn_lock(state: SessionState) -> dict[str, Any]:
    """19 release_turn_lock: §13.2 节点 19。

    Stage 2 PR C：释放 advisory lock（§4.2 / §4.3）。

    行为：

    - 从 state.pending_approval 读出锁 token
    - 调用 LockManager.release()，失败仅记日志（§13.2 节点 19 失败处理）
    - 不影响已成功的 turn 状态

    Stage 1 行为：未注入 LockManager 时保持 passthrough（向后兼容）。
    """
    manager = get_default_lock_manager()
    if manager is None:
        return {}

    pa = state.get("pending_approval") or {}
    if not pa:
        return {}

    session_id = str(state.get("session_id", ""))
    turn_id = str(state.get("turn_id", ""))
    holder_id = str(pa.get("approval_id", ""))

    token = LockToken(
        session_id=session_id,
        turn_id=turn_id,
        holder_id=holder_id,
    )
    try:
        manager.release(token)
    except Exception as exc:  # noqa: BLE001
        # §13.2 节点 19: 释放失败仅记日志，不影响已成功的 turn 状态
        logger.warning(
            "release_turn_lock failed: session_id=%s turn_id=%s error=%s",
            session_id,
            turn_id,
            exc,
        )

    # 清空 pending_approval
    return {"pending_approval": None}


# ---------------------------------------------------------------------------
# 收敛函数：Agent Loop 内循环何时退出
# ---------------------------------------------------------------------------


def loop_should_continue(state: SessionState) -> str:
    """Agent Loop 收敛函数：始终立即结束（Stage 1 不进入实际循环）。"""
    return "exit"


__all__ = [
    "acquire_turn_lock",
    "agent",
    "assemble_context",
    "compact_if_needed",
    "compact_tool_result",
    "deep_agent_plan",
    "emit_result",
    "execute",
    "governance",
    "load_agent_context",
    "load_checkpoint",
    "loop_should_continue",
    "normalize_input",
    "persist_result",
    "recall_memory_and_knowledge",
    "release_turn_lock",
    "remember",
    "route",
    "should_take_deep_branch",
    "subagent",
    "write_turn_record",
]