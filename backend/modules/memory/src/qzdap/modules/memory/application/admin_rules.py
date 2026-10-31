"""平面 B · **管理侧的人工编辑规则** ✓（B3 ✓ —— Memory 方案 §10.1 ✓）。

⚠️ **为什么要有这个模块** ✓ —— 平面 B 的**人工编辑**路径要有一套**自己的**
规则 ✓（去重 ✓ / 版本化 ✓）—— 但**敏感闸门必须与平面 A 共用同一实现**
✓（方案规则 4 ✓ —— 防两套脱敏规则漂移 ✗✗）→ 这里**直接用**
``qzdap_agent_runtime.memory.redaction.RuleRedactor`` ✓（**不另写一套** ✓）。

⚠️ **它只管规则** ✓ —— 无 IO ✓（查重要用的「现有条目」由调用方给进来 ✓
—— 端口窄 ✓ —— 模块侧不引数据库 ✓）。

依据：Memory 方案 §2.2 规则 6（平面分离 ✓）、§10.1（B3 ✓）、§7.4（管理端
编辑也走闸门 ✓ —— M-41 ✓）。
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from qzdap_agent_runtime.memory.redaction import RedactionResult, Redactor, RuleRedactor


@dataclass(frozen=True, slots=True)
class AdminEditVerdict:
    """人工编辑的**判定** ✓（拒绝就整条拒绝 ✓ —— 不是「打个码继续写」 ✗✗）。"""

    #: 是否拒绝 ✓。
    blocked: bool = False
    #: 命中的敏感类型 ✓（审计用 ✓）。
    kinds: tuple[str, ...] = ()
    #: 拒绝的原因码 ✓（``sensitive`` / ``duplicate`` ✓ —— 稳定可断言 ✓）。
    reason: str = ""


class AdminEditRules:
    """平面 B 的人工编辑规则 ✓（B3 ✓）。

    ⚠️ **规则与平面 A 可以不同** ✓（方案允许 ✓）—— 但**敏感闸门共用同一
    实现** ✓（:class:`RuleRedactor` ✓ —— 规则 4 ✓）。
    """

    def __init__(self, *, redactor: Redactor | None = None) -> None:
        # ⚠️ **默认就用平面 A 的那一个** ✓ —— 不传就等于共用 ✓（不另写 ✓）。
        self._redactor = redactor or RuleRedactor()

    @property
    def redactor(self) -> Redactor:
        """**那个共用的闸门** ✓（架构测试断言它是同一实现 ✓）。"""
        return self._redactor

    def check_sensitive(self, content: str) -> AdminEditVerdict:
        """**敏感闸门** ✓（与平面 A 同一套规则 ✓ —— M-41 ✓）。

        ⚠️ **命中就整条拒绝** ✓ —— 管理端**不能**绕过 ✓。
        """
        result: RedactionResult = self._redactor.redact(content)
        if not result.blocked:
            return AdminEditVerdict()
        return AdminEditVerdict(
            blocked=True,
            kinds=tuple(result.kinds),
            reason="sensitive",
        )

    def check_duplicate(
        self,
        content: str,
        *,
        existing: Iterable[tuple[str, str]],
        exclude_id: str | None = None,
    ) -> AdminEditVerdict:
        """**去重** ✓（人工编辑也要防重复 ✓）。

        ⚠️ **按归一化后的文本比** ✓（去空白 + 忽略大小写 ✓）—— 否则
        「同一句话换个空格」就绕过去了 ✗✗。

        :param existing: ``(条目 id, 内容)`` 的序列 ✓（由调用方给 ✓ ——
            这里不查库 ✓)。
        """
        target = _normalise(content)
        if not target:
            return AdminEditVerdict()
        for item_id, value in existing:
            if exclude_id is not None and item_id == exclude_id:
                continue
            if _normalise(value) == target:
                return AdminEditVerdict(blocked=True, reason="duplicate")
        return AdminEditVerdict()

    @staticmethod
    def next_version(current: int | None) -> int:
        """**版本化** ✓（人工编辑一次 = 一个新版本 ✓）。

        ⚠️ **从 1 起** ✓（版本 0 = 「还没编过号」 ✓ —— 旧行没有版本时按 1 处理 ✓）。
        """
        return int(current or 1) + 1


def _normalise(content: str) -> str:
    """**归一化** ✓（去空白 + 忽略大小写 ✓）。"""
    return "".join((content or "").split()).lower()


__all__ = ["AdminEditRules", "AdminEditVerdict"]
