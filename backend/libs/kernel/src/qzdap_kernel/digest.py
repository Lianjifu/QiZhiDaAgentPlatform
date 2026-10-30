"""**规范化摘要** ✓ —— 全仓**只有这一份** ✓。

⚠️ **为什么放在 kernel** ✓ —— 两个地方要用**同一个**算法 ✓：
- **幂等指纹** ✓（`tool_executions.request_hash` ✓ —— 「同键异参」的判据 ✓）；
- **审批参数摘要** ✓（恢复时比对「审批的是 A、执行的是 B」✓）。

⚠️ **两份实现 = 判据不一致** ✗✗ —— 那会让审批恢复的校验**形同虚设** ✗。

⚠️ **规范化** ✓ —— 键排序 ✓ + 紧凑分隔符 ✓ + ``ensure_ascii=False`` ✓
（中文参数按 UTF-8 编码 ✓ —— 同一组参数**永远**得到同一个摘要 ✓）。
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any


def canonical_json(payload: Mapping[str, Any]) -> str:
    """**参数的规范 JSON** ✓（键排序 ✓ —— 顺序不同不该算出不同摘要 ✓）。"""
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )


def request_hash(payload: Mapping[str, Any]) -> str:
    """**参数 → 摘要** ✓（sha256 ✓ —— 十六进制 ✓）。"""
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


__all__ = ["canonical_json", "request_hash"]
