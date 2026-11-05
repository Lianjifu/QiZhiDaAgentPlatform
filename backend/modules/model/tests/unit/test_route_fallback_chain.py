"""**路由的失败转移链 + 策略覆盖** ✓。

⚠️ **之前 ``create_route`` 不收 ``fallbackModelIds``** ✓ → 路由的
``fallback_model_ids`` 恒为 ``[]`` ✓ → ``fallback`` 策略下链只有 primary
一个 ✓ → 所谓「失败转移」**从来没发生过** ✗✗。

⚠️ **策略覆盖** ✓ —— agent 可以用**自己的**取舍去跑同一条路由 ✓。
"""

from __future__ import annotations

from uuid import UUID

import pytest

from qzdap.modules.model.application.services import ModelService
from qzdap.modules.model.domain.errors import ModelNotFound
from qzdap_kernel.ids import ModelId
from qzdap_vault.actor import ActorContext

from .test_model_catalog import TENANT, WORKSPACE, _svc


async def _models(svc: ModelService, specs: list[tuple[str, float]]) -> list[UUID]:
    """建几个 active 模型 ✓ —— ``specs`` 是 (上游名字, 单价) ✓。"""
    ids: list[UUID] = []
    for index, (upstream, price) in enumerate(specs):
        created = await svc.create_from_provider(
            tenant_id=TENANT,
            workspace_id=WORKSPACE,
            body={
                "source": "catalog",
                "providerName": f"OpenAI-{index}",
                "apiKey": f"sk-{index:04d}",
                "baseUrl": "https://api.openai.com/v1",
                "protocol": "openai",
                "models": [upstream],
            },
        )
        model_id = UUID(created["id"])
        await svc.update_model(
            model_id=model_id,
            body={"patch": {"status": "active", "priceIn": price, "priceOut": price}},
        )
        ids.append(model_id)
    return ids


async def _two_models(svc: ModelService) -> tuple[UUID, UUID]:
    primary_id, fallback_id, _ = await _models(svc, [("gpt-4o", 10.0), ("gpt-4o-mini", 5.0), ("qwen-max", 1.0)])
    return primary_id, fallback_id


@pytest.mark.asyncio
async def test_create_route_keeps_the_fallback_chain() -> None:
    svc = _svc()
    primary_id, fallback_id = await _two_models(svc)
    route = await svc.create_route(
        tenant_id=TENANT,
        workspace_id=WORKSPACE,
        body={
            "name": "带转移链的路由",
            "strategy": "fallback",
            "primaryModelId": str(primary_id),
            "fallbackModelIds": [str(fallback_id)],
        },
    )
    assert route["fallbackModelIds"] == [str(fallback_id)]


@pytest.mark.asyncio
async def test_create_route_rejects_a_foreign_fallback_model() -> None:
    svc = _svc()
    primary_id, _ = await _two_models(svc)
    with pytest.raises(ModelNotFound):
        await svc.create_route(
            tenant_id=TENANT,
            workspace_id=WORKSPACE,
            body={
                "name": "越权的转移链",
                "primaryModelId": str(primary_id),
                "fallbackModelIds": [str(UUID("00000000-0000-0000-0000-0000000000ff"))],
            },
        )


@pytest.mark.asyncio
async def test_the_fallback_strategy_chain_has_more_than_the_primary() -> None:
    svc = _svc()
    primary_id, fallback_id = await _two_models(svc)
    route = await svc.create_route(
        tenant_id=TENANT,
        workspace_id=WORKSPACE,
        body={
            "name": "转移链",
            "strategy": "fallback",
            "primaryModelId": str(primary_id),
            "fallbackModelIds": [str(fallback_id)],
        },
    )
    actor = ActorContext(
        tenant_id=TENANT, workspace_id=WORKSPACE, principal_id=UUID(int=1)
    )
    chain = await svc.select_chain_for_strategy(
        actor=actor, route_id=ModelId(UUID(route["id"]))
    )
    assert chain == [ModelId(primary_id), ModelId(fallback_id)]


@pytest.mark.asyncio
async def test_the_agent_can_override_the_routes_strategy() -> None:
    """⚠️ 同一条路由 ✓ —— agent 要 cost-first ✓ 就给它 cost-first ✓。"""
    svc = _svc()
    primary_id, fallback_id, cheap_id = await _models(
        svc, [("gpt-4o", 10.0), ("gpt-4o-mini", 5.0), ("qwen-max", 1.0)]
    )
    route = await svc.create_route(
        tenant_id=TENANT,
        workspace_id=WORKSPACE,
        body={
            "name": "默认 fallback",
            "strategy": "fallback",
            "primaryModelId": str(primary_id),
            "fallbackModelIds": [str(fallback_id)],
        },
    )
    actor = ActorContext(
        tenant_id=TENANT, workspace_id=WORKSPACE, principal_id=UUID(int=1)
    )
    route_id = ModelId(UUID(route["id"]))
    default_chain = await svc.select_chain_for_strategy(actor=actor, route_id=route_id)
    overridden = await svc.select_chain_for_strategy(
        actor=actor, route_id=route_id, strategy="cost-first"
    )
    # ⚠️ **primary 永远排第一** ✓ —— 覆盖只动**后面的取舍** ✓。
    assert default_chain[0] == overridden[0] == ModelId(primary_id)
    # ⚠️ **fallback 策略只认显式链** ✓ → [primary, 显式那个] ✓；
    # **cost-first 按价格排** ✓ → [primary, 最便宜, 居中] ✓。
    assert default_chain == [ModelId(primary_id), ModelId(fallback_id)]
    assert overridden == [
        ModelId(primary_id),
        ModelId(cheap_id),
        ModelId(fallback_id),
    ]
