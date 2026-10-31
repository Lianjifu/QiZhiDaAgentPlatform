"""**模型 id 落库前的归一** ✓（P-13 的 mypy 扫出来的真缺陷 ✓）。

⚠️ **领域里的模型 id 可能是字符串** ✓（HTTP 层解析出来的 ✓ —— `str(UUID)` ✓），
而 **ORM 列是 `PgUUID`** ✓ → 直接把字符串塞进去**会在绑定时炸** ✓
（`PgUUID(as_uuid=True)` 的绑定器要 `value.hex` ✓ —— 字符串没有 ✓）。

验收 ✓：**落库前统一成 `UUID`** ✓（字符串 / UUID / 空值三种输入 ✓）。
"""

from __future__ import annotations

from uuid import uuid4

from qzdap.modules.agent_factory.adapter.persistence.repositories import _as_uuid


def test_a_string_model_id_becomes_a_uuid() -> None:
    """**字符串 → UUID** ✓（领域给字符串 ✓ → 落库给 UUID ✓）。"""
    raw = uuid4()

    assert _as_uuid(str(raw)) == raw


def test_a_uuid_model_id_stays_a_uuid() -> None:
    """**UUID 原样** ✓。"""
    raw = uuid4()

    assert _as_uuid(raw) is raw


def test_an_absent_model_id_stays_absent() -> None:
    """**空值原样** ✓（不编一个 UUID 出来 ✗）。"""
    assert _as_uuid(None) is None


def test_a_malformed_model_id_fails_loudly() -> None:
    """**坏值明确失败** ✓（不静默吞掉 ✗）。"""
    import pytest

    with pytest.raises(ValueError):
        _as_uuid("not-a-uuid")
