"""identity 侧的 ``UserDirectoryPort`` 实现 —— **用户属性成为可查询的数据**。

依据：``docs/refactor/session-architecture/router-refactor-plan.md`` §1.5。

⚠️ **现状的诚实说明**：identity 的 ``User`` 只有 ``metadata``（JSONB 自由
格式），**部门没有结构化字段**。这里做的是**把既有约定收敛成一个端口**：
``metadata.departments`` / ``metadata.tags`` / ``metadata.roles`` 三个键。

- 读不到 → 返回空属性（**不猜**：Router 的用户标签规则匹配不到就落到兜底）；
- 读到了但不是列表 → 当成单值（兼容早期写入的字符串）。

等 identity 补上结构化的部门字段，只需改这个适配器 —— **Router 侧不用动**
（这正是端口存在的意义）。
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any
from uuid import UUID

from qzdap.modules.identity.application.ports import UserRepository
from qzdap_agent_runtime.router.types import UserAttributes, UserDirectoryPort


def _as_str_tuple(raw: Any) -> tuple[str, ...]:
    """把 ``metadata`` 里的任意形态收敛成字符串元组。"""
    if raw is None:
        return ()
    if isinstance(raw, str):
        raw = (raw,)
    if not isinstance(raw, Iterable):
        return ()
    return tuple(str(item).strip() for item in raw if str(item).strip())


class IdentityUserDirectory(UserDirectoryPort):
    """按 user id 读用户属性。

    ⚠️ **租户边界**：``UserRepository.get`` 本身已做跨租户拦截，这里再核一遍
    ``tenant_id`` —— 端口的调用方（Router）只认「同租户的用户」。
    """

    def __init__(self, users: UserRepository) -> None:
        self._users = users

    async def get_user_attributes(self, *, tenant_id: UUID, user_id: UUID) -> UserAttributes:
        user = await self._users.get(user_id)
        if user is None or user.tenant_id != tenant_id:
            return UserAttributes()
        metadata = user.metadata or {}
        return UserAttributes(
            departments=_as_str_tuple(metadata.get("departments") or metadata.get("department")),
            tags=_as_str_tuple(metadata.get("tags")),
            roles=frozenset(_as_str_tuple(metadata.get("roles"))),
        )


__all__ = ["IdentityUserDirectory"]
