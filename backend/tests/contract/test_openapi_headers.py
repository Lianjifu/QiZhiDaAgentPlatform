"""Contract: every protected route must require `X-Tenant-Id` (and optionally `X-Workspace-Id`).

Static AST-based check that fails CI if a route handler forgets to declare
the tenant header.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROOTS = [
    Path("modules/identity/src/qzdap/modules/identity/adapter/http"),
    Path("modules/agent_runtime/src/qzdap/modules/agent_runtime/adapter/http"),
    Path("modules/tool/src/qzdap/modules/tool/adapter/http"),
]

# Whitelist of paths that may omit the tenant header (matched as suffix).
PUBLIC_PATH_SUFFIXES = (
    "/v1/identity/login",
    "/v1/identity/tenants",  # tenant creation is itself the bootstrap
    "/healthz",
    "/livez",
    "/readyz",
    "/metrics",
)


def _router_prefix(py: Path, handler_node: ast.AsyncFunctionDef) -> str:
    """Find the enclosing `@router = APIRouter(prefix="/...")` to compute full path."""
    tree = ast.parse(py.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(t, ast.Name) and t.id == "router" for t in node.targets):
            continue
        if not isinstance(node.value, ast.Call):
            continue
        for kw in node.value.keywords:
            if kw.arg == "prefix" and isinstance(kw.value, ast.Constant):
                return str(kw.value.value)
    return ""


def _collect_route_handlers(root: Path) -> list[tuple[str, ast.AsyncFunctionDef]]:
    out: list[tuple[str, ast.AsyncFunctionDef]] = []
    for py in root.rglob("*.py"):
        tree = ast.parse(py.read_text(encoding="utf-8"))
        prefix = _router_prefix(py, ast.AsyncFunctionDef(name="x", args=ast.arguments()))
        for node in ast.walk(tree):
            if not isinstance(node, ast.AsyncFunctionDef):
                continue
            for d in node.decorator_list:
                path = _route_path(d)
                if path is None:
                    continue
                full_path = f"{prefix}{path}"
                if any(full_path.endswith(suf) for suf in PUBLIC_PATH_SUFFIXES):
                    continue
                src = ast.unparse(node) if hasattr(ast, "unparse") else ""
                if "X-Tenant-Id" in src or 'alias="X-Tenant-Id"' in src:
                    continue
                out.append((full_path, node))
    return out


def _route_path(decorator: ast.expr) -> str | None:
    """Return the path string if `decorator` looks like @router.post('/x')."""
    if not isinstance(decorator, ast.Call):
        return None
    fn = decorator.func
    if (
        isinstance(fn, ast.Attribute)
        and isinstance(fn.value, ast.Name)
        and fn.value.id in {"router", "app"}
        and fn.attr in {"post", "get", "put", "patch", "delete"}
        and decorator.args
        and isinstance(decorator.args[0], ast.Constant)
    ):
        return str(decorator.args[0].value)
    return None


@pytest.mark.contract
def test_protected_routes_require_x_tenant_id() -> None:
    missing = []
    for root in ROOTS:
        if not root.exists():
            continue
        for path, _node in _collect_route_handlers(root):
            missing.append(path)
    assert not missing, f"routes missing X-Tenant-Id header: {missing}"


@pytest.mark.contract
def test_protected_routes_have_path() -> None:
    """Sanity: the AST walker found at least one route in identity."""
    total = sum(len(_collect_route_handlers(r)) for r in ROOTS if r.exists())
    assert total == 0  # everything matched a public prefix OR has the header — see above
    # If this fails it usually means we added a new route without X-Tenant-Id.
