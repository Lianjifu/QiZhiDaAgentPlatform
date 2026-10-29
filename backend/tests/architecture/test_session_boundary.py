"""架构测试 —— Session 层的边界（Session 方案 §13.2）。

**边界判据**：Session 层管**会话生命周期**（建 / 查回 / 关 / 归档 / 轮次状态
机），但**不引框架**、**不反向依赖模块**。

**为什么要有这些测试**：架构退化是**静默的** —— 代码照样跑、单测照样绿，
只是「分层」这件事慢慢失效了。因此它必须是一条**会红**的检查。

⚠️ **本轮只落能判真的规则**：§13.2 的规则 1（「只有一个 turn 实现」）与
规则 2（「状态机是唯一的状态写入点」）依赖 Stage 3 的唯一 turn 实现 ——
现在跑必然红（``copilot.py`` 与 ``use_cases/run_turn*.py`` 两套都在），
故**不在本文件里假实现**，见 ``session-refactor-plan.md`` 的 Stage 3。
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

# ── 被禁的框架依赖 ────────────────────────────────────────────────────────
FORBIDDEN = ("fastapi", "starlette", "sqlalchemy", "asyncpg", "psycopg")

#: Session 契约所在的包（相对 backend/）。
SESSION_PKG = "runtimes/agent_runtime/src/qzdap_agent_runtime/session"


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


def test_the_session_package_exists() -> None:
    """Session 契约层必须在约定的位置（方案 §7.1）。"""
    assert _py_files(SESSION_PKG), "Session 包不存在 —— 契约层被挪走了？"


def test_session_layer_has_no_framework_imports() -> None:
    """Session 层不得依赖框架（§13.2 的架构测试）。"""
    violations: list[str] = []
    for path in _py_files(SESSION_PKG):
        bad = sorted(name for name in _imported_modules(path) if name.split(".")[0] in FORBIDDEN)
        if bad:
            violations.append(f"{_rel(path)}: {bad}")
    assert not violations, "Session 层引入了框架依赖：\n" + "\n".join(violations)


def test_the_session_package_does_not_depend_on_modules() -> None:
    """依赖方向只能是「模块 → 契约」—— 契约层不反向依赖模块。"""
    violations: list[str] = []
    for path in _py_files(SESSION_PKG):
        names = _imported_modules(path)
        if any(name.startswith("qzdap.modules") for name in names):
            violations.append(f"{_rel(path)}: {sorted(names)}")
    assert not violations, "Session 契约层反向依赖了模块：\n" + "\n".join(violations)


def test_the_sync_postgres_saver_is_never_imported() -> None:
    """§13.2 的规则 3 —— **同步** saver 会阻塞事件循环（§5.3）。

    只允许 ``langgraph.checkpoint.postgres.aio``。
    """
    offenders: list[str] = []
    for path in _backend_root().rglob("*.py"):
        if "/.venv/" in str(path) or "/tests/" in str(path):
            continue
        text = path.read_text(encoding="utf-8")
        if "langgraph.checkpoint.postgres" not in text:
            continue
        for match in re.finditer(
            r"from\s+(langgraph\.checkpoint\.postgres[\w.]*)\s+import|"
            r"import\s+(langgraph\.checkpoint\.postgres[\w.]*)",
            text,
        ):
            module = match.group(1) or match.group(2)
            if not module.endswith(".aio"):
                offenders.append(f"{_rel(path)}: {module}")
    assert not offenders, "引入了同步 checkpoint saver：\n" + "\n".join(offenders)


def test_the_session_status_has_exactly_one_definition() -> None:
    """会话状态**只有一处定义**（契约层）—— 模块层只做**再导出**。

    旧路径里模块领域自己定义过一个 2 值的 ``SessionStatus``（``open`` /
    ``closed``），落后于表的 check constraint（还有 ``running`` /
    ``waiting_approval`` / ``cancelled``）—— 领域枚举落后于 schema = 状态
    烂在数据里 ✗。
    """
    definitions: list[str] = []
    for path in _backend_root().rglob("*.py"):
        if "/.venv/" in str(path) or "/tests/" in str(path):
            continue
        text = path.read_text(encoding="utf-8")
        if re.search(r"^class\s+SessionStatus\b", text, re.MULTILINE):
            definitions.append(_rel(path))
    assert definitions == ["runtimes/agent_runtime/src/qzdap_agent_runtime/session/state.py"], (
        f"SessionStatus 的定义不止一处：{definitions}"
    )


def test_the_domain_module_only_reexports_the_canonical_session_status() -> None:
    """模块领域层**再导出**契约的状态，不重新定义（§7.1 的单一真相）。"""
    path = (
        _backend_root() / "modules/agent_runtime/src/qzdap/modules/agent_runtime/domain/entities.py"
    )
    text = path.read_text(encoding="utf-8")
    assert "class SessionStatus" not in text, "模块层重新定义了 SessionStatus"
    assert "qzdap_agent_runtime.session.state import SessionStatus" in text, (
        "模块层没有再导出契约层的 SessionStatus"
    )
