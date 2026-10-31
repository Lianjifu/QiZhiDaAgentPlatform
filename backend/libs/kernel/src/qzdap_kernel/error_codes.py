"""**错误码的唯一词汇** ✓ —— 平台对外的机器码 + 它的文案投影。

`ErrorCode` is the canonical machine code used in HTTP responses,
LangGraph node failures, outbox events and trace metadata. It is a
`str`-valued `Enum` so existing `qzdap_kernel.errors.AppError.code`
string fields accept the enum value without conversion.

新增错误码（Stage 1 起使用）必须登记到本枚举；运行时不允许抛出
未在本枚举中登记的字符串错误码。

⚠️ **为什么住在 kernel** ✓（2026-10-31 · G-02b 扩展 ✓）——
**错误码与错误层级是同一件事** ✓：`qzdap_kernel.errors.AppError` 的
`code` 就是这里的枚举值 ✓ → 词汇表必须**和错误层级住在一起** ✓ →
否则 base 层就得反过来依赖上层 ✗✗（`kernel` 是**零依赖**的基座 ✓）。
（与 2026-10-31 的品牌 ID 搬家同一个道理 ✓ —— **最底层的词汇住基座** ✓。）
`qzdap_schema` 因此**不再持有错误码** ✓（它只留线上的 DTO ✓）。

历史：
- v3.1：基于 §2.5 阻塞 5 决议新增 9 个会话模块错误码，与 kernel
  `AppError` 子类的 `code` 字符串共享同一字面值。
- 2026-10-31：从 `qzdap_schema.dtos.errors` 搬进 kernel ✓，
  并把**其余模块的 121 个自由字符串码**一并收敛进来 ✓ ——
  **生产代码里不再有任何错误码字面量** ✓（守门人：
  `tests/architecture/test_error_code_vocabulary.py` ✓）。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Literal


# 既有错误码（与 kernel `AppError.code` 字面值一致）
class ErrorCode(str, Enum):
    """Stable wire-level error code for every user-visible failure."""

    # 既有错误码（kernel 同步）
    VALIDATION_ERROR = "VALIDATION_ERROR"
    AUTHENTICATION_FAILED = "AUTHENTICATION_FAILED"
    FORBIDDEN = "FORBIDDEN"
    ACTION_DENIED = "ACTION_DENIED"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
    NOT_FOUND = "NOT_FOUND"
    CONFLICT = "CONFLICT"
    BUSINESS_RULE_VIOLATED = "BUSINESS_RULE_VIOLATED"
    RATE_LIMITED = "RATE_LIMITED"
    EXTERNAL_SERVICE_ERROR = "EXTERNAL_SERVICE_ERROR"
    INTERNAL_ERROR = "INTERNAL_ERROR"

    # 新增错误码（Stage 1 起使用；见 §2.5 阻塞 5）
    SESSION_BUSY = "SESSION_BUSY"
    AGENT_NOT_AVAILABLE = "AGENT_NOT_AVAILABLE"
    CONTEXT_TOO_LARGE = "CONTEXT_TOO_LARGE"
    REVISION_CONFLICT = "REVISION_CONFLICT"
    APPROVAL_EXPIRED = "APPROVAL_EXPIRED"
    APPROVAL_NOT_MATCH = "APPROVAL_NOT_MATCH"
    TOOL_ARGUMENT_INVALID = "TOOL_ARGUMENT_INVALID"
    TOOL_TIMEOUT = "TOOL_TIMEOUT"
    TOOL_RATE_LIMITED = "TOOL_RATE_LIMITED"
    # Router Stage 0（决策 #7）—— 排队语义：
    # 队列满 / 等待超时。⚠️ 两者都**不静默丢弃**：轮次落 cancelled 且可查。
    QUEUE_FULL = "QUEUE_FULL"
    QUEUE_TIMEOUT = "QUEUE_TIMEOUT"
    # Gateway Stage 0 · G-02b（方案 §9.0 的「收敛」）——
    # 这些码原先是**各模块 domain/errors.py 里的自由字符串**，
    # 现在提升为枚举成员：投影表（`ERROR_PROJECTION`）按码查文案，
    # 码散落在两套体系里必然有一套漏。
    #
    # ⚠️ 方案 §9.0 的表列了 7 个 —— **实施时又发现 6 个**（Gateway Stage 2/4a
    # 自己新增的：服务账号缺失 / 投递失败 / 出站适配器缺失 / 鉴权拒绝原因）。
    # 收敛只做一半等于没做 —— **按实况补齐**（方案 §9.0 的表已同步更新）。
    CHANNEL_NOT_FOUND = "CHANNEL_NOT_FOUND"
    CHANNEL_DISABLED = "CHANNEL_DISABLED"
    INBOUND_ADAPTER_MISSING = "INBOUND_ADAPTER_MISSING"
    OUTBOUND_ADAPTER_MISSING = "OUTBOUND_ADAPTER_MISSING"
    WEBHOOK_SIGNATURE_INVALID = "WEBHOOK_SIGNATURE_INVALID"
    WEBHOOK_TIMESTAMP_SKEW = "WEBHOOK_TIMESTAMP_SKEW"
    DUPLICATE_REQUEST = "DUPLICATE_REQUEST"
    TENANT_DENIED = "TENANT_DENIED"
    # Gateway Stage 2（服务账号物化）与 Stage 4a（出站 sink）新增的码
    CHANNEL_SERVICE_ACCOUNT_MISSING = "CHANNEL_SERVICE_ACCOUNT_MISSING"
    CHANNEL_DELIVERY_FAILED = "CHANNEL_DELIVERY_FAILED"
    IDENTITY_REJECTED = "IDENTITY_REJECTED"
    IDENTITY_CREDENTIALS_MISSING = "IDENTITY_CREDENTIALS_MISSING"
    TOKEN_INVALID = "TOKEN_INVALID"  # noqa: S105 —— 错误码 ✓ 不是口令 ✓
    TOKEN_EXPIRED = "TOKEN_EXPIRED"  # noqa: S105 —— 错误码 ✓ 不是口令 ✓
    # Gateway ② 的**拒绝原因码**（审计事件里的 reason_code）—— 与 API 错误码
    # 是两套词汇，都登记进枚举（投影表要覆盖它们），但**不互相替代**。
    SERVICE_ACCOUNT_NOT_CONFIGURED = "SERVICE_ACCOUNT_NOT_CONFIGURED"
    # Session Stage 0 · S-04 —— 审批人不能是发起人（自审批拦截 ✓）。
    APPROVER_MUST_DIFFER = "APPROVER_MUST_DIFFER"
    # Agent Stage 3 · A-15 —— **同一幂等键配了不同参数** ✓
    # （`tool_executions` 的 `request_hash` 与既有行不一致 ✓ —— **调用方的 bug**
    # ✓ → 必须**暴露** ✓ 不静默返回旧结果 ✗✗）。
    TOOL_IDEMPOTENCY_CONFLICT = "TOOL_IDEMPOTENCY_CONFLICT"
    # Agent Stage 3 —— **同一个幂等键的另一次调用还在跑** ✓ → 不重复执行 ✓
    TOOL_IN_PROGRESS = "TOOL_IN_PROGRESS"

    # ── 跨模块收敛（G-02b 扩展 · 2026-10-31）──────────────────────────
    # ⚠️ **这些码原先散落在 15 个模块的 `domain/errors.py` 与各处调用点上**
    # ✓ —— **121 个** ✓（扫描脚本扫出来的 ✓ —— 不是拍脑袋数的 ✓）。
    # 收敛的动因与 Gateway Stage 0 一样：**码有两套，投影表就得维护两套**，
    # 其中一套必然漏 ✓ —— 而漏的那套**用户看到的是裸码** ✗。
    #
    # ⚠️ **收敛只动「词汇」，不动行为** ✓ —— 每个码的**字符串值与原来
    # 完全一致** ✓（`WORKSPACE_NOT_FOUND` 是唯一的例外 ✓ —— 见下 ✓）→
    # **线上看到的码一个字都没变** ✓（除了那一个 ✓ —— 它是 auth 里
    # 自造的 `E_` 前缀码 ✓ —— 全仓只有前端 mock 用过 ✓ → 统一 ✓）。
    #
    # 守门人 = `tests/architecture/test_error_code_vocabulary.py` ✓ ——
    # **生产代码里不许再出现任何错误码字面量** ✓（不是「不许出现某几个」
    # ✓ —— 那等于留了个口子 ✓）。
    #
    # ── agent_runtime ─────────────────────────────────────────────────
    AGENT_NOT_FOUND = "AGENT_NOT_FOUND"
    AGENT_DISABLED = "AGENT_DISABLED"
    AGENT_CAPABILITY_UNAVAILABLE = "AGENT_CAPABILITY_UNAVAILABLE"
    SESSION_NOT_FOUND = "SESSION_NOT_FOUND"
    TURN_NOT_FOUND = "TURN_NOT_FOUND"
    SESSION_CLOSED = "SESSION_CLOSED"
    TOOL_ACTOR_MISSING = "TOOL_ACTOR_MISSING"
    TOOL_ACTOR_TENANT_MISMATCH = "TOOL_ACTOR_TENANT_MISMATCH"
    SUB_AGENT_UNAVAILABLE = "SUB_AGENT_UNAVAILABLE"
    SUBAGENT_CRASHED = "SUBAGENT_CRASHED"
    ZOMBIE_TAKEOVER = "ZOMBIE_TAKEOVER"
    # ── agent_factory ──────────────────────────────────────────────────
    AGENT_TEMPLATE_NOT_FOUND = "AGENT_TEMPLATE_NOT_FOUND"
    AGENT_VERSION_NOT_FOUND = "AGENT_VERSION_NOT_FOUND"
    RELEASE_NOT_FOUND = "RELEASE_NOT_FOUND"
    AGENT_TEMPLATE_NAME_CONFLICT = "AGENT_TEMPLATE_NAME_CONFLICT"
    AGENT_VERSION_TAG_CONFLICT = "AGENT_VERSION_TAG_CONFLICT"
    AGENT_VERSION_IMMUTABLE = "AGENT_VERSION_IMMUTABLE"
    AGENT_VERSION_INVALID_TRANSITION = "AGENT_VERSION_INVALID_TRANSITION"
    AGENT_FACTORY_POLICY_DENIED = "AGENT_FACTORY_POLICY_DENIED"
    # ── evaluation ─────────────────────────────────────────────────────
    EVAL_AGENT_NOT_FOUND = "EVAL_AGENT_NOT_FOUND"
    EVAL_APPROVAL_REQUIRED = "EVAL_APPROVAL_REQUIRED"
    EVAL_VERSION_MISSING = "EVAL_VERSION_MISSING"
    EVAL_INVALID_VERSION = "EVAL_INVALID_VERSION"
    EVAL_VERSION_NOT_PUBLISHED = "EVAL_VERSION_NOT_PUBLISHED"
    EVAL_GATE_FAILED = "EVAL_GATE_FAILED"
    RUNNER_ERROR = "RUNNER_ERROR"
    # ── governance ─────────────────────────────────────────────────────
    POLICY_NOT_FOUND = "POLICY_NOT_FOUND"
    POLICY_ALREADY_EXISTS = "POLICY_ALREADY_EXISTS"
    APPROVAL_NOT_FOUND = "APPROVAL_NOT_FOUND"
    APPROVAL_ALREADY_DECIDED = "APPROVAL_ALREADY_DECIDED"
    INVALID_POLICY = "INVALID_POLICY"
    INVALID_APPROVAL = "INVALID_APPROVAL"
    DATA_SUBJECT_FAILED = "DATA_SUBJECT_FAILED"
    # ── identity ───────────────────────────────────────────────────────
    TENANT_NOT_FOUND = "TENANT_NOT_FOUND"
    WORKSPACE_NOT_FOUND = "WORKSPACE_NOT_FOUND"
    USER_NOT_FOUND = "USER_NOT_FOUND"
    API_KEY_NOT_FOUND = "API_KEY_NOT_FOUND"
    TENANT_ALREADY_EXISTS = "TENANT_ALREADY_EXISTS"
    WORKSPACE_ALREADY_EXISTS = "WORKSPACE_ALREADY_EXISTS"
    USER_ALREADY_EXISTS = "USER_ALREADY_EXISTS"
    INVALID_CREDENTIALS = "INVALID_CREDENTIALS"
    API_KEY_REVOKED = "API_KEY_REVOKED"
    WORKSPACE_LIMIT_REACHED = "WORKSPACE_LIMIT_REACHED"
    WORKSPACE_DENIED = "WORKSPACE_DENIED"
    # ── knowledge ──────────────────────────────────────────────────────
    KNOWLEDGE_NOT_FOUND = "KNOWLEDGE_NOT_FOUND"
    KNOWLEDGE_INVALID = "KNOWLEDGE_INVALID"
    # ── memory ─────────────────────────────────────────────────────────
    MEMORY_NOT_FOUND = "MEMORY_NOT_FOUND"
    MEMORY_VERSION_CONFLICT = "MEMORY_VERSION_CONFLICT"
    MEMORY_SENSITIVE_CONTENT = "MEMORY_SENSITIVE_CONTENT"
    MEMORY_DUPLICATE_CONTENT = "MEMORY_DUPLICATE_CONTENT"
    MEMORY_SCOPE_UNSUPPORTED = "MEMORY_SCOPE_UNSUPPORTED"
    MEMORY_POLICY_PUBLISHER_MISSING = "MEMORY_POLICY_PUBLISHER_MISSING"
    # ── model ──────────────────────────────────────────────────────────
    MODEL_NOT_FOUND = "MODEL_NOT_FOUND"
    PROVIDER_NOT_FOUND = "PROVIDER_NOT_FOUND"
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    ROUTE_NOT_FOUND = "ROUTE_NOT_FOUND"
    MODEL_DISABLED = "MODEL_DISABLED"
    CREDENTIAL_NOT_FOUND = "CREDENTIAL_NOT_FOUND"
    MODEL_ROUTE_EXHAUSTED = "MODEL_ROUTE_EXHAUSTED"
    QUOTA_EXCEEDED = "QUOTA_EXCEEDED"
    LLM_STREAM_EMPTY = "LLM_STREAM_EMPTY"
    LLM_NOT_CONFIGURED = "LLM_NOT_CONFIGURED"
    # ── observability ──────────────────────────────────────────────────
    RUN_RECORD_NOT_FOUND = "RUN_RECORD_NOT_FOUND"
    COST_RECORD_NOT_FOUND = "COST_RECORD_NOT_FOUND"
    QUALITY_NOT_FOUND = "QUALITY_NOT_FOUND"
    OBSERVABILITY_POLICY_DENIED = "OBSERVABILITY_POLICY_DENIED"
    RUN_TYPE_INVALID = "RUN_TYPE_INVALID"
    RUN_STATUS_INVALID = "RUN_STATUS_INVALID"
    COST_TYPE_INVALID = "COST_TYPE_INVALID"
    COST_INVALID = "COST_INVALID"
    GROUP_BY_INVALID = "GROUP_BY_INVALID"
    # ── orchestration ──────────────────────────────────────────────────
    WORKFLOW_NOT_FOUND = "WORKFLOW_NOT_FOUND"
    WORKFLOW_UNAVAILABLE = "WORKFLOW_UNAVAILABLE"
    # ── platform ───────────────────────────────────────────────────────
    PLAN_NOT_FOUND = "PLAN_NOT_FOUND"
    PLAN_ALREADY_EXISTS = "PLAN_ALREADY_EXISTS"
    PLAN_RETIRED = "PLAN_RETIRED"
    SUBSCRIPTION_INVALID_TRANSITION = "SUBSCRIPTION_INVALID_TRANSITION"
    TENANT_SETTING_NOT_FOUND = "TENANT_SETTING_NOT_FOUND"
    TENANT_SETTING_CONFLICT = "TENANT_SETTING_CONFLICT"
    # ── self_evolution ─────────────────────────────────────────────────
    EVOLVE_CANDIDATE_NOT_FOUND = "EVOLVE_CANDIDATE_NOT_FOUND"
    EVOLVE_CANDIDATE_ALREADY_DECIDED = "EVOLVE_CANDIDATE_ALREADY_DECIDED"
    EVOLVE_SIGNER_MUST_DIFFER = "EVOLVE_SIGNER_MUST_DIFFER"
    INVALID_EVOLVE_CANDIDATE = "INVALID_EVOLVE_CANDIDATE"
    APPLY_GUARD_REJECTED = "APPLY_GUARD_REJECTED"
    # ── skill ──────────────────────────────────────────────────────────
    SKILL_NOT_FOUND = "SKILL_NOT_FOUND"
    SKILL_DISABLED = "SKILL_DISABLED"
    SKILL_NEEDS_CONFIRM = "SKILL_NEEDS_CONFIRM"
    SKILL_NOT_EXECUTABLE = "SKILL_NOT_EXECUTABLE"
    # ── tool ───────────────────────────────────────────────────────────
    TOOL_NOT_FOUND = "TOOL_NOT_FOUND"
    TOOL_ALREADY_EXISTS = "TOOL_ALREADY_EXISTS"
    TOOL_VERSION_MISMATCH = "TOOL_VERSION_MISMATCH"
    TOOL_DISABLED = "TOOL_DISABLED"
    TOOL_CALL_TIMEOUT = "TOOL_CALL_TIMEOUT"
    TOOL_DENIED = "TOOL_DENIED"
    TOOL_STALLED = "TOOL_STALLED"
    INVALID_TOOL_SPEC = "INVALID_TOOL_SPEC"
    UPSTREAM_UNAVAILABLE = "UPSTREAM_UNAVAILABLE"
    # ── 沙箱（runtime + 模块侧）────────────────────────────────────────
    SANDBOX_UNAVAILABLE = "SANDBOX_UNAVAILABLE"
    SANDBOX_TIMEOUT = "SANDBOX_TIMEOUT"
    SANDBOX_CANCELLED = "SANDBOX_CANCELLED"
    SANDBOX_FAILED = "SANDBOX_FAILED"
    SANDBOX_HTTP_ERROR = "SANDBOX_HTTP_ERROR"
    SANDBOX_BAD_LANGUAGE = "SANDBOX_BAD_LANGUAGE"
    SANDBOX_BAD_PATH = "SANDBOX_BAD_PATH"
    # ── 轮次（契约层）──────────────────────────────────────────────────
    TURN_CANCELLED = "TURN_CANCELLED"
    TURN_FAILED = "TURN_FAILED"
    # ── libs/vault ─────────────────────────────────────────────────────
    SECRET_NOT_FOUND = "SECRET_NOT_FOUND"  # noqa: S105 —— 错误码 ✓ 不是口令 ✓
    SECRET_ACCESS_DENIED = "SECRET_ACCESS_DENIED"  # noqa: S105 —— 错误码 ✓ 不是口令 ✓
    INVALID_SECRET_REF = "INVALID_SECRET_REF"  # noqa: S105 —— 错误码 ✓ 不是口令 ✓
    INVALID_KEY = "INVALID_KEY"
    INVALID_CIPHERTEXT = "INVALID_CIPHERTEXT"
    CRYPTO_ERROR = "CRYPTO_ERROR"
    # ── libs/auth ──────────────────────────────────────────────────────
    MISSING_TOKEN = "MISSING_TOKEN"  # noqa: S105 —— 错误码 ✓ 不是口令 ✓
    INSUFFICIENT_SCOPE = "INSUFFICIENT_SCOPE"
    INSUFFICIENT_ROLE = "INSUFFICIENT_ROLE"
    # ── libs/http ──────────────────────────────────────────────────────
    TENANT_HEADER_MISMATCH = "TENANT_HEADER_MISMATCH"
    WORKSPACE_HEADER_MISMATCH = "WORKSPACE_HEADER_MISMATCH"
    # ── libs/llm ───────────────────────────────────────────────────────
    LLM_INVALID_RESPONSE = "LLM_INVALID_RESPONSE"
    LLM_ALL_FAILED = "LLM_ALL_FAILED"
    LLM_STREAM_ERROR = "LLM_STREAM_ERROR"

    # ── 派生属性 ────────────────────────────────────────────────────────
    # ⚠️ **必须在类体里定义** ✓ —— 事后 `ErrorCode.http_status = property(...)`
    # 对类型检查器**不可见** ✗ → 调用方拿不到这三个属性 ✗✗（类型上直接报错 ✓）。
    # 元数据表（`_HTTP_STATUS` / `_RETRIABLE` / `_I18N_PREFIX`）在**类体之后**
    # 定义 ✓ —— 但属性是**调用时**才求值 ✓ → 那时表已经就位 ✓。
    @property
    def http_status(self) -> int:
        """这个错误码对应的 HTTP 状态码 ✓。"""
        return _HTTP_STATUS[self]

    @property
    def retriable(self) -> bool:
        """这个错误码**可重试**吗 ✓（限流 / 外部服务故障 ✓）。"""
        return self in _RETRIABLE

    @property
    def i18n_key(self) -> str:
        """这个错误码的 i18n key ✓。"""
        return f"{_I18N_PREFIX}{self.value.lower()}"


# ---------------------------------------------------------------------------
# 元数据表
# ---------------------------------------------------------------------------

_HTTP_STATUS: dict[ErrorCode, int] = {
    # 既有
    ErrorCode.VALIDATION_ERROR: 400,
    ErrorCode.AUTHENTICATION_FAILED: 401,
    ErrorCode.FORBIDDEN: 403,
    ErrorCode.ACTION_DENIED: 403,
    ErrorCode.APPROVAL_REQUIRED: 202,
    ErrorCode.NOT_FOUND: 404,
    ErrorCode.CONFLICT: 409,
    ErrorCode.BUSINESS_RULE_VIOLATED: 422,
    ErrorCode.RATE_LIMITED: 429,
    ErrorCode.EXTERNAL_SERVICE_ERROR: 502,
    ErrorCode.INTERNAL_ERROR: 500,
    # 新增（Stage 1）
    ErrorCode.SESSION_BUSY: 409,
    ErrorCode.AGENT_NOT_AVAILABLE: 502,
    ErrorCode.CONTEXT_TOO_LARGE: 413,
    ErrorCode.REVISION_CONFLICT: 409,
    ErrorCode.APPROVAL_EXPIRED: 410,
    ErrorCode.APPROVAL_NOT_MATCH: 409,
    ErrorCode.TOOL_ARGUMENT_INVALID: 400,
    ErrorCode.TOOL_TIMEOUT: 504,
    ErrorCode.TOOL_RATE_LIMITED: 429,
    # Agent Stage 3 · A-15 —— 幂等键复用但参数不同 → 409（冲突 ✓ 不是限流 ✓）
    ErrorCode.TOOL_IDEMPOTENCY_CONFLICT: 409,
    ErrorCode.TOOL_IN_PROGRESS: 409,
    # Router 排队语义
    ErrorCode.QUEUE_FULL: 429,
    ErrorCode.QUEUE_TIMEOUT: 503,
    # Gateway Stage 0 · G-02b —— 收敛自各模块的自由字符串（方案 §9.0 的表）
    ErrorCode.CHANNEL_NOT_FOUND: 404,
    ErrorCode.CHANNEL_DISABLED: 409,
    ErrorCode.INBOUND_ADAPTER_MISSING: 500,
    ErrorCode.OUTBOUND_ADAPTER_MISSING: 500,
    ErrorCode.WEBHOOK_SIGNATURE_INVALID: 401,
    ErrorCode.WEBHOOK_TIMESTAMP_SKEW: 401,
    ErrorCode.DUPLICATE_REQUEST: 409,
    ErrorCode.TENANT_DENIED: 403,
    ErrorCode.CHANNEL_SERVICE_ACCOUNT_MISSING: 503,
    ErrorCode.CHANNEL_DELIVERY_FAILED: 502,
    ErrorCode.IDENTITY_REJECTED: 401,
    ErrorCode.IDENTITY_CREDENTIALS_MISSING: 401,
    ErrorCode.TOKEN_INVALID: 401,
    ErrorCode.TOKEN_EXPIRED: 401,
    ErrorCode.SERVICE_ACCOUNT_NOT_CONFIGURED: 503,
    ErrorCode.APPROVER_MUST_DIFFER: 403,
    # ── 跨模块收敛（G-02b 扩展 · 2026-10-31）──────────────────────────
    # ⚠️ **每个枚举成员都必须在这里有一项** ✓ —— `http_status` 是
    # `_HTTP_STATUS[self]` ✓（查表 ✓）→ **漏一项就是运行期 KeyError** ✗✗
    # → 由 `libs/schema/tests/test_errors.py` 守门 ✓。
    # ── agent_runtime ─────────────────────────────────────────────────
    ErrorCode.AGENT_NOT_FOUND: 404,
    ErrorCode.AGENT_DISABLED: 409,
    ErrorCode.AGENT_CAPABILITY_UNAVAILABLE: 409,
    ErrorCode.SESSION_NOT_FOUND: 404,
    ErrorCode.TURN_NOT_FOUND: 404,
    ErrorCode.SESSION_CLOSED: 409,
    ErrorCode.TOOL_ACTOR_MISSING: 403,
    ErrorCode.TOOL_ACTOR_TENANT_MISMATCH: 403,
    ErrorCode.SUB_AGENT_UNAVAILABLE: 503,
    ErrorCode.SUBAGENT_CRASHED: 500,
    ErrorCode.ZOMBIE_TAKEOVER: 409,
    # ── agent_factory ──────────────────────────────────────────────────
    ErrorCode.AGENT_TEMPLATE_NOT_FOUND: 404,
    ErrorCode.AGENT_VERSION_NOT_FOUND: 404,
    ErrorCode.RELEASE_NOT_FOUND: 404,
    ErrorCode.AGENT_TEMPLATE_NAME_CONFLICT: 409,
    ErrorCode.AGENT_VERSION_TAG_CONFLICT: 409,
    ErrorCode.AGENT_VERSION_IMMUTABLE: 409,
    ErrorCode.AGENT_VERSION_INVALID_TRANSITION: 409,
    ErrorCode.AGENT_FACTORY_POLICY_DENIED: 403,
    # ── evaluation ─────────────────────────────────────────────────────
    ErrorCode.EVAL_AGENT_NOT_FOUND: 404,
    ErrorCode.EVAL_APPROVAL_REQUIRED: 202,
    ErrorCode.EVAL_VERSION_MISSING: 404,
    ErrorCode.EVAL_INVALID_VERSION: 400,
    ErrorCode.EVAL_VERSION_NOT_PUBLISHED: 409,
    ErrorCode.EVAL_GATE_FAILED: 409,
    ErrorCode.RUNNER_ERROR: 500,
    # ── governance ─────────────────────────────────────────────────────
    ErrorCode.POLICY_NOT_FOUND: 404,
    ErrorCode.POLICY_ALREADY_EXISTS: 409,
    ErrorCode.APPROVAL_NOT_FOUND: 404,
    ErrorCode.APPROVAL_ALREADY_DECIDED: 409,
    ErrorCode.INVALID_POLICY: 400,
    ErrorCode.INVALID_APPROVAL: 400,
    ErrorCode.DATA_SUBJECT_FAILED: 500,
    # ── identity ───────────────────────────────────────────────────────
    ErrorCode.TENANT_NOT_FOUND: 404,
    ErrorCode.WORKSPACE_NOT_FOUND: 404,
    ErrorCode.USER_NOT_FOUND: 404,
    ErrorCode.API_KEY_NOT_FOUND: 404,
    ErrorCode.TENANT_ALREADY_EXISTS: 409,
    ErrorCode.WORKSPACE_ALREADY_EXISTS: 409,
    ErrorCode.USER_ALREADY_EXISTS: 409,
    ErrorCode.INVALID_CREDENTIALS: 401,
    ErrorCode.API_KEY_REVOKED: 403,
    ErrorCode.WORKSPACE_LIMIT_REACHED: 409,
    ErrorCode.WORKSPACE_DENIED: 403,
    # ── knowledge ──────────────────────────────────────────────────────
    ErrorCode.KNOWLEDGE_NOT_FOUND: 404,
    ErrorCode.KNOWLEDGE_INVALID: 400,
    # ── memory ─────────────────────────────────────────────────────────
    ErrorCode.MEMORY_NOT_FOUND: 404,
    ErrorCode.MEMORY_VERSION_CONFLICT: 409,
    ErrorCode.MEMORY_SENSITIVE_CONTENT: 422,
    ErrorCode.MEMORY_DUPLICATE_CONTENT: 409,
    ErrorCode.MEMORY_SCOPE_UNSUPPORTED: 400,
    ErrorCode.MEMORY_POLICY_PUBLISHER_MISSING: 500,
    # ── model ──────────────────────────────────────────────────────────
    ErrorCode.MODEL_NOT_FOUND: 404,
    ErrorCode.PROVIDER_NOT_FOUND: 404,
    ErrorCode.PROVIDER_UNAVAILABLE: 503,
    ErrorCode.ROUTE_NOT_FOUND: 404,
    ErrorCode.MODEL_DISABLED: 409,
    ErrorCode.CREDENTIAL_NOT_FOUND: 404,
    ErrorCode.MODEL_ROUTE_EXHAUSTED: 503,
    ErrorCode.QUOTA_EXCEEDED: 429,
    ErrorCode.LLM_STREAM_EMPTY: 502,
    ErrorCode.LLM_NOT_CONFIGURED: 503,
    # ── observability ──────────────────────────────────────────────────
    ErrorCode.RUN_RECORD_NOT_FOUND: 404,
    ErrorCode.COST_RECORD_NOT_FOUND: 404,
    ErrorCode.QUALITY_NOT_FOUND: 404,
    ErrorCode.OBSERVABILITY_POLICY_DENIED: 403,
    ErrorCode.RUN_TYPE_INVALID: 400,
    ErrorCode.RUN_STATUS_INVALID: 400,
    ErrorCode.COST_TYPE_INVALID: 400,
    ErrorCode.COST_INVALID: 400,
    ErrorCode.GROUP_BY_INVALID: 400,
    # ── orchestration ──────────────────────────────────────────────────
    ErrorCode.WORKFLOW_NOT_FOUND: 404,
    ErrorCode.WORKFLOW_UNAVAILABLE: 503,
    # ── platform ───────────────────────────────────────────────────────
    ErrorCode.PLAN_NOT_FOUND: 404,
    ErrorCode.PLAN_ALREADY_EXISTS: 409,
    ErrorCode.PLAN_RETIRED: 409,
    ErrorCode.SUBSCRIPTION_INVALID_TRANSITION: 409,
    ErrorCode.TENANT_SETTING_NOT_FOUND: 404,
    ErrorCode.TENANT_SETTING_CONFLICT: 409,
    # ── self_evolution ─────────────────────────────────────────────────
    ErrorCode.EVOLVE_CANDIDATE_NOT_FOUND: 404,
    ErrorCode.EVOLVE_CANDIDATE_ALREADY_DECIDED: 409,
    ErrorCode.EVOLVE_SIGNER_MUST_DIFFER: 403,
    ErrorCode.INVALID_EVOLVE_CANDIDATE: 400,
    ErrorCode.APPLY_GUARD_REJECTED: 403,
    # ── skill ──────────────────────────────────────────────────────────
    ErrorCode.SKILL_NOT_FOUND: 404,
    ErrorCode.SKILL_DISABLED: 409,
    ErrorCode.SKILL_NEEDS_CONFIRM: 202,
    ErrorCode.SKILL_NOT_EXECUTABLE: 409,
    # ── tool ───────────────────────────────────────────────────────────
    ErrorCode.TOOL_NOT_FOUND: 404,
    ErrorCode.TOOL_ALREADY_EXISTS: 409,
    ErrorCode.TOOL_VERSION_MISMATCH: 409,
    ErrorCode.TOOL_DISABLED: 409,
    ErrorCode.TOOL_CALL_TIMEOUT: 504,
    ErrorCode.TOOL_DENIED: 403,
    ErrorCode.TOOL_STALLED: 504,
    ErrorCode.INVALID_TOOL_SPEC: 400,
    ErrorCode.UPSTREAM_UNAVAILABLE: 502,
    # ── 沙箱 ───────────────────────────────────────────────────────────
    ErrorCode.SANDBOX_UNAVAILABLE: 503,
    ErrorCode.SANDBOX_TIMEOUT: 504,
    ErrorCode.SANDBOX_CANCELLED: 409,
    ErrorCode.SANDBOX_FAILED: 502,
    ErrorCode.SANDBOX_HTTP_ERROR: 502,
    ErrorCode.SANDBOX_BAD_LANGUAGE: 400,
    ErrorCode.SANDBOX_BAD_PATH: 400,
    # ── 轮次 ───────────────────────────────────────────────────────────
    ErrorCode.TURN_CANCELLED: 409,
    ErrorCode.TURN_FAILED: 500,
    # ── libs/vault ─────────────────────────────────────────────────────
    ErrorCode.SECRET_NOT_FOUND: 404,
    ErrorCode.SECRET_ACCESS_DENIED: 403,
    ErrorCode.INVALID_SECRET_REF: 400,
    ErrorCode.INVALID_KEY: 400,
    ErrorCode.INVALID_CIPHERTEXT: 400,
    ErrorCode.CRYPTO_ERROR: 500,
    # ── libs/auth ──────────────────────────────────────────────────────
    ErrorCode.MISSING_TOKEN: 401,
    ErrorCode.INSUFFICIENT_SCOPE: 403,
    ErrorCode.INSUFFICIENT_ROLE: 403,
    # ── libs/http ──────────────────────────────────────────────────────
    ErrorCode.TENANT_HEADER_MISMATCH: 400,
    ErrorCode.WORKSPACE_HEADER_MISMATCH: 400,
    # ── libs/llm ───────────────────────────────────────────────────────
    ErrorCode.LLM_INVALID_RESPONSE: 502,
    ErrorCode.LLM_ALL_FAILED: 502,
    ErrorCode.LLM_STREAM_ERROR: 502,
}


_RETRIABLE: frozenset[ErrorCode] = frozenset(
    {
        ErrorCode.SESSION_BUSY,
        ErrorCode.REVISION_CONFLICT,
        ErrorCode.TOOL_TIMEOUT,
        ErrorCode.TOOL_RATE_LIMITED,
        ErrorCode.RATE_LIMITED,
        ErrorCode.EXTERNAL_SERVICE_ERROR,
        ErrorCode.QUEUE_FULL,
        ErrorCode.QUEUE_TIMEOUT,
        # ── 跨模块收敛（G-02b 扩展）────────────────────────────────────
        # ⚠️ **可重试 = 「换个时间 / 换个节点再来一次可能就好了」** ✓ ——
        # 配额 ✓ / 上游挂了 ✓ / 路由走完 ✓ / 沙箱超时 ✓ —— 都在这一类 ✓；
        # ⚠️ **配置类不算** ✓（`LLM_NOT_CONFIGURED` ✓ —— 重试多少次都没用 ✓）。
        ErrorCode.QUOTA_EXCEEDED,
        ErrorCode.UPSTREAM_UNAVAILABLE,
        ErrorCode.MODEL_ROUTE_EXHAUSTED,
        ErrorCode.PROVIDER_UNAVAILABLE,
        ErrorCode.LLM_ALL_FAILED,
        ErrorCode.LLM_INVALID_RESPONSE,
        ErrorCode.LLM_STREAM_ERROR,
        ErrorCode.LLM_STREAM_EMPTY,
        ErrorCode.WORKFLOW_UNAVAILABLE,
        ErrorCode.SUB_AGENT_UNAVAILABLE,
        ErrorCode.TOOL_CALL_TIMEOUT,
        ErrorCode.TOOL_STALLED,
        ErrorCode.SANDBOX_TIMEOUT,
        ErrorCode.SANDBOX_FAILED,
    }
)


_I18N_PREFIX = "errors."


# ---------------------------------------------------------------------------
# 扩展属性（用 property 而非方法以与现有 `ChunkEnvelope.kind` 风格一致）
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# 投影表：ErrorCode → 三个投放面的文案（Gateway Stage 0 · G-02）
# ---------------------------------------------------------------------------

#: 投放面 —— 同一个错误在**不同地方**要说得不一样。
#:
#: - ``http``：HTTP 错误信封的 ``message``（给 API 调用方 / 脚本看）；
#: - ``im``：IM 渠道回给群里用户的那条消息；
#: - ``web``：web 对话页展示给用户的那条消息。
ErrorSurface = Literal["http", "im", "web"]


@dataclass(frozen=True, slots=True)
class ErrorCopy:
    """一个错误码在各投放面上的文案。

    ⚠️ ``im`` / ``web`` 留空时**回落到 ``http``** —— 少写一份文案不会
    让用户看到裸码。
    """

    http: str
    im: str = ""
    web: str = ""

    def for_surface(self, surface: ErrorSurface) -> str:
        if surface == "im":
            return self.im or self.http
        if surface == "web":
            return self.web or self.http
        return self.http


#: 兜底文案 —— 表里没有的码用它。
#:
#: **为什么要有兜底**：投影表按码查文案，码会一直增加（每层都在加码）。
#: 没有兜底就会退化成「把裸码甩给用户」—— 那不是文案，是甩锅。
_FALLBACK_COPY = ErrorCopy(
    http="请求处理失败",
    im="出错了，请稍后重试。",
    web="操作未完成，请稍后重试。",
)

#: **按码查文案**的投影表（Gateway 方案 §9.0 的 G-02）。
#:
#: 只登记 **Gateway 层会产生 / 关心**的码；其余码走兜底。
#: ⚠️ **键只能是 `ErrorCode` 成员** —— 码散落在两套体系（枚举 + 模块自由
#: 字符串）里，这张表就得维护两套码，而其中一套必然漏（G-02b 收敛的动因）。
ERROR_PROJECTION: Mapping[ErrorCode, ErrorCopy] = {
    ErrorCode.VALIDATION_ERROR: ErrorCopy(
        http="请求参数不合法",
        im="请求内容不合法，请检查后重试。",
        web="请求内容不合法，请检查后重试。",
    ),
    ErrorCode.AUTHENTICATION_FAILED: ErrorCopy(
        http="身份校验失败",
        im="身份校验失败，请重新登录。",
        web="登录状态已失效，请重新登录。",
    ),
    ErrorCode.FORBIDDEN: ErrorCopy(
        http="无权访问该资源",
        im="你没有权限执行这个操作。",
        web="你没有权限执行这个操作。",
    ),
    ErrorCode.RATE_LIMITED: ErrorCopy(
        http="请求过于频繁，请稍后重试",
        im="请求太频繁了，稍等一会儿再试。",
        web="请求太频繁了，稍等一会儿再试。",
    ),
    ErrorCode.INTERNAL_ERROR: ErrorCopy(
        http="服务内部错误",
        im="服务出错了，请稍后重试。",
        web="服务出错了，请稍后重试。",
    ),
    ErrorCode.TOOL_IDEMPOTENCY_CONFLICT: ErrorCopy(
        http="工具调用的幂等键与参数不匹配",
        im="这次工具调用的参数和之前不一致，请重试。",
        web="这次工具调用的参数和之前不一致，请重试。",
    ),
    ErrorCode.TOOL_IN_PROGRESS: ErrorCopy(
        http="同样的工具调用正在执行中",
        im="这个操作正在执行，请稍等。",
        web="这个操作正在执行，请稍等。",
    ),
    ErrorCode.CONTEXT_TOO_LARGE: ErrorCopy(
        http="上下文超出模型上限",
        im="这次的内容太长了，请分几次问。",
        web="这次的内容太长了，请分几次问。",
    ),
    ErrorCode.AGENT_NOT_AVAILABLE: ErrorCopy(
        http="没有可用的智能体",
        im="暂时没有可用的智能体，请稍后再试。",
        web="暂时没有可用的智能体，请稍后再试。",
    ),
    ErrorCode.SESSION_BUSY: ErrorCopy(
        http="该会话已有进行中的轮次",
        im="这个会话还在处理上一条消息，请稍等。",
        web="这个会话还在处理上一条消息，请稍等。",
    ),
    ErrorCode.QUEUE_FULL: ErrorCopy(
        http="该会话排队已满，请稍后再发",
        im="这个会话排队的消息太多了，请稍后再发。",
        web="这个会话排队的消息太多了，请稍后再发。",
    ),
    ErrorCode.QUEUE_TIMEOUT: ErrorCopy(
        http="排队等待超时，这一轮没有执行",
        im="等太久了，这一轮没有执行，请重发。",
        web="等太久了，这一轮没有执行，请重发。",
    ),
    ErrorCode.CHANNEL_NOT_FOUND: ErrorCopy(
        http="渠道不存在",
        im="找不到对应的渠道，请检查配置。",
        web="找不到对应的渠道，请检查配置。",
    ),
    ErrorCode.CHANNEL_DISABLED: ErrorCopy(
        http="渠道已停用",
        im="该渠道已停用，暂时无法处理消息。",
        web="该渠道已停用，暂时无法处理消息。",
    ),
    ErrorCode.INBOUND_ADAPTER_MISSING: ErrorCopy(
        http="该渠道类型未注册入站解析器",
        im="这个渠道类型暂时无法接收消息。",
        web="这个渠道类型暂时无法接收消息。",
    ),
    ErrorCode.WEBHOOK_SIGNATURE_INVALID: ErrorCopy(
        http="Webhook 签名校验失败",
        im="消息来源校验未通过。",
        web="消息来源校验未通过。",
    ),
    ErrorCode.WEBHOOK_TIMESTAMP_SKEW: ErrorCopy(
        http="Webhook 时间戳超出允许偏差",
        im="消息时间戳超出允许偏差。",
        web="消息时间戳超出允许偏差。",
    ),
    ErrorCode.DUPLICATE_REQUEST: ErrorCopy(
        http="请求重复，已被幂等拦截",
        im="这条消息已经处理过了。",
        web="这条消息已经处理过了。",
    ),
    ErrorCode.TENANT_DENIED: ErrorCopy(
        http="跨租户访问被拒绝",
        im="无权访问该资源。",
        web="无权访问该资源。",
    ),
    ErrorCode.CHANNEL_SERVICE_ACCOUNT_MISSING: ErrorCopy(
        http="渠道未登记服务账号",
        im="这个渠道还没配置服务账号，暂时无法自动回复。",
        web="这个渠道还没配置服务账号，暂时无法自动回复。",
    ),
    ErrorCode.CHANNEL_DELIVERY_FAILED: ErrorCopy(
        http="渠道投递失败",
        im="消息发送失败了，请稍后重试。",
        web="消息发送失败了，请稍后重试。",
    ),
    ErrorCode.OUTBOUND_ADAPTER_MISSING: ErrorCopy(
        http="该渠道类型未注册出站适配器",
        im="这个渠道类型暂时无法发送消息。",
        web="这个渠道类型暂时无法发送消息。",
    ),
    ErrorCode.IDENTITY_REJECTED: ErrorCopy(
        http="身份校验失败",
        im="身份校验失败，请重新登录。",
        web="登录状态已失效，请重新登录。",
    ),
    ErrorCode.IDENTITY_CREDENTIALS_MISSING: ErrorCopy(
        http="缺少身份凭证",
        im="缺少身份凭证，请重新登录。",
        web="缺少身份凭证，请重新登录。",
    ),
    ErrorCode.TOKEN_INVALID: ErrorCopy(
        http="登录凭证无效",
        im="登录凭证无效，请重新登录。",
        web="登录凭证无效，请重新登录。",
    ),
    ErrorCode.TOKEN_EXPIRED: ErrorCopy(
        http="登录凭证已过期",
        im="登录已过期，请重新登录。",
        web="登录已过期，请重新登录。",
    ),
    ErrorCode.SERVICE_ACCOUNT_NOT_CONFIGURED: ErrorCopy(
        http="渠道未登记服务账号",
        im="这个渠道还没配置服务账号，暂时无法自动回复。",
        web="这个渠道还没配置服务账号，暂时无法自动回复。",
    ),
    ErrorCode.APPROVER_MUST_DIFFER: ErrorCopy(
        http="审批人不能是发起人",
        im="这个操作需要别人来确认，不能自己批。",
        web="这个操作需要别人来确认，不能自己批。",
    ),
    # ── 跨模块收敛（G-02b 扩展 · 2026-10-31）──────────────────────────
    # ⚠️ **每个枚举成员都必须有文案** ✓ —— 漏了就是「兜底文案」✓ —— 而兜底
    # 是「操作未完成，请稍后重试」✓ —— **用户不知道自己该改什么** ✗。
    # 由 `tests/architecture/test_error_code_vocabulary.py` 守门 ✓。
    # ── agent_runtime ─────────────────────────────────────────────────
    ErrorCode.AGENT_NOT_FOUND: ErrorCopy(
        http="智能体不存在",
        im="找不到这个智能体，请检查配置。",
        web="找不到这个智能体，请检查配置。",
    ),
    ErrorCode.AGENT_DISABLED: ErrorCopy(
        http="智能体已停用",
        im="这个智能体已停用，暂时无法使用。",
        web="这个智能体已停用，暂时无法使用。",
    ),
    ErrorCode.AGENT_CAPABILITY_UNAVAILABLE: ErrorCopy(
        http="智能体不支持该能力",
        im="这个智能体不支持当前的操作。",
        web="这个智能体不支持当前的操作。",
    ),
    ErrorCode.SESSION_NOT_FOUND: ErrorCopy(
        http="会话不存在", im="找不到这个会话，可能已被删除。", web="找不到这个会话，可能已被删除。"
    ),
    ErrorCode.TURN_NOT_FOUND: ErrorCopy(
        http="轮次不存在", im="找不到这一轮对话。", web="找不到这一轮对话。"
    ),
    ErrorCode.SESSION_CLOSED: ErrorCopy(
        http="会话已关闭", im="这个会话已结束，请新建一个。", web="这个会话已结束，请新建一个。"
    ),
    ErrorCode.TOOL_ACTOR_MISSING: ErrorCopy(
        http="缺少操作者身份",
        im="无法确认是谁在操作，请重新登录。",
        web="无法确认是谁在操作，请重新登录。",
    ),
    ErrorCode.TOOL_ACTOR_TENANT_MISMATCH: ErrorCopy(
        http="操作者与租户不匹配",
        im="无权在当前空间执行这个操作。",
        web="无权在当前空间执行这个操作。",
    ),
    ErrorCode.SUB_AGENT_UNAVAILABLE: ErrorCopy(
        http="子代理不可用",
        im="暂时找不到合适的子代理，请稍后再试。",
        web="暂时找不到合适的子代理，请稍后再试。",
    ),
    ErrorCode.SUBAGENT_CRASHED: ErrorCopy(
        http="子代理执行中断", im="子代理执行中断了，请重试。", web="子代理执行中断了，请重试。"
    ),
    ErrorCode.ZOMBIE_TAKEOVER: ErrorCopy(
        http="已接管中断的轮次", im="上一轮中断了，已重新开始。", web="上一轮中断了，已重新开始。"
    ),
    # ── agent_factory ──────────────────────────────────────────────────
    ErrorCode.AGENT_TEMPLATE_NOT_FOUND: ErrorCopy(
        http="智能体模板不存在",
        im="找不到这个模板，请检查配置。",
        web="找不到这个模板，请检查配置。",
    ),
    ErrorCode.AGENT_VERSION_NOT_FOUND: ErrorCopy(
        http="智能体版本不存在",
        im="找不到这个版本，请检查配置。",
        web="找不到这个版本，请检查配置。",
    ),
    ErrorCode.RELEASE_NOT_FOUND: ErrorCopy(
        http="发布记录不存在", im="找不到这次发布记录。", web="找不到这次发布记录。"
    ),
    ErrorCode.AGENT_TEMPLATE_NAME_CONFLICT: ErrorCopy(
        http="模板名称重复", im="已经有同名模板了，换个名字。", web="已经有同名模板了，换个名字。"
    ),
    ErrorCode.AGENT_VERSION_TAG_CONFLICT: ErrorCopy(
        http="版本标签重复", im="这个标签已经被别的版本用了。", web="这个标签已经被别的版本用了。"
    ),
    ErrorCode.AGENT_VERSION_IMMUTABLE: ErrorCopy(
        http="版本已发布不可修改",
        im="已发布的版本不能修改，请新建一个版本。",
        web="已发布的版本不能修改，请新建一个版本。",
    ),
    ErrorCode.AGENT_VERSION_INVALID_TRANSITION: ErrorCopy(
        http="版本状态流转不合法", im="当前状态不能这么改。", web="当前状态不能这么改。"
    ),
    ErrorCode.AGENT_FACTORY_POLICY_DENIED: ErrorCopy(
        http="策略拒绝该操作", im="这个操作被治理策略拦下了。", web="这个操作被治理策略拦下了。"
    ),
    # ── evaluation ─────────────────────────────────────────────────────
    ErrorCode.EVAL_AGENT_NOT_FOUND: ErrorCopy(
        http="评测用的智能体不存在", im="找不到要评测的智能体。", web="找不到要评测的智能体。"
    ),
    ErrorCode.EVAL_APPROVAL_REQUIRED: ErrorCopy(
        http="评测需要审批",
        im="这次评测需要人工确认后才能继续。",
        web="这次评测需要人工确认后才能继续。",
    ),
    ErrorCode.EVAL_VERSION_MISSING: ErrorCopy(
        http="评测版本缺失", im="这次评测没有对应的版本。", web="这次评测没有对应的版本。"
    ),
    ErrorCode.EVAL_INVALID_VERSION: ErrorCopy(
        http="评测版本不合法", im="版本标识不合法，请检查配置。", web="版本标识不合法，请检查配置。"
    ),
    ErrorCode.EVAL_VERSION_NOT_PUBLISHED: ErrorCopy(
        http="评测版本未发布", im="只能评测已发布的版本。", web="只能评测已发布的版本。"
    ),
    ErrorCode.EVAL_GATE_FAILED: ErrorCopy(
        http="评测门禁未通过", im="这次评测没过质量门禁。", web="这次评测没过质量门禁。"
    ),
    ErrorCode.RUNNER_ERROR: ErrorCopy(
        http="评测执行出错", im="评测执行中断了，请重试。", web="评测执行中断了，请重试。"
    ),
    # ── governance ─────────────────────────────────────────────────────
    ErrorCode.POLICY_NOT_FOUND: ErrorCopy(
        http="策略不存在", im="找不到这个策略，请检查配置。", web="找不到这个策略，请检查配置。"
    ),
    ErrorCode.POLICY_ALREADY_EXISTS: ErrorCopy(
        http="策略已存在", im="已经有同名策略了。", web="已经有同名策略了。"
    ),
    ErrorCode.APPROVAL_NOT_FOUND: ErrorCopy(
        http="审批不存在", im="找不到这条审批，可能已被处理。", web="找不到这条审批，可能已被处理。"
    ),
    ErrorCode.APPROVAL_ALREADY_DECIDED: ErrorCopy(
        http="审批已处理", im="这条审批已经处理过了。", web="这条审批已经处理过了。"
    ),
    ErrorCode.INVALID_POLICY: ErrorCopy(
        http="策略内容不合法",
        im="策略内容不合法，请检查后重试。",
        web="策略内容不合法，请检查后重试。",
    ),
    ErrorCode.INVALID_APPROVAL: ErrorCopy(
        http="审批内容不合法",
        im="审批内容不合法，请检查后重试。",
        web="审批内容不合法，请检查后重试。",
    ),
    ErrorCode.DATA_SUBJECT_FAILED: ErrorCopy(
        http="数据主体请求处理失败",
        im="处理你的数据请求时出错了，请稍后重试。",
        web="处理你的数据请求时出错了，请稍后重试。",
    ),
    # ── identity ───────────────────────────────────────────────────────
    ErrorCode.TENANT_NOT_FOUND: ErrorCopy(
        http="租户不存在", im="找不到对应的租户。", web="找不到对应的租户。"
    ),
    ErrorCode.WORKSPACE_NOT_FOUND: ErrorCopy(
        http="工作区不存在",
        im="找不到这个工作区，请检查配置。",
        web="找不到这个工作区，请检查配置。",
    ),
    ErrorCode.USER_NOT_FOUND: ErrorCopy(
        http="用户不存在", im="找不到这个用户。", web="找不到这个用户。"
    ),
    ErrorCode.API_KEY_NOT_FOUND: ErrorCopy(
        http="API Key 不存在", im="找不到这个 API Key。", web="找不到这个 API Key。"
    ),
    ErrorCode.TENANT_ALREADY_EXISTS: ErrorCopy(
        http="租户已存在", im="这个租户已经存在了。", web="这个租户已经存在了。"
    ),
    ErrorCode.WORKSPACE_ALREADY_EXISTS: ErrorCopy(
        http="工作区已存在", im="这个工作区已经存在了。", web="这个工作区已经存在了。"
    ),
    ErrorCode.USER_ALREADY_EXISTS: ErrorCopy(
        http="用户已存在", im="这个用户已经存在了。", web="这个用户已经存在了。"
    ),
    ErrorCode.INVALID_CREDENTIALS: ErrorCopy(
        http="凭证无效", im="账号或密码不正确，请重新登录。", web="账号或密码不正确，请重新登录。"
    ),
    ErrorCode.API_KEY_REVOKED: ErrorCopy(
        http="API Key 已吊销",
        im="这个 API Key 已被吊销，请换一个。",
        web="这个 API Key 已被吊销，请换一个。",
    ),
    ErrorCode.WORKSPACE_LIMIT_REACHED: ErrorCopy(
        http="工作区数量已达上限",
        im="工作区数量已达上限，请先清理。",
        web="工作区数量已达上限，请先清理。",
    ),
    ErrorCode.WORKSPACE_DENIED: ErrorCopy(
        http="无权访问该工作区", im="你没有权限访问这个工作区。", web="你没有权限访问这个工作区。"
    ),
    # ── knowledge ──────────────────────────────────────────────────────
    ErrorCode.KNOWLEDGE_NOT_FOUND: ErrorCopy(
        http="知识文档不存在", im="找不到这份文档。", web="找不到这份文档。"
    ),
    ErrorCode.KNOWLEDGE_INVALID: ErrorCopy(
        http="知识文档内容不合法",
        im="文档内容不合法，请检查后重试。",
        web="文档内容不合法，请检查后重试。",
    ),
    # ── memory ─────────────────────────────────────────────────────────
    ErrorCode.MEMORY_NOT_FOUND: ErrorCopy(
        http="记忆不存在", im="找不到这条记忆。", web="找不到这条记忆。"
    ),
    ErrorCode.MEMORY_VERSION_CONFLICT: ErrorCopy(
        http="记忆版本冲突",
        im="这条记忆被别人改过了，请刷新后重试。",
        web="这条记忆被别人改过了，请刷新后重试。",
    ),
    ErrorCode.MEMORY_SENSITIVE_CONTENT: ErrorCopy(
        http="记忆内容包含敏感信息",
        im="这段内容包含敏感信息，不能写进记忆。",
        web="这段内容包含敏感信息，不能写进记忆。",
    ),
    ErrorCode.MEMORY_DUPLICATE_CONTENT: ErrorCopy(
        http="记忆内容重复", im="这段内容已经记过了。", web="这段内容已经记过了。"
    ),
    ErrorCode.MEMORY_SCOPE_UNSUPPORTED: ErrorCopy(
        http="记忆作用域不支持", im="这个作用域不支持写入记忆。", web="这个作用域不支持写入记忆。"
    ),
    ErrorCode.MEMORY_POLICY_PUBLISHER_MISSING: ErrorCopy(
        http="记忆策略发布器缺失",
        im="记忆策略还没就绪，请稍后重试。",
        web="记忆策略还没就绪，请稍后重试。",
    ),
    # ── model ──────────────────────────────────────────────────────────
    ErrorCode.MODEL_NOT_FOUND: ErrorCopy(
        http="模型不存在", im="找不到这个模型，请检查配置。", web="找不到这个模型，请检查配置。"
    ),
    ErrorCode.PROVIDER_NOT_FOUND: ErrorCopy(
        http="模型供应商不存在", im="找不到这个模型供应商。", web="找不到这个模型供应商。"
    ),
    ErrorCode.PROVIDER_UNAVAILABLE: ErrorCopy(
        http="模型供应商暂不可用",
        im="模型服务暂时不可用，请稍后重试。",
        web="模型服务暂时不可用，请稍后重试。",
    ),
    ErrorCode.ROUTE_NOT_FOUND: ErrorCopy(
        http="模型路由不存在", im="找不到对应的模型路由。", web="找不到对应的模型路由。"
    ),
    ErrorCode.MODEL_DISABLED: ErrorCopy(
        http="模型已停用", im="这个模型已停用，请换一个。", web="这个模型已停用，请换一个。"
    ),
    ErrorCode.CREDENTIAL_NOT_FOUND: ErrorCopy(
        http="凭证不存在", im="找不到对应的凭证，请检查配置。", web="找不到对应的凭证，请检查配置。"
    ),
    ErrorCode.MODEL_ROUTE_EXHAUSTED: ErrorCopy(
        http="模型路由已用尽",
        im="没有可用的模型了，请稍后重试。",
        web="没有可用的模型了，请稍后重试。",
    ),
    ErrorCode.QUOTA_EXCEEDED: ErrorCopy(
        http="超出配额", im="用量已达上限，请稍后再试。", web="用量已达上限，请稍后再试。"
    ),
    ErrorCode.LLM_STREAM_EMPTY: ErrorCopy(
        http="模型返回为空", im="模型没有返回内容，请重试。", web="模型没有返回内容，请重试。"
    ),
    ErrorCode.LLM_NOT_CONFIGURED: ErrorCopy(
        http="模型未配置", im="还没有配置模型，请先完成配置。", web="还没有配置模型，请先完成配置。"
    ),
    # ── observability ──────────────────────────────────────────────────
    ErrorCode.RUN_RECORD_NOT_FOUND: ErrorCopy(
        http="运行记录不存在", im="找不到这次运行记录。", web="找不到这次运行记录。"
    ),
    ErrorCode.COST_RECORD_NOT_FOUND: ErrorCopy(
        http="成本记录不存在", im="找不到这条成本记录。", web="找不到这条成本记录。"
    ),
    ErrorCode.QUALITY_NOT_FOUND: ErrorCopy(
        http="质量评分不存在", im="找不到这条质量评分。", web="找不到这条质量评分。"
    ),
    ErrorCode.OBSERVABILITY_POLICY_DENIED: ErrorCopy(
        http="观测策略拒绝该操作", im="这个操作被观测策略拦下了。", web="这个操作被观测策略拦下了。"
    ),
    ErrorCode.RUN_TYPE_INVALID: ErrorCopy(
        http="运行类型不合法", im="运行类型不合法，请检查配置。", web="运行类型不合法，请检查配置。"
    ),
    ErrorCode.RUN_STATUS_INVALID: ErrorCopy(
        http="运行状态不合法", im="运行状态不合法，请检查配置。", web="运行状态不合法，请检查配置。"
    ),
    ErrorCode.COST_TYPE_INVALID: ErrorCopy(
        http="成本类型不合法", im="成本类型不合法，请检查配置。", web="成本类型不合法，请检查配置。"
    ),
    ErrorCode.COST_INVALID: ErrorCopy(
        http="成本数据不合法",
        im="成本数据不合法，请检查后重试。",
        web="成本数据不合法，请检查后重试。",
    ),
    ErrorCode.GROUP_BY_INVALID: ErrorCopy(
        http="分组维度不合法", im="这个分组维度不支持。", web="这个分组维度不支持。"
    ),
    # ── orchestration ──────────────────────────────────────────────────
    ErrorCode.WORKFLOW_NOT_FOUND: ErrorCopy(
        http="工作流不存在",
        im="找不到这个工作流，请检查配置。",
        web="找不到这个工作流，请检查配置。",
    ),
    ErrorCode.WORKFLOW_UNAVAILABLE: ErrorCopy(
        http="工作流暂不可用",
        im="工作流暂时不可用，请稍后重试。",
        web="工作流暂时不可用，请稍后重试。",
    ),
    # ── platform ───────────────────────────────────────────────────────
    ErrorCode.PLAN_NOT_FOUND: ErrorCopy(
        http="套餐不存在", im="找不到这个套餐，请检查配置。", web="找不到这个套餐，请检查配置。"
    ),
    ErrorCode.PLAN_ALREADY_EXISTS: ErrorCopy(
        http="套餐已存在", im="已经有同名套餐了。", web="已经有同名套餐了。"
    ),
    ErrorCode.PLAN_RETIRED: ErrorCopy(
        http="套餐已下线", im="这个套餐已下线，请换一个。", web="这个套餐已下线，请换一个。"
    ),
    ErrorCode.SUBSCRIPTION_INVALID_TRANSITION: ErrorCopy(
        http="订阅状态流转不合法", im="当前订阅状态不能这么改。", web="当前订阅状态不能这么改。"
    ),
    ErrorCode.TENANT_SETTING_NOT_FOUND: ErrorCopy(
        http="租户配置不存在", im="找不到这个租户配置。", web="找不到这个租户配置。"
    ),
    ErrorCode.TENANT_SETTING_CONFLICT: ErrorCopy(
        http="租户配置冲突",
        im="配置已被别人改过，请刷新后重试。",
        web="配置已被别人改过，请刷新后重试。",
    ),
    # ── self_evolution ─────────────────────────────────────────────────
    ErrorCode.EVOLVE_CANDIDATE_NOT_FOUND: ErrorCopy(
        http="演进候选不存在", im="找不到这个演进候选。", web="找不到这个演进候选。"
    ),
    ErrorCode.EVOLVE_CANDIDATE_ALREADY_DECIDED: ErrorCopy(
        http="演进候选已决策", im="这个候选已经决策过了。", web="这个候选已经决策过了。"
    ),
    ErrorCode.EVOLVE_SIGNER_MUST_DIFFER: ErrorCopy(
        http="签名人不能是发起人",
        im="这个操作需要别人来确认，不能自己签。",
        web="这个操作需要别人来确认，不能自己签。",
    ),
    ErrorCode.INVALID_EVOLVE_CANDIDATE: ErrorCopy(
        http="演进候选不合法",
        im="候选内容不合法，请检查后重试。",
        web="候选内容不合法，请检查后重试。",
    ),
    ErrorCode.APPLY_GUARD_REJECTED: ErrorCopy(
        http="应用守卫拒绝", im="这次变更没有通过守卫检查。", web="这次变更没有通过守卫检查。"
    ),
    # ── skill ──────────────────────────────────────────────────────────
    ErrorCode.SKILL_NOT_FOUND: ErrorCopy(
        http="技能不存在", im="找不到这个技能。", web="找不到这个技能。"
    ),
    ErrorCode.SKILL_DISABLED: ErrorCopy(
        http="技能已停用", im="这个技能已停用，暂时无法使用。", web="这个技能已停用，暂时无法使用。"
    ),
    ErrorCode.SKILL_NEEDS_CONFIRM: ErrorCopy(
        http="技能需要确认",
        im="这个操作需要你确认后才能继续。",
        web="这个操作需要你确认后才能继续。",
    ),
    ErrorCode.SKILL_NOT_EXECUTABLE: ErrorCopy(
        http="技能不可执行", im="这个技能当前不能直接执行。", web="这个技能当前不能直接执行。"
    ),
    # ── tool ───────────────────────────────────────────────────────────
    ErrorCode.TOOL_NOT_FOUND: ErrorCopy(
        http="工具不存在", im="找不到这个工具，请检查配置。", web="找不到这个工具，请检查配置。"
    ),
    ErrorCode.TOOL_ALREADY_EXISTS: ErrorCopy(
        http="工具已存在", im="已经有同名工具了。", web="已经有同名工具了。"
    ),
    ErrorCode.TOOL_VERSION_MISMATCH: ErrorCopy(
        http="工具版本不匹配", im="工具版本对不上，请检查配置。", web="工具版本对不上，请检查配置。"
    ),
    ErrorCode.TOOL_DISABLED: ErrorCopy(
        http="工具已停用", im="这个工具已停用，暂时无法使用。", web="这个工具已停用，暂时无法使用。"
    ),
    ErrorCode.TOOL_CALL_TIMEOUT: ErrorCopy(
        http="工具调用超时", im="工具执行超时了，请重试。", web="工具执行超时了，请重试。"
    ),
    ErrorCode.TOOL_DENIED: ErrorCopy(
        http="工具被拒绝", im="这个工具调用被治理策略拦下了。", web="这个工具调用被治理策略拦下了。"
    ),
    ErrorCode.TOOL_STALLED: ErrorCopy(
        http="工具执行停滞", im="工具一直没返回，已中止。", web="工具一直没返回，已中止。"
    ),
    ErrorCode.INVALID_TOOL_SPEC: ErrorCopy(
        http="工具定义不合法", im="工具定义不合法，请检查配置。", web="工具定义不合法，请检查配置。"
    ),
    ErrorCode.UPSTREAM_UNAVAILABLE: ErrorCopy(
        http="上游服务不可用",
        im="上游服务暂时不可用，请稍后重试。",
        web="上游服务暂时不可用，请稍后重试。",
    ),
    # ── 沙箱 ───────────────────────────────────────────────────────────
    ErrorCode.SANDBOX_UNAVAILABLE: ErrorCopy(
        http="沙箱不可用",
        im="代码沙箱暂时不可用，请稍后重试。",
        web="代码沙箱暂时不可用，请稍后重试。",
    ),
    ErrorCode.SANDBOX_TIMEOUT: ErrorCopy(
        http="沙箱执行超时",
        im="沙箱执行超时了，请缩小范围再试。",
        web="沙箱执行超时了，请缩小范围再试。",
    ),
    ErrorCode.SANDBOX_CANCELLED: ErrorCopy(
        http="沙箱执行已取消", im="沙箱执行被取消了。", web="沙箱执行被取消了。"
    ),
    ErrorCode.SANDBOX_FAILED: ErrorCopy(
        http="沙箱执行失败", im="沙箱执行失败了，请重试。", web="沙箱执行失败了，请重试。"
    ),
    ErrorCode.SANDBOX_HTTP_ERROR: ErrorCopy(
        http="沙箱服务通信失败",
        im="沙箱服务通信失败，请稍后重试。",
        web="沙箱服务通信失败，请稍后重试。",
    ),
    ErrorCode.SANDBOX_BAD_LANGUAGE: ErrorCopy(
        http="沙箱不支持该语言", im="沙箱不支持这种编程语言。", web="沙箱不支持这种编程语言。"
    ),
    ErrorCode.SANDBOX_BAD_PATH: ErrorCopy(
        http="沙箱路径不合法", im="这个路径不被允许访问。", web="这个路径不被允许访问。"
    ),
    # ── 轮次 ───────────────────────────────────────────────────────────
    ErrorCode.TURN_CANCELLED: ErrorCopy(
        http="轮次已取消", im="这次回答已经停止。", web="这次回答已经停止。"
    ),
    ErrorCode.TURN_FAILED: ErrorCopy(
        http="轮次执行失败", im="这次回答没能完成，请重试。", web="这次回答没能完成，请重试。"
    ),
    # ── libs/vault ─────────────────────────────────────────────────────
    ErrorCode.SECRET_NOT_FOUND: ErrorCopy(
        http="密钥不存在", im="找不到对应的密钥，请检查配置。", web="找不到对应的密钥，请检查配置。"
    ),
    ErrorCode.SECRET_ACCESS_DENIED: ErrorCopy(
        http="无权访问该密钥", im="你没有权限读取这个密钥。", web="你没有权限读取这个密钥。"
    ),
    ErrorCode.INVALID_SECRET_REF: ErrorCopy(
        http="密钥引用不合法",
        im="密钥引用格式不对，请检查配置。",
        web="密钥引用格式不对，请检查配置。",
    ),
    ErrorCode.INVALID_KEY: ErrorCopy(
        http="密钥不合法", im="密钥格式不对，请检查配置。", web="密钥格式不对，请检查配置。"
    ),
    ErrorCode.INVALID_CIPHERTEXT: ErrorCopy(
        http="密文不合法", im="加密内容不合法，请重新操作。", web="加密内容不合法，请重新操作。"
    ),
    ErrorCode.CRYPTO_ERROR: ErrorCopy(
        http="加解密失败", im="加解密处理失败了，请重试。", web="加解密处理失败了，请重试。"
    ),
    # ── libs/auth ──────────────────────────────────────────────────────
    ErrorCode.MISSING_TOKEN: ErrorCopy(
        http="缺少访问令牌", im="请先登录再继续。", web="请先登录再继续。"
    ),
    ErrorCode.INSUFFICIENT_SCOPE: ErrorCopy(
        http="权限范围不足", im="你的账号没有这个操作的权限。", web="你的账号没有这个操作的权限。"
    ),
    ErrorCode.INSUFFICIENT_ROLE: ErrorCopy(
        http="角色权限不足", im="你的角色不能执行这个操作。", web="你的角色不能执行这个操作。"
    ),
    # ── libs/http ──────────────────────────────────────────────────────
    ErrorCode.TENANT_HEADER_MISMATCH: ErrorCopy(
        http="租户标识不一致",
        im="请求里的租户标识不一致，请重试。",
        web="请求里的租户标识不一致，请重试。",
    ),
    ErrorCode.WORKSPACE_HEADER_MISMATCH: ErrorCopy(
        http="工作区标识不一致",
        im="请求里的工作区标识不一致，请重试。",
        web="请求里的工作区标识不一致，请重试。",
    ),
    # ── libs/llm ───────────────────────────────────────────────────────
    ErrorCode.LLM_INVALID_RESPONSE: ErrorCopy(
        http="模型返回不合法",
        im="模型返回的内容无法解析，请重试。",
        web="模型返回的内容无法解析，请重试。",
    ),
    ErrorCode.LLM_ALL_FAILED: ErrorCopy(
        http="全部模型都失败",
        im="所有模型都没能响应，请稍后重试。",
        web="所有模型都没能响应，请稍后重试。",
    ),
    ErrorCode.LLM_STREAM_ERROR: ErrorCopy(
        http="模型流式响应中断", im="模型响应中断了，请重试。", web="模型响应中断了，请重试。"
    ),
    # ── 既有成员里此前没有文案的（补齐）────────────────────────────────
    ErrorCode.ACTION_DENIED: ErrorCopy(
        http="操作被拒绝", im="这个操作不能执行。", web="这个操作不能执行。"
    ),
    ErrorCode.APPROVAL_EXPIRED: ErrorCopy(
        http="审批已过期", im="这条审批过期了，请重新发起。", web="这条审批过期了，请重新发起。"
    ),
    ErrorCode.APPROVAL_NOT_MATCH: ErrorCopy(
        http="审批内容不匹配",
        im="审批的内容对不上，请重新发起。",
        web="审批的内容对不上，请重新发起。",
    ),
    ErrorCode.APPROVAL_REQUIRED: ErrorCopy(
        http="需要审批",
        im="这个操作需要人工确认后才能继续。",
        web="这个操作需要人工确认后才能继续。",
    ),
    ErrorCode.BUSINESS_RULE_VIOLATED: ErrorCopy(
        http="违反业务规则", im="这个操作不符合业务规则。", web="这个操作不符合业务规则。"
    ),
    ErrorCode.CONFLICT: ErrorCopy(
        http="状态冲突",
        im="当前状态不能这么改，请刷新后重试。",
        web="当前状态不能这么改，请刷新后重试。",
    ),
    ErrorCode.EXTERNAL_SERVICE_ERROR: ErrorCopy(
        http="外部服务错误", im="外部服务出错了，请稍后重试。", web="外部服务出错了，请稍后重试。"
    ),
    ErrorCode.NOT_FOUND: ErrorCopy(
        http="资源不存在", im="找不到对应的资源。", web="找不到对应的资源。"
    ),
    ErrorCode.REVISION_CONFLICT: ErrorCopy(
        http="版本冲突",
        im="内容已被别人改过，请刷新后重试。",
        web="内容已被别人改过，请刷新后重试。",
    ),
    ErrorCode.TOOL_ARGUMENT_INVALID: ErrorCopy(
        http="工具参数不合法",
        im="工具参数不合法，请检查后重试。",
        web="工具参数不合法，请检查后重试。",
    ),
    ErrorCode.TOOL_RATE_LIMITED: ErrorCopy(
        http="工具调用过于频繁",
        im="这个工具调用太频繁了，请稍后再试。",
        web="这个工具调用太频繁了，请稍后再试。",
    ),
    ErrorCode.TOOL_TIMEOUT: ErrorCopy(
        http="工具调用超时", im="工具执行超时了，请重试。", web="工具执行超时了，请重试。"
    ),
}

_BY_VALUE: Mapping[str, ErrorCode] = {code.value: code for code in ErrorCode}


def try_project_error(code: str | ErrorCode, surface: ErrorSurface = "http") -> str | None:
    """码在表里才给文案；不认识就返回 ``None``。

    ⚠️ 给**已经有自己文案**的调用方用 —— 投影表没登记这个码时，调用方宁可
    保留原文，也不要被兜底文案覆盖（兜底会盖掉有用的细节）。
    """
    resolved = code if isinstance(code, ErrorCode) else _BY_VALUE.get(code)
    copy = ERROR_PROJECTION.get(resolved) if resolved is not None else None
    if copy is None:
        return None
    return copy.for_surface(surface)


def project_error(code: str | ErrorCode, surface: ErrorSurface = "http") -> str:
    """按错误码 + 投放面取文案。

    ⚠️ **码不认识就返回兜底文案**，不是把裸码返回去 —— 裸码对用户毫无意义
    （对日志毫无意义，但日志里另有 ``code`` 字段 ✓）。
    """
    resolved = code if isinstance(code, ErrorCode) else _BY_VALUE.get(code)
    copy = ERROR_PROJECTION.get(resolved) if resolved is not None else None
    if copy is None:
        return _FALLBACK_COPY.for_surface(surface)
    return copy.for_surface(surface)


def project_error_message(code: str, message: str, surface: ErrorSurface = "http") -> str:
    """**没有自己的消息时**用投影文案；有自己的消息就保留。

    ⚠️ 判据是「消息为空，或消息就是码本身」（`AppError.__init__` 是
    ``message or self.code``）—— 那说明调用方**没写消息**，信封里装的是
    **裸码**。有具体消息的**一律保留** —— 投影文案不覆盖有用的细节。
    """
    if not message or message == code:
        return project_error(code, surface)
    return message


__all__ = [
    "ERROR_PROJECTION",
    "ErrorCode",
    "ErrorCopy",
    "ErrorSurface",
    "project_error",
    "project_error_message",
    "try_project_error",
]
