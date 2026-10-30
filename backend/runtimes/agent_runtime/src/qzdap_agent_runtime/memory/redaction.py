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


# ---------------------------------------------------------------------------
# 规则闸门（纯规则 ✓ —— A3 策略层无 IO ✓）
# ---------------------------------------------------------------------------

#: 敏感信息类型 → 正则 ✓（§4.3 ✓）。
#:
#: ⚠️ **宁可误伤** ✓ —— 命中就**拒绝写入** ✓（误伤只是少记一条 ✗；
#: 漏掉就是一条敏感信息进了库 ✗✗ —— 后者不可逆 ✓）。
SENSITIVE_PATTERNS: dict[str, str] = {
    # ⚠️ **用前后瞻而不是 `\b`** ✓ —— CJK 字符在 Unicode 正则里**也是词字符**
    # ✓ → 「我的手机号是138…」里 `是` 与 `1` 之间**没有边界** ✗✗ → `\b` 会漏。
    "id_card": r"(?<!\d)\d{17}[\dXx](?!\d)",
    "phone": r"(?<!\d)1[3-9]\d{9}(?!\d)",
    "bank_card": r"(?<!\d)\d{16,19}(?!\d)",
    "password": r"(?i)(密码|password|passwd|pwd)\s*(是|为|[:：=])\s*\S+",
    "secret": r"(?i)(api[_-]?key|secret|token|密钥)\s*[:：=]\s*\S+",
}


class RuleRedactor:
    """规则闸门 ✓ —— 命中敏感信息 → **整条拒绝** ✓（§4.3 ✓）。

    ⚠️ **不是「打码后继续写」** ✗✗ —— 半条敏感信息进库 = 泄漏了一半 ✗✗。
    """

    def redact(self, content: str) -> RedactionResult:
        import re

        text = content or ""
        kinds: list[str] = []
        for kind, pattern in SENSITIVE_PATTERNS.items():
            if re.search(pattern, text):
                kinds.append(kind)
        if not kinds:
            return RedactionResult(blocked=False)
        return RedactionResult(
            blocked=True,
            kinds=tuple(kinds),
            reason="敏感信息不允许写入记忆",
        )


__all__ = ["SENSITIVE_PATTERNS", "RedactionResult", "Redactor", "RuleRedactor"]
