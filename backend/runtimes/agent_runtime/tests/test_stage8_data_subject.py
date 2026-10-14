"""Tests for Stage 8: DataSubjectService + UserDataExport + graph_state deprecation."""

from __future__ import annotations

import pytest

from qzdap_agent_runtime.governance import (
    ALL_SCOPES,
    CheckpointStorePort,
    DataSubjectService,
    DeletionAuditEntry,
    DeletionScope,
    InMemoryDataSubjectService,
    InMemoryUserDataExportService,
    LongTermStorePort,
    MessagesPort,
    TracePort,
    UserDataExport,
    UserDataExportService,
)


# ---------------------------------------------------------------------------
# Protocol duck-typing
# ---------------------------------------------------------------------------


def test_data_subject_service_satisfies_protocol() -> None:
    assert isinstance(InMemoryDataSubjectService(), DataSubjectService)


def test_user_data_export_satisfies_protocol() -> None:
    assert isinstance(InMemoryUserDataExportService(), UserDataExportService)


def test_all_scopes_contains_4_stores() -> None:
    """§8 Stage 8 退出条件: 4 处存储全部覆盖。"""
    assert set(ALL_SCOPES) == {
        DeletionScope.CHECKPOINTS,
        DeletionScope.STORE,
        DeletionScope.MESSAGES,
        DeletionScope.TRACE,
    }


# ---------------------------------------------------------------------------
# In-memory mock stores
# ---------------------------------------------------------------------------


class _MockCheckpointStore:
    def __init__(self) -> None:
        self.threads: dict[tuple[str, str], list[str]] = {}
        self.deleted: list[str] = []

    def add(self, tenant_id: str, user_id: str, thread_id: str) -> None:
        self.threads.setdefault((tenant_id, user_id), []).append(thread_id)

    def list_threads(self, tenant_id: str, user_id: str) -> list[str]:
        return list(self.threads.get((tenant_id, user_id), []))

    def delete_thread(self, thread_id: str) -> int:
        self.deleted.append(thread_id)
        for k, v in list(self.threads.items()):
            if thread_id in v:
                v.remove(thread_id)
        return 1


class _MockLongTermStore:
    def __init__(self) -> None:
        self.deleted_count = 0

    def delete_user_facts(self, tenant_id: str, user_id: str) -> int:
        self.deleted_count += 1
        return 1

    def list_user_facts(self, tenant_id: str, user_id: str) -> list[dict]:
        return [{"fact_id": "f-1", "tenant_id": tenant_id, "user_id": user_id}]


class _MockMessagesStore:
    def __init__(self) -> None:
        self.deleted_count = 0

    def delete_user_messages(self, tenant_id: str, user_id: str) -> int:
        self.deleted_count += 1
        return 5

    def list_user_messages(self, tenant_id: str, user_id: str) -> list[dict]:
        return [
            {"turn_id": "t-1", "role": "user", "content": "msg 1", "tenant_id": tenant_id, "user_id": user_id},
            {"turn_id": "t-2", "role": "assistant", "content": "reply", "tenant_id": tenant_id, "user_id": user_id},
        ]


class _MockTraceStore:
    def __init__(self) -> None:
        self.deleted_count = 0

    def delete_user_traces(self, tenant_id: str, user_id: str) -> int:
        self.deleted_count += 1
        return 3

    def list_user_references(self, tenant_id: str, user_id: str) -> list[dict]:
        return [{"trace_id": "tr-1", "tenant_id": tenant_id, "user_id": user_id}]


# ---------------------------------------------------------------------------
# InMemoryDataSubjectService
# ---------------------------------------------------------------------------


