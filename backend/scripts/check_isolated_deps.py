"""**isolated install 检查** ✓ —— 每个包的依赖声明要**完整** ✓。

⚠️ **为什么要有这个守门人**（实施计划 P-02 ✓）—— 某个包 import 了另一个
workspace 包却**没在 pyproject 里声明** ✓ → 开发机上有（整个 workspace 都在
site-packages 里 ✓）→ **装不上** ✓（isolated install 直接
``ModuleNotFoundError`` ✗✗）→ **发布时才炸** ✗✗。

⚠️ **判据只有一个来源** ✓ —— 各包自己的 ``pyproject.toml`` ✓
（不许「反正 workspace 里都有」这种借口 ✓）。

用法::

    python scripts/check_isolated_deps.py           # 检查全部
    python scripts/check_isolated_deps.py --quiet   # 只在失败时输出

退出码：0 = 全过 ✓；1 = 有缺失声明 ✗。
"""

from __future__ import annotations

import argparse
import ast
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
MEMBER_GLOBS = ("libs/*", "modules/*", "runtimes/*", "composition/*")

#: **发行名 → import 名** 的手工映射 ✓ —— 只有这两个包的名字会撞 ✓
#: （``qzdap-agent-runtime`` 是模块 ✓，``qzdap-agent-runtime-runtime`` 是
#: 契约层 runtime ✓ —— 见根 pyproject 的注释 ✓）。
EXTRA_ROOTS = {
    "qzdap-agent-runtime": ("qzdap.modules.agent_runtime",),
    "qzdap-agent-runtime-runtime": ("qzdap_agent_runtime",),
}


@dataclass(frozen=True)
class Member:
    """一个 workspace 包 ✓。"""

    name: str
    path: Path
    distribution: str
    #: **它自己的 import 前缀** ✓（它能提供哪些模块 ✓）。
    roots: tuple[str, ...]
    #: **它声明的依赖** ✓（发行名 ✓）。
    dependencies: frozenset[str]

    def owns(self, module: str) -> bool:
        """这个 import 名是不是它的 ✓。"""
        return any(module == root or module.startswith(f"{root}.") for root in self.roots)


def _normalize_dep(raw: str) -> str:
    """``foo[extra]>=1.0; python_version>'3.9'`` → ``foo`` ✓。"""
    return re.split(r"[\[<>=!~;\s]", raw.strip(), maxsplit=1)[0]


def _import_roots(src: Path) -> tuple[str, ...]:
    """一个包**自己提供**的 import 前缀 ✓。"""
    roots: set[str] = set()
    if not src.is_dir():
        return ()
    for path in src.rglob("__init__.py"):
        rel = path.parent.relative_to(src)
        roots.add(".".join(rel.parts))
    # 没有 ``__init__.py`` 的单文件包 ✓（少见的形态 ✓）。
    for path in src.glob("*.py"):
        if path.name != "__init__.py":
            roots.add(path.stem)
    return tuple(sorted(roots))


def _load_members() -> list[Member]:
    members: list[Member] = []
    for pattern in MEMBER_GLOBS:
        for path in sorted(BACKEND.glob(pattern)):
            pyproject = path / "pyproject.toml"
            if not pyproject.is_file():
                continue
            data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
            distribution = str(data.get("project", {}).get("name") or path.name)
            deps = data.get("project", {}).get("dependencies") or []
            roots = list(_import_roots(path / "src"))
            roots.extend(EXTRA_ROOTS.get(distribution, ()))
            members.append(
                Member(
                    name=path.name,
                    path=path,
                    distribution=distribution,
                    roots=tuple(sorted(set(roots))),
                    dependencies=frozenset(_normalize_dep(d) for d in deps),
                )
            )
    return members


def _imported_modules(path: Path) -> set[str]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError:  # pragma: no cover - 由 CI 的 lint 兜底 ✓
        return set()
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module)
    return names


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--quiet", action="store_true", help="只在失败时输出 ✓")
    args = parser.parse_args()

    members = _load_members()
    violations: list[str] = []
    for member in members:
        src = member.path / "src"
        if not src.is_dir():
            continue
        for py_file in sorted(src.rglob("*.py")):
            for module in _imported_modules(py_file):
                if not module.startswith("qzdap"):
                    continue
                owner = next((m for m in members if m is not member and m.owns(module)), None)
                if owner is None:
                    continue
                # ⚠️ **只管「依赖 lib」的声明** ✓ —— **模块之间的 import** 是
                # **层次问题** ✓（归 import-linter 契约管 ✓ —— 那些契约还没启用
                # ✗✗ —— 见实施计划 P-12 的说明 ✓）—— 这里不重复管 ✓。
                if owner.path.parent.name != "libs":
                    continue
                if owner.distribution not in member.dependencies:
                    rel = py_file.relative_to(BACKEND)
                    violations.append(
                        f"{rel}: import {module} → 缺声明 "
                        f"{owner.distribution}（{member.distribution} 未声明）"
                    )
    if violations:
        print("✗ isolated install 检查失败 —— 下列 import 缺依赖声明：")
        for item in violations:
            print(f"  · {item}")
        return 1
    if not args.quiet:
        print(f"✓ isolated install 检查通过（{len(members)} 个包 ✓）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
