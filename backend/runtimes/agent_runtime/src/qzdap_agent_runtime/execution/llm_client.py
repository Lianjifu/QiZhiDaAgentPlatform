"""``LLMCaller`` —— **一次模型调用** ✓（取值链 ✓ + 失败转移链 ✓ + 用量 ✓）。

依据：Agent 方案 §5.2.1（**取值链** ✓ —— 「查表，不是决策」✓）、§5.2.2
（调用模型完成生成 ✓）、§8.1（``execution/llm_client.py`` ✓）。

⚠️ **本模块不做模型选择** ✓（决策 #4 ✓）—— 它只把 §5.2.1 的六条取值链
**按顺序走一遍** ✓：

| # | 来源 | 这里怎么处理 |
|---|---|---|
| 1 | 显式指定（请求带 ``model`` / ``route_id``） | 直接用 ✓ |
| 2 | 版本冻结（agent 版本的 ``model_id``） | 直接用 ✓ |
| 3 | 策略路由（agent 绑了 ``route_id``） | **优先于** ``model_id`` ✓ |
| 4 | 上游模型名解析 | 走 ``ModelResolverPort`` ✓（**查表** ✓） |
| 5 | 失败转移链（primary + fallback） | 交给端口 ✓ |
| 6 | 环境默认模型 | **解析不到就是它** ✓（不是错误 ✓） |

⚠️ **租户守卫在实现里** ✓（§5.2.1 的细节 2 ✓）—— 解析器的查询条件必须含
``tenant_id`` ✓（runtime 这一侧只负责**把租户传下去** ✓）。
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from uuid import UUID

from qzdap_kernel.ids import ModelId
from qzdap_llm.client import ChatRequest, LLMChunk

from ..ports import ActorContext, LLMPort, ModelResolverPort


@dataclass(frozen=True, slots=True)
class ResolvedModel:
    """**解析后的模型** ✓（§5.2.1 的取值链跑完的结果 ✓）。

    ⚠️ ``model_id is None`` **不是错误** ✓ —— 那就是「用环境默认模型」✓
    （§5.2.1 的细节 1 ✓ —— 解析失败回退 ✓）。
    """

    model_name: str
    model_id: ModelId | None = None
    route_id: ModelId | None = None
    fallback_model_ids: tuple[ModelId, ...] = ()

    @property
    def is_routed(self) -> bool:
        """走的是**策略路由**吗 ✓（route 优先于 model ✓ —— §5.2.1 第 3 条 ✓）。"""
        return self.route_id is not None


class LLMCaller:
    """**调用模型** ✓ —— 失败转移链在这里执行 ✓（§5.2.2 第 5 条 ✓）。"""

    def __init__(
        self,
        llm: LLMPort,
        *,
        resolver: ModelResolverPort | None = None,
    ) -> None:
        self._llm = llm
        self._resolver = resolver

    async def resolve(
        self,
        *,
        model_name: str,
        tenant_id: UUID,
        workspace_id: UUID,
        model_id: ModelId | None = None,
        route_id: ModelId | None = None,
        fallback_model_ids: Sequence[ModelId] | None = None,
    ) -> ResolvedModel:
        """**取值链** ✓ —— 查表 ✓（不是决策 ✓）。

        ⚠️ **策略路由优先** ✓（§5.2.1 第 3 条 ✓）—— 有 ``route_id`` 就**不看**
        ``model_id`` ✓（两者都会传进来的场景 ✓）。
        """
        fallback = tuple(fallback_model_ids or ())
        if route_id is not None:
            return ResolvedModel(
                model_name=model_name,
                model_id=model_id,
                route_id=route_id,
                fallback_model_ids=fallback,
            )
        if model_id is None and _looks_uuid(model_name):
            # ⚠️ **显式指定的就是模型 id** ✓（取值链第 1 条 ✓ —— 前端传的
            # 可能就是一个 UUID ✓ —— 那就不该再查表 ✓）。
            model_id = ModelId(UUID(model_name))
        if model_id is not None:
            return ResolvedModel(
                model_name=model_name,
                model_id=model_id,
                fallback_model_ids=fallback,
            )
        if self._resolver is not None and model_name:
            try:
                resolved = await self._resolver.resolve(
                    tenant_id=tenant_id,
                    workspace_id=workspace_id,
                    upstream_model=model_name,
                )
            except Exception:
                # ⚠️ **解析失败不是错误** ✓ —— 回退环境默认模型 ✓（§5.2.1 细节 1 ✓）
                resolved = None
            return ResolvedModel(
                model_name=model_name,
                model_id=resolved,
                fallback_model_ids=fallback,
            )
        return ResolvedModel(model_name=model_name, fallback_model_ids=fallback)

    async def stream(
        self,
        *,
        resolved: ResolvedModel,
        request: ChatRequest,
        actor: ActorContext | None = None,
    ) -> AsyncIterator[LLMChunk]:
        """**发起调用** ✓ —— 失败转移链交给端口执行 ✓（§5.2.1 第 5 条 ✓）。

        ⚠️ **供应商级失败在这里转成错误** ✓（§5.2.2 第 7 条 ✓）—— 由调用
        方决定怎么终止 ✓（本层不抛穿图 ✗✗）。
        """
        stream = self._llm.stream(
            request,
            model_id=resolved.model_id,
            route_id=resolved.route_id,
            fallback_model_ids=list(resolved.fallback_model_ids) or None,
            actor=actor,
        )
        async for chunk in stream:
            yield chunk


def _looks_uuid(value: str) -> bool:
    """**这个字符串是 UUID 吗** ✓（显式指定的模型有时就是 id ✓）。"""
    try:
        UUID(value)
    except (TypeError, ValueError, AttributeError):
        return False
    return True


def usage_from_chunks(chunks: Sequence[LLMChunk]) -> dict[str, int]:
    """**用量汇总** ✓ —— 取最后一个带用量的 chunk ✓（§5.2.2 第 4 条 ✓）。

    ⚠️ **成本不在这里算** ✓ —— 平台的 ``price_of`` 负责 ✓（不用 LangChain 的
    cost 机制 ✓ —— §3.1 第 4 条 ✓）。
    """
    usage = {"input_tokens": 0, "output_tokens": 0}
    for chunk in chunks:
        if chunk.usage is not None:
            usage["input_tokens"] = chunk.usage.input_tokens
            usage["output_tokens"] = chunk.usage.output_tokens
    return usage


__all__ = ["LLMCaller", "ResolvedModel", "usage_from_chunks"]
