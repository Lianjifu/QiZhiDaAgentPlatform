"""Token 估算（**按语种**）—— Context 层的**唯一**口径 ✓。

依据：Context 方案 §8.1（`tokens.py`）、Stage 0 的验收口径。

⚠️ **为什么不能按字符数一刀切**：旧路径（``adapter/graph/state.py``）用
``len // 4`` 估 token —— 对**中文**会**低估约 4 倍** ✗✗（中文一个字通常
就是 1 个 token ✓）。于是「上下文超没超预算」这条判断在中文场景下**失真**
✗（该压缩的不压缩 ✗）。

⚠️ **口径统一是硬要求**（Context 方案 §9 Stage 0 的验收）：新旧两条路径
的估算差异 **< 10%** ✓ —— 所以**旧路径必须调这一份** ✗✗（两套算法各算各的
= 没统一 ✗）。

口径（§5.3）：

- **CJK** 字符：1 字 ≈ 1 token ✓；
- 其余字符：4 字符 ≈ 1 token ✓；
- 空串：0 ✓（旧路径按 ``max(1, ...)`` 记 1 ✗ —— 空内容不该占预算 ✓）。

⚠️ **这不是绝对真值** ✓ —— 真实 tokenizer 因模型而异 ✓；它只是**预算口径**
✓（新旧一致 ✓ 比「准」更重要 ✓）。
"""

from __future__ import annotations

from typing import Any

#: CJK 统一表意文字的区间（汉字）✓ —— 常见中文、日文汉字都在内 ✓。
_CJK_RANGES = (
    ("一", "鿿"),  # CJK 统一表意文字
    ("㐀", "䶿"),  # 扩展 A
    ("豈", "﫿"),  # 兼容表意文字
)


def _is_cjk(char: str) -> bool:
    return any(low <= char <= high for low, high in _CJK_RANGES)


def estimate_tokens(text: str) -> int:
    """按语种估算一段文本的 token 数 ✓。

    - CJK 字符按 1 个算 ✓；
    - 其余按 4 字符 1 个算 ✓（向上取整 ✓）。

    ⚠️ **空串返回 0** ✓ —— 旧路径的空内容会记 1 ✗（白占预算 ✗）。
    """
    if not text:
        return 0
    cjk_count = sum(1 for char in text if _is_cjk(char))
    other_count = len(text) - cjk_count
    return cjk_count + (other_count + 3) // 4


def estimate_message_tokens(messages: list[dict[str, Any]]) -> int:
    """一批消息的 token 估算 ✓（**轮次内**口径 ✓）。

    ⚠️ **工具调用也要算** ✓ —— 它同样进模型的上下文 ✓（旧路径也算 ✓）。

    ⚠️ **只有内容与工具调用计入** ✓ —— ``role`` / 其它字段不进上下文 ✓
    （旧路径也是这个口径 ✓）。
    """
    total = 0
    for item in messages:
        total += estimate_tokens(str(item.get("content") or ""))
        for call in item.get("tool_calls") or []:
            total += estimate_tokens(str(call))
    return total


__all__ = ["estimate_message_tokens", "estimate_tokens"]
