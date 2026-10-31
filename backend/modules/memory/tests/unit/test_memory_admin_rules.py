"""Memory Stage 7：**平面 B 的规则与配置发布** ✓（M-37 / M-38 ✓）。

验收覆盖 ✓：

- **B3 的人工编辑规则** ✓（`admin_rules.py` ✓）：敏感闸门**与平面 A 共用
  同一实现** ✓（规则 4 ✓）+ **去重** ✓ + **版本化** ✓；
- **人工编辑走 B3** ✓（M-38 ✓）—— 管理端**不能**写出重复的记忆 ✓；
- **B2 的「配置发布与生效」** ✓（M-37 ✓）—— 发布写进 agent ✓ → 运行时
  **下一次就读到** ✓（不用重启 ✓）。
"""

from __future__ import annotations

import sys as _sys
from uuid import UUID, uuid4

import pytest

from qzdap.modules.memory.application.admin_rules import AdminEditRules
from qzdap.modules.memory.application.admin_service import MemoryAdminService
from qzdap_agent_runtime.memory.policy import (
    MemoryPolicyConfig,
    MemoryPolicyPublisherPort,
    PolicyBinding,
)
from qzdap_agent_runtime.memory.redaction import RuleRedactor
from qzdap_kernel.errors import ValidationError

print("DEBUG tests module:", _sys.modules.get("tests"), file=_sys.stderr)
print("DEBUG sys.path head:", _sys.path[:6], file=_sys.stderr)


class RecordingPublisher(MemoryPolicyPublisherPort):
    """**记录发布内容**的假发布端 ✓（端口窄 ✓ —— 不碰 agent 目录 ✓）。"""

    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def publish(
        self,
        *,
        tenant_id: UUID,
        workspace_id: UUID,
        label: str,
        config: MemoryPolicyConfig,
    ) -> int:
        self.calls.append(
            {
                "tenant_id": tenant_id,
                "workspace_id": workspace_id,
                "label": label,
                "config": config,
            }
        )
        return 2


def test_the_sensitive_gate_is_the_plane_a_implementation() -> None:
    """**敏感闸门共用同一实现** ✓（规则 4 ✓ —— 防两套规则漂移 ✗✗）。"""
    rules = AdminEditRules()
    assert isinstance(rules.redactor, RuleRedactor)
    # ⚠️ **同一个实现** ✓ —— 不是「长得像」✓。
    assert type(rules.redactor) is RuleRedactor


def test_the_admin_gate_blocks_the_same_content_as_plane_a() -> None:
    """管理端与平面 A **判得一样** ✓（同一套规则 ✓）。"""
    rules = AdminEditRules()
    verdict = rules.check_sensitive("我的密码是 hunter2")
    assert verdict.blocked
    assert verdict.reason == "sensitive"
    assert "password" in verdict.kinds
    assert not rules.check_sensitive("我在上海办公").blocked


def test_the_duplicate_rule_ignores_whitespace_and_case() -> None:
    """**去重** ✓（归一化后比 ✓ —— 「换个空格」绕不过去 ✗✗）。"""
    rules = AdminEditRules()
    existing = [("id-1", "我在 上海 办公")]
    assert rules.check_duplicate("我在上海办公", existing=existing).blocked
    assert not rules.check_duplicate("我在杭州办公", existing=existing).blocked
    # ⚠️ **排除自己** ✓ —— 改一条时它自己的旧值不算重复 ✓。
    assert not rules.check_duplicate("我在上海办公", existing=existing, exclude_id="id-1").blocked


def test_the_version_rule_bumps_by_one() -> None:
    """**版本化** ✓（人工编辑一次 = 一个新版本 ✓）。"""
    assert AdminEditRules.next_version(1) == 2
    assert AdminEditRules.next_version(None) == 2


