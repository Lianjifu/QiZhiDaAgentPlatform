"""架构测试 —— Session 层的边界（Session 方案 §13.2）。

**边界判据**：Session 层管**会话生命周期**（建 / 查回 / 关 / 归档 / 轮次状态
机），但**不引框架**、**不反向依赖模块**。

**为什么要有这些测试**：架构退化是**静默的** —— 代码照样跑、单测照样绿，
只是「分层」这件事慢慢失效了。因此它必须是一条**会红**的检查。

⚠️ **§13.2 的规则 1 与规则 2 已经落地** ✓（2026-10-31 ✓）——

| 规则 | 判据 | 测试 |
|---|---|---|
| 1 | **只有一个 turn 实现** ✓ | `test_there_is_exactly_one_turn_implementation` |
| 2 | **状态机是唯一的状态写入点** ✓ | `test_the_state_machine_is_the_only_turn_status_writer` |
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

# ── 被禁的框架依赖 ────────────────────────────────────────────────────────
FORBIDDEN = ("fastapi", "starlette", "sqlalchemy", "asyncpg", "psycopg")

#: Session 契约所在的包（相对 backend/）。
SESSION_PKG = "runtimes/agent_runtime/src/qzdap_agent_runtime/session"

#: **唯一**的 turn 实现所在文件（相对 backend/）✓ —— 契约层 ✓。
CANONICAL_TURN_IMPL = "runtimes/agent_runtime/src/qzdap_agent_runtime/session/turn_runner.py"

#: **转调**可以碰的东西 —— 碰了这些就是「自己又实现了一遍」✗✗。
TURN_IMPL_PRIMITIVES = frozenset(
    {
        "AgentLoopRunner",
        "SessionGraphRunner",
        "TurnExecutorPort",
        "CompiledStateGraph",
        "create_react_agent",
        "astream",
        "ainvoke",
    }
)

#: 状态机允许的写法 ✓（§13.2 规则 2 ✓）—— 写点必须用其中之一 ✓。
STATE_MACHINE_NAMES = frozenset(
    {
        "plan_turn_transition",
        "turn_status_of",
        "assert_turn_transition",
        "TurnStatus",
    }
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


def _production_files() -> list[Path]:
    """**生产代码** ✓ —— 测试 / 迁移 / 虚拟环境不算 ✓。"""
    out: list[Path] = []
    for path in _backend_root().rglob("*.py"):
        text = str(path)
        if "/.venv/" in text or "/tests/" in text or "/migrations/" in text:
            continue
        out.append(path)
    return sorted(out)


def _parse(path: Path) -> ast.Module | None:
    try:
        return ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError:  # pragma: no cover - 语法错误由别处拦
        return None


def _names_in(node: ast.AST) -> set[str]:
    """节点里用到的名字（``Name.id`` + ``Attribute.attr``）✓。"""
    names: set[str] = set()
    for child in ast.walk(node):
        if isinstance(child, ast.Name):
            names.add(child.id)
        elif isinstance(child, ast.Attribute):
            names.add(child.attr)
    return names


def _is_turn_update(node: ast.AST) -> bool:
    """这段表达式里有没有 ``update(SessionTurnORM)`` ✓。"""
    for child in ast.walk(node):
        if not isinstance(child, ast.Call):
            continue
        func = child.func
        if not (isinstance(func, ast.Name) and func.id == "update"):
            continue
        if any(isinstance(arg, ast.Name) and arg.id == "SessionTurnORM" for arg in child.args):
            return True
    return False


def _turn_status_write_lines(tree: ast.Module) -> list[int]:
    """**写轮次状态的行** ✓ —— 三种写法 ✓。

    1. ``SessionTurnORM(status=...)`` ✓（建行 ✓）；
    2. ``update(SessionTurnORM)....values(status=...)`` ✓（改行 ✓）；
    3. 裸 SQL 里的 ``UPDATE session_turns ... SET status`` ✓。
    """
    lines: list[int] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.id if isinstance(func, ast.Name) else ""
        if name == "SessionTurnORM" and any(kw.arg == "status" for kw in node.keywords):
            lines.append(node.lineno)
        elif name == "text":
            for arg in node.args:
                if not (isinstance(arg, ast.Constant) and isinstance(arg.value, str)):
                    continue
                sql = " ".join(arg.value.lower().split())
                if "update session_turns" in sql and "set status" in sql:
                    lines.append(node.lineno)
        elif (
            isinstance(func, ast.Attribute)
            and func.attr == "values"
            and any(kw.arg == "status" for kw in node.keywords)
            and _is_turn_update(func.value)
        ):
            lines.append(node.lineno)
    return sorted(lines)


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


def test_there_is_exactly_one_turn_implementation() -> None:
    """§13.2 的规则 1 —— **只有一个 turn 实现** ✓。

    判据 ✓：生产代码里 ``run_turn`` / ``_run_turn`` 的**定义**只能落在契约层
    的 ``turn_runner.py`` ✓ —— 其他地方（IM 通道、子智能体、评测）**只能转调**
    ✓ —— 一旦它们自己碰了轮次编排（agent loop / graph / 执行器）✓ 就是
    「第二套 turn 实现」✗✗ → 这条测试会红 ✓。
    """
    definitions: list[str] = []
    second_implementations: list[str] = []
    for path in _production_files():
        tree = _parse(path)
        if tree is None:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if node.name not in {"run_turn", "_run_turn"}:
                continue
            where = f"{_rel(path)}:{node.lineno}"
            if _rel(path) == CANONICAL_TURN_IMPL:
                definitions.append(where)
                continue
            used = sorted(_names_in(node) & TURN_IMPL_PRIMITIVES)
            if used:
                second_implementations.append(f"{where} → {used}")
    assert [d.split(":")[0] for d in definitions] == [CANONICAL_TURN_IMPL], (
        f"turn 实现不止一处：{definitions}"
    )
    assert not second_implementations, "别处又实现了一遍 turn：\n" + "\n".join(
        second_implementations
    )


def test_the_old_turn_use_cases_are_gone() -> None:
    """旧的 ``use_cases/run_turn*.py`` **必须不存在** ✓（方案 Stage 6 ✓）。

    留着它 = 两套实现并存 ✗✗ —— 哪怕新的一套是对的 ✗。
    """
    offenders = [
        _rel(path) for path in _backend_root().rglob("run_turn*.py") if "/.venv/" not in str(path)
    ]
    assert not offenders, f"旧的 turn 用例还在：{offenders}"


def test_the_state_machine_is_the_only_turn_status_writer() -> None:
    """§13.2 的规则 2 —— **状态机是唯一的状态写入点** ✓。

    判据 ✓：生产代码里**写** ``session_turns.status`` 的地方（建行 / 改行 /
    裸 SQL 三种写法 ✓）**必须**用状态机的词表与判定 ✓
    （``TurnStatus`` / ``plan_turn_transition`` ✓）—— 状态词表散落在各处
    = 迟早出现「表里有的状态、状态机里没有」✗✗。
    """
    offenders: list[str] = []
    for path in _production_files():
        tree = _parse(path)
        if tree is None:
            continue
        lines = _turn_status_write_lines(tree)
        if not lines:
            continue
        names = _names_in(tree)
        imports_state = any(
            name.startswith("qzdap_agent_runtime.session.state") for name in _imported_modules(path)
        )
        if imports_state and names & STATE_MACHINE_NAMES:
            continue
        offenders.append(f"{_rel(path)}:{lines}")
    assert not offenders, "轮次状态的写入点没走状态机：\n" + "\n".join(offenders)
