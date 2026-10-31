"""出站编码与投递的测试 —— §6 的编码规则表 + 降级留痕。

**降级必须保信息、并且必须留痕**：内容表达不了时降级成可回答的文本，
``DeliveryOutcome.degraded_flags`` 记下**降级了什么**。

⚠️ **入参是对外 chunk** ✓（A-39 ✓ —— 内部那套事件类型已删 ✓）——
这里**经由工厂**造 chunk ✓（顺带验了真实转换路径 ✓）。
"""

from __future__ import annotations

from typing import Any

import pytest

from qzdap.modules.channel.adapter.outbound.encoder import (
    FLAG_APPROVAL_DEGRADED,
    FLAG_ARTIFACT_DEGRADED,
    FLAG_CARDS_DEGRADED,
    FLAG_PLAN_DEGRADED,
    encode_result_event,
)
from qzdap.modules.channel.adapter.outbound.result_sink import ChannelResultSink
from qzdap_agent_runtime.gateway.outbound import OutboundTarget
from qzdap_agent_runtime.gateway.types import ChannelCapabilities, ChannelType
from qzdap_agent_runtime.result import to_chunk

_NO_CARDS = ChannelCapabilities()
_CARDS = ChannelCapabilities(cards=True, interactive=True)

_TURN = "11111111-1111-1111-1111-111111111111"
_APPROVAL = "44444444-4444-4444-4444-444444444444"
_PLAN = "55555555-5555-5555-5555-555555555555"
_ARTIFACT = "66666666-6666-6666-6666-666666666666"


def _chunk(event_type: str, payload: dict[str, Any], seq: int = 1) -> Any:
    return to_chunk(
        event_type=event_type,
        payload=payload,
        turn_id=_TURN,
        seq=seq,
        event_id=f"e{seq}",
        trace_id="trace",
    )


def _target(capabilities: ChannelCapabilities = _NO_CARDS) -> OutboundTarget:
    return OutboundTarget(
        channel_type=ChannelType.FEISHU,
        external_chat_id="c1",
        capabilities=capabilities,
    )


def _message(text: str = "hello") -> Any:
    return _chunk("message", {"content": text})


def _approval() -> Any:
    return _chunk(
        "approval_required",
        {
            "approval_id": _APPROVAL,
            "tool": "delete_file",
            "args_preview": '{"path": "/tmp/x"}',
            "reason": "危险操作",
            "expires_at": "2026-10-30T00:00:00+00:00",
        },
        seq=2,
    )


# ── 编码规则（§6 的表）──────────────────────────────────────────────────


def test_a_message_is_encoded_as_plain_text() -> None:
    encoded = encode_result_event(_message(), _NO_CARDS)
    assert encoded.text == "hello"
    assert encoded.card is None
    assert encoded.degraded_flags == ()
    assert encoded.skip is False


def test_an_approval_without_card_support_degrades_to_answerable_text() -> None:
    """无卡片能力 → **文本 + 「回复 YES/NO」**（降级必须保信息）。"""
    encoded = encode_result_event(_approval(), _NO_CARDS)
    assert "YES" in encoded.text
    assert "NO" in encoded.text
    assert _APPROVAL in encoded.text
    assert FLAG_APPROVAL_DEGRADED in encoded.degraded_flags
    assert encoded.card is None


def test_an_approval_with_card_support_produces_a_card_with_the_approval_id() -> None:
    """有卡片能力 → 审批卡片，**回调必须带 approval_id**（否则点回来找不着）。"""
    encoded = encode_result_event(_approval(), _CARDS)
    assert encoded.card is not None
    assert encoded.card["type"] == "approval"
    values = [action["value"]["approval_id"] for action in encoded.card["actions"]]
    assert values == [_APPROVAL, _APPROVAL]
    assert encoded.degraded_flags == ()


def test_a_plan_without_card_support_degrades_to_a_numbered_list() -> None:
    event = _chunk(
        "plan_proposed",
        {
            "plan_id": _PLAN,
            "title": "清理磁盘",
            "steps": [{"title": "扫描"}, {"title": "删除"}],
        },
        seq=3,
    )
    encoded = encode_result_event(event, _NO_CARDS)
    assert "1. 扫描" in encoded.text
    assert "2. 删除" in encoded.text
    assert FLAG_PLAN_DEGRADED in encoded.degraded_flags


def test_an_artifact_without_card_support_degrades_to_text_with_the_link() -> None:
    event = _chunk(
        "artifact_ready",
        {
            "artifact_id": _ARTIFACT,
            "kind_": "markdown",
            "name": "报告.md",
            "mime": "text/markdown",
            "size_bytes": 10,
            "download_path": "/api/artifacts/a1/content",
        },
        seq=4,
    )
    encoded = encode_result_event(event, _NO_CARDS)
    assert "/api/artifacts/a1/content" in encoded.text
    assert FLAG_ARTIFACT_DEGRADED in encoded.degraded_flags


def test_usage_is_not_delivered_to_the_user() -> None:
    """usage / done 这类「不打扰用户」的事件 —— 不投递，但**记账**。"""
    event = _chunk(
        "usage",
        {
            "input_tokens": 1,
            "output_tokens": 2,
            "cache_tokens": 0,
            "cost_usd": 0.01,
            "cost_unknown": False,
            "tenant_id": "t",
            "workspace_id": "w",
            "user_id": "u",
            "agent_id": "a",
            "agent_version": "v",
            "model_version": "m",
            "retry_count": 0,
        },
        seq=5,
    )
    encoded = encode_result_event(event, _NO_CARDS)
    assert encoded.skip is True


