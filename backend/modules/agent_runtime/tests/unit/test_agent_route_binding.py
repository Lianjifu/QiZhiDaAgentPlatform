"""**agent 的路由绑定** ✓ —— 「这个 agent 走哪条路由」是 agent 的配置 ✓。

⚠️ **之前只有 HTTP 请求体能传 route_id** ✓ —— 换个客户端就没了 ✗✗；
``agent_versions.route_id``（迁移 0042 ✓）存着但**对话路径从不读** ✗✗。
本文件盯住这条链路 ✓。
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from qzdap.modules.agent_runtime.domain.catalog import CatalogAgent

TENANT = UUID("00000000-0000-0000-0000-000000000001")
WORKSPACE = UUID("00000000-0000-0000-0000-000000000002")
ROUTE = UUID("00000000-0000-0000-0000-0000000000aa")


def _agent() -> CatalogAgent:
    return CatalogAgent.create(
        id=uuid4(),
        tenant_id=TENANT,
        workspace_id=WORKSPACE,
        name="客服",
        category="客服应答",
        owner="管理员",
    )


def test_patch_sets_the_route_binding() -> None:
    agent = _agent().apply_patch({"routeId": str(ROUTE), "routeStrategy": "cost-first"})
    assert agent.route_id == ROUTE
    assert agent.route_strategy == "cost-first"


def test_patch_accepts_a_uuid_object() -> None:
    agent = _agent().apply_patch({"routeId": ROUTE})
    assert agent.route_id == ROUTE


def test_patch_rejects_an_unknown_strategy() -> None:
    with pytest.raises(ValueError, match="routeStrategy must be one of"):
        _agent().apply_patch({"routeStrategy": "whatever"})


def test_patch_clears_the_route_binding() -> None:
    agent = _agent().apply_patch({"routeId": str(ROUTE)})
    cleared = agent.apply_patch({"routeId": None, "routeStrategy": ""})
    assert cleared.route_id is None
    assert cleared.route_strategy is None


def test_an_unparsable_route_id_is_treated_as_unset() -> None:
    agent = _agent().apply_patch({"routeId": "not-a-uuid"})
    assert agent.route_id is None


def test_the_admin_payload_exposes_the_binding() -> None:
    agent = _agent().apply_patch({"routeId": str(ROUTE), "routeStrategy": "latency-first"})
    payload = agent.to_admin_dict()
    assert payload["routeId"] == str(ROUTE)
    assert payload["routeStrategy"] == "latency-first"


def test_publishing_keeps_the_binding_in_the_snapshot() -> None:
    agent = _agent().apply_patch({"routeId": str(ROUTE), "routeStrategy": "cost-first"})
    published = agent.publish()
    snapshot = published.versions[0]["snapshot"]
    assert snapshot["routeId"] == str(ROUTE)
    assert snapshot["routeStrategy"] == "cost-first"
