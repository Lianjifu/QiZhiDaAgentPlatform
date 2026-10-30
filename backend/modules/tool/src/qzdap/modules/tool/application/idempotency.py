"""**幂等键与参数指纹** ✓（Agent 方案 §5.3.2 ✓）。

⚠️ **指纹算法在 kernel** ✓（``qzdap_kernel.digest`` ✓）—— 幂等指纹与审批
参数摘要**必须是同一份** ✓（两份实现 = 判据不一致 ✗✗）。

⚠️ **同键异参就是调用方的 bug** ✓ → 必须**暴露** ✓
（``TOOL_IDEMPOTENCY_CONFLICT`` ✓）不静默返回旧结果 ✗✗。
"""

from __future__ import annotations

from qzdap_kernel.digest import canonical_json, request_hash

__all__ = ["canonical_json", "request_hash"]
