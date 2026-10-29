"""出站（① Channel Gateway 的另一半）—— 端口 + 投递结果 + 降级标记。

依据：``docs/refactor/session-architecture/gateway-refactor-plan.md`` §6
（出站：统一编码与投递）、§9.1（``facade.py`` 的 ``Gateway.emit``）。

**决策 #1：出站归 ①**（与入站对称）—— 不单列「Result Encoder」，那会让渠道知识
有两份。因此本模块只定义**契约**（端口 + 结果形状 + 降级标记）；**编码规则与渠道
知识**在 ``modules/channel``（它有各平台的卡片 / 交互能力与出站适配器）。

⚠️ **与方案草图的一处偏离（实施修正）**：方案写的是
``deliver(event) -> DeliveryOutcome`` —— 但**投递目标**（渠道、外部会话、渠道能力）
不在事件里：``ResultEvent`` 是**会话内部**的协议，与渠道无关。没有目标就无法投递，
所以本端口带一个 ``target`` 参数。事件与目标分开，Gateway 才能把同一份事件流
投给不同渠道。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal, Protocol, runtime_checkable

from qzdap_agent_runtime.gateway.types import ChannelCapabilities, ChannelType

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Mapping

    from qzdap_agent_runtime.result.events import ResultEvent

DeliveryStatus = Literal["sent", "degraded", "skipped", "failed"]


@dataclass(frozen=True, slots=True)
class OutboundTarget:
    """投递目标 —— 「这条事件要发给谁、用哪种表达」。

    - ``capabilities`` 来自**入站时**的渠道能力声明（§3.5）—— 出站不再按
      ``channel_type`` 硬判断支不支持卡片；
    - ``metadata`` 是随行信息（``channel_id`` / ``turn_id`` …），最终进适配器的
      ``metadata`` 参数。
    """

    channel_type: ChannelType
    external_chat_id: str
    capabilities: ChannelCapabilities = field(default_factory=ChannelCapabilities)
    metadata: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class DeliveryOutcome:
    """一次投递的结果 —— **降级必须留痕**。

    - ``status="degraded"`` —— 内容送达了，但**表达被降级**（卡片 → 文本）；
    - ``degraded_flags`` —— 具体降级了什么（``interactive_degraded`` /
      ``cards_degraded`` / …），供审计与前端判断；
    - ``status="skipped"`` —— 按规则**故意不发**（``usage`` / ``done`` 这类
      「不打扰用户」的事件）；
    - ``status="failed"`` —— 投递失败（调用方决定重试还是进死信）。
    """

    status: DeliveryStatus
    external_message_id: str | None = None
    degraded_flags: tuple[str, ...] = ()
    error: str | None = None

    @property
    def ok(self) -> bool:
        """「没有丢内容」—— 送达、降级送达、故意不发都算成功。"""
        return self.status in {"sent", "degraded", "skipped"}

    @property
    def degraded(self) -> bool:
        return self.status == "degraded" or bool(self.degraded_flags)


@runtime_checkable
class ResultSink(Protocol):
    """出站端口 —— 把标准结果事件编码成渠道的表达并投递。

    **唯一的 ``ResultSink`` 定义**：``runtimes/agent_runtime/result/sink.py``
    的同名协议已改为从这里导入（X1 的「按需取用」—— 事件类型与 sink 语义正是
    台账 §5.3 点名要取用的资产）。
    """

    async def deliver(
        self, event: ResultEvent, *, target: OutboundTarget
    ) -> DeliveryOutcome:
        """编码并投递一条事件 —— 失败抛异常还是返回 failed 由实现自选。"""
        ...

    def replay(self, turn_id: str, after_seq: int = 0) -> AsyncIterator[ResultEvent]:
        """按 seq 重放某一轮的事件流（无感重放的前置能力，Stage 4b 启用）。"""
        ...


__all__ = [
    "DeliveryOutcome",
    "DeliveryStatus",
    "OutboundTarget",
    "ResultSink",
]
