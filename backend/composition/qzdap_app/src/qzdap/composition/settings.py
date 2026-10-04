"""Settings (pydantic-settings, QZDAP_-prefixed env)."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from qzdap_llm.config import LLMConfig, LLMProvider
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
    env: Literal["development", "test", "ci", "staging", "production"] = "development"
    debug: bool = True
    log_level: str = "INFO"
    log_json: bool = True

    # http
    http_host: str = "0.0.0.0"
    http_port: int = 8100
    http_workers: int = 1
    http_request_body_max_bytes: int = 10 * 1024 * 1024

    # database
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/qzdap_dev"
    database_pool_size: int = 20
    database_max_overflow: int = 10
    database_pool_recycle: int = 3600
    database_echo: bool = False

    # redis
    redis_url: str = "redis://localhost:6379/0"
    redis_max_connections: int = 50

    # auth
    jwt_secret: str = "dev-secret-not-for-production-use-only"
    jwt_algorithm: str = "HS256"
    jwt_issuer: str = "qzdap-dev"
    jwt_audience: str = "qzdap-api"
    jwt_access_ttl_seconds: int = 3600
    api_key_hash_rounds: int = 12

    # multi-tenancy
    ban_mock_token: int = 0
    allow_demo_token: int = 1
    demo_tenant_id: str = "00000000-0000-0000-0000-000000000001"
    dev_admin_email: str = "admin@example.com"
    dev_admin_password: str = "dev-admin-password-change-me"

    # llm
    llm_provider: str = "mock"
    llm_base_url: str = "https://api.openai.com/v1"
    llm_api_key: str = ""
    llm_default_model: str = "gpt-4o-mini"
    llm_timeout_seconds: int = 30
    llm_mock_latency_ms: int = 50
    llm_failover_providers: str = ""
    llm_embedding_model: str = "text-embedding-3-small"
    llm_embedding_dim: int = 1536

    # event bus
    event_bus: Literal["inprocess", "redis-stream"] = "inprocess"
    event_redis_stream_prefix: str = "qzdap:events:"
    event_dlq_stream: str = "qzdap:events:dlq"
    event_redis_consumer_name: str = ""  # env QZDAP_EVENT_REDIS_CONSUMER_NAME wins
    event_redis_max_retries: int = 3
    event_redis_block_ms: int = 1000
    event_redis_count: int = 10

    # audit pipeline (A5)
    # ``direct`` keeps the synchronous SqlAuditLogAdapter (default —
    # backward compatible). ``kafka`` routes audit events through
    # KafkaAuditPublisher → topic → KafkaAuditConsumer → audit_log SQL.
    audit_mode: Literal["direct", "kafka"] = "direct"
    audit_consumer_enabled: bool = True  # set false on N-1 k8s replicas
    audit_kafka_bootstrap_servers: str = "localhost:9092"
    audit_kafka_topic: str = "qzdap.audit.events"
    audit_kafka_dlq_topic: str = "qzdap.audit.events.dlq"
    audit_kafka_consumer_group: str = ""  # env/hostname fallback
    audit_kafka_max_retries: int = 3
    audit_kafka_block_ms: int = 1000
    audit_kafka_request_timeout_ms: int = 5000

    # rate limit
    rate_limit_per_tenant_per_min: int = 1000
    rate_limit_per_api_key_per_min: int = 1000
    rate_limit_window_seconds: int = 60

    # tool runtime
    tool_call_timeout_seconds: float = 30.0

    # sandbox_runtime (gVisor sidecar)
    sandbox_runtime_url: str = "http://127.0.0.1:8093"
    sandbox_runtime_secret: str = "dev-sandbox-runtime-secret-change-me"
    sandbox_default_image: str = "qzdap/sandbox-python:latest"
    skill_artifact_root: str = "/tmp/qzdap-skill-artifacts"
    skill_invocation_default_timeout_seconds: int = 30
    skill_artifact_tail_max_bytes: int = 4096

    # skill signing (A6) — ``disabled`` = NoOpSkillVetter (dev/test
    # opt-out, NEVER in prod); ``local`` = LocalTrustStoreSkillVetter
    # with a fail-loud boot if the trust dir is missing/empty;
    # ``vault`` = VaultBackedSkillVetter (Tier B, not implemented here).
    skill_signing_mode: Literal["disabled", "local", "vault"] = "disabled"
    skill_trust_dir: str = "./.qzdap/skill-trust"

    # Tier B — knowledge / plan pack signing (mirrors skill signing).
    # ``disabled`` = NoOp*Vetter; ``local`` = LocalTrustStore*Vetter.
    # ``vault`` is intentionally not wired here — symmetric to skill
    # ``vault`` branch but tracked as a separate ticket.
    knowledge_signing_mode: Literal["disabled", "local"] = "disabled"
    knowledge_trust_dir: str = "./.qzdap/knowledge-trust"
    plan_signing_mode: Literal["disabled", "local"] = "disabled"
    plan_trust_dir: str = "./.qzdap/plan-trust"

    # Tier B — vault-backed SkillVetter (mode="vault" wiring).
    # ``vault_skill_trust_ref`` is the KV v2 ref the vetter polls;
    # payload is ``{key_id: <PEM>}``.  ``refresh_seconds`` is the
    # in-process TTL between Vault re-reads (rotate-after-rotate lag).
    vault_skill_trust_ref: str = "vault:secret/data/qzdap/skill-trust/keys"
    vault_skill_trust_refresh_seconds: float = 300.0
    vault_skill_trust_min_keys: int = 1

    # Tier B — office seed walkers for knowledge + plan packs.  Same
    # shape as ``platform_seed_office_skill_packs`` (A6).
    platform_seed_office_knowledge_packs: bool = True
    platform_seed_office_plan_packs: bool = True
    platform_office_knowledge_packs_root: str = "packs/office/knowledge"
    platform_office_plan_packs_root: str = "packs/office/plans"

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

    # P5 governance
    policy_enabled: bool = True
    policy_cache_ttl_seconds: int = 30
    policy_approval_ttl_seconds: int = 3600
    vault_mode: Literal["env", "file", "noop", "csi", "vault"] = "env"
    vault_file_root: str = "/etc/qzdap/vault"
    embedding_provider: Literal["openai", "http", "noop"] = "noop"

    # P7 knowledge
    knowledge_storage_root: str = "/tmp/qzdap-knowledge-assets"
    knowledge_default_chunk_size: int = 800
    knowledge_default_chunk_overlap: int = 80

    # P7 orchestration
    orchestration_max_total_steps: int = 64
    orchestration_default_step_timeout_seconds: int = 60
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

    # P9 platform — default catalog + seed
    platform_default_plan_code: str = "free"
    platform_seed_default_plans: bool = True

    # A6 — office skill pack seeder (walks platform_office_skill_packs_root
    # at lifespan boot; requires skill_signing_mode=local unless
    # platform_seed_office_skill_packs=false).
    platform_seed_office_skill_packs: bool = True
    platform_office_skill_packs_root: str = "packs/office/skills"

    # A4 self-evolution — kind-specific ApplyGuard draft surface
    # (one JSONL per (tenant, kind); atomic append + fsync).
    evolution_drafts_dir: str = "var/evolution/drafts"
    evolution_apply_guard_mode: Literal["drafts", "direct"] = "drafts"

    # P6 model
    model_master_key: str = ""
    model_master_key_version: int = 1
    model_quota_default_window: Literal["minute", "hour", "day"] = "minute"
    model_quota_default_max_requests: int = 1000
    model_quota_default_max_tokens: int = 2_000_000
    model_invocation_timeout_seconds: float = 30.0

    # P6 channel
    channel_webhook_signature_tolerance_seconds: int = 300
    channel_default_inbound_max_body_bytes: int = 1 * 1024 * 1024
    # DingTalk Stream v2 encryption — the app secret is the AES key
    # material for inbound webhook payloads. Leave empty in dev to
    # preserve the legacy placeholder behaviour.
    dingtalk_app_secret: str = ""
    # WeChat Work (企业微信) JSON v2 callback — base64-decoded
    # EncodingAESKey (43 chars). Empty in dev keeps the placeholder.
    wechatwork_encoding_aes_key: str = ""

    def llm_config(self) -> LLMConfig:
        return LLMConfig(
            provider=LLMProvider(self.llm_provider),
            base_url=self.llm_base_url,
            api_key=self.llm_api_key,
            default_model=self.llm_default_model,
            embedding_model=self.llm_embedding_model,
            embedding_dim=self.llm_embedding_dim,
            timeout_seconds=self.llm_timeout_seconds,
            mock_latency_ms=self.llm_mock_latency_ms,
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]


def reset_settings_cache() -> None:
    get_settings.cache_clear()
