"""Settings (pydantic-settings, QZDAP_-prefixed env)."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="QZDAP_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # core
    # ⚠️ **只有一个开发环境** ✓ —— 演示 / 预发 / 生产环境都已退役 ✓
    # （``test`` / ``ci`` 是跑测试用的取值 ✓ —— 不是部署环境 ✓）。
    env: Literal["development", "test", "ci"] = "development"
    debug: bool = True
    log_level: str = "INFO"
    log_json: bool = True

    # database
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:9153/qzdap_dev"
    database_pool_size: int = 20
    database_max_overflow: int = 10
    database_pool_recycle: int = 3600
    database_echo: bool = False

    # ── Router（排队语义）──────────────────────────────────────────────
    # ⚠️ **排队是破坏性契约变更** ✓（Router 方案 §0.7 ✓）—— 默认**关** ✓
    # （关着 = 旧语义「拒绝 409 SESSION_BUSY」✓）；前端先兼容 `queued`
    # chunk ✓ 再开这个开关 ✓。
    router_queue_enabled: bool = False

    # ── 会话超时清扫 ────────────────────────────────────────────────────
    # ⚠️ **会话空闲阈值（天）** ✓ —— 决策 #7 ✓（30 天 ✓ —— 不按 agent /
    # 工作区分别配 ✓ —— 那会让配置面爆炸 ✓）。
    session_idle_timeout_days: int = 30
    # ⚠️ **事件流保留期（天）** ✓ —— ``session_events`` 是**重放日志** ✓
    # （轮次的终态在 ``session_turns`` ✓ —— 删事件不丢轮次 ✓）→ 不设保留期
    # 的话这张表只增不减 ✗✗。默认 7 天 ✓（断线重连用得到 ✓）。
    session_event_retention_days: int = 7

    # redis
    redis_url: str = "redis://localhost:9154/0"
    redis_max_connections: int = 50

    # auth
    # ⚠️ **本地默认值** ✓ —— 换成真值前相关能力是降级的 ✓
    # （见 ``/readyz`` 的 ``runtime`` 健康报告 ✓）。
    jwt_secret: str = "dev-secret-not-for-production-use-only"  # noqa: S105
    jwt_algorithm: str = "HS256"
    jwt_issuer: str = "qzdap-dev"
    jwt_audience: str = "qzdap-api"
    jwt_access_ttl_seconds: int = 3600

    # ── multi-tenancy / 种子数据 ─────────────────────────────────────────
    # ⚠️ **只剩开发环境这一套** ✓ —— 演示环境已退役 ✓（不再有 demo 租户 /
    # 演示账号 / 独立演示库 ✓）。开发环境的租户、账号、口令全在下面
    # ``dev_*`` 字段里 ✓（成员口令与管理员口令分开 ✓）。
    dev_tenant_slug: str = "dev"
    dev_tenant_display_name: str = "Dev Tenant"
    dev_admin_email: str = "admin@dev.qzdap.dev"
    dev_admin_password: str = "dev-admin-password-change-me"  # noqa: S105
    # ⚠️ **开发环境也要有「用户侧」账号** ✓（2026-11-01 ✓）——
    # **管理员只进管理台** ✓（前端 ``roleRoutes`` ✓ —— 管理员登录后落到
    # ``/admin/*`` ✓），**用户侧那套页面（工作台 / 对话 / 任务…）得另有一个
    # 成员账号** ✓ —— 否则开发环境**只能看管理台** ✗✗。
    # ⚠️ **口令与管理员的不共用** ✓（成员不该拿到管理员口令 ✓）。
    dev_user_email: str = "user@dev.qzdap.dev"
    dev_user_password: str = "dev-user-password-change-me"  # noqa: S105

    # ── LLM ──────────────────────────────────────────────────────────────
    # 历史: 之前这里有 llm_provider / llm_api_key / llm_base_url /
    # llm_default_model / llm_embedding_model / llm_embedding_dim 等字段
    # 用于构造 LLMConfig 作为全局默认 client. 这条路径已下线:
    # LLM 凭据统一在 管理侧 → 模型管理 配 (admin_model_providers.encrypted_payload),
    # 调用时由 ModelService._decrypt() 解密. 任何"未配置"场景由
    # unavailable_providers.UnavailableLLMClient 抛 ProviderUnavailable (503).
    # 这里只保留 test env 的 mock 逃生通道所需的字段(已无环境变量对应).

    # P6 model
    event_bus: Literal["inprocess", "redis-stream"] = "inprocess"
    event_redis_stream_prefix: str = "qzdap:events:"
    event_dlq_stream: str = "qzdap:events:dlq"
    event_redis_consumer_name: str = ""  # env QZDAP_EVENT_REDIS_CONSUMER_NAME wins
    event_redis_max_retries: int = 3
    event_redis_block_ms: int = 1000
    event_redis_count: int = 10

    # rate limit
    rate_limit_per_tenant_per_min: int = 1000
    rate_limit_window_seconds: int = 60

    # tool runtime
    tool_call_timeout_seconds: float = 30.0

    # sandbox_runtime (gVisor sidecar)
    sandbox_runtime_url: str = "http://127.0.0.1:9158"
    sandbox_runtime_secret: str = "dev-sandbox-runtime-secret-change-me"  # noqa: S105
    sandbox_default_image: str = "qzdap/sandbox-python:latest"

    # Agent 内置文件工具 (bash / read_file / write_file / edit_file / ls /
    # glob / grep) 看到的工作区根目录。每个 workspace 一个子目录:
    # `<workspace_root>/<workspace_id>/`。
    # dev 环境通常设到 /tmp/qzdap-workspaces 方便随时 reset。
    workspace_root: str = "/var/qzdap/workspaces"

    # Vault-backed KV resolver (Tier B, mode="vault").  Mirrors the
    # ``QZDAP_VAULT_URL`` / ``QZDAP_VAULT_TOKEN`` pattern used elsewhere;
    # HashicorpVaultSecretsResolver pulls URL + token from these fields
    # before falling back to ``VAULT_ADDR`` / ``VAULT_TOKEN``.
    vault_url: str = ""
    vault_token: str = ""

    # cors
    cors_allow_origins: str = "http://localhost:5173,http://localhost:3000"
    cors_allow_credentials: bool = True
    cors_allow_methods: str = "GET,POST,PUT,PATCH,DELETE,OPTIONS"
    cors_allow_headers: str = "*"

    # observability
    otlp_endpoint: str = ""
    metrics_path: str = "/metrics"
    traces_sample_rate: float = 1.0

    # 公开端点（不需要 token）—— 逗号分隔.
    # 结尾带 "*" 的是前缀规则, 其余按精确路径匹配.
    # 除这些以外的请求一律要求带 JWT: 没有 principal 就没有绑定的租户,
    # ORM 的租户自动过滤会退化成空操作, 路由就会去信调用方自己填的
    # X-Tenant-Id —— 那不是边界, 只是提示.
    public_paths: str = (
        "/healthz,/livez,/readyz,/metrics,/docs,/openapi.json,"
        "/v1/identity/login,/v1/identity/tenants,/v1/channels/*/webhook"
    )

    # P5 governance
    policy_enabled: bool = True
    policy_cache_ttl_seconds: int = 30
    policy_approval_ttl_seconds: int = 3600
    vault_mode: Literal["env", "file", "noop", "csi", "vault"] = "env"
    vault_file_root: str = "/etc/qzdap/vault"
    embedding_provider: Literal["openai", "http", "noop"] = "noop"

    knowledge_default_chunk_size: int = 800
    knowledge_default_chunk_overlap: int = 80

    embedding_runtime_url: str = "http://127.0.0.1:8102"
    embedding_runtime_api_key: str = ""
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"

    # P8 agent_factory + evaluation
    agent_factory_eval_score_min: float = 0.6
    evaluation_runner_concurrency: int = 4
    evaluation_case_default_timeout_seconds: float = 60.0

    # P9 observability — pricing source (JSON; fallback to defaults if malformed)
    model_pricing_json: str = (
        '{"default":{"input":"0.00015","output":"0.0006"},'
        '"gpt-4o-mini":{"input":"0.00015","output":"0.0006"},'
        '"gpt-4o":{"input":"0.0025","output":"0.01"}}'
    )
    tool_unit_cost_json: str = '{"echo":"0","reverse":"0","clock":"0"}'
    skill_unit_cost_json: str = "{}"
    memory_write_unit_cost_usd: float = 0.00001
    knowledge_ingest_unit_cost_usd: float = 0.001
    channel_send_unit_cost_usd: float = 0.0005
    default_currency: str = "USD"

    platform_seed_default_plans: bool = True

    # A4 self-evolution — kind-specific ApplyGuard draft surface
    # (one JSONL per (tenant, kind); atomic append + fsync).
    evolution_drafts_dir: str = "var/evolution/drafts"
    evolution_apply_guard_mode: Literal["drafts", "direct"] = "drafts"

    # P6 model
    model_master_key: str = ""
    model_invocation_timeout_seconds: float = 30.0
    # ⚠️ **LLM 上游重试** ✓ —— 只对瞬时错误 ✓（限流 / 5xx / 连接错 ✓）；
    # ⚠️ **流式吐过字之后不重试** ✓（重放会重复吐字 ✗✗）。
    llm_retry_max_attempts: int = 3
    llm_retry_base_delay_seconds: float = 0.2
    llm_retry_max_delay_seconds: float = 5.0

    # ── agent 循环（runtime）──────────────────────────────────────────
    #: **整轮超时** ✓（秒 ✓）—— 之前没有 ✓ → 上游挂住时连接一直占着 ✗✗。
    agent_turn_timeout_seconds: float = 300.0
    #: **单步超时** ✓（秒 ✓）—— 一步推理 / 一次模型调用的上限 ✓。
    agent_step_timeout_seconds: float = 120.0
    #: **单轮工具调用上限** ✓（0 = 不限 ✓）—— 模型一次吐 N 个调用 ✓ →
    #: 全部执行 ✓ → 成本 ✓ / 副作用 ✓ 都放大 N 倍 ✗✗。
    agent_max_tool_calls: int = 24

    # DingTalk Stream v2 encryption — the app secret is the AES key
    # material for inbound webhook payloads. Leave empty in dev to
    # preserve the legacy placeholder behaviour.
    dingtalk_app_secret: str = ""
    # WeChat Work (企业微信) JSON v2 callback — base64-decoded
    # EncodingAESKey (43 chars). Empty in dev keeps the placeholder.
    wechatwork_encoding_aes_key: str = ""


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]


def reset_settings_cache() -> None:
    get_settings.cache_clear()
