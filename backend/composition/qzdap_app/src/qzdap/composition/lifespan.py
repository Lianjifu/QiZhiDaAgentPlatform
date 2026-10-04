"""Lifespan + bootstrap helpers.

On boot, the lifespan:
  1. Configures logging + tracing + default LLM client.
  2. Builds the per-request IdentityService factory and stores it on
     `app.state.identity_factory` so the FastAPI dependency can resolve it.
  3. Seeds a default tenant + workspace + admin user when the DB is empty
     (dev/test only — see ``ensure_default_resources``).
  4. Starts the event bus.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from logging import getLogger
from uuid import UUID

from fastapi import FastAPI

from qzdap.composition.container import Container

_log = getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Boot/shutdown hooks."""
    container: Container = app.state.container

    # ── logging ──────────────────────────────────────────────────────────
    from qzdap_observability.logging import configure_logging

    configure_logging(
        level=container.settings.log_level, json=container.settings.log_json
    )

    # ── tracing ──────────────────────────────────────────────────────────
    if container.settings.otlp_endpoint:
        from qzdap_observability.tracing import configure_tracing

        configure_tracing(
            service_name="qzdap-app",
            otlp_endpoint=container.settings.otlp_endpoint,
            sample_rate=container.settings.traces_sample_rate,
        )

    # ── LLM default client ───────────────────────────────────────────────
    container.configure_llm_default()

    # ── per-request identity factory ─────────────────────────────────────
    from qzdap.modules.identity.adapter.persistence.repositories import (
        SqlAPIKeyRepository,
        SqlTenantRepository,
        SqlUserRepository,
        SqlWorkspaceRepository,
    )
    from qzdap.modules.identity.application.services import IdentityService

    class _IdentityFactoryRequest:
        def __init__(self, sf) -> None:  # type: ignore[no-untyped-def]
            self._sf = sf
            self._token_issuer = container.jwt_issuer()

        def for_session(self, session):  # type: ignore[no-untyped-def]
            return IdentityService(
                tenants=SqlTenantRepository(session),
                workspaces=SqlWorkspaceRepository(session),
                users=SqlUserRepository(session),
                api_keys=SqlAPIKeyRepository(session),
                hasher=container.hasher(),
                issuer=_TokenIssuerAdapter(self._token_issuer),
            )

    class _TokenIssuerAdapter:
        def __init__(self, issuer) -> None:  # type: ignore[no-untyped-def]
            self._issuer = issuer

        def issue(self, user, workspace_id):  # type: ignore[no-untyped-def]
            email = str(getattr(user, "email", "") or "").lower()
            roles = {"workspace_member"}
            if email.startswith("admin@"):
                roles.add("admin")
            token, exp = self._issuer.issue_access_token(
                principal_id=user.id,
                tenant_id=user.tenant_id,
                workspace_id=workspace_id,
                roles=frozenset(roles),
            )
            return token, exp

    app.state.identity_factory = _IdentityFactoryRequest(container.session_factory())

    from qzdap.modules.agent_runtime.adapter.sandbox.http_client import (
        HttpSandboxRuntimeClient,
    )

    app.state.sandbox_client = HttpSandboxRuntimeClient(
        base_url=container.settings.sandbox_runtime_url,
        secret=container.settings.sandbox_runtime_secret,
        default_image=container.settings.sandbox_default_image,
    )

    # ── per-request agent_runtime factory ────────────────────────────────
    from qzdap.modules.agent_runtime.adapter.events import (
        AgentRuntimeEventPublisher,
    )
    from qzdap.modules.agent_runtime.adapter.llm import LLMPortAdapter
    from qzdap.modules.agent_runtime.adapter.persistence.repositories import (
        SqlSessionRepository,
        SqlTurnRepository,
    )
    from qzdap.modules.agent_runtime.application.services import (
        AgentRuntimeService,
    )

    # P6: model_service may be None when QZDAP_MODEL_MASTER_KEY is unset
    # in dev/test. In production this is a hard fail — the
    # ``_validate_production_secrets`` gate in Container.__init__ will
    # have already raised, so reaching this branch in prod means a
    # later RuntimeError from ``model_credential_cipher``; surface it
    # as a boot failure rather than silently degrading to a non-
    # functional runtime.
    model_service = None
    try:
        model_service = container.model_service()
    except RuntimeError as exc:
        if getattr(container.settings, "env", "development") == "production":
            raise RuntimeError(
                f"production boot requires model_service: {exc}. "
                "Set QZDAP_MODEL_MASTER_KEY to a non-development value via "
                "QZDAP_MODEL_MASTER_KEY_REF or your secrets manager."
            ) from exc
        _log.warning("model_service disabled: %s", exc)

    class _AgentRuntimeFactory:
        def __init__(self) -> None:
            self._llm_client = container.llm_client()
            self._bus = container.bus()

        def for_session(self, session):  # type: ignore[no-untyped-def]
            llm = LLMPortAdapter(
                self._llm_client,
                model_service=model_service,
            )
            # Lazily resolve the per-request knowledge service and wrap it
            # in the agent_runtime's KnowledgePort adapter so RunTurnUseCase
            # can pull RAG context into the system prompt.
            from qzdap.modules.agent_runtime.adapter.knowledge import (
                KnowledgeServiceAdapter,
            )
            from qzdap.modules.agent_runtime.adapter.memory import (
                MemoryServiceAdapter,
            )

            knowledge_adapter: object | None = None
            knowledge_factory = getattr(app.state, "knowledge_service_factory", None)
            if knowledge_factory is not None:
                try:
                    knowledge_adapter = KnowledgeServiceAdapter(
                        knowledge_factory.for_session(session)
                    )
                except Exception:  # pragma: no cover - defensive  # noqa: BLE001
                    _log.warning(
                        "knowledge adapter unavailable; turns will skip RAG",
                        exc_info=True,
                    )
                    knowledge_adapter = None

            memory_adapter: object | None = None
            memory_factory = getattr(app.state, "memory_service_factory", None)
            if memory_factory is not None:
                try:
                    memory_adapter = MemoryServiceAdapter(
                        memory_factory.for_session(session)
                    )
                except Exception:  # pragma: no cover - defensive  # noqa: BLE001
                    _log.warning(
                        "memory adapter unavailable; turns will skip recall",
                        exc_info=True,
                    )
                    memory_adapter = None

            return AgentRuntimeService(
                sessions=SqlSessionRepository(session),
                turns=SqlTurnRepository(session),
                llm=llm,
                events=AgentRuntimeEventPublisher(self._bus),
                knowledge_port=knowledge_adapter,
                memory_port=memory_adapter,
            )

    app.state.agent_runtime_factory = _AgentRuntimeFactory()

    from qzdap.modules.agent_runtime.adapter.graph import SessionGraphRunner
    from qzdap.modules.agent_runtime.adapter.persistence.catalog_repositories import (
        SqlCatalogAgentRepository,
        SqlCatalogAgentUserStateRepository,
        SqlSessionMessageRepository,
    )
    from qzdap.modules.agent_runtime.application.catalog import AgentCatalogService
    from qzdap.modules.agent_runtime.application.copilot import CopilotSessionService

    class _AgentCatalogFactory:
        def for_session(self, session):  # type: ignore[no-untyped-def]
            return AgentCatalogService(
                SqlCatalogAgentRepository(session),
                SqlCatalogAgentUserStateRepository(session),
            )

    app.state.agent_catalog_factory = _AgentCatalogFactory()

    class _CopilotFactory:
        def for_session(self, session):  # type: ignore[no-untyped-def]
            llm = LLMPortAdapter(
                container.llm_client(),
                model_service=model_service,
            )
            catalog = _AgentCatalogFactory().for_session(session)
            from qzdap.modules.agent_runtime.adapter.knowledge import (
                KnowledgeServiceAdapter,
            )
            from qzdap.modules.agent_runtime.adapter.memory import MemoryServiceAdapter
            from qzdap.modules.agent_runtime.adapter.sandbox import SandboxRuntimeAdapter
            from qzdap.modules.agent_runtime.adapter.skills import SkillServiceAdapter
            from qzdap_schema.ids import TenantId, UserId, WorkspaceId

            knowledge_factory = getattr(app.state, "knowledge_service_factory", None)
            memory_factory = getattr(app.state, "memory_service_factory", None)
            skill_factory = getattr(app.state, "skill_factory", None)
            knowledge_port = (
                KnowledgeServiceAdapter(knowledge_factory.for_session(session))
                if knowledge_factory is not None
                else None
            )
            memory_port = (
                MemoryServiceAdapter(memory_factory.for_session(session))
                if memory_factory is not None
                else None
            )
            skill_port = None
            if skill_factory is not None:
                skill_port = SkillServiceAdapter(
                    svc=skill_factory.for_session(session),
                    tenant_id=TenantId(UUID(int=0)),
                    workspace_id=WorkspaceId(UUID(int=0)),
                    owner_id=UserId(UUID(int=0)),
                )
            sandbox_port = None
            sandbox_client = getattr(app.state, "sandbox_client", None)
            if sandbox_client is not None:
                sandbox_port = SandboxRuntimeAdapter(
                    sandbox_client,
                    tenant_id=TenantId(UUID(int=0)),
                    workspace_id=WorkspaceId(UUID(int=0)),
                    agent_id=None,
                )
            approval = None
            try:
                approval = container.approval_service()
            except Exception:  # noqa: BLE001
                approval = None
            graph = SessionGraphRunner(
                llm=llm,
                skill_port=skill_port,
                sandbox_port=sandbox_port,
                memory_port=memory_port,
                knowledge_port=knowledge_port,
                approval_factory=approval,
            )
            _ = (TenantId, UserId, WorkspaceId)
            return CopilotSessionService(
                sessions=SqlSessionRepository(session),
                turns=SqlTurnRepository(session),
                messages=SqlSessionMessageRepository(session),
                catalog=catalog,
                events=AgentRuntimeEventPublisher(container.bus()),
                graph=graph,
            )

    app.state.copilot_factory = _CopilotFactory()
    app.state.model_service = model_service

    from qzdap.modules.model.adapter.llm.client_factory import (
        build_default_client_factory,
    )
    from qzdap.modules.model.adapter.llm.prober import HttpCatalogProber
    from qzdap.modules.model.adapter.persistence.repositories import (
        SqlHealthRepository,
        SqlModelRepository,
        SqlProviderRepository,
        SqlRouteRepository,
    )
    from qzdap.modules.model.application.services import (
        ModelService as CatalogModelService,
    )

    class _ModelFactory:
        def for_session(self, session):  # type: ignore[no-untyped-def]
            cipher = None
            try:
                cipher = container.model_credential_cipher()
            except RuntimeError:
                cipher = None
            return CatalogModelService(
                SqlModelRepository(session),
                SqlProviderRepository(session),
                SqlRouteRepository(session),
                SqlHealthRepository(session),
                cipher=cipher,
                client_factory=build_default_client_factory(
                    request_timeout_seconds=container.settings.model_invocation_timeout_seconds,
                ),
                prober=HttpCatalogProber(),
            )

        def __call__(self, session):  # type: ignore[no-untyped-def]
            return self.for_session(session)

    app.state.model_service_factory = _ModelFactory()

    # ── per-request channel factory ─────────────────────────────────────────
    channel_service_obj = None
    try:
        channel_service_obj = container.channel_service()
    except Exception as exc:
        if getattr(container.settings, "env", "development") == "production":
            raise RuntimeError(
                f"production boot requires channel_service: {exc}. "
                "channel outbound depends on QZDAP_MODEL_MASTER_KEY and the "
                "channel credentials in your secrets manager."
            ) from exc
        _log.warning("channel_service disabled: %s", exc)

    app.state.channel_service = channel_service_obj
    app.state.channel_inbound_registry = container.channel_inbound_registry()
    app.state.channel_outbound_registry = container.channel_outbound_registry()

    # ── per-request tool factory ─────────────────────────────────────
    import httpx as _httpx
    from qzdap.modules.tool.adapter.adapters import (
        CustomInvokerRegistry,
        MCPRuntimeAdapter,
        OpenAPIRuntimeAdapter,
        built_in_invoke_clock,
        built_in_invoke_echo,
        built_in_invoke_reverse,
    )
    from qzdap.modules.tool.adapter.events import ToolEventPublisher
    from qzdap.modules.tool.adapter.persistence.repositories import (
        SqlToolCallRepository,
        SqlToolRepository,
    )
    from qzdap.modules.tool.application.services import ToolService

    http_client = _httpx.AsyncClient(timeout=30.0)
    secrets_resolver = container.secrets_resolver()
    openapi_rt = OpenAPIRuntimeAdapter(
        http=http_client, secrets_resolver=secrets_resolver
    )
    mcp_rt = MCPRuntimeAdapter(http=http_client, secrets_resolver=secrets_resolver)

    custom_invoker = CustomInvokerRegistry()
    custom_invoker.register("echo", built_in_invoke_echo)
    custom_invoker.register("reverse", built_in_invoke_reverse)
    custom_invoker.register("clock", built_in_invoke_clock)

    class _ToolFactory:
        def __init__(self) -> None:
            self._bus = container.bus()

        def for_session(self, session):  # type: ignore[no-untyped-def]
            return ToolService(
                tools=SqlToolRepository(session),
                calls=SqlToolCallRepository(session),
                custom=custom_invoker,
                openapi=openapi_rt,
                mcp=mcp_rt,
                events=ToolEventPublisher(self._bus),
                tool_call_timeout_seconds=container.settings.tool_call_timeout_seconds,
            )

    app.state.tool_factory = _ToolFactory()

    # ── per-request skill factory ─────────────────────────────────────────
    from qzdap.modules.skill.adapter.persistence.repositories import (
        SqlSkillRepository,
        SqlSkillUserStateRepository,
    )
    from qzdap.modules.skill.application.services import SkillService

    class _SkillFactory:
        def for_session(self, session):  # type: ignore[no-untyped-def]
            return SkillService(
                skills=SqlSkillRepository(session),
                user_state=SqlSkillUserStateRepository(session),
                sandbox_jobs=getattr(app.state, "sandbox_client", None),
            )

        def __call__(self, session):  # type: ignore[no-untyped-def]
            return self.for_session(session)

    app.state.skill_factory = _SkillFactory()

    policy_guard = (
        container.policy_guard() if container.settings.policy_enabled else None
    )

    # ── per-request memory factory ──────────────────────────────────────
    from qzdap.modules.memory.adapter.persistence.repositories import (
        SqlMemoryCatalogRepository,
    )
    from qzdap.modules.memory.adapter.persistence.vector_adapter import (
        PgMemoryVectorAdapter,
    )
    from qzdap.modules.memory.application.services import MemoryService
    from qzdap_vector.pg_vector import PgVectorStore

    memory_vectors = PgMemoryVectorAdapter(
        PgVectorStore(
            container.engine(),
            table="admin_memory_vec",
            dim=container.settings.llm_embedding_dim,
        )
    )
    memory_embedding = container.memory_embedding_adapter()

    class _MemoryFactory:
        def for_session(self, session):  # type: ignore[no-untyped-def]
            return MemoryService(
                SqlMemoryCatalogRepository(session),
                embedding=memory_embedding,
                vectors=memory_vectors,
            )

        def __call__(self, session):  # type: ignore[no-untyped-def]
            return self.for_session(session)

    app.state.memory_service_factory = _MemoryFactory()

    # ── per-request knowledge factory ───────────────────────────────────
    from qzdap.modules.knowledge.adapter.persistence.repositories import (
        SqlKnowledgeCatalogRepository,
    )
    from qzdap.modules.knowledge.adapter.persistence.vector_adapter import (
        PgKnowledgeVectorAdapter,
    )
    from qzdap.modules.knowledge.application.services import KnowledgeService
    from qzdap_vector.pg_vector import PgVectorStore

    knowledge_vectors = PgKnowledgeVectorAdapter(
        PgVectorStore(
            container.engine(),
            table="admin_knowledge_chunks_vec",
            dim=container.settings.llm_embedding_dim,
        )
    )
    knowledge_embedding = container.memory_embedding_adapter()

    class _KnowledgeFactory:
        def for_session(self, session):  # type: ignore[no-untyped-def]
            return KnowledgeService(
                SqlKnowledgeCatalogRepository(session),
                embedding=knowledge_embedding,
                vectors=knowledge_vectors,
                chunk_size=container.settings.knowledge_default_chunk_size,
                chunk_overlap=container.settings.knowledge_default_chunk_overlap,
            )

        def __call__(self, session):  # type: ignore[no-untyped-def]
            return self.for_session(session)

    app.state.knowledge_service_factory = _KnowledgeFactory()

    # ── per-request workflow catalog factory ────────────────────────────
    from qzdap.modules.orchestration.adapter.persistence.repositories import (
        SqlWorkflowRepository,
        SqlWorkflowRunRepository,
        SqlWorkflowUserStateRepository,
    )
    from qzdap.modules.orchestration.application.services import (
        OrchestrationService,
    )

    class _OrchestrationFactory:
        def for_session(self, session):  # type: ignore[no-untyped-def]
            return OrchestrationService(
                workflows=SqlWorkflowRepository(session),
                user_state=SqlWorkflowUserStateRepository(session),
                runs=SqlWorkflowRunRepository(session),
            )

        def __call__(self, session):  # type: ignore[no-untyped-def]
            return self.for_session(session)

    app.state.orchestration_service_factory = _OrchestrationFactory()

    # ── P8 evaluation (independent module) ──────────────────────────────
    from qzdap.modules.evaluation.adapter.events import (
        MessagingEvaluationEventPublisher,
    )
    from qzdap.modules.evaluation.adapter.persistence.repositories import (
        SqlEvalDatasetRepository,
        SqlEvalRunRepository,
    )
    from qzdap.modules.evaluation.application.runner import EvalRunner
    from qzdap.modules.evaluation.application.services import (
        EvaluationService,
    )

    evaluation_bus = container.bus()
    evaluation_publisher = MessagingEvaluationEventPublisher(evaluation_bus)

    class _EvaluationFactory:
        def __init__(self) -> None:
            self._publisher = evaluation_publisher
            self._policy_guard = policy_guard

        def for_session(self) -> EvaluationService:
            sf = container.session_factory().maker()
            ds_repo = SqlEvalDatasetRepository(sf)
            run_repo = SqlEvalRunRepository(sf)
            sub_agent_factory = getattr(app.state, "agent_runtime_factory", None)
            sub_agent = _sub_agent_for_evaluation(sub_agent_factory)
            runner = EvalRunner(
                run_repo=run_repo,
                dataset_repo=ds_repo,
                sub_agent=sub_agent,
                publisher=self._publisher,
                scoring_threshold=(container.settings.agent_factory_eval_score_min),
                concurrency=container.settings.evaluation_runner_concurrency,
                case_timeout_seconds=(
                    container.settings.evaluation_case_default_timeout_seconds
                ),
            )
            return EvaluationService.from_parts(
                dataset_repository=ds_repo,
                run_repository=run_repo,
                runner=runner,
                publisher=self._publisher,
                policy_guard=self._policy_guard,
            )

    def _sub_agent_for_evaluation(ar_factory):  # type: ignore[no-untyped-def]
        """Return the SubAgentPort used to drive evaluation cases.

        Wire to the real ``RealSubAgentPort`` when the agent_runtime
        factory is available; fall back to the deterministic stub when
        it is not (legacy dev shells, missing ``QZDAP_MODEL_MASTER_KEY``,
        boot in a slim test harness). Heuristic scoring against the stub
        will fail most cases — the gate wiring (pass / fail / no_eval)
        still validates the lifecycle.
        """
        if ar_factory is None:
            from qzdap.modules.evaluation.adapter.sub_agent_stub import (
                StubSubAgentPort,
            )

            return StubSubAgentPort()

        from qzdap.modules.evaluation.adapter.agent_factory_adapter import (
            EvaluationServiceAdapter,
        )

        sf_for_query = container.session_factory().maker()
        agent_factory = EvaluationServiceAdapter(
            run_repository=SqlEvalRunRepository(sf_for_query),
            score_threshold=container.settings.agent_factory_eval_score_min,
        )
        return _PerCaseRealSubAgent(
            container=container,
            agent_factory=agent_factory,
        )

    class _PerCaseRealSubAgent:
        """Builds a fresh AgentRuntimeService per case so each eval turn
        gets an isolated session + connection pool. The AgentRuntimeService
        is composed from the live container bus + session factory."""

        def __init__(self, *, container, agent_factory) -> None:  # type: ignore[no-untyped-def]
            self._container = container
            self._agent_factory = agent_factory

        async def run_turn_to_completion(self, **kwargs):  # type: ignore[no-untyped-def]
            from qzdap.modules.agent_runtime.adapter.events import (
                AgentRuntimeEventPublisher,
            )
            from qzdap.modules.agent_runtime.adapter.llm import LLMPortAdapter
            from qzdap.modules.agent_runtime.adapter.persistence.repositories import (
                SqlSessionRepository,
                SqlTurnRepository,
            )
            from qzdap.modules.agent_runtime.application.services import (
                AgentRuntimeService,
            )
            from qzdap.modules.evaluation.adapter.sub_agent_real import (
                RealSubAgentPort,
            )

            sf = self._container.session_factory().maker()
            # model_service() raises if QZDAP_MODEL_MASTER_KEY is unset;
            # LLMPortAdapter degrades to the default client on None.
            try:
                model_service = self._container.model_service()
            except RuntimeError:
                model_service = None
            llm = LLMPortAdapter(self._container.llm_client(), model_service=model_service)
            runtime = AgentRuntimeService(
                sessions=SqlSessionRepository(sf),
                turns=SqlTurnRepository(sf),
                llm=llm,
                events=AgentRuntimeEventPublisher(self._container.bus()),
            )
            adapter = RealSubAgentPort(
                runtime=runtime,
                agent_factory=self._agent_factory,
            )
            return await adapter.run_turn_to_completion(**kwargs)

    app.state.evaluation_service_factory = _EvaluationFactory()

    # Seed the 50-case golden dataset for every existing tenant on
    # first boot.  Idempotent — re-running is a no-op when the dataset
    # already exists.
    await _seed_builtin_eval_datasets(app, container)

    # Seed the 3 default Plans (free / pro / enterprise) on first
    # boot.  Idempotent — re-running is a no-op when plans already
    # exist.  Runs only when ``platform_seed_default_plans`` is true.
    if container.settings.platform_seed_default_plans:
        await _seed_default_plans(container)

    # Catalog skills are created via /api/admin/skills; signed office
    # skill packs are no longer seeded into sandbox runtimes.
    if container.settings.platform_seed_office_skill_packs:
        _log.info("office skill pack seed skipped (skill catalog replaces packs)")

    # Catalog knowledge is created via /api/admin/knowledge; signed office
    # knowledge packs are no longer seeded into RAG packages.
    if container.settings.platform_seed_office_knowledge_packs:
        _log.info("office knowledge pack seed skipped (knowledge catalog replaces packs)")
    if container.settings.platform_seed_office_plan_packs:
        _log.info("office plan pack seed skipped (workflow catalog replaces packs)")

    # ── P8 agent_factory (depends on evaluation; this is the P8-6 closed
    # loop — agent_factory reads the latest passed eval run via
    # EvaluationServiceAdapter).
    from qzdap.modules.agent_factory.adapter.events import (
        MessagingAgentFactoryEventPublisher,
    )
    from qzdap.modules.agent_factory.adapter.persistence.repositories import (
        SqlAgentTemplateRepository,
        SqlAgentVersionRepository,
        SqlReleaseRepository,
    )
    from qzdap.modules.agent_factory.application.services import (
        AgentFactoryService,
    )

    agent_factory_bus = container.bus()
    agent_factory_publisher = MessagingAgentFactoryEventPublisher(agent_factory_bus)

    class _AgentFactoryFactory:
        def __init__(self) -> None:
            self._publisher = agent_factory_publisher
            self._policy_guard = policy_guard

        def for_session(self) -> AgentFactoryService:
            sf = container.session_factory().maker()
            evaluation_query = _build_evaluation_query(sf)
            return AgentFactoryService.from_parts(
                template_repository=SqlAgentTemplateRepository(sf),
                version_repository=SqlAgentVersionRepository(sf),
                release_repository=SqlReleaseRepository(sf),
                evaluation_query=evaluation_query,
                publisher=self._publisher,
                policy_guard=self._policy_guard,
                eval_score_min=(container.settings.agent_factory_eval_score_min),
            )

    def _build_evaluation_query(sf):  # type: ignore[no-untyped-def]
        from qzdap.modules.evaluation.adapter.agent_factory_adapter import (
            EvaluationServiceAdapter,
        )
        from qzdap.modules.evaluation.adapter.persistence.repositories import (
            SqlEvalRunRepository,
        )

        return EvaluationServiceAdapter(
            run_repository=SqlEvalRunRepository(sf),
            score_threshold=container.settings.agent_factory_eval_score_min,
        )

    app.state.agent_factory_service_factory = _AgentFactoryFactory()

    # ── P9 observability_module (per-request service factory + subscriber) ──
    from qzdap.modules.observability_module.adapter.persistence.repositories import (
        SqlCostRecordRepository,
        SqlRunRecordRepository,
    )
    from qzdap.modules.observability_module.application.pricing import (
        PricingCatalog,
    )
    from qzdap.modules.observability_module.application.recorder import (
        ObservabilityRecorder,
    )
    from qzdap.modules.observability_module.application.recorder import (
        install as obs_install,
    )
    from qzdap.modules.observability_module.application.services import (
        ObservabilityService,
    )

    obs_pricing_catalog = PricingCatalog.from_settings(container.settings)
    obs_session_factory = container.session_factory().maker

    class _ObservabilityFactory:
        def __init__(self) -> None:
            self._pricing = obs_pricing_catalog

        def for_session(self) -> ObservabilityService:
            sf = obs_session_factory()
            return ObservabilityService.from_parts(
                run_repo=SqlRunRecordRepository(sf),
                cost_repo=SqlCostRecordRepository(sf),
                pricing=self._pricing,
            )

    app.state.observability_service_factory = _ObservabilityFactory()

    # ── P9 platform (per-request service factory + default-plans seed) ──
    from qzdap.modules.platform.adapter.persistence import (
        ObservabilityCostRepositoryBridge,
        SqlSubscriptionRepository,
        SqlTenantSettingRepository,
    )
    from qzdap.modules.platform.adapter.persistence import (
        SqlPlanRepository as PlatformSqlPlanRepository,
    )
    from qzdap.modules.platform.application.services import PlatformService

    class _PlatformFactory:
        def for_session(self) -> PlatformService:
            sf = container.session_factory().maker()
            return PlatformService.from_parts(
                plan_repo=PlatformSqlPlanRepository(sf),
                subscription_repo=SqlSubscriptionRepository(sf),
                setting_repo=SqlTenantSettingRepository(sf),
                publisher=None,
                # Bridge into observability's SqlCostRecordRepository
                # so ``aggregate_costs`` actually reads tenant spend.
                cost_repo=ObservabilityCostRepositoryBridge(sf),
            )

    app.state.platform_service_factory = _PlatformFactory()

    from qzdap.modules.platform.adapter.persistence.ops_repositories import (
        SqlAdminOpsRepository,
    )
    from qzdap.modules.platform.application.ops_service import AdminOpsService

    class _AdminOpsFactory:
        def for_session(self, session):  # type: ignore[no-untyped-def]
            return AdminOpsService(SqlAdminOpsRepository(session))

    app.state.admin_ops_factory = _AdminOpsFactory()

    # ── bus (must be available before subscribers install) ──────────────
    bus = container.bus()
    await bus.start()
    app.state.bus = bus

    # ── A5 audit pipeline: Kafka producer (always if mode=kafka) + ──────
    # ── co-located consumer (conditional, default on for single replica) ─
    audit_producer = None
    audit_consumer = None
    if container.settings.audit_mode == "kafka":
        audit_producer = container.kafka_audit_producer()
        await audit_producer.start()
        app.state.audit_producer = audit_producer
        if container.settings.audit_consumer_enabled:
            audit_consumer = container.kafka_audit_consumer()
            await audit_consumer.start()
            app.state.audit_consumer = audit_consumer
            _log.info("kafka audit consumer active (group=%s)", audit_consumer.group_id)
        else:
            _log.info("kafka audit producer active; consumer disabled (multi-replica)")

    # ── P9 observability subscriber (passive; never raises back) ────────
    obs_recorder = ObservabilityRecorder(
        run_repo=SqlRunRecordRepository(obs_session_factory()),
        cost_repo=SqlCostRecordRepository(obs_session_factory()),
        pricing=obs_pricing_catalog,
    )
    await obs_install(bus, obs_recorder, logger=_log)

    # ── P5 audit subscriber (governance events → audit_log) ─────────────
    from qzdap.modules.governance.adapter.subscribers import audit_subscriber

    audit_recorder = container.audit_recorder()
    evaluator = container.policy_evaluator()
    await audit_subscriber.install(
        bus,
        audit_recorder,
        cache_invalidator=evaluator.invalidate,
    )

    # ── P7 channel → agent_runtime dispatch subscriber ──────────────────
    # Conditional install: only when both the channel module is wired
    # and the agent_runtime factory is available. Older dev shells
    # (legacy / model_service absent) skip this and inbound webhooks
    # simply don't trigger agent replies.
    ar_factory = getattr(app.state, "agent_runtime_factory", None)
    channel_service_obj = getattr(app.state, "channel_service", None)
    if channel_service_obj is not None and ar_factory is not None:
        from qzdap.modules.channel.adapter.dispatch.dispatch_subscriber import (
            ChannelDispatchSubscriber,
        )

        dispatch = ChannelDispatchSubscriber(
            channel_repository=channel_service_obj.channel_repo,
            agent_runtime_factory=ar_factory,
            outbound_registry_getter=lambda: (
                getattr(app.state, "channel_outbound_registry", {}) or {}
            ),
            clock=container.clock(),
            open_session=container.session_factory().maker,
        )
        await dispatch.install(bus)
        app.state.channel_dispatch_subscriber = dispatch
        _log.info("channel dispatch subscriber active")
    else:
        _log.info(
            "channel dispatch subscriber skipped (channel_service=%s, ar_factory=%s)",
            channel_service_obj is not None,
            ar_factory is not None,
        )

    # ── seed default resources ───────────────────────────────────────────
    await ensure_default_resources(container)

    # ── redis client (for /readyz) ───────────────────────────────────────
    try:
        app.state.redis = container.redis_client()
    except Exception:  # noqa: BLE001
        _log.warning("redis client not attached; /readyz will report redis=skipped")

    try:
        yield
    finally:
        if audit_consumer is not None:
            await audit_consumer.stop()
        if audit_producer is not None:
            await audit_producer.stop()
        await bus.stop()
        sandbox = getattr(app.state, "sandbox", None)
        if sandbox is not None:
            await sandbox.shutdown()


