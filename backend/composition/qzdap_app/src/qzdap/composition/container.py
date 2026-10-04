"""DI container — instantiates adapters and wires them into services.

Per-request wiring (e.g. session-scoped repositories) happens in
``composition.lifespan``; the container only owns the long-lived
adapters and settings.
"""

from __future__ import annotations

from datetime import UTC
from typing import Any

from qzdap_auth.api_key import ApiKeyHasher
from qzdap_auth.jwt import JWTConfig, JWTIssuer, JWTVerifier
from qzdap_llm.config import LLMConfig
from qzdap_llm.embeddings import set_default_client
from qzdap_llm.mock import MockLLMClient
from qzdap_llm.openai_compatible import OpenAICompatibleClient
from qzdap_messaging.bus import EventBus
from qzdap_messaging.in_process import InProcessBus
from qzdap_persistence.session_factory import SessionFactory, create_engine
from qzdap_vault.hashicorp_vault import HashicorpVaultSecretsResolver
from qzdap_vault.resolver import VaultSecretsResolver
from qzdap_vector.store import VectorStore

from qzdap.composition.settings import Settings


class Container:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._services: dict[type, Any] = {}
        self._kafka_audit_producer: object | None = None
        self._kv_resolver: HashicorpVaultSecretsResolver | None = None
        # Fail-loud prod gate — same pattern as
        # ``model_credential_cipher`` raising on missing
        # ``QZDAP_MODEL_MASTER_KEY``.  Runs before any service is built so
        # the boot never gets far with a misconfigured prod secret.
        if settings.env == "production":
            self._validate_production_secrets(settings)

    # ── infra ───────────────────────────────────────────────────────────────

    @staticmethod
    def _validate_production_secrets(settings: Settings) -> None:
        """Boot-time fail-loud check for prod secrets that still hold the
        development defaults.  Mirrors ``model_credential_cipher`` raising
        on missing ``QZDAP_MODEL_MASTER_KEY`` — explicit fail beats silent
        misconfig.  Only fires when ``settings.env == "production"``.

        Anything starting with ``dev-`` (case-insensitive) is treated as
        a development sentinel.  Operators must set every secret to a
        non-sentinel value before the prod pod starts.

        In addition to raw-secret sentinel detection, this gate refuses
        to boot prod with any of the *default* dev/test backends:

        - signing modes must not be ``"disabled"`` (skill / knowledge /
          plan vetters fall through to NoOp variants)
        - ``embedding_provider`` must not be ``"noop"`` (memory &
          knowledge writes embed to a fake zero vector — semantic
          recall silently breaks)
        - ``vault_mode`` must be ``"csi"`` or ``"vault"`` (raw
          ``os.environ`` reads bypass the secrets manager)
        - ``event_bus`` must be ``"redis-stream"`` (cross-replica
          publishes are silently dropped with ``inprocess``)
        - ``model_master_key`` must be set + non-sentinel (model
          credential cipher refuses otherwise; we surface it here so
          the boot report is one consolidated failure)
        """
        sentinel_prefixes = ("dev-", "dev_")
        checks: tuple[tuple[str, str], ...] = (
            ("QZDAP_JWT_SECRET", settings.jwt_secret),
            ("QZDAP_SANDBOX_RUNTIME_SECRET", settings.sandbox_runtime_secret),
            ("QZDAP_DEV_ADMIN_PASSWORD", settings.dev_admin_password),
            ("QZDAP_MODEL_MASTER_KEY", settings.model_master_key),
        )
        offenders: list[str] = []
        for name, value in checks:
            stripped = value.strip()
            if not stripped or stripped.lower().startswith(sentinel_prefixes):
                offenders.append(name)
        if not settings.sandbox_runtime_url.strip():
            offenders.append("QZDAP_SANDBOX_RUNTIME_URL")
        if offenders:
            joined = ", ".join(offenders)
            raise RuntimeError(
                f"production env refuses to boot with development secrets: {joined}. "
                "Set QZDAP_JWT_SECRET / QZDAP_SANDBOX_RUNTIME_SECRET / QZDAP_DEV_ADMIN_PASSWORD "
                "/ QZDAP_MODEL_MASTER_KEY to real values via the QZDAP_*_REF indirection "
                "or your secrets manager."
            )

        # ── default-backend refusal ────────────────────────────────────
        # Each entry: (env var, current value, set of forbidden values).
        # Forbidding the dev default stops the prod path from silently
        # degrading to NoOp / NoOp-vetter / in-process bus.
        backend_checks: tuple[tuple[str, str, frozenset[str]], ...] = (
            ("QZDAP_SKILL_SIGNING_MODE", settings.skill_signing_mode,
             frozenset({"disabled"})),
            ("QZDAP_KNOWLEDGE_SIGNING_MODE", settings.knowledge_signing_mode,
             frozenset({"disabled"})),
            ("QZDAP_PLAN_SIGNING_MODE", settings.plan_signing_mode,
             frozenset({"disabled"})),
            ("QZDAP_EMBEDDING_PROVIDER", settings.embedding_provider,
             frozenset({"noop"})),
            ("QZDAP_VAULT_MODE", settings.vault_mode,
             frozenset({"env", "noop"})),
            ("QZDAP_EVENT_BUS", settings.event_bus,
             frozenset({"inprocess"})),
        )
        backend_offenders: list[str] = []
        for name, value, forbidden in backend_checks:
            if value in forbidden:
                backend_offenders.append(
                    f"{name}={value!r} (must not be any of {sorted(forbidden)})"
                )
        if backend_offenders:
            joined = ", ".join(backend_offenders)
            raise RuntimeError(
                "production env refuses to boot with dev-default backends: "
                f"{joined}. Set QZDAP_SKILL_SIGNING_MODE / QZDAP_KNOWLEDGE_SIGNING_MODE "
                "/ QZDAP_PLAN_SIGNING_MODE to 'local' or 'vault'; "
                "QZDAP_EMBEDDING_PROVIDER to 'openai' or 'http'; "
                "QZDAP_VAULT_MODE to 'csi' or 'vault'; "
                "QZDAP_EVENT_BUS to 'redis-stream'."
            )

    def engine(self):
        return create_engine(
            self.settings.database_url,
            pool_size=self.settings.database_pool_size,
            max_overflow=self.settings.database_max_overflow,
            pool_recycle=self.settings.database_pool_recycle,
            echo=self.settings.database_echo,
        )

    def session_factory(self) -> SessionFactory:
        return SessionFactory(self.engine())

    def redis_client(self):
        """Async Redis client for /readyz + RedisStreamBus.

        Imports lazily so the `redis` package is only required when
        something actually uses the connection (the in-process bus does
        not need it).
        """
        from redis.asyncio import Redis

        return Redis.from_url(
            self.settings.redis_url,
            max_connections=self.settings.redis_max_connections,
            decode_responses=False,
        )

    def bus(self) -> EventBus:
        """Return the configured EventBus backend.

        ``QZDAP_EVENT_BUS=inprocess`` (default) returns the in-process bus
        used by dev + tests. ``QZDAP_EVENT_BUS=redis-stream`` wires a real
        Redis Streams bus — every replica gets a stable consumer name
        (env / hostname / uuid4 fallback) so events reach all
        subscribers across the cluster.
        """
        if self.settings.event_bus == "redis-stream":
            from qzdap_messaging.redis_stream import RedisStreamBus

            return RedisStreamBus(
                self.redis_client(),
                prefix=self.settings.event_redis_stream_prefix,
                dlq_stream=self.settings.event_dlq_stream,
                consumer_name=self.settings.event_redis_consumer_name,
                max_retries=self.settings.event_redis_max_retries,
                block_ms=self.settings.event_redis_block_ms,
                count=self.settings.event_redis_count,
            )
        return InProcessBus()

    def hasher(self) -> ApiKeyHasher:
        return ApiKeyHasher()

    def jwt_config(self) -> JWTConfig:
        return JWTConfig(
            secret=self.settings.jwt_secret,
            algorithm=self.settings.jwt_algorithm,
            issuer=self.settings.jwt_issuer,
            audience=self.settings.jwt_audience,
            access_ttl_seconds=self.settings.jwt_access_ttl_seconds,
        )

    def jwt_issuer(self) -> JWTIssuer:
        return JWTIssuer(self.jwt_config())

    def jwt_verifier(self) -> JWTVerifier:
        return JWTVerifier(self.jwt_config())

    def llm_client(self):
        cfg: LLMConfig = self.settings.llm_config()
        if cfg.provider.value == "mock":
            return MockLLMClient(cfg)
        return OpenAICompatibleClient(cfg)

    def vector_store(self) -> VectorStore | None:
        """Hook up the pgvector store once we have an engine. Kept lazy to
        avoid forcing a connection at boot."""
        from qzdap_vector.pg_vector import PgVectorStore

        return PgVectorStore(self.engine(), dim=self.settings.llm_embedding_dim)

    def configure_llm_default(self) -> None:
        set_default_client(self.llm_client())

    def kv_resolver(self) -> HashicorpVaultSecretsResolver | None:
        """Singleton KV resolver — used by knowledge/plan vault vetters.

        Returns ``None`` unless ``QZDAP_VAULT_MODE=vault`` so the rest of the
        app can degrade gracefully (the A1 env/file resolvers stay in
        place for ``QZDAP_*_SECRET_REF`` lookups via ``secrets_resolver()``).
        """
        if self._kv_resolver is not None:
            return self._kv_resolver
        if self.settings.vault_mode != "vault":
            return None
        from qzdap_vault.hashicorp_vault import HashicorpVaultSecretsResolver

        self._kv_resolver = HashicorpVaultSecretsResolver(
            url=self.settings.vault_url,
            token=self.settings.vault_token,
            cache_ttl_seconds=30.0,
            cache_max_entries=256,
        )
        return self._kv_resolver

    # ── P5 secrets ──────────────────────────────────────────────────────────
    def secrets_resolver(self) -> VaultSecretsResolver | None:
        """Resolve the configured vault backend.

        ``vault_mode="noop"`` returns ``None`` so the tool/skill runtimes
        fall back to their no-op resolver (no auth headers).
        """
        mode = self.settings.vault_mode
        if mode == "noop":
            return None
        if mode == "env":
            from qzdap_vault.env_vault import EnvVaultSecretsResolver

            return EnvVaultSecretsResolver()
        if mode == "file":
            from qzdap_vault.file_vault import FileVaultSecretsResolver

            return FileVaultSecretsResolver(allowed_root=self.settings.vault_file_root)
        if mode == "csi":
            from qzdap_vault.csi_vault import CSIVaultSecretsResolver

            return CSIVaultSecretsResolver()
        if mode == "vault":
            from qzdap_vault.hashicorp_vault import HashicorpVaultSecretsResolver

            return HashicorpVaultSecretsResolver(
                url=self.settings.vault_url,
                token=self.settings.vault_token,
                cache_ttl_seconds=30.0,
                cache_max_entries=256,
            )
        raise RuntimeError(f"unknown vault_mode: {mode}")

    # ── P4 memory + P5 governance clock / id generator ─────────────────────
    def clock(self):
        from datetime import datetime

        class _WallClock:
            def now(self) -> datetime:
                return datetime.now(UTC)

        return _WallClock()

    def id_generator(self):
        from uuid import uuid4

        class _Uuid4Generator:
            def new_id(self):  # type: ignore[no-untyped-def]
                return uuid4()

        return _Uuid4Generator()

    def messaging_event_publisher(self) -> object:
        """Adapter that wraps an EventBus into the ``publish(topic, payload)``
        narrow Protocol used by governance."""
        from qzdap.modules.governance.adapter.events import (
            MessagingEventPublisher,
        )

        return MessagingEventPublisher(self.bus())

    def channel_event_publisher(self):
        """Adapter that wraps the bus for the P6 channel module's
        ``(event, *, tenant_id, workspace_id, trace_id)``-shaped
        publisher protocol. Channel events flow through
        ``EventEnvelope.wrap`` so their ``event_name`` is the
        PascalCase class name — matching the audit recorder's
        PascalCase subscription keys."""
        from qzdap.modules.channel.adapter.events import (
            MessagingChannelEventPublisher,
        )

        return MessagingChannelEventPublisher(self.bus())

    def audit_recorder(self):
        """Construct the governance AuditRecorder bound to the live bus.

        Each ``append`` call opens its own session via the async
        sessionmaker (audit events arrive outside any HTTP request).

        When ``audit_mode == "kafka"`` the AuditLogPort is a
        ``KafkaAuditPublisher`` (singleton); scrubbing runs inside the
        producer so the topic payload is already compliant. When
        ``"direct"`` we fall back to the synchronous SQL adapter.
        """
        from qzdap.modules.governance.application.audit_recorder import (
            AuditRecorder,
            build_default_topics,
        )

        if self.settings.audit_mode == "kafka":
            return AuditRecorder(
                audit_port=self.kafka_audit_producer(),
                clock=self.clock(),
                topics=build_default_topics(),
            )
        from qzdap.modules.governance.adapter.persistence.repositories import (
            SqlAuditLogAdapter,
        )

        return AuditRecorder(
            audit_port=SqlAuditLogAdapter(self.session_factory().maker()),
            clock=self.clock(),
            topics=build_default_topics(),
        )

    def kafka_audit_producer(self):
        """Singleton Kafka audit publisher — shared by recorder + lifespan.

        Lazy because the AIOKafkaProducer only constructs when the
        ``audit_mode == "kafka"`` branch is exercised; we don't want
        to import ``aiokafka`` on every direct-mode boot.
        """
        if self._kafka_audit_producer is None:
            from qzdap_messaging.kafka_audit import KafkaAuditPublisher

            self._kafka_audit_producer = KafkaAuditPublisher(
                bootstrap_servers=self.settings.audit_kafka_bootstrap_servers,
                topic=self.settings.audit_kafka_topic,
                dlq_topic=self.settings.audit_kafka_dlq_topic,
                max_retries=self.settings.audit_kafka_max_retries,
                request_timeout_ms=self.settings.audit_kafka_request_timeout_ms,
            )
        return self._kafka_audit_producer

    def kafka_audit_consumer(self):
        """Build a fresh KafkaAuditConsumer bound to the SQL audit port.

        Returns a new instance each call so lifespan can call ``start``
        on it; the consumer drains into ``SqlAuditLogAdapter`` which
        opens its own async session per write (mirroring the direct
        path).
        """
        from qzdap.modules.governance.adapter.persistence.repositories import (
            SqlAuditLogAdapter,
        )
        from qzdap_messaging.kafka_audit import (
            KafkaAuditConsumer,
            resolve_consumer_group,
        )

        return KafkaAuditConsumer(
            bootstrap_servers=self.settings.audit_kafka_bootstrap_servers,
            topic=self.settings.audit_kafka_topic,
            group_id=resolve_consumer_group(self.settings.audit_kafka_consumer_group),
            audit_port=SqlAuditLogAdapter(self.session_factory().maker()),
            block_ms=self.settings.audit_kafka_block_ms,
        )

    def policy_evaluator(self):
        """Construct the policy evaluator with per-call SQL adapters.

        The Sql* adapters each take an ``async_sessionmaker``; the cache
        lives in-process keyed by tenant.
        """
        from qzdap.modules.governance.adapter.persistence.repositories import (
            SqlApprovalRepository,
            SqlDecisionEventRepo,
            SqlPolicyRepository,
        )
        from qzdap.modules.governance.application.policy_evaluator import (
            PolicyEvaluator,
        )

        sf = self.session_factory().maker()
        return PolicyEvaluator(
            policy_repo=SqlPolicyRepository(sf),
            approval_repo=SqlApprovalRepository(sf),
            decision_repo=SqlDecisionEventRepo(sf),
            clock=self.clock(),
            ids=self.id_generator(),
            publisher=self.messaging_event_publisher(),
            cache_ttl_seconds=self.settings.policy_cache_ttl_seconds,
            approval_ttl_seconds=self.settings.policy_approval_ttl_seconds,
        )

    def policy_guard(self):
        """The cross-cutting PolicyGuard used by every gated use case."""
        from qzdap.modules.governance.adapter.guard.policy_guard import PolicyGuard

        return PolicyGuard(evaluator=self.policy_evaluator())

    def policy_service(self):
        from qzdap.modules.governance.adapter.persistence.repositories import (
            SqlPolicyRepository,
        )
        from qzdap.modules.governance.application.policy_service import PolicyService

        return PolicyService(
            repo=SqlPolicyRepository(self.session_factory().maker()),
            clock=self.clock(),
            ids=self.id_generator(),
            publisher=self.messaging_event_publisher(),
        )

    def approval_service(self):
        from qzdap.modules.governance.adapter.persistence.repositories import (
            SqlApprovalRepository,
        )
        from qzdap.modules.governance.application.approval_service import (
            ApprovalService,
        )

        return ApprovalService(
            repo=SqlApprovalRepository(self.session_factory().maker()),
            clock=self.clock(),
            ids=self.id_generator(),
            publisher=self.messaging_event_publisher(),
            default_ttl_seconds=self.settings.policy_approval_ttl_seconds,
        )

    def evolution_service(self):
        """Self-evolution candidate service (A4).

        Wires the kind-dispatching :class:`ApplyGuard` so each candidate
        is written to its kind-specific draft surface (memory working
        layer / skill draft / routing draft / dream artifacts) instead
        of touching any live production table. Set
        ``QZDAP_EVOLUTION_APPLY_GUARD_MODE=direct`` to fall back to the
        no-op ``DirectApplyGuard`` (e.g. for ephemeral CI).
        """
        from qzdap.modules.self_evolution.adapter.persistence.repositories import (
            SqlEvolutionCandidateRepository,
        )
        from qzdap.modules.self_evolution.application.apply_guard import (
            DirectApplyGuard,
            JsonlDraftStore,
            KindDispatchingApplyGuard,
        )
        from qzdap.modules.self_evolution.application.evolution_service import (
            EvolutionCandidateService,
        )

        if self.settings.evolution_apply_guard_mode == "direct":
            guard: object = DirectApplyGuard()
        else:
            guard = KindDispatchingApplyGuard(
                store=JsonlDraftStore(base_dir=self.settings.evolution_drafts_dir),
            )

        return EvolutionCandidateService(
            repo=SqlEvolutionCandidateRepository(self.session_factory().maker()),
            clock=self.clock(),
            ids=self.id_generator(),
            apply_guard=guard,  # type: ignore[arg-type]
            publisher=self.messaging_event_publisher(),
            default_ttl_seconds=3600,
        )

    def memory_embedding_adapter(self):
        """Pick the embedding adapter per ``settings.embedding_provider``."""
        provider = self.settings.embedding_provider
        if provider == "openai":
            from qzdap.modules.memory.adapter.embedding.openai_adapter import (
                OpenAIEmbeddingAdapter,
            )

            return OpenAIEmbeddingAdapter(
                api_key=self.settings.openai_api_key,
                base_url=self.settings.openai_base_url,
                model=self.settings.llm_embedding_model,
                dim=self.settings.llm_embedding_dim,
            )
        if provider == "http":
            from qzdap.modules.memory.adapter.embedding.http_adapter import (
                HttpEmbeddingAdapter,
            )

            return HttpEmbeddingAdapter(
                base_url=self.settings.embedding_runtime_url,
                api_key=self.settings.embedding_runtime_api_key,
            )
        from qzdap.modules.memory.adapter.embedding.noop_adapter import (
            NoOpEmbeddingAdapter,
        )

        return NoOpEmbeddingAdapter(dim=self.settings.llm_embedding_dim)

    def memory_vector_store(self):
        """The pgvector store used by the memory repository."""
        from qzdap_vector.pg_vector import PgVectorStore

        return PgVectorStore(self.engine(), dim=self.settings.llm_embedding_dim)

    # ── P6 model ────────────────────────────────────────────────────────────

    def model_credential_cipher(self):
        """Build the AES-GCM cipher used to encrypt ModelCredential rows.

        Reads ``QZDAP_MODEL_MASTER_KEY`` (hex-encoded, 32 bytes after
        decoding) and constructs the model-layer cipher. When the key is
        blank, the system raises at boot — explicit fail beats silent
        plaintext.
        """
        from qzdap.modules.model.adapter.crypto.credential_cipher import (
            build_cipher_from_env,
        )

        master = self.settings.model_master_key.strip()
        if not master:
            raise RuntimeError(
                "QZDAP_MODEL_MASTER_KEY is required for the P6 model module "
                "(set it to 32 bytes hex-encoded; see doc/12 §P6)."
            )
        try:
            return build_cipher_from_env(master_key_hex=master)
        except Exception as exc:  # pragma: no cover - defensive boot path
            raise RuntimeError(f"QZDAP_MODEL_MASTER_KEY is invalid: {exc}") from exc

    def model_service(self):
        """Facade used by agent_runtime: opens a session per invoke."""
        from qzdap.modules.model.adapter.llm.client_factory import (
            build_default_client_factory,
        )
        from qzdap.modules.model.adapter.persistence.repositories import (
            SqlHealthRepository,
            SqlModelRepository,
            SqlProviderRepository,
            SqlRouteRepository,
        )
        from qzdap.modules.model.application.services import ModelService

        cipher = self.model_credential_cipher()
        client_factory = build_default_client_factory(
            request_timeout_seconds=self.settings.model_invocation_timeout_seconds,
        )
        session_factory = self.session_factory()

        class _InvokeFacade:
            async def invoke(self, *, actor, model_id, req):  # type: ignore[no-untyped-def]
                async with session_factory.session() as session:
                    svc = ModelService(
                        SqlModelRepository(session),
                        SqlProviderRepository(session),
                        SqlRouteRepository(session),
                        SqlHealthRepository(session),
                        cipher=cipher,
                        client_factory=client_factory,
                    )
                    try:
                        result = await svc.invoke(actor=actor, model_id=model_id, req=req)
                        await session.commit()
                        return result
                    except Exception:
                        await session.rollback()
                        raise

        return _InvokeFacade()

    # ── P6 channel ──────────────────────────────────────────────────────────

    def channel_webhook_cipher(self):
        """AES-GCM cipher for ChannelSecret rows.

        Reuses the model master key for v1 — both secret tables share the
        same envelope format (nonce(12) || ct || tag(16)). A future
        rotation can split the key version per secret class.
        """
        return self.model_credential_cipher()

    def channel_inbound_registry(self):
        """Dict[ChannelType, InboundAdapter] — parsed once at boot."""
        from qzdap.modules.channel.adapter.inbound import (
            DingTalkInboundAdapter,
            FeishuInboundAdapter,
            WebInboundAdapter,
            WeChatWorkInboundAdapter,
        )
        from qzdap.modules.channel.domain.value_objects import ChannelType

        # Inject channel-specific encryption material so the
        # encrypted inbound adapters (DingTalk Stream v2 AES-CBC,
        # Wecom JSON v2 AES-CBC) can decrypt ciphertext at parse time.
        # An empty secret keeps the legacy ``kind=encrypted``
        # placeholder behaviour so dev / unit tests stay green.
        return {
            ChannelType.FEISHU: FeishuInboundAdapter(),
            ChannelType.DINGTALK: DingTalkInboundAdapter(
                app_secret=self.settings.dingtalk_app_secret,
            ),
            ChannelType.WECHATWORK: WeChatWorkInboundAdapter(
                encoding_aes_key=self.settings.wechatwork_encoding_aes_key,
            ),
            ChannelType.WEB: WebInboundAdapter(),
        }

    def channel_outbound_registry(self):
        """Dict[ChannelType, OutboundAdapter] — long-lived singletons.

        Each outbound adapter takes a shared ``httpx.AsyncClient`` so the
        connection pool is reused across deliveries. Feishu / DingTalk /
        WeChatWork adapters carry empty placeholder credentials at boot
        and read ``outbound_config`` from the channel row when sending.
        """
        import httpx
        from qzdap.modules.channel.adapter.outbound import (
            DingTalkOutboundAdapter,
            FeishuOutboundAdapter,
            WebOutboundAdapter,
            WeChatWorkOutboundAdapter,
        )
        from qzdap.modules.channel.domain.value_objects import ChannelType

        http = httpx.AsyncClient(timeout=30.0)
        timeout = self.settings.model_invocation_timeout_seconds
        return {
            ChannelType.FEISHU: FeishuOutboundAdapter(
                http=http,
                app_id="",
                app_secret="",
                request_timeout_seconds=timeout,
            ),
            ChannelType.DINGTALK: DingTalkOutboundAdapter(
                http=http,
                webhook_url="",
                request_timeout_seconds=timeout,
            ),
            ChannelType.WECHATWORK: WeChatWorkOutboundAdapter(
                http=http,
                corp_id="",
                corp_secret="",
                agent_id="",
                encoding_aes_key="",
                token="",
                request_timeout_seconds=timeout,
            ),
            ChannelType.WEB: WebOutboundAdapter(
                http=http,
                webhook_url=None,
                request_timeout_seconds=timeout,
            ),
        }

    def channel_service(self):
        """Assemble the ChannelService with all adapter dependencies.

        Returns ``None`` if the AES-GCM cipher cannot be built (e.g.
        missing ``QZDAP_MODEL_MASTER_KEY``) so the lifespan can fall back
        to a no-op registration for legacy dev shells.
        """
        try:
            cipher = self.channel_webhook_cipher()
        except RuntimeError:
            return None

        from qzdap.modules.channel.adapter.persistence.repositories import (
            SqlChannelDeliveryRepository,
            SqlChannelRepository,
            SqlWebhookSecretRepository,
        )
        from qzdap.modules.channel.application.services import ChannelService

        sf = self.session_factory().maker()
        return ChannelService(
            channel_repo=SqlChannelRepository(sf),
            delivery_repo=SqlChannelDeliveryRepository(sf),
            secret_repo=SqlWebhookSecretRepository(sf),
            cipher=cipher,
            clock=self.clock(),
            ids=self.id_generator(),
            publisher=self.channel_event_publisher(),
        )
