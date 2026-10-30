"""审批挂起的**落库形状**与**校验清单**（Session 方案 §8）。

⚠️ **为什么必须落库**：审批挂起时，工具已经「卡住」了 —— 恢复它需要知道
「挂起的是哪个工具、参数是什么、属于哪一轮」✓。这些信息只在**进程内存**里
是不够的（进程重启 = 审批永久卡死 ✗✗）。

落点：**``session_turns.pending_approval``**（JSONB，决策 #6 ✓）—— 不新建
``session_approvals`` 表 ✓。

**恢复时的校验清单**（§8，任一不过 → **不执行工具**，返回明确错误码 ✓）：

| # | 校验 | 错误码 | 本层负责 |
|---|---|---|---|
| 1 | 审批存在且 ``status='approved'`` | ``APPROVAL_NOT_MATCH`` | ✅ 查 governance 的审批记录 ✓ |
| 2 | 审批未过期 | ``APPROVAL_EXPIRED`` | ✅ 查 ``expires_at`` ✓ |
| 3 | 审批绑定的会话 / 轮次与当前一致 | ``APPROVAL_NOT_MATCH`` | ✅ 用本模块落下的 ``session_id`` / ``turn_id`` ✓ |
| 4 | ``approver_id != requester_id`` | ``APPROVER_MUST_DIFFER`` | ✅ governance 侧 ✓ |
| 5 | 审批记录的**参数摘要**与挂起时一致 | ``TOOL_ARGUMENT_INVALID`` | ✅ 用本模块的 ``arguments_digest`` ✓ |

⚠️ **第 5 项的关键**：比对的是「**审批记录里的参数**」与「挂起时落库的摘要」
—— 而不是「恢复时前端传回来的参数」（那个能被改 ✗）。审批记录是治理域的
**权威** ✓。

**这一层是契约层** —— 不引框架、不引模块 ✓。
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID


def arguments_digest(arguments: Mapping[str, Any] | None) -> str:
    """工具参数的**规范化摘要** ✓。

    ⚠️ **必须规范化**：同样的参数，键序不同就应该是同一个摘要 ✓ ——
    否则「参数没变」也会被误判成「被改了」✗。规范化 = 键排序 + 无空格
    的 JSON ✓（值里如果还有 dict/list，也会被递归排序 ✓）。
    """
    canonical = json.dumps(
        arguments or {},
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class PendingApproval:
    """审批挂起时落库的形状（``session_turns.pending_approval`` ✓）。"""

    approval_id: UUID
    tool_name: str
    arguments_digest: str
    session_id: UUID
    turn_id: UUID
    created_at: datetime

    def to_json(self) -> dict[str, Any]:
        """落库的 JSON 形状 ✓（时间用 ISO 字符串 ✓）。"""
        return {
            "approval_id": str(self.approval_id),
            "tool_name": self.tool_name,
            "arguments_digest": self.arguments_digest,
            "session_id": str(self.session_id),
            "turn_id": str(self.turn_id),
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_json(cls, raw: Mapping[str, Any] | None) -> PendingApproval | None:
        """从落库的 JSON 读回来 —— **读不懂就返回 ``None``** ✓（不猜）。"""
        if not raw:
            return None
        try:
            created_at = datetime.fromisoformat(str(raw["created_at"]))
        except (KeyError, TypeError, ValueError):
            return None
        try:
            return cls(
                approval_id=UUID(str(raw["approval_id"])),
                tool_name=str(raw["tool_name"]),
                arguments_digest=str(raw["arguments_digest"]),
                session_id=UUID(str(raw["session_id"])),
                turn_id=UUID(str(raw["turn_id"])),
                created_at=created_at
                if created_at.tzinfo
                else created_at.replace(tzinfo=UTC),
            )
        except (KeyError, TypeError, ValueError):
            return None


__all__ = ["PendingApproval", "arguments_digest"]