async def _seed_default_plans(container: Container) -> None:
    """Seed the 3 default Plans (free / pro / enterprise).

    Idempotent: skips when a plan with the same ``code`` already
    exists.  Called once at lifespan start when
    ``platform_seed_default_plans`` is enabled (default: true).
    """
    from qzdap.modules.platform.adapter.persistence import (
        SqlPlanRepository as PlatformSqlPlanRepository,
    )
    from qzdap.modules.platform.adapter.persistence.mappers import plan_to_orm
    from qzdap.modules.platform.fixtures.default_plans import (
        DEFAULT_PLANS,
        build_default_plan,
    )

    sf = container.session_factory()
    seeded = 0
    try:
        async with sf.session() as session:
            repo = PlatformSqlPlanRepository(session)
            for spec in DEFAULT_PLANS:
                existing = await repo.get_by_code(code=spec.code)
                if existing is not None:
                    continue
                plan = build_default_plan(spec)
                session.add(plan_to_orm(plan))
                seeded += 1
            if seeded > 0:
                await session.commit()
                _log.info("seeded %d default plans", seeded)
    except Exception:  # noqa: BLE001
        _log.exception("seed_default_plans failed; continuing boot")


async def _seed_builtin_eval_datasets(app: FastAPI, container: Container) -> None:
    """Seed the 50-case golden dataset for every existing tenant.

    Idempotent: skips tenants that already have a ``golden-default``
    dataset.  Called once at lifespan start so the dataset is ready
    by the time HTTP requests land.
    """
    from uuid import uuid4

    from qzdap.modules.evaluation.adapter.persistence.mappers import (
        case_to_orm,
        dataset_to_orm,
    )
    from qzdap.modules.evaluation.adapter.persistence.models import (
        EvalDatasetORM,
    )
    from qzdap.modules.evaluation.domain.entities import EvalCase, EvalDataset
    from qzdap.modules.evaluation.domain.value_objects import (
        EvalDatasetKind,
    )
    from qzdap.modules.evaluation.fixtures.golden_dataset import (
        BUILTIN_GOLDEN_DATASET_DESCRIPTION,
        BUILTIN_GOLDEN_DATASET_NAME,
        builtin_golden_cases,
    )
    from qzdap_schema.ids import TenantId, UserId, WorkspaceId
    from sqlalchemy import select

    factory = getattr(app.state, "evaluation_service_factory", None)
    if factory is None:
        _log.warning("evaluation_service_factory not wired; skipping seed")
        return

    cases = builtin_golden_cases()
    sf = container.session_factory().maker()

    # Discover existing tenants + workspaces.
    from qzdap_persistence.base import TenantScopedMixin

    stmt = (
        select(EvalDatasetORM.tenant_id, EvalDatasetORM.workspace_id)
        .where(EvalDatasetORM.name == BUILTIN_GOLDEN_DATASET_NAME)
        .distinct()
    )
    seeded_pairs: set[tuple[object, object]] = {
        (r[0], r[1]) for r in (await sf.execute(stmt)).all()
    }

    tenant_stmt = select(TenantScopedMixin.tenant_id).limit(500)
    try:
        tenant_rows = (await sf.execute(tenant_stmt)).all()
    except Exception:  # noqa: BLE001
        tenant_rows = []

    seeded = 0
    for row in tenant_rows:
        tenant_id_val = row[0]
        # workspace_id is tenant-wide for the seed (use a per-tenant
        # synthetic zero workspace — datasets don't need a real workspace
        # to be queryable).
        from uuid import UUID as _UUID

        workspace_id_val = _UUID(int=0)
        key = (tenant_id_val, workspace_id_val)
        if key in seeded_pairs:
            continue
        now = datetime.now(UTC)
        ds = EvalDataset.create(
            tenant_id=TenantId(_UUID(str(tenant_id_val))),
            workspace_id=WorkspaceId(workspace_id_val),
            name=BUILTIN_GOLDEN_DATASET_NAME,
            description=BUILTIN_GOLDEN_DATASET_DESCRIPTION,
            kind=EvalDatasetKind.BUILTIN,
            case_count=len(cases),
            created_by=UserId(uuid4()),
            now=now,
        )
        sf.add(dataset_to_orm(ds))
        await sf.flush()
        for c in cases:
            case = EvalCase.create(
                tenant_id=ds.tenant_id,
                workspace_id=ds.workspace_id,
                dataset_id=ds.id,
                ordinal=c.ordinal,
                input=c.input,
                expected_keywords=c.expected_keywords,
                min_keywords_hit_ratio=c.min_keywords_hit_ratio,
                max_latency_ms=c.max_latency_ms,
                now=now,
            )
            sf.add(case_to_orm(case))
        await sf.flush()
        seeded += 1

    await sf.commit()
    if seeded:
        _log.info("seeded golden-default eval dataset for %d tenants", seeded)


