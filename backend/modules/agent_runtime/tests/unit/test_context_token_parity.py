"""**新旧两条路径**的 token 估算口径必须一致 ✓。

依据：Context 方案 §3.6 / 决策 #2 ——

- 旧路径（``adapter/graph/state.py``）原本按 ``len // 4`` 一刀切 ✗✗ ——
  对**中文低估约 4 倍** ✗；
- 新路径（契约层 ``context/tokens.py``）按语种估算 ✓；
- 口径不一致 → 「超没超预算」的判断会漂移 ✗（同一个会话，两条路径结论
  相反 ✗✗）。

Stage 0 的验收：同一批语料上，两条路径的估算差异 **< 10%** ✓。
"""

from __future__ import annotations

import pytest
from qzdap_agent_runtime.context.tokens import estimate_message_tokens

from qzdap.modules.agent_runtime.adapter.graph.state import estimate_tokens

_CORPUS = [
    "你好，这是一段中文上下文。",
    "The quick brown fox jumps over the lazy dog.",
    "你好 hello 世界 world 混合 mixed 语料 12345",
    "",
]


@pytest.mark.parametrize("text", _CORPUS)
def test_the_two_paths_agree(text: str) -> None:
    old = estimate_tokens([{"role": "user", "content": text}])
    new = estimate_message_tokens([{"role": "user", "content": text}])
    if new == 0:
        assert old == 0
        return
    assert abs(old - new) / new < 0.10


def test_chinese_is_no_longer_underestimated() -> None:
    """中文**不再被低估 4 倍** ✓ —— 旧实现按 ``len // 4`` 算 ✗✗。"""
    text = "这是一段中文上下文，用来验证估算口径。"
    estimated = estimate_tokens([{"role": "user", "content": text}])
    assert estimated >= len(text) * 0.9  # 1 字 ≈ 1 token ✓
