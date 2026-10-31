"""架构测试 —— **错误码只有一套词汇**（Gateway Stage 0 · G-02b → 跨模块扩展 ✓）。

**为什么要有它**：错误码原先散落在**两套体系**里 —— `ErrorCode` 枚举
（2026-10-31 起住在 `qzdap_kernel.error_codes` ✓）与各模块 `domain/errors.py`
及调用点上的**自由字符串** ✓。投影表 `ERROR_PROJECTION` 按码查文案 ✓：
**码有两套，表就得维护两套，其中一套必然漏** ✓ —— 漏的那套**用户看到的是
裸码** ✗。

**2026-10-31 的扩展** ✓：原先这个守卫只管 **Gateway 域的 15 个码** ✓，
其余模块自己的 ~150 个码**明确「不属本层」** ✓ —— 那是个**没人接的活** ✗
（台账 §5.2 G12 行：「其余模块自己的 ~150 个码未接管 ✓」✓）。
现在**全量收敛** ✓ —— **生产代码里不再有任何错误码字面量** ✓，
枚举 **160 个成员** ✓（扫出来的 ✓ —— 不是拍脑袋数的 ✓）。

**判据**（四条 ✓）：
1. **生产代码里没有错误码字面量** ✓ —— 只能引用 `ErrorCode.X.value` ✓；
2. **每个枚举成员都有 HTTP 状态** ✓ —— `http_status` 是查表 ✓ →
   **漏一项就是运行期 KeyError** ✗✗；
3. **每个枚举成员都有文案** ✓ —— 否则用户看到的是兜底文案 ✓（"操作未完成"
   ✓ —— **用户不知道自己该改什么** ✗）；
4. **枚举值互不重复** ✓ —— 两个成员同一个值 = 两套词汇 ✓。
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

#: 受检目录（相对 backend/）—— 生产代码。
PROD_DIRS = (
    "libs/",
    "modules/",
    "runtimes/",
    "composition/",
)

#: **错误码的形状** ✓ —— 全大写 + 至少一个下划线 ✓（`"free"` 不是错误码 ✓
#: —— 那是套餐代号 ✓ —— 不归这套词汇管 ✓）。
_ERROR_CODE_SHAPE = re.compile(r"^[A-Z][A-Z0-9_]*_[A-Z0-9_]+$")

#: **码的位置** ✓ —— 关键字参数 / 类属性 / 字典键 ✓。
_CODE_KEYWORDS = ("code", "reason_code", "error_code")
_CODE_DICT_KEYS = ("code", "reason_code", "error_code")

#: Gateway Stage 0 收敛进来的那 15 个码 ✓ —— **不许改名** ✓
#: （它们已经在生产里跑了 ✓ —— 改名 = 破坏线上契约 ✗）。
GATEWAY_CODES: tuple[str, ...] = (
    "CHANNEL_NOT_FOUND",
    "CHANNEL_DISABLED",
    "INBOUND_ADAPTER_MISSING",
    "OUTBOUND_ADAPTER_MISSING",
    "WEBHOOK_SIGNATURE_INVALID",
    "WEBHOOK_TIMESTAMP_SKEW",
    "DUPLICATE_REQUEST",
    "TENANT_DENIED",
    "CHANNEL_SERVICE_ACCOUNT_MISSING",
    "CHANNEL_DELIVERY_FAILED",
    "IDENTITY_REJECTED",
    "IDENTITY_CREDENTIALS_MISSING",
    "TOKEN_INVALID",
    "TOKEN_EXPIRED",
    "SERVICE_ACCOUNT_NOT_CONFIGURED",
)


def _backend_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _py_files(rel_dir: str) -> list[Path]:
    root = _backend_root() / rel_dir
    if not root.exists():
        return []
    return sorted(p for p in root.rglob("*.py") if "/tests/" not in str(p))


def _literal_codes(path: Path) -> list[tuple[int, str]]:
    """**文件里所有「错误码位置」上的字符串字面量** ✓。

    ⚠️ **只认错误码位置** ✓ —— `code=` / `"code":` / 类属性 `code =` ✓ ——
    别的位置的字符串（提示词 ✓ / 计划代号 ✓ / 正则 ✓）**不归这套词汇管** ✓。
    """
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError:  # pragma: no cover
        return []
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        # 关键字参数：``raise X(code="FOO")``
        if isinstance(node, ast.keyword) and node.arg in _CODE_KEYWORDS:
            value = node.value
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                found.append((node.lineno, value.value))
        # 类属性 / 模块级赋值：``code = "FOO"``
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id == "code"
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
        ):
            found.append((node.lineno, node.value.value))
        # 字典：``{"error_code": "FOO"}``
        if isinstance(node, ast.Dict):
            for key, value in zip(node.keys, node.values, strict=False):
                if (
                    isinstance(key, ast.Constant)
                    and key.value in _CODE_DICT_KEYS
                    and isinstance(value, ast.Constant)
                    and isinstance(value.value, str)
                ):
                    found.append((node.lineno, value.value))
    return found


def test_no_error_code_literals_in_production_code() -> None:
    """**生产代码里不许再出现错误码字面量** ✓ —— 只能引用 `ErrorCode.X.value` ✓。

    ⚠️ 判据是「**任何**码的位置上不许有全大写字面量」✓ —— 不是「不许出现
    某几个码」✓ —— 那等于留了个口子 ✓（下一个模块又会自己造 ✓）。
    """
    violations: list[str] = []
    for rel_dir in PROD_DIRS:
        for path in _py_files(rel_dir):
            for lineno, value in _literal_codes(path):
                if not _ERROR_CODE_SHAPE.match(value):
                    continue
                rel = path.relative_to(_backend_root())
                violations.append(f"{rel}:{lineno}: {value!r}")
    assert not violations, "错误码又以字面量出现了（应改为 ErrorCode.X.value）：\n" + "\n".join(
        violations
    )


def test_every_gateway_code_is_still_an_error_code_member() -> None:
    """Gateway 域的 15 个码**不许改名 / 删掉** ✓（线上已经在用 ✓）。"""
    from qzdap_kernel.error_codes import ErrorCode

    members = {code.value for code in ErrorCode}
    missing = sorted(code for code in GATEWAY_CODES if code not in members)
    assert not missing, f"这些码没了或改名了：{missing}"


def test_every_error_code_has_a_http_status() -> None:
    """**每个枚举成员都要能查到 HTTP 状态** ✓ —— `http_status` 是查表 ✓。

    ⚠️ **漏一项 = 运行期 KeyError** ✗✗（`http_status` 直接 `_HTTP_STATUS[self]` ✓）
    → 所以这条是**硬闸门** ✓。
    """
    from qzdap_kernel.error_codes import ErrorCode

    missing = []
    for code in ErrorCode:
        try:
            _ = code.http_status
        except KeyError:
            missing.append(code.value)
    assert not missing, f"这些码没有 HTTP 状态（`_HTTP_STATUS` 漏了）：{missing}"


def test_every_error_code_has_a_projection_entry() -> None:
    """**每个枚举成员都要有文案** ✓ —— 否则用户只看到兜底 ✓。

    ⚠️ 兜底文案是「操作未完成，请稍后重试」✓ —— **用户不知道自己该改什么** ✗。
    """
    from qzdap_kernel.error_codes import ERROR_PROJECTION, ErrorCode

    missing = sorted(code.value for code in ErrorCode if code not in ERROR_PROJECTION)
    assert not missing, f"投影表漏了这些码：{missing}"


def test_error_code_values_are_unique() -> None:
    """**枚举值互不重复** ✓ —— 两个成员同一个值 = 两套词汇 ✓。"""
    from qzdap_kernel.error_codes import ErrorCode

    seen: dict[str, str] = {}
    duplicates: list[str] = []
    for code in ErrorCode:
        if code.value in seen:
            duplicates.append(f"{code.value}（{seen[code.value]} 与 {code.name}）")
        seen[code.value] = code.name
    assert not duplicates, f"这些码的值重复了：{duplicates}"


def test_the_projection_table_is_keyed_by_enum_members_only() -> None:
    """投影表的键**只能是** `ErrorCode` 成员 ✓ —— 两套码必然有一套漏 ✓。"""
    from qzdap_kernel.error_codes import ERROR_PROJECTION, ErrorCode

    strays = sorted(repr(key) for key in ERROR_PROJECTION if not isinstance(key, ErrorCode))
    assert not strays, f"投影表里有非枚举的键：{strays}"