async def ensure_default_resources(container: Container) -> None:
    """Seed a demo tenant + workspace + admin user when the DB is empty.

    Runs only in dev/test (skipped in production / ci unless explicitly
    enabled via ``QZDAP_DEV_SEED_DEFAULT_RESOURCES=1``). Idempotent: a no-op
    once any tenant row exists.

    Also seeds built-in custom tools (echo/reverse/clock) for the demo
    tenant whenever the tools table is empty, so the smoke flow
    GET /v1/tools → POST .../invoke works without manual registration.
    """
    import os

    from qzdap.modules.identity.adapter.persistence.models import TenantORM
    from qzdap.modules.identity.adapter.persistence.repositories import (
        SqlTenantRepository,
        SqlUserRepository,
        SqlWorkspaceRepository,
    )
    from qzdap.modules.identity.domain import Tenant, User, Workspace
    from sqlalchemy import func, select

    settings = container.settings
    if (
        settings.env not in {"development", "test"}
        and os.environ.get("QZDAP_DEV_SEED_DEFAULT_RESOURCES", "1") != "1"
    ):
        return

    sf = container.session_factory()
    try:
        async with sf.session() as session:
            # Bail early if anything already exists.
            existing = (
                await session.execute(select(func.count()).select_from(TenantORM))
            ).scalar_one()
            if existing and existing > 0:
                # Tenant already exists — skip the identity seed but still
                # try to seed built-in tools below.
                row = (
                    await session.execute(select(TenantORM).limit(1))
                ).scalar_one_or_none()
                tenant_id = row.id if row is not None else UUID(settings.demo_tenant_id)
            else:
                tenant_id = UUID(settings.demo_tenant_id)
                tenant = Tenant.create(
                    id=tenant_id,
                    slug="demo",
                    display_name="Demo Tenant",
                    metadata={"seeded": True},
                )
                ws = Workspace.create(
                    id=__import__("uuid").uuid4(),
                    tenant_id=tenant_id,
                    slug="default",
                    display_name="Default Workspace",
                )
                await SqlTenantRepository(session).add(tenant)
                await SqlWorkspaceRepository(session).add(ws)
                await session.commit()
                _log.info(
                    "seeded default tenant/workspace",
                    extra={
                        "tenant_id": str(tenant_id),
                        "workspace_id": str(ws.id),
                    },
                )

            users_repo = SqlUserRepository(session)
            hashed = container.hasher().hash(settings.dev_admin_password)
            login_accounts = (
                (settings.dev_admin_email, "Demo Admin"),
                ("admin@acme.com", "Demo Admin"),
                ("user@acme.com", "Demo User"),
            )
            seeded_logins: list[str] = []
            for email, display_name in login_accounts:
                existing_user = await users_repo.get_by_email_global(email)
                if existing_user is not None:
                    continue
                await users_repo.add(
                    User.create(
                        id=__import__("uuid").uuid4(),
                        tenant_id=tenant_id,
                        email=email,
                        display_name=display_name,
                        hashed_password=hashed,
                    )
                )
                seeded_logins.append(email)
            if seeded_logins:
                await session.commit()
                _log.info("seeded demo login accounts", extra={"emails": seeded_logins})

            # Seed built-in custom tools (echo / reverse / clock) for the
            # demo tenant whenever the tools table is empty, so the smoke
            # flow GET /v1/tools → POST .../invoke works without manual
            # registration. Idempotent: skips rows that already exist.
            from qzdap.modules.tool.adapter.persistence.models import ToolORM

            tool_count = (
                await session.execute(select(func.count()).select_from(ToolORM))
            ).scalar_one()
            if tool_count == 0:
                # Find ANY existing workspace (whichever tenant it belongs
                # to) — built-in tools will be tied to that tenant for
                # smoke purposes. Production seed is per-tenant and is
                # out of scope for this fixture.
                from qzdap.modules.identity.adapter.persistence.models import (
                    WorkspaceORM,
                )

                ws_row = (
                    await session.execute(select(WorkspaceORM).limit(1))
                ).scalar_one_or_none()
                seed_tenant_id = ws_row.tenant_id if ws_row is not None else tenant_id
                if ws_row is not None:
                    from uuid import uuid4

                    from qzdap.modules.tool.adapter.persistence.models import ToolORM

                    for name in ("echo", "reverse", "clock"):
                        session.add(
                            ToolORM(
                                id=uuid4(),
                                tenant_id=seed_tenant_id,
                                workspace_id=ws_row.id,
                                name=name,
                                description=f"built-in {name}",
                                protocol="custom",
                                spec={},
                                spec_operations=[],
                                auth_config=None,
                                rate_limit_per_minute=None,
                                enabled=True,
                                version=1,
                            )
                        )
                    await session.commit()
                    _log.info("seeded built-in tools tenant_id=%s", seed_tenant_id)
    except Exception:  # noqa: BLE001
        _log.exception("ensure_default_resources failed; continuing boot")
