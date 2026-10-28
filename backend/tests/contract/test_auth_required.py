"""Contract: 除公开端点外, 每个请求都必须带 token.

背景 —— 这份契约 2026-10-04 写完就没被执行过: ``backend/tests/`` 不在
pytest 的 ``testpaths`` 里, 于是它烂掉了, 而且烂得**很贵**: 它当时断言
的是"每个路由都要声明 ``X-Tenant-Id`` 请求头", 那是**头部驱动**时代的
模型. 现在租户来自 **JWT 的 ``tid``**, 请求头只是交叉校验.

今天真正的边界是这样一条链:

    没有 token → 没有 principal → 没有绑定租户 → ORM 的租户自动过滤
    退化成空操作 → 路由开始相信调用方自己填的 ``X-Tenant-Id``

也就是说: 头部从来不是边界, 只是提示. 边界由 ``AuthRequiredMiddleware``
统一把守 —— 没有 principal 的非公开请求一律 401.

这份契约守的就是那把锁:

* 公开端点清单里的每条规则都必须真的指向存在的路由 (防拼错).
* 公开端点不得覆盖到**会改数据**的路由 (防"顺手把前缀放宽了").
* 匿名请求必须被拒 (真的发一个 HTTP 请求, 不是看代码).
* 公开端点保持可达 (防把登录接口也锁了).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from shared.route_table import (
    covered_routes,
    pattern_matches,
    public_path_patterns,
    route_table,
)

from qzdap.composition.main import create_app
from qzdap.composition.settings import Settings, get_settings

#: 交付出去的默认公开端点清单 —— 改动它必须是**有意**的.
EXPECTED_DEFAULT_PUBLIC_PATHS = (
    "/healthz,/livez,/readyz,/metrics,/docs,/openapi.json,"
    "/v1/identity/login,/v1/identity/tenants,/v1/channels/*/webhook"
)

#: 公开但**会改数据**的路由 —— 只有这几个是允许的.
#: 登录(建会话)、建租户(引导)、webhook(外部系统回调).
PUBLIC_BUT_MUTATING = {
    ("/v1/identity/login", "POST"),
    ("/v1/identity/tenants", "POST"),
    ("/v1/channels/{channel_id}/webhook", "POST"),
}

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


@pytest.fixture(scope="module")
def app():
    return create_app()


@pytest.fixture(scope="module")
def routes(app):
    return route_table(app)


@pytest.fixture(scope="module")
def client(app):
    return TestClient(app)


@pytest.fixture(scope="module")
def patterns():
    return public_path_patterns(get_settings().public_paths)


def test_public_path_list_is_deliberate() -> None:
    """交付出去的默认清单是固定的 —— 加一个公开端点必须改这里, 改不动就得想清楚."""
    default = Settings.model_fields["public_paths"].default
    assert default == EXPECTED_DEFAULT_PUBLIC_PATHS


def test_public_paths_resolve_to_real_routes(patterns, routes) -> None:
    """公开端点清单里的每条规则都得指向真实存在的路由 (防拼错/防路由改名后忘了改)."""
    for pattern in patterns:
        if "*" in pattern:
            # glob 规则: 至少要盖住一个路由.
            assert covered_routes([pattern], routes), f"公开端点规则没盖住任何路由: {pattern}"
            continue
        exact = {(r.path, r.method) for r in routes}
        assert any(path == pattern for path, _method in exact), (
            f"公开端点 {pattern} 在路由表里不存在"
        )


def test_public_paths_do_not_expose_mutating_routes(patterns, routes) -> None:
    """公开端点不能盖住会改数据的路由 —— 除非它本来就在白名单里."""
    for route in covered_routes(patterns, routes):
        if route.method in SAFE_METHODS:
            continue
        assert route.key in PUBLIC_BUT_MUTATING, (
            f"公开端点规则盖住了会改数据的路由: {route.method} {route.path} "
            f"(要么改路由, 要么把它加进 PUBLIC_BUT_MUTATING 白名单)"
        )


def test_webhook_pattern_only_covers_the_webhook(patterns) -> None:
    """``/v1/channels/*/webhook`` 只放开 webhook —— 不能连 channel 的 CRUD 一起放开."""
    assert "/v1/channels/*/webhook" in patterns
    assert not pattern_matches("/v1/channels/*/webhook", "/v1/channels")
    assert pattern_matches("/v1/channels/*/webhook", "/v1/channels/abc/webhook")


@pytest.mark.parametrize(
    "path",
    [
        "/api/admin/agents",
        "/api/catalog/agents",
        "/api/sessions",
        "/api/admin/skills",
        "/api/admin/workflows",
        "/v1/tools",
        "/api/account/settings",
    ],
)
def test_anonymous_requests_are_rejected(client, path) -> None:
    """没有 token 的请求一律 401 —— 这正是那份烂掉的契约当初想守的东西."""
    response = client.get(path)
    assert response.status_code == 401, f"{path} 匿名访问返回了 {response.status_code}"
    assert response.json().get("code") == "MISSING_TOKEN"


def test_anonymous_write_is_rejected(client) -> None:
    """匿名**写**也要被拒 —— 之前 ``POST /api/admin/agents`` 不带 token 就能建智能体."""
    response = client.post(
        "/api/admin/agents",
        json={"name": "未授权写入测试", "category": "企业通用"},
        headers={
            "X-Tenant-Id": "00000000-0000-0000-0000-000000000001",
            "X-Workspace-Id": "fc896c10-0c0a-42a4-af38-f94ccb9da6cc",
        },
    )
    assert response.status_code == 401, response.text


@pytest.mark.parametrize("path", ["/healthz", "/livez", "/readyz", "/metrics"])
def test_public_endpoints_stay_reachable(client, path) -> None:
    """公开端点不能被误锁 —— 锁了探针就瞎了."""
    response = client.get(path)
    assert response.status_code == 200, f"{path} 返回了 {response.status_code}"
