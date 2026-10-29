"""架构测试 —— Router 层的边界（Router 方案 §10.2）。

**边界判据**（§2.1 + §5）：Router 只做两件事 —— **派生会话 key** 与
**选出 agent**。它不碰会话生命周期、不装上下文、不调 LLM、也不引框架。

**为什么要有这些测试**：架构退化是**静默的** —— 代码照样跑、单测照样绿，
只是「分层」这件事慢慢失效了。因此它必须是一条**会红**的检查。
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

# ── 被禁的框架依赖 ────────────────────────────────────────────────────────
FORBIDDEN = ("fastapi", "starlette", "sqlalchemy", "asyncpg", "psycopg")

#: Router 契约所在的包（相对 backend/）。
ROUTER_PKG = "runtimes/agent_runtime/src/qzdap_agent_runtime/router"

#: Router **不得**依赖的包（§10.2 的规则 2 / 3）。
FORBIDDEN_PACKAGES = (
    "qzdap_agent_runtime.context",  # 上下文装配归 Context 层
    "qzdap_llm",  # 模型策略链归 Agent 层的 Execution
)


def _backend_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _py_files(rel_dir: str) -> list[Path]:
    root = _backend_root() / rel_dir
    if not root.exists():
        return []
    return sorted(p for p in root.rglob("*.py") if "/tests/" not in str(p))


def _imported_modules(path: Path) -> set[str]:
    """该文件**直接** import 的模块名（完整的 dotted path）。"""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError:  # pragma: no cover - 语法错误由别处拦
        return set()
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names.add(node.module)
    return names


def _rel(path: Path) -> str:
    return str(path.relative_to(_backend_root()))


def test_the_router_package_exists() -> None:
    """Router 契约层必须在约定的位置（方案 §7.1）。"""
    assert _py_files(ROUTER_PKG), "Router 包不存在 —— 契约层被挪走了？"


def test_router_layer_has_no_framework_imports() -> None:
    """Router 层不得依赖框架（§10.2 的架构测试）。"""
    violations: list[str] = []
    for path in _py_files(ROUTER_PKG):
        bad = sorted(name for name in _imported_modules(path) if name.split(".")[0] in FORBIDDEN)
        if bad:
            violations.append(f"{_rel(path)}: {bad}")
    assert not violations, "Router 层引入了框架依赖：\n" + "\n".join(violations)


def test_router_does_not_touch_context_or_llm() -> None:
    """Router 不装上下文、不调 LLM（§10.2 的规则 2 / 3）。"""
    violations: list[str] = []
    for path in _py_files(ROUTER_PKG):
        names = _imported_modules(path)
        bad = sorted(
            name
            for name in names
            if any(
                name == forbidden or name.startswith(f"{forbidden}.")
                for forbidden in FORBIDDEN_PACKAGES
            )
        )
        if bad:
            violations.append(f"{_rel(path)}: {bad}")
    assert not violations, "Router 越界依赖：\n" + "\n".join(violations)


def test_router_does_not_write_session_lifecycle_fields() -> None:
    """Router 不写会话的生命周期字段（§10.2 的规则 1，决策 #10）。

    **会话的创建/查回归 Session** —— Router 只派生 key、选 agent。
    唯一允许的会话侧写入是它自己的排队列（``next_ingress_seq``）。
    """
    forbidden = (
        r"INSERT\s+INTO\s+agent_sessions",
        r"UPDATE\s+agent_sessions\s+SET\s+[^;]*\bstatus\b",
        r"UPDATE\s+agent_sessions\s+SET\s+[^;]*\bagent_id\b",
        r"UPDATE\s+agent_sessions\s+SET\s+[^;]*\bowner_id\b",
        r"UPDATE\s+agent_sessions\s+SET\s+[^;]*\bcurrent_revision\b",
        r"UPDATE\s+agent_sessions\s+SET\s+[^;]*\bwait_status\b",
    )
    violations: list[str] = []
    for path in _py_files(ROUTER_PKG):
        text = path.read_text(encoding="utf-8")
        for pattern in forbidden:
            if re.search(pattern, text, re.IGNORECASE | re.DOTALL):
                violations.append(f"{_rel(path)}: {pattern}")
    assert not violations, "Router 写了会话的生命周期字段：\n" + "\n".join(violations)


def test_the_router_package_does_not_depend_on_modules() -> None:
    """依赖方向只能是「模块 → 契约」—— Router 不反向依赖模块。"""
    violations: list[str] = []
    for path in _py_files(ROUTER_PKG):
        names = _imported_modules(path)
        if any(name.startswith("qzdap.modules") for name in names):
            violations.append(f"{_rel(path)}: {sorted(names)}")
    assert not violations, "Router 反向依赖了模块：\n" + "\n".join(violations)
