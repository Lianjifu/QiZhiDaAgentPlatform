"""Context Stage 0：token 估算（**按语种**）的口径与对照。

依据：Context 方案 §3.6（两条路径口径不一致的缺陷）、§9 Stage 0 的验收：

- 中文 / 英文 / 混合语料上，**按语种**估算符合口径 ✓；
- 中文语料上与 ``tiktoken`` 的偏差 **< 15%** ✓（``tiktoken`` **仅作测试期
  对照** ✓ —— 不进生产依赖 ✓）。

⚠️ **新旧两条路径的一致性**在模块侧测（``modules/agent_runtime/tests/unit/
test_context_token_parity.py`` ✓）—— 契约层不 import 模块 ✓。
"""

from __future__ import annotations

import pytest

from qzdap_agent_runtime.context.tokens import (
    estimate_message_tokens,
    estimate_tokens,
)

#: 与真实 tokenizer 的最大允许偏差（Context 方案 §9 Stage 0 验收 ✓）。
_MAX_DEVIATION = 0.15


class TestByLanguage:
    def test_cjk_counts_as_one_per_char(self) -> None:
        assert estimate_tokens("中文测试") == 4

    def test_ascii_uses_four_chars_per_token(self) -> None:
        assert estimate_tokens("abcdefgh") == 2

    def test_empty_string_is_zero(self) -> None:
        assert estimate_tokens("") == 0

    def test_mixed_content_adds_both(self) -> None:
        # "Hello中文" = 5 ASCII → 2 tokens + 2 CJK → 2 tokens
        assert estimate_tokens("Hello中文") == 4

    def test_punctuation_is_not_cjk(self) -> None:
        # 全角标点不在 CJK 区间里 —— 按 4 字符 1 token 算 ✓
        assert estimate_tokens("，。！") == 1


class TestMessageTokens:
    def test_tool_calls_are_counted(self) -> None:
        total = estimate_message_tokens(
            [{"role": "assistant", "content": "hi", "tool_calls": [{"name": "x"}]}]
        )
        assert total == estimate_tokens("hi") + estimate_tokens("[{'name': 'x'}]")

    def test_empty_message_costs_nothing(self) -> None:
        assert estimate_message_tokens([{"role": "user", "content": ""}]) == 0


@pytest.fixture(scope="module")
def encoder():  # type: ignore[no-untyped-def]
    tiktoken = pytest.importorskip("tiktoken")
    return tiktoken.get_encoding("cl100k_base")


class TestAgainstTiktoken:
    """与真实 tokenizer 的偏差 —— **只作对照** ✓（不是绝对真值 ✓）。"""

    def _deviation(self, encoder, text: str) -> float:
        real = len(encoder.encode(text))
        est = estimate_tokens(text)
        assert real > 0
        return abs(est - real) / real

    def test_chinese_within_tolerance(self, encoder) -> None:  # type: ignore[no-untyped-def]
        text = "你好，这是一段中文上下文，用来验证 token 估算的口径是否合理。"
        assert self._deviation(encoder, text) < _MAX_DEVIATION

    def test_english_within_tolerance(self, encoder) -> None:  # type: ignore[no-untyped-def]
        text = "The quick brown fox jumps over the lazy dog. " * 5
        assert self._deviation(encoder, text) < _MAX_DEVIATION

    def test_mixed_within_tolerance(self, encoder) -> None:  # type: ignore[no-untyped-def]
        text = "你好 hello 世界 world 混合 mixed 语料 corpus 样本 sample 12345"
        assert self._deviation(encoder, text) < _MAX_DEVIATION
