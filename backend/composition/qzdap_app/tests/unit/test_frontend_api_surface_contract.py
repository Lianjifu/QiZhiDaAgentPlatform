"""Contract: 前端真实发起的每一个 API 调用, 后端都必须有对应端点.

已有 ``test_frontend_pathmap_contract.py`` 守的是**翻译表**那一侧 ——
``pathMap.ts`` 里声明了 ``backendPath`` 的规则, 那个路径必须真存在.

但翻译表只覆盖了「前端路径 ≠ 后端路径」的那些调用. 前端绝大多数管理端
调用是**原样透传**的 (``/api/admin/...`` → ``/api/admin/...``), 它们**根本
不进翻译表** —— 于是「前端调了、后端没有」这一类漂移没人守.

本文件补上这一侧:

1. 扫 ``frontend/web/src`` 下所有真实调用点(排除测试夹具与 mock handler),
   抽出 (方法, 路径);
2. 路径**不走翻译表**的那些, 必须原样存在于后端 OpenAPI 里;
3. 走翻译表的那些交给 ``test_frontend_pathmap_contract.py`` 守, 这里跳过.

每个已知缺口写进 ``KNOWN_GAPS``, 附理由 —— 后端补上后从表里删掉即可.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from qzdap.composition.main import create_app

_REPO_ROOT = Path(__file__).resolve().parents[4]
_WEB_SRC = _REPO_ROOT.parent / "frontend" / "web" / "src"
_PATH_MAP = _REPO_ROOT.parent / "frontend" / "packages" / "api" / "src" / "pathMap.ts"

# mock handler / 夹具 / 单测里的路径不是真实调用 —— 不算漂移.
_SKIP_FILE = re.compile(
    r"(\.test\.|\.spec\.|mock-handler|fixtures?\.[tj]sx?$|/mock\.[tj]s$|__tests__)"
)
# 路径字面量: '/api/xxx' | "/api/xxx" | `/api/xxx/${id}/yyy`
_LITERAL = re.compile(r"""(?P<q>['"`])(?P<path>/api/[^'"`\s]*)(?P=q)""")
# 拼接式: '/api/a/' + encodeURIComponent(vars.id) + '/b'
_CONCAT = re.compile(
    r"""(?P<q>['"`])(?P<path>/api/[^'"`\s]*)(?P=q)\s*\+\s*"""
    r"""(?:encodeURIComponent\([^()]*\)|String\([^()]*\)|`[^`]*`|'[^']*'|"[^"]*")"""
)
# 赋值的路径基址: const PATH = '/api/admin/knowledge' —— 后面靠 ${PATH} 拼,
# 单独看不是一次调用.
_CONST = re.compile(r"""const\s+([A-Za-z_$][\w$]*)\s*=\s*['"](/api/[^'"]*)['"]""")
# 模板字面量: `${PATH}/kbs/__batch__`
_TEMPLATE = re.compile(r"`(?P<body>[^`\n]*\$\{[^`\n]*)`")
# 注释行里的路径不是调用.
_COMMENT_LINE = re.compile(r"^\s*(//|\*|/\*)")
# pathMap 的规则条目 —— 形状与 pathMap.ts 一致
_RULE_RE = re.compile(
    r"\{\s*key:\s*'(?P<key>[^']+)'\s*,\s*rule:\s*\{(?P<rule>[^}]*)\}\s*\}",
    re.DOTALL,
)
_BACKEND_PATH_RE = re.compile(r"backendPath:\s*'(?P<path>[^']*)'")


def _segments(path: str) -> list[str]:
    """把路径切成段 —— 段里的 ``{x}`` / ``:id`` 视为占位符."""
    out: list[str] = []
    for seg in path.split("/"):
        if not seg:
            continue
        out.append(seg)
    return out


def _is_placeholder(seg: str) -> bool:
    """段里带占位符就算 —— ``{id}`` / ``:id`` / ``batch-${action}`` 都算."""
    return seg.startswith("{") or seg.startswith(":") or "${" in seg or "{" in seg


def _canonical(path: str) -> tuple[str, ...]:
    """规范化路径 —— 去掉查询串, 占位符统一成 ``{}``."""
    path = path.split("?", 1)[0]
    segs = []
    for seg in _segments(path):
        if "${" in seg or seg.startswith(":") or (seg.startswith("{") and seg.endswith("}")):
            segs.append("{x}")
        else:
            segs.append(seg)
    return tuple(segs)


def _matches(frontend: tuple[str, ...], backend: tuple[str, ...]) -> bool:
    """前端路径能否落在后端某个路径上（占位符段互通）.

    两边都当占位符处理 —— 前端的 ``${action}`` 这类动态段, 只要后端有**某个**
    同形端点就算有（``batch-${action}`` 落到 ``batch-triage`` 上 ✓）。
    """
    if len(frontend) != len(backend):
        return False
    return all(
        f == b or _is_placeholder(f) or _is_placeholder(b)
        for f, b in zip(frontend, backend, strict=True)
    )


def _normalize_expr(expr: str) -> str:
    """把一个路径表达式压成一条路径 —— 拼接、模板、包装函数全部归一."""
    expr = re.sub(r"encodeURIComponent\([^()]*\)", "{x}", expr)
    expr = re.sub(r"String\([^()]*\)", "{x}", expr)
    expr = re.sub(r"\$\{[^}]*\}", "{x}", expr)
    expr = re.sub(r"""['"`]""", "", expr)
    expr = expr.replace("+", "")
    # 归一后可能连成 ``/api/a{x}`` —— 那才补分隔；``batch-{x}`` 这种
    # 「同一段里的后半截」不能补（补了段数就错了）。
    expr = re.sub(r"(?<=[A-Za-z0-9_])\{x\}", "/{x}", expr)
    return expr


def _frontend_paths() -> set[str]:
    """前端真实调用过的 API 路径（原始写法, 未经归一）.

    三种写法都要认:
    - 字面量 ``'/api/xxx'``
    - 拼接 ``'/api/a/' + encodeURIComponent(vars.id) + '/b'``
    - 模板 `` `${PATH}/kbs/__batch__` `` —— ``PATH`` 是文件里声明的基址常量

    注释行与「被当作基址用的常量」不算调用 —— 前者不是代码, 后者的完整
    路径由模板拼出来（基址本身不是一个端点）。
    """
    found: set[str] = set()
    for file in sorted(_WEB_SRC.rglob("*")):
        if file.suffix not in {".ts", ".tsx"} or not file.is_file():
            continue
        if _SKIP_FILE.search(file.as_posix()):
            continue
        text = file.read_text(encoding="utf-8")
        code = "\n".join(line for line in text.splitlines() if not _COMMENT_LINE.match(line))

        consts = dict(_CONST.findall(code))
        base_names = {name for name in consts if f"${{{name}}}" in code}

        for match in _CONCAT.finditer(code):
            found.add(match.group("path"))
        for match in _LITERAL.finditer(code):
            path = match.group("path")
            # 基址常量本身不是端点 —— 模板里拼出来的完整路径才是.
            if path in consts.values() and any(f"${{{name}}}" in code for name in base_names):
                continue
            found.add(path)
        for template in _TEMPLATE.finditer(code):
            resolved = _resolve_template(template.group("body"), consts)
            if resolved.startswith("/api/"):
                found.add(resolved)
    return found


def _resolve_template(body: str, consts: dict[str, str]) -> str:
    """把 ``${PATH}/kbs`` 里的常量替换掉 —— 未知变量一律当占位符."""

    def repl(match: re.Match[str]) -> str:
        name = match.group(1)
        return consts.get(name, "{x}")

    return re.sub(r"\$\{([^}]*)\}", repl, body)


def _path_map_rules() -> list[tuple[tuple[str, ...], str]]:
    """pathMap 的 (key, backendPath) —— key 已规范化."""
    if not _PATH_MAP.exists():  # pragma: no cover — 仓库布局变了
        return []
    text = _PATH_MAP.read_text(encoding="utf-8")
    out: list[tuple[tuple[str, ...], str]] = []
    for match in _RULE_RE.finditer(text):
        key = _canonical(match.group("key"))
        path_match = _BACKEND_PATH_RE.search(match.group("rule"))
        out.append((key, path_match.group("path") if path_match else ""))
    # 长前缀优先 —— 与前端 translateApiPath 的顺序一致
    out.sort(key=lambda item: len(item[0]), reverse=True)
    return out


def _covered_by_path_map(path: tuple[str, ...], rules: list[tuple[tuple[str, ...], str]]) -> bool:
    """这个前端路径是不是走了翻译表（走后端由另一个契约测试守）."""
    for key, _backend_path in rules:
        if len(key) != len(path):
            continue
        if all(k == p or _is_placeholder(k) for k, p in zip(key, path, strict=True)):
            return True
    return False


# 已知缺口 —— 前端真的在调、后端确实没有. 每条写清楚为什么.
KNOWN_GAPS: dict[str, str] = {
    "/api/admin/skills/example": "前端单测用的假路径（api-client.test.ts），不是真实调用.",
}


@pytest.fixture(scope="module")
def live_routes() -> set[tuple[str, ...]]:
    """后端真实存在的路径集合."""
    app = create_app()
    return {_canonical(path) for path in app.openapi().get("paths", {})}


@pytest.mark.contract
def test_frontend_calls_have_backend_routes(live_routes: set[tuple[str, ...]]) -> None:
    """前端真实调用的路径 —— 不走翻译表的那些必须在后端存在."""
    rules = _path_map_rules()
    missing: list[str] = []
    for raw in sorted(_frontend_paths()):
        path = _canonical(_normalize_expr(raw))
        if path in {_canonical(k) for k in KNOWN_GAPS}:
            continue
        if _covered_by_path_map(path, rules):
            continue
        if not any(_matches(path, live) for live in live_routes):
            missing.append(raw)
    assert not missing, (
        "前端调用了但后端没有这些端点:\n  "
        + "\n  ".join(missing)
        + "\n(要么后端补端点, 要么前端改调已存在的端点)"
    )


@pytest.mark.contract
def test_frontend_scan_finds_any_paths(live_routes: set[tuple[str, ...]]) -> None:
    """扫描器本身不能空转 —— 否则上面的检查形同虚设."""
    assert len(_frontend_paths()) > 20
