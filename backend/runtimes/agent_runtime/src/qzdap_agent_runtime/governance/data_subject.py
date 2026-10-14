"""Data governance — §8 Stage 8 (GDPR / PIPL 数据主体请求)。

Stage 8 PR A 范围：

- `DataSubjectService` Protocol: 删除用户数据 (4 处存储)
  * langgraph_checkpoints
  * langgraph_store
  * session_messages
  * LangSmith trace
  * 写 audit_log
- `InMemoryDataSubjectService`: 进程内实现
- `UserDataExport` Protocol: 导出用户可携数据
  * messages
  * memory hits
  * knowledge references
- `DeletionAuditEntry`: 删除审计记录 (scope / status / completed_at)

§8 Stage 8 退出条件:
- 删除请求一键清理 4 处存储
- 数据可携 (export 接口)
- audit 留痕
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol, runtime_checkable


# ---------------------------------------------------------------------------
# 4 处存储范围 (§8 / §11 风险)
# ---------------------------------------------------------------------------


class DeletionScope(str, Enum):
    """§8 Stage 8: 4 处存储范围。"""

    CHECKPOINTS = "checkpoints"     # langgraph_checkpoints
    STORE = "store"                 # langgraph_store (L2 记忆)
    MESSAGES = "messages"           # session_messages
    TRACE = "trace"                 # LangSmith trace


ALL_SCOPES: tuple[DeletionScope, ...] = (
    DeletionScope.CHECKPOINTS,
    DeletionScope.STORE,
    DeletionScope.MESSAGES,
    DeletionScope.TRACE,
)


# ---------------------------------------------------------------------------
# 审计记录 (§8)
# ---------------------------------------------------------------------------


@dataclass
class DeletionAuditEntry:
    """§8 Stage 8: 数据删除审计记录。"""

    request_id: str
    user_id: str
    tenant_id: str
    scopes: tuple[DeletionScope, ...]
    status: str  # "pending" | "completed" | "failed"
    requested_at: float
    completed_at: float | None = None
    error_message: str | None = None
    counts: dict[str, int] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# DataSubjectService Protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class DataSubjectService(Protocol):
    """§8 Stage 8: 数据主体删除服务 (GDPR / PIPL)。"""

    async def delete_user_data(
        self,
        user_id: str,
        tenant_id: str,
        scopes: tuple[DeletionScope, ...] = ALL_SCOPES,
    ) -> DeletionAuditEntry: ...


# ---------------------------------------------------------------------------
# InMemoryDataSubjectService
# ---------------------------------------------------------------------------


@runtime_checkable
class CheckpointStorePort(Protocol):
    """§8 Stage 8: 抽象 checkpointer store (langgraph_checkpoints)。"""

    def list_threads(self, tenant_id: str, user_id: str) -> list[str]: ...

    def delete_thread(self, thread_id: str) -> int: ...


@runtime_checkable
class LongTermStorePort(Protocol):
    """§8 Stage 8: 抽象 L2 长期存储 (langgraph_store / memory_l2_embeddings)。"""

    def delete_user_facts(self, tenant_id: str, user_id: str) -> int: ...


@runtime_checkable
class MessagesPort(Protocol):
    """§8 Stage 8: 抽象 session_messages 表。"""

    def delete_user_messages(self, tenant_id: str, user_id: str) -> int: ...


@runtime_checkable
class TracePort(Protocol):
    """§8 Stage 8: 抽象 LangSmith trace 存储。"""

    def delete_user_traces(self, tenant_id: str, user_id: str) -> int: ...


class InMemoryDataSubjectService:
    """§8 Stage 8: 进程内 DataSubjectService (单测 / 本地 dev 用)。"""

    def __init__(
        self,
        *,
        checkpoint_store: CheckpointStorePort | None = None,
        long_term_store: LongTermStorePort | None = None,
        messages: MessagesPort | None = None,
        trace: TracePort | None = None,
    ) -> None:
        self._checkpoints = checkpoint_store
        self._long_term = long_term_store
        self._messages = messages
        self._trace = trace
        self._audit_log: list[DeletionAuditEntry] = []

    @property
    def audit_log(self) -> list[DeletionAuditEntry]:
        return list(self._audit_log)

    async def delete_user_data(
        self,
        user_id: str,
        tenant_id: str,
        scopes: tuple[DeletionScope, ...] = ALL_SCOPES,
    ) -> DeletionAuditEntry:
        """§8 Stage 8: 删除用户数据 (4 处存储) + 写 audit log。

        即使某 scope 失败, 仍继续处理其他 scope, 保证最大数据清除 (GDPR/PIPL 友好)。
        """
        entry = DeletionAuditEntry(
            request_id=str(uuid.uuid4()),
            user_id=user_id,
            tenant_id=tenant_id,
            scopes=tuple(scopes),
            status="pending",
            requested_at=time.time(),
        )
        errors: list[str] = []
        for scope in scopes:
            try:
                count = self._delete_one(scope, user_id, tenant_id)
                if count is not None:
                    entry.counts[scope.value] = count
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{scope.value}: {exc}")
                entry.counts[scope.value] = -1  # 标记失败
        if errors:
            entry.status = "partial" if entry.counts else "failed"
            entry.error_message = "; ".join(errors)
        else:
            entry.status = "completed"
        entry.completed_at = time.time()
        self._audit_log.append(entry)
        return entry

    def _delete_one(self, scope: DeletionScope, user_id: str, tenant_id: str) -> int | None:
        """单 scope 删除; 返回删除条数, None 表示该 scope 无 store。"""
        if scope == DeletionScope.CHECKPOINTS:
            if self._checkpoints is None:
                return None
            threads = self._checkpoints.list_threads(tenant_id, user_id)
            total = 0
            for t in threads:
                total += self._checkpoints.delete_thread(t)
            return total
        if scope == DeletionScope.STORE:
            if self._long_term is None:
                return None
            return self._long_term.delete_user_facts(tenant_id, user_id)
        if scope == DeletionScope.MESSAGES:
            if self._messages is None:
                return None
            return self._messages.delete_user_messages(tenant_id, user_id)
        if scope == DeletionScope.TRACE:
            if self._trace is None:
                return None
            return self._trace.delete_user_traces(tenant_id, user_id)
        return None


# ---------------------------------------------------------------------------
# UserDataExport Protocol (§8 / §11 风险)
# ---------------------------------------------------------------------------


@dataclass
class UserDataExport:
    """§8 Stage 8: 用户可携数据 (GDPR 数据可携权)。"""

    user_id: str
    tenant_id: str
    messages: list[dict[str, Any]] = field(default_factory=list)
    memory_hits: list[dict[str, Any]] = field(default_factory=list)
    knowledge_references: list[dict[str, Any]] = field(default_factory=list)
    exported_at: float = field(default_factory=time.time)


@runtime_checkable
class UserDataExportService(Protocol):
    """§8 Stage 8: 导出用户可携数据。"""

    async def export_user_data(
        self,
        user_id: str,
        tenant_id: str,
    ) -> UserDataExport: ...


class InMemoryUserDataExportService:
    """§8 Stage 8: 进程内导出服务。"""

    def __init__(
        self,
        *,
        checkpoint_store: CheckpointStorePort | None = None,
        long_term_store: LongTermStorePort | None = None,
        messages: MessagesPort | None = None,
        knowledge: Any | None = None,  # KnowledgeStore
    ) -> None:
        self._checkpoints = checkpoint_store
        self._long_term = long_term_store
        self._messages = messages
        self._knowledge = knowledge

    async def export_user_data(
        self,
        user_id: str,
        tenant_id: str,
    ) -> UserDataExport:
        """§8 Stage 8: 导出 messages / memory / knowledge。"""
        export = UserDataExport(user_id=user_id, tenant_id=tenant_id)
        # Messages
        if self._messages is not None and hasattr(self._messages, "list_user_messages"):
            export.messages = self._messages.list_user_messages(tenant_id, user_id)
        # Memory (L2 事实)
        if self._long_term is not None and hasattr(self._long_term, "list_user_facts"):
            export.memory_hits = self._long_term.list_user_facts(tenant_id, user_id)
        # Knowledge (L3 references)
        if self._knowledge is not None and hasattr(self._knowledge, "list_user_references"):
            export.knowledge_references = self._knowledge.list_user_references(
                tenant_id, user_id
            )
        return export


__all__ = [
    "ALL_SCOPES",
    "CheckpointStorePort",
    "DataSubjectService",
    "DeletionAuditEntry",
    "DeletionScope",
    "InMemoryDataSubjectService",
    "InMemoryUserDataExportService",
    "LongTermStorePort",
    "MessagesPort",
    "TracePort",
    "UserDataExport",
    "UserDataExportService",
]