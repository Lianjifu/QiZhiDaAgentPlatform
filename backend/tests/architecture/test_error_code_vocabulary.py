"""架构测试 —— **错误码只有一套词汇**（Gateway Stage 0 · G-02b）。

**为什么要有它**：错误码散落在两套体系里 —— `ErrorCode` 枚举（`libs/schema`）
与各模块 `domain/errors.py` 里的**自由字符串**。投影表 `ERROR_PROJECTION`
按码查文案：码有两套，表就得维护两套，**其中一套必然漏**（方案 §9.0）。

**本守卫的范围 = Gateway 域的码**（本层会产生 / 关心的那些）。
其余模块自己的码（150+ 个）**不属本层** —— 全量收敛是跨层工程，
不在这里假装做完（见 Gateway 方案 §13 的「未接管」）。

**判据**：这些码在**生产代码里不许再以字面量出现** —— 只能引用枚举
（`ErrorCode.X.value`）。字面量回来了 = 又长出一套词汇。
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

#: Gateway 域收敛进来的码（方案 §9.0 的表 + Gateway Stage 2/4a 自己新增的）。
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

#: 受检目录（相对 backend/）—— 生产代码。
PROD_DIRS = (
    "libs/",
    "modules/",
    "runtimes/",
    "composition/",
)

#: 字面量写法：`code = "X"` / `code="X"`（`reason_code` 与 `error_code` 同理）。
_LITERAL = re.compile(r"""\b(?:code|reason_code|error_code)\s*=\s*["']([A-Z_]+)["']""")


def _backend_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _py_files(rel_dir: str) -> list[Path]:
    root = _backend_root() / rel_dir
    if not root.exists():
        return []
    return sorted(p for p in root.rglob("*.py") if "/tests/" not in str(p))


def test_every_gateway_code_is_an_error_code_member() -> None:
    """Gateway 域的码**必须**在 `ErrorCode` 枚举里（收敛的底线）。"""
    from qzdap_schema.dtos.errors import ErrorCode

    members = {code.value for code in ErrorCode}
    missing = sorted(code for code in GATEWAY_CODES if code not in members)
    assert not missing, f"这些码没进 ErrorCode 枚举：{missing}"


def test_gateway_codes_are_not_hardcoded_as_literals() -> None:
    """生产代码里不许再出现这些码的**字面量** —— 只能引用枚举。"""
    wanted = set(GATEWAY_CODES)
    violations: list[str] = []
    for rel_dir in PROD_DIRS:
        for path in _py_files(rel_dir):
            for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
                for match in _LITERAL.finditer(line):
                    if match.group(1) in wanted:
                        rel = path.relative_to(_backend_root())
                        violations.append(f"{rel}:{lineno}: {match.group(0)}")
    assert not violations, "这些错误码又以字面量出现了（应改为 ErrorCode.X.value）：\n" + "\n".join(
        violations
    )


def test_the_gateway_codes_have_a_projection_entry() -> None:
    """投影表要覆盖 Gateway 域的码 —— 否则这些失败对用户只剩裸码。"""
    from qzdap_schema.dtos.errors import ERROR_PROJECTION, ErrorCode

    missing = sorted(
        code
        for code in GATEWAY_CODES
        if code in {c.value for c in ErrorCode} and ErrorCode(code) not in ERROR_PROJECTION
    )
    assert not missing, f"投影表漏了这些码：{missing}"


def test_no_module_error_class_uses_a_bare_string_code() -> None:
    """模块的 `domain/errors.py` 里，错误类的 `code` 必须是枚举引用。

    ⚠️ 只查 **`domain/errors.py`** —— 那里的 `code = "..."` 是**类的稳定码**
    （最容易被复制粘贴扩散的地方）；调用点上的 `code="..."` 由上一条守卫管。
    """
    from qzdap_schema.dtos.errors import ErrorCode

    members = {code.value for code in ErrorCode}
    violations: list[str] = []
    for rel_dir in ("modules/", "libs/", "runtimes/"):
        for path in _py_files(rel_dir):
            if path.name != "errors.py" or "domain" not in str(path):
                continue
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"))
            except SyntaxError:  # pragma: no cover
                continue
            for node in ast.walk(tree):
                if not isinstance(node, ast.ClassDef):
                    continue
                for stmt in node.body:
                    target = None
                    value = None
                    if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1:
                        target = stmt.targets[0]
                        value = stmt.value
                    elif isinstance(stmt, ast.AnnAssign):
                        target = stmt.target
                        value = stmt.value
                    if target is None or value is None:
                        continue
                    if not (isinstance(target, ast.Name) and target.id == "code"):
                        continue
                    # ⚠️ **只管 Gateway 域的码** —— 其余模块自己的码
                    # （150+ 个）不属本层（见模块 docstring）。
                    if (
                        isinstance(value, ast.Constant)
                        and isinstance(value.value, str)
                        and value.value in GATEWAY_CODES
                        and value.value not in members
                    ):
                        rel = path.relative_to(_backend_root())
                        violations.append(f"{rel}: {node.name}.code = {value.value!r}")
    assert not violations, "错误类的 code 仍是没进枚举的字面量：\n" + "\n".join(violations)
