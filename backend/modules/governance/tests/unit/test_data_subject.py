"""**数据主体请求**（C9 ✓）的单元测试 ✓。

⚠️ **治理域只认 scope** ✓ —— 这里验的是**分发与汇总** ✓，
不是某个域的表 ✓（那是各域自己的测试 ✓）。
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest

from qzdap.modules.governance.application.data_subject import (
    DataSubjectRequest,
    DataSubjectService,
)
from qzdap.modules.governance.domain.errors import DataSubjectFailed


class _Scope:
    """**一个假域** ✓（记录自己被调了几次 ✓）。"""

    def __init__(self, name: str, *, fail: bool = False) -> None:
        self.scope = name
        self.fail = fail
        self.calls: list[DataSubjectRequest] = []

    async def delete(self, request: DataSubjectRequest) -> dict[str, Any]:
        self.calls.append(request)
        if self.fail:
            raise RuntimeError("boom")
        return {"deleted": 1}

    async def export(self, request: DataSubjectRequest) -> dict[str, Any]:
        self.calls.append(request)
        if self.fail:
            raise RuntimeError("boom")
        return {"exported": 1}


def _request() -> DataSubjectRequest:
    return DataSubjectRequest(tenant_id=uuid4(), user_id=uuid4(), workspace_id=uuid4())


@pytest.mark.asyncio
async def test_the_request_goes_to_every_scope() -> None:
    """**逐个 scope 分发** ✓（不是只打第一个 ✓）。"""
    memory = _Scope("memory")
    profile = _Scope("profile")
    svc = DataSubjectService(scopes=[memory, profile])

    results = await svc.delete(_request())

    assert set(results) == {"memory", "profile"}
    assert memory.calls and profile.calls
    assert svc.scopes == ("memory", "profile")


@pytest.mark.asyncio
async def test_the_export_also_goes_to_every_scope() -> None:
    """**导出也要逐个 scope** ✓。"""
    memory = _Scope("memory")
    svc = DataSubjectService(scopes=[memory])

    results = await svc.export(_request())

    assert results == {"memory": {"exported": 1}}
    assert memory.calls


@pytest.mark.asyncio
async def test_a_failing_scope_is_reported_and_the_others_still_run() -> None:
    """**一个失败不能挡别的** ✓ —— 都要跑完 ✓ 再报错 ✓。

    ⚠️ **不能假装成功** ✓ —— 失败必须**报出来** ✓（否则「删了一半」显示成功 ✗✗）。
    """
    broken = _Scope("broken", fail=True)
    healthy = _Scope("healthy")
    svc = DataSubjectService(scopes=[broken, healthy])

    with pytest.raises(DataSubjectFailed):
        await svc.delete(_request())

    # ⚠️ **健康的那个照样跑了** ✓（不因为前面失败就跳过 ✓）。
    assert healthy.calls


@pytest.mark.asyncio
async def test_registering_the_same_scope_twice_keeps_the_last_one() -> None:
    """**同名注册后者覆盖前者** ✓（免得重复注册踩坑 ✗✗）。"""
    first = _Scope("memory")
    second = _Scope("memory")
    svc = DataSubjectService(scopes=[first, second])

    await svc.delete(_request())

    assert not first.calls
    assert second.calls