class TestDataSubjectService:
    async def test_delete_all_scopes(self) -> None:
        """§8 Stage 8: 4 处存储一键清理。"""
        cp = _MockCheckpointStore()
        cp.add("t-1", "u-1", "thread-1")
        cp.add("t-1", "u-1", "thread-2")
        lt = _MockLongTermStore()
        msg = _MockMessagesStore()
        tr = _MockTraceStore()
        svc = InMemoryDataSubjectService(
            checkpoint_store=cp, long_term_store=lt,
            messages=msg, trace=tr,
        )
        entry = await svc.delete_user_data("u-1", "t-1")
        assert entry.status == "completed"
        assert entry.counts["checkpoints"] == 2
        assert entry.counts["store"] == 1
        assert entry.counts["messages"] == 5
        assert entry.counts["trace"] == 3
        assert entry.completed_at is not None

    async def test_delete_specific_scopes_only(self) -> None:
        """§8 Stage 8: 可选只清理部分 scope。"""
        cp = _MockCheckpointStore()
        cp.add("t-1", "u-1", "thread-1")
        lt = _MockLongTermStore()
        msg = _MockMessagesStore()
        tr = _MockTraceStore()
        svc = InMemoryDataSubjectService(
            checkpoint_store=cp, long_term_store=lt,
            messages=msg, trace=tr,
        )
        entry = await svc.delete_user_data(
            "u-1", "t-1",
            scopes=(DeletionScope.MESSAGES,),
        )
        assert entry.status == "completed"
        assert "messages" in entry.counts
        assert "checkpoints" not in entry.counts
        assert "store" not in entry.counts
        assert "trace" not in entry.counts
        # 其他 3 个 store 未调用
        assert cp.deleted == []
        assert lt.deleted_count == 0
        assert tr.deleted_count == 0
        # messages 调了
        assert msg.deleted_count == 1

    async def test_partial_failure_marks_status(self) -> None:
        """§8 Stage 8: 即使某 scope 失败, 仍继续处理其他 scope (GDPR 友好)。"""

        class _BoomStore:
            def delete_user_messages(self, tenant_id, user_id):
                raise RuntimeError("db down")

        cp = _MockCheckpointStore()
        lt = _MockLongTermStore()
        msg = _BoomStore()
        tr = _MockTraceStore()
        svc = InMemoryDataSubjectService(
            checkpoint_store=cp, long_term_store=lt,
            messages=msg,  # type: ignore[arg-type]
            trace=tr,
        )
        entry = await svc.delete_user_data("u-1", "t-1")
        # messages 失败, 但其他 scope 仍处理
        assert entry.status == "partial"
        assert entry.counts["messages"] == -1  # 失败标记
        assert entry.counts["checkpoints"] == 0
        assert entry.counts["store"] == 1
        assert entry.counts["trace"] == 3
        assert "messages" in entry.error_message

    async def test_no_stores_returns_completed(self) -> None:
        """无 store 时也返回 completed (空操作)。"""
        svc = InMemoryDataSubjectService()
        entry = await svc.delete_user_data("u-1", "t-1")
        assert entry.status == "completed"
        assert entry.counts == {}

    async def test_audit_log_records_all_requests(self) -> None:
        """§8 Stage 8: 每次删除请求都写 audit log。"""
        svc = InMemoryDataSubjectService()
        await svc.delete_user_data("u-1", "t-1")
        await svc.delete_user_data("u-2", "t-1")
        assert len(svc.audit_log) == 2

    async def test_audit_entry_has_request_id_and_timestamps(self) -> None:
        svc = InMemoryDataSubjectService()
        entry = await svc.delete_user_data("u-1", "t-1")
        assert entry.request_id  # 非空
        assert entry.requested_at > 0
        assert entry.completed_at is not None
        assert entry.completed_at >= entry.requested_at


# ---------------------------------------------------------------------------
# InMemoryUserDataExportService (§8 GDPR 数据可携权)
# ---------------------------------------------------------------------------


class TestUserDataExport:
    async def test_export_with_all_stores(self) -> None:
        """§8 Stage 8: 导出 messages / memory / knowledge。"""
        cp = _MockCheckpointStore()
        lt = _MockLongTermStore()
        msg = _MockMessagesStore()
        # knowledge 是 dynamic, 不强类型
        class _KnStore:
            def list_user_references(self, tenant_id, user_id):
                return [{"trace_id": "tr-1", "user_id": user_id}]
        kn = _KnStore()
        svc = InMemoryUserDataExportService(
            checkpoint_store=cp, long_term_store=lt,
            messages=msg, knowledge=kn,
        )
        export = await svc.export_user_data("u-1", "t-1")
        assert isinstance(export, UserDataExport)
        assert export.user_id == "u-1"
        assert export.tenant_id == "t-1"
        assert len(export.messages) == 2
        assert len(export.memory_hits) == 1
        assert len(export.knowledge_references) == 1
        assert export.exported_at > 0

    async def test_export_no_stores_returns_empty(self) -> None:
        svc = InMemoryUserDataExportService()
        export = await svc.export_user_data("u-1", "t-1")
        assert export.messages == []
        assert export.memory_hits == []
        assert export.knowledge_references == []

    async def test_export_partial_stores(self) -> None:
        """只注入 messages, 其他 store 不存在 → 仍能 export (部分数据)。"""
        msg = _MockMessagesStore()
        svc = InMemoryUserDataExportService(messages=msg)
        export = await svc.export_user_data("u-1", "t-1")
        assert len(export.messages) == 2
        assert export.memory_hits == []
        assert export.knowledge_references == []


# ---------------------------------------------------------------------------
# §8 Stage 8 退出条件: 数据可携 (export 接口)
# ---------------------------------------------------------------------------


class TestStage8ExitCriteria:
    def test_deletion_audit_4_scopes(self) -> None:
        """§8 退出条件: 4 处存储一键清理 + audit 留痕。"""
        cp = _MockCheckpointStore()
        cp.add("t-1", "u-1", "thread-1")
        lt = _MockLongTermStore()
        msg = _MockMessagesStore()
        tr = _MockTraceStore()
        svc = InMemoryDataSubjectService(
            checkpoint_store=cp, long_term_store=lt,
            messages=msg, trace=tr,
        )
        import asyncio
        entry = asyncio.run(svc.delete_user_data("u-1", "t-1"))
        # 4 处都清理
        assert all(s.value in entry.counts for s in ALL_SCOPES)
        # audit 留痕
        assert entry.user_id == "u-1"
        assert entry.tenant_id == "t-1"
        assert entry.completed_at is not None
        # 1 条 audit log
        assert len(svc.audit_log) == 1