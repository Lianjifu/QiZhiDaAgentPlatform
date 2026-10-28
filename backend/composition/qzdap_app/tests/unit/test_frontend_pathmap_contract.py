"""Contract: 前端的 pathMap 必须跟后端真实路由对得上.

``frontend/packages/api/src/pathMap.ts`` 是前端 ``/api/*`` 路径到后端真实
路径的映射表. 它文件头里写着自己要守的规矩:

    Batch 7 audit 标准: 路径对应 ``@router.<verb>("<path>")`` 必须存在于
    backend 的某个 router 里.

但那条规矩之前只是一次性手工审计的记录 —— **没有任何测试在执行它**,
所以表一直在漂. 这个文件把它变成可执行的守门:

1. 每条声明了 ``backendPath`` 的规则, 那个路径必须真的存在于后端路由表里.
2. 每条标了 ``unmatched: true`` 的规则 (mock 自创、backend 未实现),
   那个路径必须**确实不存在** —— 免得后端后来实现了, phantom 列表却还留着.

另外顺带报一下漂移规模: 前端 mock 覆盖了哪些端点、后端有没有对应实现.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from qzdap.composition.main import create_app

_REPO_ROOT = Path(__file__).resolve().parents[4]
_PATH_MAP = _REPO_ROOT.parent / "frontend" / "packages" / "api" / "src" / "pathMap.ts"

# pathMap 里的规则条目:
#   { key: '/api/x', rule: { method: 'GET', backendPath: '/v1/y' } }
#   { key: '/api/x', rule: { method: 'GET', backendPath: '', unmatched: true } }
_RULE_RE = re.compile(
    r"\{\s*key:\s*'(?P<key>[^']+)'\s*,\s*rule:\s*\{(?P<rule>[^}]*)\}\s*\}",
    re.DOTALL,
)
_BACKEND_PATH_RE = re.compile(r"backendPath:\s*'(?P<path>[^']*)'")
_UNMATCHED_RE = re.compile(r"unmatched:\s*true")
_METHOD_RE = re.compile(r"method:\s*'(?P<method>[A-Za-z]+)'")


def _live_route_paths() -> set[str]:
    """后端真实注册的路由路径.

    用 OpenAPI schema 而不是遍历 ``app.routes`` —— 这个 FastAPI 版本把
    ``include_router`` 包成 ``_IncludedRouter``, 路由是**延迟**挂载的:
    ``route.path`` 上只有局部路径 (``/login``), 前缀要等匹配时才补上
    (``/v1/identity/login``). 遍历 ``app.routes`` 会拿到错的路径表.

    OpenAPI schema 是运行时真正对外暴露的那份路径, 跟实际请求一致.
    """
    app = create_app()
    return set(app.openapi().get("paths", {}))


def _path_to_regex(path: str) -> re.Pattern[str]:
    """``/api/admin/agents/{agent_id}`` → 能匹配具体 id 的正则."""
    return re.compile(
        "^" + re.sub(r"\{[^}]+\}", r"[^/]+", path.replace("/", r"/")) + "$"
    )


def _rules() -> list[tuple[str, str, str, bool]]:
    """返回 (key, method, backendPath, unmatched) 四元组列表."""
    if not _PATH_MAP.exists():  # pragma: no cover — 仓库布局变了
        pytest.skip(f"pathMap not found at {_PATH_MAP}")
    text = _PATH_MAP.read_text(encoding="utf-8")
    out: list[tuple[str, str, str, bool]] = []
    for match in _RULE_RE.finditer(text):
        rule_body = match.group("rule")
        path_match = _BACKEND_PATH_RE.search(rule_body)
        method_match = _METHOD_RE.search(rule_body)
        if path_match is None:
            continue
        out.append(
            (
                match.group("key"),
                (method_match.group("method") if method_match else "").upper(),
                path_match.group("path"),
                bool(_UNMATCHED_RE.search(rule_body)),
            )
        )
    return out


@pytest.fixture(scope="module")
def live_routes() -> set[tuple[str, str]]:
    """后端真实存在的 (路径, 方法) 集合."""
    app = create_app()
    out: set[tuple[str, str]] = set()
    for path, operations in app.openapi().get("paths", {}).items():
        for method in operations:
            if method.lower() in {"head", "options"}:
                continue
            out.add((path, method.upper()))
    return out


def _route_exists(routes: set[tuple[str, str]], path: str, method: str) -> bool:
    """(路径, 方法) 在后端存在吗 —— 路径里的 ``{id}`` 当通配处理."""
    for live_path, live_method in routes:
        if live_method != method:
            continue
        if _path_to_regex(live_path).match(path):
            return True
    return False


# 已知的后端缺口 —— pathMap 里有这条规则, 但后端确实没实现.
#
# 列出来而不是悄悄放过, 是为了让"新增的漂移"能立刻失败; 每条都要写清楚
# 为什么, 以及将来怎么处理. 后端补上之后, 从这里删掉即可.
KNOWN_BACKEND_GAPS: dict[tuple[str, str], str] = {
    (
        "POST",
        "/api/release-approvals",
    ): "后端没有创建审批的端点 —— 审批由 agent runtime 内部创建 "
    "(approval_factory), 后端只暴露列表/通过/拒绝. 前端目前没有 UI 调这个端点.",
}


@pytest.mark.contract
def test_path_map_rules_point_at_real_backend_routes(
    live_routes: set[tuple[str, str]],
) -> None:
    """每条声明了 backendPath 的规则, 后端必须真的有那个 (路径, 方法) 端点."""
    missing: list[str] = []
    for key, method, backend_path, unmatched in _rules():
        if unmatched or not backend_path:
            continue
        if (method, key) in KNOWN_BACKEND_GAPS:
            continue
        if not _route_exists(live_routes, backend_path, method):
            missing.append(f"{method} {key} -> {backend_path}")
    assert not missing, (
        "pathMap 里这些规则指向的后端端点不存在:\n  "
        + "\n  ".join(missing)
        + "\n(要么后端改了路径, 要么这条规则该标成 unmatched: true)"
    )


@pytest.mark.contract
def test_path_map_unmatched_rules_stay_phantom(
    live_routes: set[tuple[str, str]],
) -> None:
    """标了 unmatched 的端点, 后端不能已经实现了 —— 那会让"未接入"变成谎报."""
    stale: list[str] = []
    for key, method, _backend_path, unmatched in _rules():
        if not unmatched:
            continue
        # unmatched 规则的 backendPath 是空串, 拿 key 本身去查.
        if _route_exists(live_routes, key, method):
            stale.append(f"{method} {key}")
    assert not stale, (
        "pathMap 里这些端点标成了 unmatched, 但后端其实已经实现了:\n  "
        + "\n  ".join(stale)
        + "\n(把它们改成正常的 backendPath 规则)"
    )


@pytest.mark.contract
def test_path_map_has_rules(live_routes: set[str]) -> None:
    """路径表不能被清空 —— 那样等于绕过了上面两条检查."""
    assert len(_rules()) > 0
