"""Unit tests for CatalogAgent profile persistence round-trip."""

from __future__ import annotations

from uuid import UUID, uuid4

from qzdap.modules.agent_runtime.domain.catalog import CatalogAgent

TENANT = UUID("00000000-0000-0000-0000-000000000001")
WORKSPACE = UUID("00000000-0000-0000-0000-000000000002")


def _make_agent() -> CatalogAgent:
    return CatalogAgent.create(
        id=uuid4(),
        tenant_id=TENANT,
        workspace_id=WORKSPACE,
        name="Test Agent",
        category="客服",
        owner="Alice",
    )


def test_profile_defaults_to_none() -> None:
    a = _make_agent()
    assert a.profile is None
    out = a.to_admin_dict()
    assert out["profile"] is None


def test_apply_patch_accepts_dict_profile() -> None:
    a = _make_agent()
    tool_profile = {
        "kind": "Tool",
        "authKind": "api_key",
        "baseUrl": "https://api.example.com",
        "endpointPath": "/v1/chat",
        "httpMethod": "POST",
        "sourceKind": "http_endpoint",
        "networkPolicy": "allowlist",
        "allowedHosts": ["api.example.com"],
        "timeoutMs": 30000,
    }
    next_a = a.apply_patch({"profile": tool_profile})
    assert next_a.profile == tool_profile
    out = next_a.to_admin_dict()
    assert out["profile"] == tool_profile


def test_apply_patch_accepts_mcp_profile() -> None:
    a = _make_agent()
    mcp_profile = {
        "kind": "MCP",
        "transport": "streamable-http",
        "serverUrl": "https://mcp.example.com",
        "command": "",
        "args": [],
        "env": {},
        "probeIntervalS": 300,
        "connectionTimeoutS": 10,
        "tokenRotationDays": 90,
        "selectedTools": ["list_repos"],
    }
    next_a = a.apply_patch({"profile": mcp_profile})
    assert next_a.profile == mcp_profile
    assert next_a.profile["kind"] == "MCP"
    assert next_a.profile["selectedTools"] == ["list_repos"]


def test_apply_patch_can_clear_profile_with_null() -> None:
    a = _make_agent()
    a = a.apply_patch({"profile": {"kind": "Tool", "baseUrl": "x"}})
    assert a.profile is not None
    cleared = a.apply_patch({"profile": None})
    assert cleared.profile is None


def test_apply_patch_ignores_non_dict_non_null_profile() -> None:
    a = _make_agent()
    a = a.apply_patch({"profile": {"kind": "Tool"}})
    # 非法类型(str/list/int)应被忽略,profile 保持原值
    after = a.apply_patch({"profile": "not-a-dict"})
    assert after.profile == {"kind": "Tool"}
    after_list = a.apply_patch({"profile": [1, 2, 3]})
    assert after_list.profile == {"kind": "Tool"}


def test_profile_round_trip_via_admin_dict() -> None:
    a = _make_agent()
    profile = {
        "kind": "Tool",
        "authKind": "bearer",
        "apiKey": "sk-test-1234",
        "baseUrl": "https://api.example.com",
        "endpointPath": "/v1/embeddings",
        "httpMethod": "POST",
        "sourceKind": "openapi_url",
        "networkPolicy": "allowlist",
        "allowedHosts": ["api.example.com", "*.example.com"],
        "timeoutMs": 60000,
    }
    a = a.apply_patch({"profile": profile})
    out = a.to_admin_dict()
    # 模拟往返:取出再 apply_patch 回去
    a2 = _make_agent()
    a2 = a2.apply_patch({"profile": out["profile"]})
    assert a2.profile == profile
