"""Result 层：**只有一套**结果形状 ✓ —— 一律是**对外 chunk** ✓（A-39 ✓）。

⚠️ **以前这里有第二套** ✓（16 种 ``*Event`` ✓ —— 与对外 chunk **一一对应**
✓）—— 两套形状 = **两处要改** ✗✗ → 现在**只剩 chunk** ✓
（``qzdap_schema.dtos.turn`` ✓ —— **前端已经认这个** ✓）。

⚠️ **换的过程中没丢字段** ✓（方案 A-39 的提醒 ✓）—— 内部事件多带的东西已经
**补进 chunk 契约** ✓（``event_id`` ✓ / usage 的 6 维 ✓ / error 的
``detailed`` ✓ / ``source_turn_id`` ✓ / ``query_hash`` ✓ / ``removed_ids``
✓ / ``expires_at`` ✓ / done 的状态与版本 ✓）。

依据：Agent 方案（关注点 #24 ✓）+ Gateway 方案 §9.0（降级标记 ✓ —— C-22 ✓）。
"""

from __future__ import annotations

from .factory import DEGRADATION_FLAGS, DegradationFlag, to_chunk

__all__ = [
    "DEGRADATION_FLAGS",
    "DegradationFlag",
    "to_chunk",
]
