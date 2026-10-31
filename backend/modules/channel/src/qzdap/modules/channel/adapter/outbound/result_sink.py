"""出站 sink —— 标准结果事件 → 编码 → 投递到渠道（Gateway ① 的出站实现）。

**决策 #1：出站归 ①**（与入站对称）—— 编码规则在 :mod:`.encoder`，渠道知识
（哪个渠道能发卡片）随入站时的能力声明一起给（§3.5）。

**降级必须保信息、并且必须留痕**：内容表达不了时降级成可回答的文本，
``DeliveryOutcome.degraded_flags`` 记下**降级了什么** —— 不静默丢弃、不假装送达。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from qzdap.modules.channel.adapter.outbound.encoder import (
    FLAG_CARDS_DEGRADED,
    encode_result_event,
)
from qzdap_agent_runtime.gateway.outbound import DeliveryOutcome, OutboundTarget

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Mapping

    from qzdap.modules.channel.application.ports import OutboundAdapter
    from qzdap_agent_runtime.gateway.types import ChannelType
    from qzdap_agent_runtime.result.events import ResultEvent

_log = logging.getLogger("qzdap.channel.outbound")


class ChannelResultSink:
    """Gateway 出站端口的渠道侧实现 —— 编码 + 投递。"""

    def __init__(self, *, outbound_registry: Mapping[ChannelType, OutboundAdapter]) -> None:
        self._registry = dict(outbound_registry)

    async def deliver(self, event: ResultEvent, *, target: OutboundTarget) -> DeliveryOutcome:
        """编码一条事件并投给目标渠道。

        **不抛异常**：投递失败返回 ``status="failed"`` —— 由调用方决定重试还是
        进死信（§6：投递失败 → 重试 → 死信）。
        """
        encoded = encode_result_event(event, target.capabilities)
        if encoded.skip:
            # 「不打扰用户」的事件（usage / done / 内部事件）—— 记一笔，不投递。
            return DeliveryOutcome(status="skipped")

        adapter = self._registry.get(target.channel_type)
        if adapter is None:
            return DeliveryOutcome(
                status="failed",
                error=f"no outbound adapter for channel type {target.channel_type}",
            )

        degraded = list(encoded.degraded_flags)
        card = encoded.card
        if card is not None:
            sender = getattr(adapter, "send_card", None)
            if sender is None:
                # 渠道**能**发卡片，但适配器还不会发 → 降级为文本并记痕。
                degraded.append(FLAG_CARDS_DEGRADED)
                card = None

        metadata: dict[str, Any] = {**encoded.metadata, **dict(target.metadata)}
        try:
            if card is not None:
                message_id = await sender(  # type: ignore[misc]
                    external_chat_id=target.external_chat_id,
                    card=card,
                    metadata=metadata,
                )
            else:
                message_id = await adapter.send_reply(
                    external_chat_id=target.external_chat_id,
                    text=encoded.text,
                    metadata=metadata,
                )
        except Exception as exc:  # 投递失败不炸掉主链路
            _log.warning(
                "outbound delivery failed: channel_type=%s error=%s",
                target.channel_type,
                exc,
            )
            return DeliveryOutcome(
                status="failed",
                error=f"{type(exc).__name__}: {exc}",
                degraded_flags=tuple(degraded),
            )

        return DeliveryOutcome(
            status="degraded" if degraded else "sent",
            external_message_id=message_id,
            degraded_flags=tuple(degraded),
        )

    async def replay(self, turn_id: str, after_seq: int = 0) -> AsyncIterator[ResultEvent]:
        """出站重放 —— **未实现**。

        无感重放要的是「把事件流重放给**客户端**」，那需要 ``session_events``
        真写真读（Session Stage 4，Gateway 方案 §0.5 的硬依赖）。
        渠道侧的重放是另一回事（把消息再发一遍给用户），本阶段不做。
        """
        raise NotImplementedError(
            "outbound replay needs session_events (Session Stage 4); Gateway Stage 4b enables it"
        )
        yield  # pragma: no cover — keeps the async-generator typing


__all__ = ["ChannelResultSink"]
