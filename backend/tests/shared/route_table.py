"""路由表工具 —— 把 FastAPI 的路由摊平成 ``(路径, 方法)`` 列表.

为什么不能直接遍历 ``app.routes``: 这个 FastAPI 版本 (0.141) 把
``include_router`` 包成 ``_IncludedRouter``, 路由是**延迟**挂载的 ——
``route.path`` 上只有局部路径 (``/login`` 而不是 ``/v1/identity/login``),
前缀要等匹配时才补上. 遍历 ``app.routes`` 会拿到一张**错的**路径表.

``app.openapi()["paths"]`` 是运行时真正对外暴露的那份, 但它只有路径和
方法, 拿不到依赖图. 这里把两者结合: 递归展开 ``_IncludedRouter``, 得到
``(完整路径, 方法, 依赖图)``, 既能跟 OpenAPI 对账, 也能看出某个路由
声明了哪些依赖.
"""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass, field
from typing import Any

from fastapi.routing import APIRoute
from starlette.routing import Route


@dataclass(frozen=True)
class RouteInfo:
    path: str
    method: str
    #: 依赖图里所有依赖函数的 ``__name__`` (含嵌套).
    dependencies: frozenset[str] = field(default_factory=frozenset)

    @property
    def key(self) -> tuple[str, str]:
        return (self.path, self.method)


def _is_included_router(obj: Any) -> bool:
    # 不 import FastAPI 的私有类 —— 它每个版本都可能改名.
    return hasattr(obj, "original_router") and hasattr(obj, "include_context")


def _dependency_names(dependant: Any) -> frozenset[str]:
    names: set[str] = set()

    def walk(dep: Any) -> None:
        for sub in getattr(dep, "dependencies", []) or []:
            call = getattr(sub, "call", None)
            names.add(getattr(call, "__name__", str(call)))
            walk(sub)

    walk(dependant)
    return frozenset(names)


def _walk(router: Any, prefix: str, out: list[RouteInfo]) -> None:
    for route in getattr(router, "routes", []) or []:
        if _is_included_router(route):
            ctx = route.include_context
            _walk(route.original_router, prefix + (getattr(ctx, "prefix", "") or ""), out)
            continue
        if isinstance(route, APIRoute):
            for method in sorted(route.methods or []):
                if method in {"HEAD", "OPTIONS"}:
                    continue
                out.append(
                    RouteInfo(
                        path=prefix + route.path,
                        method=method,
                        dependencies=_dependency_names(route.dependant),
                    )
                )
            continue
        if isinstance(route, Route):
            # Starlette 的原生路由 (FastAPI 自带的 /docs /openapi.json 等).
            for method in sorted(route.methods or {"GET"}):
                if method in {"HEAD", "OPTIONS"}:
                    continue
                out.append(RouteInfo(path=prefix + route.path, method=method))
            continue
        # Starlette Mount / Router —— 继续往下走.
        sub_prefix = prefix + (getattr(route, "path", "") or "")
        _walk(route, sub_prefix, out)


def route_table(app: Any) -> list[RouteInfo]:
    """返回应用的全部 ``(路径, 方法)`` 路由及其依赖图."""
    out: list[RouteInfo] = []
    _walk(app, "", out)
    return out


def public_path_patterns(raw: str) -> list[str]:
    """把逗号分隔的公开端点配置拆成 pattern 列表."""
    return [p.strip() for p in raw.split(",") if p.strip()]


def pattern_matches(pattern: str, path: str) -> bool:
    """带 ``*`` 的是 glob 规则, 其余按精确路径匹配.

    语义必须和 ``qzdap_http.middleware.AuthRequiredMiddleware`` 里那份
    **完全一致** —— 否则测试守的是一个跟运行时不是一回事的规则.
    """
    if "*" in pattern:
        return fnmatch.fnmatchcase(path, pattern)
    return path == pattern


def covered_routes(patterns: list[str], routes: list[RouteInfo]) -> list[RouteInfo]:
    """被公开端点规则覆盖到的路由."""
    return [r for r in routes if any(pattern_matches(p, r.path) for p in patterns)]


__all__ = [
    "RouteInfo",
    "covered_routes",
    "pattern_matches",
    "public_path_patterns",
    "route_table",
]