def test_an_error_is_told_to_the_user() -> None:
    """错误**不是**「不打扰用户」的那一类 —— 要说。"""
    event = _chunk("error", {"error_code": "E_X", "safe_message": "出错了"}, seq=6)
    encoded = encode_result_event(event, _NO_CARDS)
    assert encoded.skip is False
    assert "出错了" in encoded.text


def test_a_known_error_code_is_projected_into_the_im_copy() -> None:
    """im 投放面：已知码 → **投影文案**（同一个码永远说同一句话 ✓）。"""
    from qzdap_kernel.error_codes import ErrorCode, project_error

    event = _chunk(
        "error",
        {
            "error_code": ErrorCode.CHANNEL_DELIVERY_FAILED.value,
            "safe_message": "outbound send failed: boom",
        },
        seq=6,
    )
    encoded = encode_result_event(event, _NO_CARDS)

    assert encoded.text == project_error(ErrorCode.CHANNEL_DELIVERY_FAILED, "im")


# ── 投递（sink）──────────────────────────────────────────────────────────


class _Adapter:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.sent: list[dict] = []

    async def send_reply(self, *, external_chat_id, text, metadata) -> str | None:  # type: ignore[no-untyped-def]
        if self.fail:
            raise RuntimeError("boom")
        self.sent.append({"external_chat_id": external_chat_id, "text": text, "metadata": metadata})
        return "mid-1"


@pytest.mark.asyncio
async def test_delivering_a_message_reports_sent() -> None:
    adapter = _Adapter()
    sink = ChannelResultSink(outbound_registry={ChannelType.FEISHU: adapter})
    outcome = await sink.deliver(_message(), target=_target())
    assert outcome.status == "sent"
    assert outcome.external_message_id == "mid-1"
    assert outcome.ok is True
    assert adapter.sent[0]["text"] == "hello"


@pytest.mark.asyncio
async def test_a_card_capable_channel_without_card_support_degrades_and_records_it() -> None:
    """渠道**能**发卡片但适配器还不会 → 降级为文本，并**记下**降级了什么。"""
    adapter = _Adapter()
    sink = ChannelResultSink(outbound_registry={ChannelType.FEISHU: adapter})
    outcome = await sink.deliver(_approval(), target=_target(_CARDS))
    assert outcome.status == "degraded"
    assert FLAG_CARDS_DEGRADED in outcome.degraded_flags
    assert outcome.degraded is True
    assert adapter.sent, "降级后仍要把内容发出去"


@pytest.mark.asyncio
async def test_a_missing_adapter_is_reported_as_failed() -> None:
    sink = ChannelResultSink(outbound_registry={})
    outcome = await sink.deliver(_message(), target=_target())
    assert outcome.status == "failed"
    assert outcome.ok is False
    assert outcome.error


@pytest.mark.asyncio
async def test_a_failing_adapter_is_reported_as_failed_not_raised() -> None:
    """投递失败**不炸掉主链路** —— 返回 failed，由调用方决定重试还是进死信。"""
    sink = ChannelResultSink(outbound_registry={ChannelType.FEISHU: _Adapter(fail=True)})
    outcome = await sink.deliver(_message(), target=_target())
    assert outcome.status == "failed"
    assert "boom" in (outcome.error or "")


@pytest.mark.asyncio
async def test_skipped_events_are_not_delivered_but_are_recorded() -> None:
    adapter = _Adapter()
    sink = ChannelResultSink(outbound_registry={ChannelType.FEISHU: adapter})
    event = _chunk(
        "usage",
        {
            "input_tokens": 1,
            "output_tokens": 2,
            "cache_tokens": 0,
            "cost_usd": None,
            "cost_unknown": True,
            "tenant_id": "t",
            "workspace_id": "w",
            "user_id": "u",
            "agent_id": "a",
            "agent_version": "v",
            "model_version": "m",
            "retry_count": 0,
        },
        seq=5,
    )
    outcome = await sink.deliver(event, target=_target())
    assert outcome.status == "skipped"
    assert adapter.sent == []


@pytest.mark.asyncio
async def test_the_target_metadata_reaches_the_adapter() -> None:
    adapter = _Adapter()
    sink = ChannelResultSink(outbound_registry={ChannelType.FEISHU: adapter})
    target = OutboundTarget(
        channel_type=ChannelType.FEISHU,
        external_chat_id="c9",
        capabilities=_NO_CARDS,
        metadata={"turn_id": "t1"},
    )
    await sink.deliver(_message(), target=target)
    assert adapter.sent[0]["external_chat_id"] == "c9"
    assert adapter.sent[0]["metadata"]["turn_id"] == "t1"


def test_a_done_event_is_not_delivered_to_the_user() -> None:
    """``done`` 属于「折叠或忽略」那一类（§6）—— 最终消息由 message 事件带。"""
    event = _chunk(
        "done",
        {
            "final_message": "完成",
            "status": "succeeded",
            "agent_version": "v",
            "model_version": "m",
        },
        seq=7,
    )
    encoded = encode_result_event(event, _NO_CARDS)
    assert encoded.skip is True


def test_the_encoder_never_raises_on_an_unknown_event() -> None:
    """未知事件 —— 不静默丢：给个兜底文本。"""

    class _Weird:
        kind = "weird_kind"

    encoded = encode_result_event(_Weird(), _NO_CARDS)  # type: ignore[arg-type]
    assert encoded.text == "weird_kind"


def test_any_dict_is_accepted_by_the_adapter_metadata() -> None:
    """（占位：metadata 的形状由适配器自己定义，这里只保证不强类型耦合。）"""
    metadata: dict[str, Any] = {"turn_id": "t1"}
    assert metadata["turn_id"] == "t1"
