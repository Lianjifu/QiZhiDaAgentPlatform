"""架构测试 —— Gateway 层的边界（Gateway 方案 §11.2）。

**边界判据**（§2.1）：runtime 层与各模块的**应用层**不得依赖框架；
Gateway 只持端口，**不反向依赖模块**。

**为什么要有这条测试**：架构退化是**静默的** —— 代码照样编译、单测照样绿，
只是「分层」这件事慢慢失效了。因此它必须是一条**会红**的检查。
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

# ── 被禁的框架依赖 ────────────────────────────────────────────────────────
FORBIDDEN = ("fastapi", "starlette", "sqlalchemy", "asyncpg", "psycopg")

#: 受检目录（相对 backend/）。
#:
#: ⚠️ ``runtimes/`` 下**不止**契约层：``embedding_runtime`` / ``sandbox_runtime``
#: 是**独立的 FastAPI 服务**（自带 app / routes），引框架是它们的本职 ✓。
#: 契约层是 ``runtimes/agent_runtime/src``（Gateway 契约 + 会话/运行时层 ✓）。
SCAN_DIRS = (
    "runtimes/agent_runtime/src",
    "modules/agent_runtime/src/qzdap/modules/agent_runtime/application",
    "modules/memory/src/qzdap/modules/memory/application",
    "modules/knowledge/src/qzdap/modules/knowledge/application",
)

#: Gateway 契约所在的包（**不得**反向依赖模块）。
GATEWAY_PKG = "runtimes/agent_runtime/src/qzdap_agent_runtime/gateway"

#: **已知豁免** —— 每条都要写明「为什么还在」+「归谁清理」。
#:
#: ⚠️ 豁免表**只能变短**：新增一条必须同时说明为什么不能当场修；
#: 旧实现删掉后**必须**从表里移除（否则豁免会变成永久的通融）。
KNOWN_EXEMPTIONS: dict[str, str] = {
    "modules/agent_runtime/src/qzdap/modules/agent_runtime/application/use_cases/delegate_subagent.py": (
        "子代理委派用例直接写了 SQL（应用层引框架）。"
        "归属 **Session Stage 5b** —— 它调用的是第二套 turn 实现（X2），"
        "随那一套一起删。"
    ),
}


def _backend_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _py_files(rel_dir: str) -> list[Path]:
    root = _backend_root() / rel_dir
    if not root.exists():
        return []
    return sorted(p for p in root.rglob("*.py") if "/tests/" not in str(p))


def _imported_modules(path: Path) -> set[str]:
    """该文件**直接** import 的顶层模块名。"""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError:  # pragma: no cover - 语法错误的文件由别处拦
        return set()
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names.add(node.module.split(".")[0])
    return names


def _rel(path: Path) -> str:
    return str(path.relative_to(_backend_root()))


@pytest.mark.parametrize("rel_dir", SCAN_DIRS)
def test_no_framework_imports_in_runtime_and_application_layers(rel_dir: str) -> None:
    """runtime 层与应用层**不得**依赖框架（§2.1 的边界判据）。"""
    violations: list[str] = []
    for path in _py_files(rel_dir):
        if _rel(path) in KNOWN_EXEMPTIONS:
            continue
        bad = sorted(_imported_modules(path) & set(FORBIDDEN))
        if bad:
            violations.append(f"{_rel(path)}: {bad}")
    assert not violations, "应用层/runtime 层引入了框架依赖：\n" + "\n".join(violations)


def test_the_known_exemptions_are_still_needed() -> None:
    """豁免表**不许有陈旧条目** —— 旧实现删了就必须把豁免删掉。"""
    stale = [
        rel
        for rel in KNOWN_EXEMPTIONS
        if not (_backend_root() / rel).exists()
    ]
    assert not stale, "豁免表里有已经不存在的文件（请移除豁免）：\n" + "\n".join(stale)


def test_the_gateway_package_does_not_depend_on_modules() -> None:
    """Gateway **不反向依赖模块** —— 依赖方向只能是「模块 → Gateway 契约」。

    Gateway 住在 ``runtimes/`` 里（它是**契约**的所在地）；若它反过来 import
    ``qzdap.modules.*``，依赖方向就拧了 —— 契约层会被具体实现拖住。
    """
    violations: list[str] = []
    for path in _py_files(GATEWAY_PKG):
        names = _imported_modules(path)
        if any(name.startswith("qzdap") and "modules" in name for name in names):
            violations.append(f"{_rel(path)}: {sorted(names)}")
    assert not violations, "Gateway 反向依赖了模块：\n" + "\n".join(violations)


def test_the_gateway_package_has_no_framework_imports() -> None:
    """Gateway 是**无框架**的契约层（§2.2）。"""
    violations: list[str] = []
    for path in _py_files(GATEWAY_PKG):
        bad = sorted(_imported_modules(path) & set(FORBIDDEN))
        if bad:
            violations.append(f"{_rel(path)}: {bad}")
    assert not violations, "Gateway 引入了框架依赖：\n" + "\n".join(violations)
