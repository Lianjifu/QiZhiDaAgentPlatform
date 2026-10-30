"""``Redactor`` —— **敏感信息闸门** ✓。

依据：Memory 方案 §4.3（闸门 ✓）、§10.1（A3 策略层**与平面 B 共用同一实现** ✓）。

⚠️ **这一层是契约层** —— 纯规则 ✓（无 IO ✓）。

⚠️ **命中 → 拒绝写入并记审计** ✓（§4.3 ✓）—— 不是「打个码继续写」 ✗✗
（半条敏感信息进库 = 泄漏了一半 ✗）。

⚠️ **管理面与运行面共用同一份实现** ✓（§10.1 B3 ✓）—— 管理端人工编辑也
要走闸门 ✓（X16 的后半段 ✓ → M-42 ✓）。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class RedactionResult:
    """闸门的判定 ✓。

    ⚠️ ``blocked=True`` 表示**整条拒绝** ✓（不是「脱敏后继续写」 ✗）。
    """

    #: 是否拒绝写入 ✓。
    blocked: bool
    #: 命中的敏感类型 ✓（`id_card` / `phone` / `bank_card` / `password` /
    #: `secret` / `address` ✓ —— §4.3 ✓）。
    kinds: tuple[str, ...] = ()
    #: 判定说明 ✓（审计用 ✓）。
    reason: str = ""


@runtime_checkable
class Redactor(Protocol):
    """敏感信息闸门 ✓（无 IO ✓ —— 纯规则 ✓）。"""

    def redact(self, content: str) -> RedactionResult:
        """判定一段内容能不能进记忆库 ✓。"""
        ...


__all__ = ["RedactionResult", "Redactor"]
