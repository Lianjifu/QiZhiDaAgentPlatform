"""**幂等键与参数指纹** ✓（Agent 方案 §5.3.2 ✓）。

⚠️ **指纹只认参数** ✓ —— 同一个幂等键配了**不同参数**就是**调用方的 bug**
✓ → 必须**暴露** ✓（`TOOL_IDEMPOTENCY_CONFLICT` ✓）不静默返回旧结果 ✗✗。

⚠️ **规范化** ✓ —— 键排序 ✓ + 紧凑分隔符 ✓ + ``ensure_ascii=False`` ✓
（中文参数按 UTF-8 编码 ✓ —— 同一组参数**永远**得到同一个指纹 ✓）。
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any


def canonical_json(payload: Mapping[str, Any]) -> str:
    """**参数的规范 JSON** ✓（键排序 ✓ —— 顺序不同不该算出不同指纹 ✓）。"""
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )


def request_hash(arguments: Mapping[str, Any]) -> str:
    """**参数 → 指纹** ✓（sha256 ✓ —— 与 `tool_executions.request_hash` 同口径 ✓）。"""
    return hashlib.sha256(canonical_json(arguments).encode("utf-8")).hexdigest()


__all__ = ["canonical_json", "request_hash"]