@pytest.mark.asyncio
async def test_the_admin_edit_refuses_a_duplicate() -> None:
    """**人工编辑不能写出重复** ✓（M-38 ✓）。"""
    # ⚠️ **共享夹具在函数里导入** ✓ —— 测试模块之间的导入**依赖收集顺序**
    # ✗✗（`tests` 这个包名会被先收集到的模块占住 ✓ —— 谁先导入谁说了算 ✓）
    # → 放在模块顶层 = **这个文件排在前面就 import 不到** ✗✗。
    from tests.unit.test_memory_catalog import InMemoryCatalog
    from tests.unit.test_memory_policy_binding import WORKSPACE, _l2

    catalog = InMemoryCatalog()
    first = _l2(session_id=uuid4(), value="我在上海办公")
    second = _l2(session_id=uuid4(), value="另一条")
    catalog.l2[first.id] = first
    catalog.l2[second.id] = second
    admin = MemoryAdminService(catalog)
    with pytest.raises(ValidationError) as excinfo:
        await admin.update_l2(
            second.id,
            workspace_id=WORKSPACE,
            patch={"value": "我在上海办公", "version": 1},
        )
    assert excinfo.value.code == "MEMORY_DUPLICATE_CONTENT"
    # ⚠️ **被拒的内容没有进库** ✓。
    assert catalog.l2[second.id].value == "另一条"


@pytest.mark.asyncio
async def test_the_publish_writes_through_the_port() -> None:
    """**配置发布** ✓（M-37 ✓）—— 走窄端口 ✓（不 import agent 模块 ✓）。"""
    from tests.unit.test_memory_catalog import InMemoryCatalog
    from tests.unit.test_memory_policy_binding import TENANT, WORKSPACE

    catalog = InMemoryCatalog()
    publisher = RecordingPublisher()
    admin = MemoryAdminService(catalog, publisher=publisher)
    result = await admin.publish_policy(
        tenant_id=TENANT,
        workspace_id=WORKSPACE,
        label="长期记忆",
        config=MemoryPolicyConfig(enabled=False, scope="session"),
    )
    assert result["published"] == 2
    assert publisher.calls
    call = publisher.calls[0]
    assert call["label"] == "长期记忆"
    config = call["config"]
    assert isinstance(config, MemoryPolicyConfig)
    assert config.enabled is False


@pytest.mark.asyncio
async def test_the_publish_without_a_publisher_fails_loudly() -> None:
    """**没接线就明确失败** ✓（不假装发布成功 ✗✗）。"""
    from tests.unit.test_memory_catalog import InMemoryCatalog
    from tests.unit.test_memory_policy_binding import TENANT, WORKSPACE

    catalog = InMemoryCatalog()
    admin = MemoryAdminService(catalog)
    with pytest.raises(ValidationError) as excinfo:
        await admin.publish_policy(
            tenant_id=TENANT,
            workspace_id=WORKSPACE,
            label="长期记忆",
            config=MemoryPolicyConfig(),
        )
    assert excinfo.value.code == "MEMORY_POLICY_PUBLISHER_MISSING"


@pytest.mark.asyncio
async def test_the_workspace_scope_is_refused() -> None:
    """**工作区级写不了** ✓（L3 已退役 ✓ —— 决策 #1 ✓）→ 明确拒绝 ✓。"""
    from tests.unit.test_memory_catalog import InMemoryCatalog
    from tests.unit.test_memory_policy_binding import TENANT, WORKSPACE

    catalog = InMemoryCatalog()
    admin = MemoryAdminService(catalog, publisher=RecordingPublisher())
    with pytest.raises(ValidationError) as excinfo:
        await admin.publish_policy(
            tenant_id=TENANT,
            workspace_id=WORKSPACE,
            label="团队知识",
            config=MemoryPolicyConfig(scope="workspace"),
        )
    assert excinfo.value.code == "MEMORY_SCOPE_UNSUPPORTED"


@pytest.mark.asyncio
async def test_the_published_config_is_what_the_runtime_parses() -> None:
    """**发布出去的形状 = 运行时解析的形状** ✓（生效 ✓ —— 不用重启 ✓）。"""
    config = MemoryPolicyConfig(
        enabled=False,
        scope="session",
        retention_days=30,
    )
    raw = config.to_agent_policy(label="长期记忆")
    policy = PolicyBinding(raw=raw).to_policy()
    assert policy.enabled is False
    assert policy.scope.value == "session"
    assert policy.policy_label == "长期记忆"
    assert policy.retention_days == 30
    # ⚠️ **不再有 ``l3EntryIds``** ✓ —— L3 退役 ✓（决策 #1 ✓ —— M-47 ✓）。
    assert "l3EntryIds" not in raw
    # ⚠️ **用户级是默认** ✓（发布没写 scope 时不该变成别的 ✓）。
    assert (
        PolicyBinding(raw=MemoryPolicyConfig().to_agent_policy(label="x")).to_policy().scope.value
        == "user"
    )
