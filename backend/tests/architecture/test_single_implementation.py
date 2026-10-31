"""单实现守卫 —— 「同一关注点不得有两套实现并存」。

**数据源 =** [`implementation-plan.md`](../../docs/refactor/session-architecture/implementation-plan.md)
§1.2 的「关注点 → 唯一实现 → 旧实现 → 归属层 · Stage」表（30 条），
§6.2 是它的落地形态。

**为什么要有它**：台账 §3.1 的 grep 脚本查的是「**某个旧符号还在不在**」——
它回答「删干净了吗」，但答不了「**有没有两套同时存在**」。后者由本守卫负责。

**与 grep 脚本互补**：grep 说「旧的删了没」，本守卫说「新的接管了没」。
**只有两条都绿**，台账的「已清理」判据才成立。

**分批启用**：新旧在「允许并存窗口」内**必然**同时存在（这正是「先上新、
后清旧」）。因此规则**不能**一上来就要求「不得同时存在」—— 它在**窗口关闭**
的那个 Stage 才启用。窗口未关闭的关注点**不在这张表里**（它们还没有守卫）。
"""

from __future__ import annotations

import ast
from pathlib import Path

#: 允许并存窗口**已关闭**的关注点。
#:
#: (关注点名, 新符号, 旧符号, 新符号所在目录)
#:
#: ⚠️ **新窗口关闭时，把那一行加进来** —— 加进来 = 断言「新实现存在、
#: 旧实现不存在」。窗口未关闭的关注点**不要**加（那会让 CI 从第一天起就红）。
CLOSED_CONCERNS: tuple[tuple[str, str, str, str], ...] = (
    (
        "入站归一化",
        "InboundMessage",
        "ParsedMessage",
        "runtimes/agent_runtime/src/qzdap_agent_runtime/gateway",
    ),
    (
        "入站归一化（事件）",
        "InboundMessage",
        "ChannelMessageReceived",
        "runtimes/agent_runtime/src/qzdap_agent_runtime/gateway",
    ),
    (
        "入站去重",
        "IdempotencyGuard",
        "record_request_id",
        "runtimes/agent_runtime/src/qzdap_agent_runtime/gateway",
    ),
    (
        "入站去重（会话元数据）",
        "IdempotencyGuard",
        "recent_request_ids",
        "runtimes/agent_runtime/src/qzdap_agent_runtime/gateway",
    ),
    (
        "身份与鉴权",
        "HmacWebhookVerifier",
        "_verify_signature",
        "runtimes/agent_runtime/src/qzdap_agent_runtime/gateway",
    ),
    (
        "身份与鉴权（硬编码身份）",
        "HmacWebhookVerifier",
        "SYSTEM_USER_ID",
        "runtimes/agent_runtime/src/qzdap_agent_runtime/gateway",
    ),
)

#: 生产包里**已知的** ``InMemory*`` 假实现（基线白名单）。
#:
#: ⚠️ 白名单之外出现任何 ``InMemory*`` 即红 —— 这是「不许新增长孤儿」的闸门。
#: 基线里的每个都会在**对应层的 Stage** 里被删掉（删一个移一个）。
#: （数据源 = 实施方案 §1.5；2026-10-29 核对：self_evolution 的
#: ``InMemoryDraftStore`` 是白名单定稿之后新增的，已补进基线。）
INMEMORY_BASELINE = {
    # ⚠️ **只剩三个** ✓（2026-10-31：Agent Stage 7 把 runtime 里那 16 个
    # 全删了 ✓；当天 Memory C5 的**向量补写队列**是**生产在用**的 ✓ ——
    # 登记进基线 ✓ —— 归属 Memory 层 ✓）。
    "InMemoryOutboxRepository",   # runtime 的 outbox ✓（Session Stage 4b 取用 ✓）
    "InMemoryDraftStore",         # self_evolution 的草稿存储 ✓（归 self_evolution ✓）
    # ⚠️ **Memory 的向量补写队列** ✓（C5 ✓）—— 它是**生产在用**的进程内
    # 有界队列 ✓（组合根起停 ✓ —— **应用级** ✓ 不是每请求一个 ✓）——
    # 队列满了就丢 ✓（不阻塞对话 ✓）+ **兜底补写**捡回来 ✓（丢的不丢向量 ✓）。
    "InMemoryVectorWriteQueue",
}

#: 生产包的受检根（相对 backend/）。
PROD_DIRS = ("runtimes/", "modules/", "libs/", "composition/")


def _backend_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _py_files(rel_dir: str) -> list[Path]:
    root = _backend_root() / rel_dir
    if not root.exists():
        return []
    return sorted(
        p for p in root.rglob("*.py") if "/tests/" not in str(p) and "/tests" not in str(p)
    )


def _symbol_hits(rel_dir: str, symbol: str) -> list[str]:
    """在生产包里找这个符号（按标识符/属性名匹配，不是裸子串）。"""
    hits: list[str] = []
    for path in _py_files(rel_dir):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:  # pragma: no cover
            continue
        for node in ast.walk(tree):
            name = None
            if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                name = node.name
            elif isinstance(node, ast.Name):
                name = node.id
            elif isinstance(node, ast.Attribute):
                name = node.attr
            if name == symbol:
                hits.append(str(path.relative_to(_backend_root())))
                break
    return hits


def test_closed_concerns_have_no_second_implementation() -> None:
    """窗口已关闭的关注点：**新实现存在、旧实现不存在**。"""
    problems: list[str] = []
    for concern, new_sym, old_sym, new_dir in CLOSED_CONCERNS:
        if not _symbol_hits(new_dir, new_sym):
            problems.append(f"关注点『{concern}』：新实现 {new_sym} 不在 {new_dir} —— 接管没落地？")
        old_hits = [
            f"{rel_dir}:{hit}"
            for rel_dir in PROD_DIRS
            for hit in _symbol_hits(rel_dir, old_sym)
        ]
        if old_hits:
            problems.append(f"关注点『{concern}』：旧实现 {old_sym} 仍在 → {old_hits}")
    assert not problems, "存在两套实现：\n" + "\n".join(problems)


def test_no_inmemory_stubs_outside_the_baseline() -> None:
    """生产包不得有【新的】 ``InMemory*`` 假实现（实施方案 §1.5 的规则 R1/R2）。"""
    found: set[str] = set()
    for rel_dir in PROD_DIRS:
        for path in _py_files(rel_dir):
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"))
            except SyntaxError:  # pragma: no cover
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef) and node.name.startswith("InMemory"):
                    found.add(node.name)
    unexpected = sorted(found - INMEMORY_BASELINE)
    assert not unexpected, (
        "生产包里出现了基线之外的 InMemory* 假实现（新增的孤儿）：\n"
        + "\n".join(unexpected)
        + "\n（要么接线，要么把它加进基线并写明归属）"
    )


def test_the_inmemory_baseline_has_no_stale_entries() -> None:
    """基线里的每个 ``InMemory*`` 都得**真的还在**（删了就该移出基线）。"""
    found: set[str] = set()
    for rel_dir in PROD_DIRS:
        for path in _py_files(rel_dir):
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"))
            except SyntaxError:  # pragma: no cover
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef) and node.name.startswith("InMemory"):
                    found.add(node.name)
    stale = sorted(INMEMORY_BASELINE - found)
    assert not stale, "基线里有已经不存在的条目（请移出）：\n" + "\n".join(stale)
