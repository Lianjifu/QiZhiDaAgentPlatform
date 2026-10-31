"""出站编码器 —— 标准结果事件 → 渠道表达（Gateway 方案 §6 的编码规则表）。

**决策 #1：出站归 ①**（与入站对称）—— 渠道知识只有一份，就在这里。

**降级必须保信息**：表达不了的内容要降级成**可回答的文本**，并记 degraded ——
**不得静默丢弃**（§6 的 ``interactive_action`` 契约）。

⚠️ **卡片：编码已就绪，发送暂缓**（§10 Stage 4a 的实施说明）——
编码器会产出卡片载荷，但**本阶段一律按「无卡片能力」降级为文本**，原因：

1. 卡片上的按钮要有人接。**入站侧还没有「卡片点击 → 审批决策」的回调处理** ——
   先发卡片，等于做出一个点了没反应的按钮；
2. 各平台的卡片载荷**无法离线验证**（要真实 app 凭证 + 真实会话）。

因此编码器保留卡片分支（能力具备且适配器支持时才走），当前所有渠道都走文本
降级，并把降级记进 :class:`DeliveryOutcome` —— **能力具备而没启用，是可见的**，
不是悄悄少发。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from qzdap_kernel.error_codes import try_project_error
from qzdap_schema.dtos.turn import (
    ApprovalRequiredChunk,
    ArtifactReadyChunk,
    AttachmentReadyChunk,
    ErrorChunk,
    MessageChunk,
    PlanProposedChunk,
)

if TYPE_CHECKING:
    from qzdap_agent_runtime.gateway.types import ChannelCapabilities

#: 降级标记 —— 记进 DeliveryOutcome.degraded_flags，供审计与前端判断。
FLAG_APPROVAL_DEGRADED = "approval_degraded"
FLAG_PLAN_DEGRADED = "plan_degraded"
FLAG_ARTIFACT_DEGRADED = "artifact_degraded"
FLAG_INTERACTIVE_DEGRADED = "interactive_degraded"
FLAG_CARDS_DEGRADED = "cards_degraded"

#: 这些事件**不发给用户**（§6 的最后一行：折叠或忽略）。
#: 「忽略」不是「静默丢弃」—— 投递结果里记 ``skipped``。
SILENT_KINDS = frozenset(
    {
        "usage",
        "done",
        "context_compacted",
        "tool_call",
        "tool_result",
        "skill_invocation",
        "memory_write",
        "knowledge_search",
    }
)


@dataclass(frozen=True, slots=True)
class EncodedOutbound:
    """编码结果 —— 要发出去的**文本**（+ 可选的卡片载荷）。"""

    text: str
    card: dict[str, Any] | None = None
    degraded_flags: tuple[str, ...] = ()
    skip: bool = False
    metadata: dict[str, str] = field(default_factory=dict)


def encode_result_event(event: Any, capabilities: ChannelCapabilities) -> EncodedOutbound:
    """把一条**对外 chunk** 编码成渠道表达。

    **规则表见 Gateway 方案 §6**；能力来自**入站时**的渠道能力声明（§3.5），
    出站不再按 ``channel_type`` 硬判断。

    ⚠️ **入参是 chunk** ✓（A-39 ✓ —— 内部那 16 种事件类型**已删** ✓ ——
    两套形状 = 两处要改 ✗✗）。
    """
    kind = str(getattr(event, "kind", "unknown"))

    if kind in SILENT_KINDS:
        return EncodedOutbound(text="", skip=True)

    if isinstance(event, MessageChunk):
        return EncodedOutbound(text=event.content)

    if isinstance(event, ApprovalRequiredChunk):
        args = _args_preview(event.arguments)
        text = (
            f"需要审批：{event.tool_name}\n"
            f"理由：{event.reason}\n"
            f"参数：{args}\n"
            f"回复 YES 同意 / NO 拒绝（审批编号 {event.approval_id}）"
        )
        if not capabilities.cards:
            return EncodedOutbound(text=text, degraded_flags=(FLAG_APPROVAL_DEGRADED,))
        return EncodedOutbound(
            text=text,
            card={
                "type": "approval",
                "title": f"需要审批：{event.tool_name}",
                "body": f"{event.reason}\n{args}",
                # 回调必须带 approval_id —— 点击动作要能找回是哪一次审批。
                "actions": [
                    {"label": "同意", "value": {"approval_id": str(event.approval_id)}},
                    {"label": "拒绝", "value": {"approval_id": str(event.approval_id)}},
                ],
            },
        )

    if isinstance(event, PlanProposedChunk):
        steps = "\n".join(
            f"{index}. {_step_title(step)}" for index, step in enumerate(event.steps, start=1)
        )
        text = f"计划：{event.title}\n{steps}".rstrip()
        if not capabilities.cards:
            return EncodedOutbound(text=text, degraded_flags=(FLAG_PLAN_DEGRADED,))
        return EncodedOutbound(
            text=text,
            card={
                "type": "plan",
                "title": event.title,
                "steps": [_step_title(step) for step in event.steps],
            },
        )

    if isinstance(event, (ArtifactReadyChunk, AttachmentReadyChunk)):
        text = f"{event.name} 已就绪：{event.download_path}"
        if not capabilities.cards:
            return EncodedOutbound(text=text, degraded_flags=(FLAG_ARTIFACT_DEGRADED,))
        return EncodedOutbound(
            text=text,
            card={
                "type": "artifact",
                "title": event.name,
                "download_path": event.download_path,
            },
        )

    if isinstance(event, ErrorChunk):
        # 错误**要告诉用户**（不是 usage/done 那类「不打扰用户」的事件）。
        # 已知错误码 → 用**投影文案**（同一个码永远说同一句话 ✓）；
        # 细节留在 `detailed` 里（仅日志/trace 用）。
        projected = try_project_error(event.code, "im")
        if projected:
            return EncodedOutbound(text=projected)
        return EncodedOutbound(text=f"出错了：{event.message}")

    # 未知种类 —— 不静默丢：按文本兜底，交给投递结果记账。
    return EncodedOutbound(text=kind)


def _args_preview(arguments: Any) -> str:
    """**参数预览** ✓（chunk 里是结构化的参数 ✓ —— 这里拍平成一行 ✓）。"""
    if isinstance(arguments, dict):
        preview = arguments.get("preview")
        if preview:
            return str(preview)
        return ", ".join(f"{key}={value}" for key, value in sorted(arguments.items()))
    return str(arguments)


def _step_title(step: Any) -> str:
    if isinstance(step, dict):
        for key in ("title", "name", "step", "description"):
            value = step.get(key)
            if value:
                return str(value)
        return str(step)
    return str(step)


__all__ = [
    "FLAG_APPROVAL_DEGRADED",
    "FLAG_ARTIFACT_DEGRADED",
    "FLAG_CARDS_DEGRADED",
    "FLAG_INTERACTIVE_DEGRADED",
    "FLAG_PLAN_DEGRADED",
    "SILENT_KINDS",
    "EncodedOutbound",
    "encode_result_event",
]
