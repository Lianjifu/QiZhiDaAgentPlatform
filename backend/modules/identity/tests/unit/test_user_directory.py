"""``UserDirectoryPort`` 的 identity 侧实现（Router 方案 §1.5）。

**为什么要有它**：「按用户标签路由」需要能按用户的部门 / 角色 / 画像筛
agent，但现状里部门**没有结构化字段** —— `User.metadata` 是自由格式 JSONB。
这个适配器把那份约定收敛成一个**可查询的端口**，等 identity 补上结构化字段
时只需改这里。
"""

from __future__ import annotations

from dataclasses import replace
from uuid import uuid4

from _identity_unit_in_memory import InMemoryUserRepository

from qzdap.modules.identity.adapter.user_directory import IdentityUserDirectory
from qzdap.modules.identity.domain import Tenant, User
from qzdap_agent_runtime.router.types import UserAttributes


def _user_with_metadata(metadata: dict) -> User:
    tenant = Tenant.create(id=uuid4(), slug="acme", display_name="Acme")
    user = User.create(
        id=uuid4(),
        tenant_id=tenant.id,
        email="hi@x.com",
        display_name="Hi",
    )
    return replace(user, metadata=metadata)


async def _directory_with(user: User) -> IdentityUserDirectory:
    users = InMemoryUserRepository()
    await users.add(user)
    return IdentityUserDirectory(users)


async def test_departments_and_tags_are_exposed() -> None:
    user = _user_with_metadata({"departments": ["财务部"], "tags": ["审计"]})
    directory = await _directory_with(user)

    attrs = await directory.get_user_attributes(tenant_id=user.tenant_id, user_id=user.id)

    assert attrs.departments == ("财务部",)
    assert attrs.tags == ("审计",)


async def test_a_single_department_string_is_accepted() -> None:
    """早期写入的是字符串 —— 兼容它，不当成列表炸掉。"""
    user = _user_with_metadata({"department": "财务部"})
    directory = await _directory_with(user)

    attrs = await directory.get_user_attributes(tenant_id=user.tenant_id, user_id=user.id)

    assert attrs.departments == ("财务部",)


async def test_an_unknown_user_yields_empty_attributes() -> None:
    """读不到就**读不到** —— 不猜，Router 的规则会落到兜底。"""
    directory = await _directory_with(_user_with_metadata({}))

    attrs = await directory.get_user_attributes(tenant_id=uuid4(), user_id=uuid4())

    assert attrs == UserAttributes()


async def test_a_cross_tenant_read_is_refused() -> None:
    """端口只认「同租户的用户」。"""
    user = _user_with_metadata({"departments": ["财务部"]})
    directory = await _directory_with(user)

    attrs = await directory.get_user_attributes(tenant_id=uuid4(), user_id=user.id)

    assert attrs == UserAttributes()
