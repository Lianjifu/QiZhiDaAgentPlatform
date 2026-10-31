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

import asyncio
import os
from contextlib import asynccontextmanager, suppress
from datetime import UTC, datetime
from logging import getLogger
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

from fastapi import FastAPI

from qzdap.modules.memory.domain.entities import EMBEDDING_DIM
from qzdap_kernel.error_codes import ErrorCode

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Awaitable, Callable

    from qzdap.composition.container import Container

_log = getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Boot/shutdown hooks."""
    container: Container = app.state.container

    # ── logging ──────────────────────────────────────────────────────────
    from qzdap_observability.logging import configure_logging

    configure_logging(level=container.settings.log_level, json=container.settings.log_json)

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

    # Phase 1: 把 agent.model (upstream 名字符串) 解析成 ModelId (UUID).
    # 不依赖 master key, 始终可用 — catalog 缺失时返回 None, 运行时
    # 退到 env 默认 LLM. 这样没配 catalog 的旧 agent 仍能跑, 不破坏向后兼容.
    catalog_model_resolver = container.catalog_model_resolver()

    # ⚠️ 旧的 ``_AgentRuntimeFactory``（门面 ``AgentRuntimeService``）**已删**
    # （2026-10-30，Session Stage 5b）—— 它服务的第二套 turn 实现已删 ✓，
    # 剩下的会话门面与 copilot 重复 ✗。现在只有 copilot 一条链 ✓。

    # Phase 14: 注入 DelegateSubagentUseCase 到 app.state, 让 builtin
    # delegate_to_agent 工具通过 _get_delegate_subagent_usecase() 拿.
    from qzdap.modules.agent_runtime.application.use_cases.delegate_subagent import (
        DelegateRuntime,
        DelegateSubagentUseCase,
    )

    def _delegate_runtime(db_session):  # type: ignore[no-untyped-def]
        """委派一次需要的端口（**请求级** ✓）。"""
        from qzdap.modules.agent_runtime.adapter.events import (
            AgentRuntimeEventPublisher,
        )
        from qzdap.modules.agent_runtime.adapter.persistence.repositories import (
            SqlSessionRepository,
        )
        from qzdap.modules.agent_runtime.application.one_shot_turn import (
            OneShotTurnService,
        )
        from qzdap.modules.agent_runtime.application.use_cases.create_session import (
            CreateSessionUseCase,
        )

        sessions = SqlSessionRepository(db_session)
        create_session = CreateSessionUseCase(sessions, AgentRuntimeEventPublisher(container.bus()))
        copilot = _CopilotFactory().for_session(db_session)
        return DelegateRuntime(
            sessions=sessions,
            catalog=_AgentCatalogFactory().for_session(db_session),
            create_session=create_session,
            one_shot=OneShotTurnService(
                create_session=create_session,
                copilot=copilot,
                # ⚠️ **跑一轮**走模块侧入口 ✓（S-21b ✓）。
                turn_entry=copilot.turn_entry,
            ),
        )

    app.state.delegate_subagent_usecase = DelegateSubagentUseCase(
        runtime_factory=_delegate_runtime,
        session_factory=container.session_factory(),
    )
    # 把 use case 句柄推到 builtin_extra_tools 那边.
    from qzdap.modules.tool.adapter.adapters.builtin_extra_tools import (
        bind_delegate_subagent_usecase,
    )

    bind_delegate_subagent_usecase(app.state.delegate_subagent_usecase)

    from qzdap.modules.agent_runtime.adapter.graph import SessionGraphRunner
    from qzdap.modules.agent_runtime.adapter.persistence.catalog_repositories import (
        SqlCatalogAgentRepository,
        SqlCatalogAgentUserStateRepository,
    )
    from qzdap.modules.agent_runtime.adapter.persistence.session_claim import (
        PostgresTurnClaim,
    )
    from qzdap.modules.agent_runtime.adapter.persistence.session_messages import (
        PostgresSessionMessageStore,
    )
    from qzdap.modules.agent_runtime.adapter.turn.cancel import SqlCancelProbe
    from qzdap.modules.agent_runtime.adapter.turn.executor import SessionGraphExecutor
    from qzdap.modules.agent_runtime.adapter.turn.lifecycle import TurnLifecycle
    from qzdap.modules.agent_runtime.adapter.turn.session_state import SqlSessionState
    from qzdap.modules.agent_runtime.application.catalog import AgentCatalogService
    from qzdap.modules.agent_runtime.application.copilot import CopilotSessionService
    from qzdap.modules.agent_runtime.application.turn_entry import TurnEntryService
    from qzdap_agent_runtime.session.turn_runner import TurnRunner

    async def _evaluate_catalog_agent(*, agent, prompt):
        result = await catalog_evaluation_runner(
            tenant_id=agent.tenant_id,
            workspace_id=agent.workspace_id,
            owner_id=UUID(int=0),
            agent_id=str(agent.id),
            user_input=prompt,
        )
        return result["final_message"]

    class _AgentCatalogFactory:
        def for_session(self, session):  # type: ignore[no-untyped-def]
            return AgentCatalogService(
                SqlCatalogAgentRepository(session),
                SqlCatalogAgentUserStateRepository(session),
                evaluator=_evaluate_catalog_agent,
            )

    app.state.agent_catalog_factory = _AgentCatalogFactory()

    # ── Session Manager（Session Stage 1）──────────────────────────────
    # 会话实例的创建与查回**归 Session 层**（决策 #10：Router 不写会话表）。
    # 消费方是 Router Stage 2 的 IM 路径 —— 本层只交付**契约 + 实现** ✓。
    class _SessionManagerFactory:
        def for_session(self, session):  # type: ignore[no-untyped-def]
            from qzdap.modules.agent_runtime.adapter.persistence.session_store import (
                PostgresSessionStore,
            )
            from qzdap_agent_runtime.session.manager import SessionManager

            return SessionManager(store=PostgresSessionStore(session))

    app.state.session_manager_factory = _SessionManagerFactory()

    # ── 会话内的两个序列（Session Stage 2）──────────────────────────────
    # 轮次序 ``ingress_seq`` 的**调用方是 Router**（入站顺序 = FIFO 顺序），
    # 消息序 ``session_seq`` 由 Session 自己用 —— 但**分配器只有这一份**
    # （两处各写一个原子自增，阈值迟早不一致 ✗）。
    class _SessionSequenceFactory:
        def for_session(self, session):  # type: ignore[no-untyped-def]
            from qzdap.modules.agent_runtime.adapter.persistence.session_sequence import (
                PostgresSessionSequence,
            )

            return PostgresSessionSequence(session)

    app.state.session_sequence_factory = _SessionSequenceFactory()

    # ── Router 策略（Router Stage 1）────────────────────────────────────
    # 建会话的 agent 由**规则链**选出 —— 旧的 `agentId` 直取已下线
    # （台账 R2）。候选池来自 agent 目录，用户属性来自 identity，
    # **策略本身在契约层**（qzdap_agent_runtime.router），这里只做接线。
    class _RouterStrategyFactory:
        def __init__(self) -> None:
            self._catalog_factory = app.state.agent_catalog_factory

        def for_session(self, session):  # type: ignore[no-untyped-def]
            from qzdap.modules.agent_runtime.adapter.routing import (
                CatalogRoutingAdapter,
            )
            from qzdap.modules.identity.adapter.persistence.repositories import (
                SqlUserRepository,
            )
            from qzdap.modules.identity.adapter.user_directory import (
                IdentityUserDirectory,
            )
            from qzdap_agent_runtime.router.strategy import RuleChainStrategy

            return RuleChainStrategy(
                catalog=CatalogRoutingAdapter(self._catalog_factory.for_session(session)),
                users=IdentityUserDirectory(SqlUserRepository(session)),
            )

    app.state.router_strategy_factory = _RouterStrategyFactory()

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
            from qzdap.modules.agent_runtime.adapter.persistence.artifact_store import (
                PostgresArtifactStore,
            )
            from qzdap.modules.agent_runtime.adapter.persistence.context_manifest_store import (
                PostgresContextManifestStore,
            )
            from qzdap.modules.agent_runtime.adapter.persistence.idempotency_store import (
                PostgresIdempotencyStore,
            )
            from qzdap.modules.agent_runtime.adapter.sandbox import (
                SandboxRuntimeAdapter,
            )
            from qzdap.modules.agent_runtime.adapter.skills import SkillServiceAdapter
            from qzdap_agent_runtime.gateway.idempotency import IdempotencyGuard
            from qzdap_kernel.ids import TenantId, UserId, WorkspaceId

            knowledge_factory = getattr(app.state, "knowledge_service_factory", None)
            memory_factory = getattr(app.state, "memory_runtime_service_factory", None)
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
            except Exception:
                approval = None
            graph = SessionGraphRunner(
                llm=llm,
                skill_port=skill_port,
                sandbox_port=sandbox_port,
                memory_port=memory_port,
                knowledge_port=knowledge_port,
                approval_factory=approval,
                # Phase 1.5: 让 graph 走 model 解析 (前端 chat 不带 body.model 时,
                # agent_row.model='deepseek-flash' 这种 str 也能查 admin_models).
                catalog_model_resolver=catalog_model_resolver,
                # ⚠️ **manifest 的落库口** ✓（Context Stage 4 ✓）—— 每次模型
                # 调用一条 ✓（Context 方案 §5.1.1 ✓）—— 与轮次**同事务** ✓
                # （同一个 session ✓）。
                context_manifest_store=PostgresContextManifestStore(session),
                # ⚠️ **产物的落库口** ✓ —— 产物（模型 / 工具的输出 ✓）落
                # ``session_artifacts`` ✓（迁移 0064 ✓）—— **跟着会话走** ✓
                # —— 与轮次**同事务** ✓（同一个 session ✓）。
                artifact_store=PostgresArtifactStore(session),
            )
            _ = (TenantId, UserId, WorkspaceId)
            sessions_repo = SqlSessionRepository(session)
            messages_store = PostgresSessionMessageStore(session)
            # **唯一 turn 实现**（契约层，Session 方案 §6）—— 编排在这里装配，
            # 能力全部走端口 ✓。
            # ⚠️ **排队** ✓（Router Stage 3 · 决策 #1「S1 严格排队」✓）——
            # **开关默认关** ✓（Router 方案 §0.7 ✓ —— 破坏性契约变更 ✓
            # 要先上前端兼容 ✓）。关着 = 旧语义「拒绝 409」✓。
            queue = None
            sequence = None
            if container.settings.router_queue_enabled:
                from qzdap.modules.agent_runtime.adapter.persistence.session_queue import (
                    PostgresTurnQueue,
                )
                from qzdap.modules.agent_runtime.adapter.persistence.session_sequence import (
                    PostgresSessionSequence,
                )

                queue = PostgresTurnQueue(session)
                sequence = PostgresSessionSequence(session)
            turn_runner = TurnRunner(
                executor=SessionGraphExecutor(graph),
                lifecycle=TurnLifecycle(
                    journal=container.session_journal(),
                    events=AgentRuntimeEventPublisher(container.bus()),
                ),
                messages=messages_store,
                session_state=SqlSessionState(sessions_repo),
                cancel=SqlCancelProbe(sessions_repo),
                queue=queue,
                # ⚠️ **入站序号分配器** ✓（排队时用 ✓ —— Router 方案 §4.2 ✓）。
                sequence=sequence,
                # ⚠️ **准入归编排** ✓（S-21b ✓）—— 幂等 + 会话占用 ✓
                # （幂等守卫自持事务 ✓ —— claim 必须在轮次开始前落库, 否则并发
                # 的第二个请求看不到它, 两轮都会起 ✓）。
                idempotency=IdempotencyGuard(PostgresIdempotencyStore(container.session_factory())),
                claim=PostgresTurnClaim(session),
            )
            # ⚠️ **跑一轮的模块侧入口** ✓（S-21b ✓）—— 读 + 组装 ✓，
            # 幂等 / claim / 转发在契约层 ✓。
            turn_entry = TurnEntryService(
                sessions=sessions_repo,
                messages=messages_store,
                catalog=catalog,
                turn_runner=turn_runner,
            )
            return CopilotSessionService(
                sessions=sessions_repo,
                turns=SqlTurnRepository(session),
                # 消息存取归 Session 层（新表唯一落点，S-15b ✓）——
                # 调用方不再直接依赖旧表 repo ✓（切读/停旧写只改实现）。
                messages=messages_store,
                catalog=catalog,
                events=AgentRuntimeEventPublisher(container.bus()),
                graph=graph,
                # 新架构的轮次 + 事件日志 —— 重放的落点（Stage 4b）。
                journal=container.session_journal(),
                turn_entry=turn_entry,
            )

    async def catalog_evaluation_runner(
        *, tenant_id, workspace_id, owner_id, agent_id, user_input, agent_version=None
    ):
        from dataclasses import replace

        from qzdap_kernel.errors import AppError

        sf = container.session_factory()
        async with sf.session() as evaluation_session:
            catalog = _AgentCatalogFactory().for_session(evaluation_session)
            catalog.bind_scope(tenant_id=tenant_id, workspace_id=workspace_id)
            candidates = await catalog._agents.list_for_workspace(workspace_id)
            agent = next(
                (
                    a
                    for a in candidates
                    if a.tenant_id == tenant_id
                    and (str(a.id) == str(agent_id) or a.name == str(agent_id))
                ),
                None,
            )
            if agent is None:
                raise AppError(
                    "evaluation agent not found",
                    code=ErrorCode.EVAL_AGENT_NOT_FOUND.value,
                    status=404,
                )
            if agent_version:
                version = next(
                    (v for v in agent.versions if v.get("version") == agent_version),
                    None,
                )
                if not version or not isinstance(version.get("snapshot"), dict):
                    raise AppError(
                        "evaluation version snapshot missing",
                        code=ErrorCode.EVAL_VERSION_MISSING.value,
                        status=422,
                    )
                agent = replace(agent.apply_patch(version["snapshot"]), version=agent_version)
            copilot = _CopilotFactory().for_session(evaluation_session)
            graph = copilot._graph
            turn_id = uuid4()
            output = {
                "final_message": "",
                "turn_id": str(turn_id),
                "input_tokens": 0,
                "output_tokens": 0,
            }
            async for chunk in graph.run_turn(
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                owner_id=owner_id,
                turn_id=turn_id,
                user_input=user_input,
                history=[],
                agent=agent,
                model=agent.model,
            ):
                if chunk.kind == "approval_required":
                    raise AppError(
                        "evaluation requires human approval",
                        code=ErrorCode.EVAL_APPROVAL_REQUIRED.value,
                        status=409,
                    )
                if chunk.kind == "error":
                    raise AppError(chunk.message, code=chunk.code, status=502)
                if chunk.kind == "done":
                    output["final_message"] = chunk.final_message or ""
                if chunk.kind == "usage":
                    output["input_tokens"], output["output_tokens"] = (
                        chunk.input_tokens,
                        chunk.output_tokens,
                    )
            await evaluation_session.commit()
            return output

    app.state.catalog_evaluation_runner = catalog_evaluation_runner
    app.state.copilot_factory = _CopilotFactory()
    app.state.model_service = model_service

    # ── 渠道入站 → 一轮会话（Session Stage 5b）────────────────────────
    # IM 的入站**不再经过「第二套 turn 实现」**（台账 X2）—— 与 web 走同一条
    # 链路 ✓：会话粘性（channel_session_key）+ 唯一 turn 实现。
    def _channel_turn_ports(request, db_session):  # type: ignore[no-untyped-def]
        """**请求作用域**的端口（skill / sandbox / tool）—— 与 web 侧同口径 ✓。

        ⚠️ 不绑这些端口 = 那一轮**没有工具**（web 侧由 HTTP 层绑；IM 侧在这里
        绑 ✓）—— 少绑一个就是一次静默的功能退化 ✗。
        """
        from qzdap.modules.agent_runtime.adapter.sandbox import SandboxRuntimeAdapter
        from qzdap.modules.agent_runtime.adapter.skills import SkillServiceAdapter
        from qzdap.modules.agent_runtime.adapter.tools import ToolServiceAdapter
        from qzdap_kernel.ids import TenantId, UserId, WorkspaceId

        tenant_id = TenantId(request.tenant_id)
        workspace_id = WorkspaceId(request.workspace_id)
        owner_id = UserId(request.owner_id)
        ports: dict[str, Any] = {}

        skill_factory = getattr(app.state, "skill_factory", None)
        if skill_factory is not None:
            ports["skill_port"] = SkillServiceAdapter(
                svc=skill_factory.for_session(db_session),
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                owner_id=owner_id,
            )
        sandbox_client = getattr(app.state, "sandbox_client", None)
        if sandbox_client is not None:
            ports["sandbox_port"] = SandboxRuntimeAdapter(
                sandbox_client,
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                agent_id=None,
            )
        tool_factory = getattr(app.state, "tool_factory", None)
        if tool_factory is not None:
            ports["tool_port"] = ToolServiceAdapter(
                tool_service=tool_factory.for_session(db_session),
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                owner_id=owner_id,
            )
        # ⚠️ **专家装配器** ✓（Agent Stage 4 ✓ / Stage 5 接线 ✓）—— 与 web 侧
        # **同口径** ✓（同一份装配 ✓ —— 两套就不是同一套了 ✗✗）。
        expert_factory = getattr(app.state, "expert_assembler_factory", None)
        if expert_factory is not None:
            ports["expert_assembler"] = expert_factory.for_scope(
                request.tenant_id,
                request.workspace_id,
                request.owner_id,
                db_session,
            )
        return ports

    class _ChannelTurnFactory:
        """渠道入站的**请求级**装配 ✓。"""

        def for_session(self, db_session):  # type: ignore[no-untyped-def]
            from qzdap.modules.agent_runtime.application.channel_turn import (
                ChannelTurnService,
            )

            copilot = _CopilotFactory().for_session(db_session)
            return ChannelTurnService(
                # 会话粘性归 Session Manager（唯一 owner ✓）。
                sessions=app.state.session_manager_factory.for_session(db_session),
                copilot=copilot,
                # ⚠️ **跑一轮**走模块侧入口 ✓（S-21b ✓）—— 与 web 侧同一条 ✓。
                turn_entry=copilot.turn_entry,
                ports=lambda request: _channel_turn_ports(request, db_session),
                # ⚠️ **Router 的规则链** ✓（台账 R19 ✓）—— 渠道入站**也走规则
                # 链** ✓（与 web 侧**同一条链** ✓ —— 渠道登记的 agent 只是
                # 「显式指定」这一条规则的输入 ✓）。
                strategy=app.state.router_strategy_factory.for_session(db_session),
            )

    app.state.channel_turn_factory = _ChannelTurnFactory()

    # Phase 2: 注册 catalog_model_resolver 到 app.state, 让 agent_factory router
    # 在 POST /v1/agents (template) 和 /v1/agents/{aid}/versions (version) 时
    # 能把请求里的 model_id (上游名字符串) 解析成 admin_models.id (UUID).
    # agent_factory_router 通过 request.app.state.catalog_model_resolver 拿到.
    app.state.catalog_model_resolver = container.catalog_model_resolver()

    from qzdap.modules.model.adapter.llm.client_factory import (
        build_default_client_factory,
    )
    from qzdap.modules.model.adapter.llm.connectivity_tester import (
        HttpConnectivityTester,
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
                connectivity_tester=HttpConnectivityTester(),
                verification_secret=container.settings.jwt_secret.encode(),
            )

        def __call__(self, session):  # type: ignore[no-untyped-def]
            return self.for_session(session)

    app.state.model_service_factory = _ModelFactory()

    # Phase 14: 后台 health 采样器 — 定期跑 health_check 写 admin_model_health
    # 不阻塞主流程; 关停时干净 cancel.
    async def _health_sampler_loop() -> None:
        # 间隔 (s). 短间隔保证 dev 可观察; 生产可调.
        interval = int(os.environ.get("QZDAP_HEALTH_SAMPLER_INTERVAL", "60"))
        # 模块引用在闭包内做 (避免 lifespan 启动前 import)
        from sqlalchemy import select

        from qzdap.modules.model.adapter.persistence.models import (
            ProviderORM,
        )

        try:
            while True:
                try:
                    async with container.session_factory().session() as session:
                        # 找所有 healthy 状态的 provider
                        result = await session.execute(
                            select(ProviderORM).where(ProviderORM.status == "healthy")
                        )
                        providers = result.scalars().all()
                        for prov in providers:
                            try:
                                # 用 _ModelFactory 拿全配置 ModelService
                                async with container.session_factory().session() as p_session:
                                    factory = _ModelFactory()
                                    svc = factory.for_session(p_session)
                                    await svc.health_check(prov.id)
                                    # health_check 内部 commit + 写 health 事件
                            except Exception as _prov_exc:  # defensive
                                _log.warning(
                                    "health_sampler_provider_failed: %s: %s",
                                    prov.id,
                                    _prov_exc,
                                )
                except Exception as _loop_exc:  # defensive
                    _log.warning("health_sampler_iteration_failed: %s", _loop_exc)
                await asyncio.sleep(interval)
        except asyncio.CancelledError:
            _log.info("health_sampler_cancelled")
            raise

    sampler_task: asyncio.Task[None] | None = None
    if os.environ.get("QZDAP_HEALTH_SAMPLER_DISABLED", "").lower() not in (
        "1",
        "true",
        "yes",
    ):
        try:
            sampler_task = asyncio.create_task(_health_sampler_loop())
            _log.info(
                "health_sampler_started interval=%ds",
                int(os.environ.get("QZDAP_HEALTH_SAMPLER_INTERVAL", "60")),
            )
        except RuntimeError as _task_exc:
            _log.warning("health_sampler_failed_to_start: %s", _task_exc)
            sampler_task = None

    async def _stop_sampler() -> None:
        if sampler_task is not None and not sampler_task.done():
            sampler_task.cancel()
            try:
                await sampler_task
            except asyncio.CancelledError:
                pass
            except Exception as _stop_exc:  # defensive
                _log.debug("health_sampler_stop_failed: %s", _stop_exc)

    app.state.health_sampler_stop = _stop_sampler

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
    # web 入口的门面（①②③ + ④）—— 与渠道门面同型。
    app.state.web_gateway = container.web_gateway()

    # ── per-request tool factory ─────────────────────────────────────
    import httpx as _httpx

    from qzdap.modules.tool.adapter.adapters import (
        CustomInvokerRegistry,
        MCPRuntimeAdapter,
        OpenAPIRuntimeAdapter,
        ToolAuditRecorder,
        bind_audit_recorder,
        bind_settings_for_tools,
        built_in_invoke_apply_patch,
        built_in_invoke_ask_user_question,
        built_in_invoke_bash,
        built_in_invoke_calculator,
        built_in_invoke_clock,
        built_in_invoke_code_search,
        built_in_invoke_convert_format,
        built_in_invoke_csv_query,
        built_in_invoke_delegate_to_agent,
        built_in_invoke_diff,
        built_in_invoke_echo,
        built_in_invoke_edit_file,
        built_in_invoke_fetch_url_with_auth,
        built_in_invoke_git_diff,
        built_in_invoke_git_log,
        built_in_invoke_git_status,
        built_in_invoke_glob,
        built_in_invoke_grep,
        built_in_invoke_http_fetch,
        built_in_invoke_image_view,
        built_in_invoke_json_query,
        built_in_invoke_ls,
        built_in_invoke_notify_user,
        built_in_invoke_pdf_read,
        built_in_invoke_plan_submit,
        built_in_invoke_read_file,
        built_in_invoke_reverse,
        built_in_invoke_todo_write,
        built_in_invoke_web_search,
        built_in_invoke_write_artifact,
        built_in_invoke_write_file,
    )
    from qzdap.modules.tool.adapter.events import ToolEventPublisher
    from qzdap.modules.tool.adapter.persistence.repositories import (
        SqlToolCallRepository,
        SqlToolRepository,
    )
    from qzdap.modules.tool.application.services import ToolService

    http_client = _httpx.AsyncClient(timeout=30.0)
    secrets_resolver = container.secrets_resolver()
    openapi_rt = OpenAPIRuntimeAdapter(http=http_client, secrets_resolver=secrets_resolver)
    mcp_rt = MCPRuntimeAdapter(http=http_client, secrets_resolver=secrets_resolver)

    custom_invoker = CustomInvokerRegistry(workspace_root=container.settings.workspace_root)
    bind_settings_for_tools(container.settings)
    bind_audit_recorder(ToolAuditRecorder(session_factory=container.session_factory()))
    custom_invoker.register("echo", built_in_invoke_echo)
    custom_invoker.register("reverse", built_in_invoke_reverse)
    custom_invoker.register("clock", built_in_invoke_clock)
    # 内置联网工具 — 主进程 httpx 出网, 不走 sandbox. 见
    # custom_invoker.built_in_invoke_web_search / built_in_invoke_http_fetch.
    custom_invoker.register("web_search", built_in_invoke_web_search)
    custom_invoker.register("http_fetch", built_in_invoke_http_fetch)
    # 文件系统 + shell built-ins (对标 Claude Code 的 Bash / Read / Write /
    # Edit / LS / Glob / Grep). 全部走 CUSTOM 协议 in-process, 工作区路径
    # 限制在 settings.workspace_root / <workspace_id>/ 下, _safe_resolve()
    # 拦截路径穿越与 protected prefix (.git/ / node_modules/ / .venv/ 等)。
    custom_invoker.register("bash", built_in_invoke_bash)
    custom_invoker.register("read_file", built_in_invoke_read_file)
    custom_invoker.register("write_file", built_in_invoke_write_file)
    custom_invoker.register("edit_file", built_in_invoke_edit_file)
    custom_invoker.register("ls", built_in_invoke_ls)
    custom_invoker.register("glob", built_in_invoke_glob)
    custom_invoker.register("grep", built_in_invoke_grep)
    # ── Extended built-ins (ticket: agent-builtin-tools-v2.md) ──────
    custom_invoker.register("apply_patch", built_in_invoke_apply_patch)
    custom_invoker.register("diff", built_in_invoke_diff)
    custom_invoker.register("image_view", built_in_invoke_image_view)
    custom_invoker.register("pdf_read", built_in_invoke_pdf_read)
    custom_invoker.register("json_query", built_in_invoke_json_query)
    custom_invoker.register("csv_query", built_in_invoke_csv_query)
    custom_invoker.register("git_status", built_in_invoke_git_status)
    custom_invoker.register("git_diff", built_in_invoke_git_diff)
    custom_invoker.register("git_log", built_in_invoke_git_log)
    custom_invoker.register("code_search", built_in_invoke_code_search)
    custom_invoker.register("convert_format", built_in_invoke_convert_format)
    custom_invoker.register("fetch_url_with_auth", built_in_invoke_fetch_url_with_auth)
    custom_invoker.register("calculator", built_in_invoke_calculator)
    # ── Frontend-coupled stubs ──────────────────────────────────────
    custom_invoker.register("ask_user_question", built_in_invoke_ask_user_question)
    custom_invoker.register("notify_user", built_in_invoke_notify_user)
    custom_invoker.register("plan_submit", built_in_invoke_plan_submit)
    custom_invoker.register("todo_write", built_in_invoke_todo_write)
    custom_invoker.register("delegate_to_agent", built_in_invoke_delegate_to_agent)
    # ⚠️ **产物工具** ✓ —— 产出内容交给会话层落库 ✓（工具层不碰会话表 ✓）。
    custom_invoker.register("write_artifact", built_in_invoke_write_artifact)

    # ⚠️ **熔断器是进程内共享的单例** ✓ —— 每请求新建一个 = **永远不熔断** ✗✗
    # （那是「有熔断代码但没熔断」✗）。
    from qzdap.modules.tool.application.reliability import CircuitBreaker

    tool_circuit_breaker = CircuitBreaker()

    class _ToolFactory:
        def __init__(self) -> None:
            self._bus = container.bus()

        def for_session(self, session):  # type: ignore[no-untyped-def]
            from qzdap.modules.agent_runtime.adapter.persistence.tool_executions import (
                PostgresToolExecutionStore,
            )

            return ToolService(
                tools=SqlToolRepository(session),
                calls=SqlToolCallRepository(session),
                custom=custom_invoker,
                openapi=openapi_rt,
                mcp=mcp_rt,
                events=ToolEventPublisher(self._bus),
                tool_call_timeout_seconds=container.settings.tool_call_timeout_seconds,
                # ⚠️ **幂等的唯一权威** ✓（`tool_executions` ✓ —— 跨 worker 有效 ✓
                # —— 此前**从未被写** ✓ → 幂等只在进程内 dict 里 ✗✗）。
                executions=PostgresToolExecutionStore(session),
                breaker=tool_circuit_breaker,
            )

    app.state.tool_factory = _ToolFactory()
    app.state.mcp_runtime = mcp_rt

    # ── 专家装配（Agent Stage 4）───────────────────────────────────────
    # ⚠️ **专家实例 = 模型 + 指令 + 工具集** ✓（Agent 方案 §4.2 ✓）——
    # 装配器**只取不选** ✓：选专家是路由端口 ✓ / 模型是查表 ✓ / 工具是
    # 绑定集 + 治理过滤 ✓。
    # ⚠️ **请求作用域** ✓ —— 绑定集与工具运行时都绑着租户 / 工作区 / 用户 ✓
    # → **按请求装配** ✓（不是全局单例 ✗ —— 那样会串租户 ✗✗）。
    class _ExpertAssemblerFactory:
        """**按请求装配专家实例** ✓（Agent Stage 4 ✓ / Stage 5 接线 ✓）。

        ⚠️ **请求作用域** ✓ —— 绑定集与工具运行时都绑着租户 / 工作区 / 用户 ✓
        → **按请求装配** ✓（不是全局单例 ✗ —— 那样会串租户 ✗✗）。
        """

        def for_scope(self, tenant_id, workspace_id, owner_id, db_session):  # type: ignore[no-untyped-def]
            from qzdap.modules.agent_runtime.adapter.graph.agent_loop import (
                ModuleToolRuntime,
                RuntimeLLMPort,
                RuntimeModelResolver,
            )
            from qzdap.modules.agent_runtime.adapter.sandbox import (
                SandboxRuntimeAdapter,
            )
            from qzdap.modules.agent_runtime.adapter.skills import SkillServiceAdapter
            from qzdap.modules.agent_runtime.adapter.tools.agent_router_adapter import (
                CatalogAgentLister,
                CatalogAgentRouter,
            )
            from qzdap.modules.agent_runtime.adapter.tools.catalog_binding_reader import (
                CatalogBindingReader,
            )
            from qzdap.modules.agent_runtime.adapter.tools.tool_binding_adapter import (
                ToolBindingAdapter,
            )
            from qzdap.modules.agent_runtime.adapter.tools.tool_service_adapter import (
                ToolServiceAdapter,
            )
            from qzdap_agent_runtime.agent_loop.expert import ExpertAssembler
            from qzdap_kernel.ids import TenantId, UserId, WorkspaceId

            tid = TenantId(tenant_id)
            wid = WorkspaceId(workspace_id)
            uid = UserId(owner_id)
            tool_service = app.state.tool_factory.for_session(db_session)
            tool_port = ToolServiceAdapter(
                tool_service=tool_service,
                tenant_id=tid,
                workspace_id=wid,
                owner_id=uid,
            )
            skill_port = None
            skill_factory = getattr(app.state, "skill_factory", None)
            if skill_factory is not None:
                skill_port = SkillServiceAdapter(
                    svc=skill_factory.for_session(db_session),
                    tenant_id=tid,
                    workspace_id=wid,
                    owner_id=uid,
                )
            sandbox_port = None
            sandbox_client = getattr(app.state, "sandbox_client", None)
            if sandbox_client is not None:
                sandbox_port = SandboxRuntimeAdapter(
                    sandbox_client,
                    tenant_id=tid,
                    workspace_id=wid,
                    agent_id=None,
                )
            catalog = AgentCatalogService(
                SqlCatalogAgentRepository(db_session),
                SqlCatalogAgentUserStateRepository(db_session),
                evaluator=_evaluate_catalog_agent,
            )
            return ExpertAssembler(
                router=CatalogAgentRouter(
                    catalog=CatalogAgentLister(catalog),
                ),
                bindings=ToolBindingAdapter(
                    tools=tool_port,
                    skills=skill_port,
                    agents=CatalogBindingReader(SqlCatalogAgentRepository(db_session)),
                    sandbox=sandbox_port is not None,
                ),
                llm=RuntimeLLMPort(
                    LLMPortAdapter(
                        container.llm_client(),
                        model_service=model_service,
                    )
                ),
                resolver=RuntimeModelResolver(getattr(app.state, "catalog_model_resolver", None)),
                # ⚠️ **工具执行只有一份** ✓（旧的 `execute_tool` ✓ —— 它包着
                # `modules/tool` 的 `InvokeToolUseCase` ✓ 唯一权威 ✓）。
                tool_runtime=ModuleToolRuntime(
                    skill_port=skill_port,
                    sandbox_port=sandbox_port,
                    tool_port=tool_port,
                    tenant_id=tenant_id,
                ),
            )

    app.state.expert_assembler_factory = _ExpertAssemblerFactory()

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

    policy_guard = container.policy_guard() if container.settings.policy_enabled else None

    # ── per-request memory factory ──────────────────────────────────────
    from qzdap.modules.memory.adapter.persistence.repositories import (
        SqlMemoryCatalogRepository,
    )
    from qzdap.modules.memory.adapter.persistence.vector_adapter import (
        PgMemoryVectorAdapter,
    )
    from qzdap.modules.memory.application.admin_service import MemoryAdminService
    from qzdap.modules.memory.application.services import MemoryRuntimeService
    from qzdap_vector.pg_vector import PgVectorStore

    memory_vectors = PgMemoryVectorAdapter(
        PgVectorStore(
            container.engine(),
            table="admin_memory_vec",
            dim=EMBEDDING_DIM,
        )
    )
    memory_embedding = container.memory_embedding_adapter()

    # ⚠️ **向量补写队列 + 后台 worker** ✓（C5 ✓ —— Memory 方案 §5.4 ✓）——
    # **应用级** ✓（每请求一个队列 = 队列就没了 ✗✗）。
    from qzdap.modules.memory.adapter.vectorize import (
        MemoryVectorBackfill,
        MemoryVectorizeAdapter,
    )
    from qzdap_agent_runtime.memory.vectorize import (
        InMemoryVectorWriteQueue,
        VectorizeWorker,
    )

    memory_vector_queue = InMemoryVectorWriteQueue()
    memory_vector_worker = VectorizeWorker(
        queue=memory_vector_queue,
        store=MemoryVectorizeAdapter(embedding=memory_embedding, vectors=memory_vectors),
        backfill=MemoryVectorBackfill(container.session_factory()),
    )
    app.state.memory_vector_queue = memory_vector_queue
    app.state.memory_vector_worker = memory_vector_worker

    class _MemoryRuntimeFactory:
        """**运行面** ✓ —— 对话路径用它 ✓（召回 / 写入 ✓）。"""

        def for_session(self, session):  # type: ignore[no-untyped-def]
            from qzdap.modules.agent_runtime.adapter.persistence.session_activity import (
                PostgresSessionActivity,
            )
            from qzdap.modules.memory.adapter.persistence.buffer_repository import (
                SqlMemoryBufferRepository,
            )

            return MemoryRuntimeService(
                SqlMemoryCatalogRepository(session),
                embedding=memory_embedding,
                vectors=memory_vectors,
                # ⚠️ **落库后异步补向量** ✓（C5 ✓ —— 写路径不等 embedding ✓）。
                vector_queue=memory_vector_queue,
                # ⚠️ **会话缓冲 + 活跃度** ✓（决策 #5 ✓ —— 会话级策略 ✓）。
                buffer=SqlMemoryBufferRepository(session),
                activity=PostgresSessionActivity(session),
            )

        def __call__(self, session):  # type: ignore[no-untyped-def]
            return self.for_session(session)

    class _MemoryAdminFactory:
        """**管理面** ✓ —— 管理端接口用它 ✓（目录 / 策略 / 审核 / 趋势 ✓）。"""

        def for_session(self, session):  # type: ignore[no-untyped-def]
            from qzdap.modules.agent_runtime.adapter.memory.policy_publisher import (
                AgentMemoryPolicyPublisher,
            )
            from qzdap.modules.agent_runtime.adapter.memory.session_info import (
                PostgresSessionInfo,
            )
            from qzdap.modules.knowledge.adapter.promotion import (
                KnowledgeCandidateAdapter,
            )
            from qzdap.modules.memory.adapter.persistence.buffer_repository import (
                SqlMemoryBufferRepository,
            )

            return MemoryAdminService(
                SqlMemoryCatalogRepository(session),
                embedding=memory_embedding,
                vectors=memory_vectors,
                # ⚠️ **团队知识候选** ✓（决策 #1 ✓ —— L3 退役 ✓）——
                # 提升的终点是 knowledge ✓（**人工审核发布** ✓）。
                knowledge=KnowledgeCandidateAdapter(
                    app.state.knowledge_service_factory.for_session(session)
                ),
                # ⚠️ **策略发布的落点** ✓（B2 的「配置发布与生效」✓ —— M-37 ✓）——
                # 发布写进 agent 行 ✓ → 运行时**下一次就读到** ✓。
                publisher=AgentMemoryPolicyPublisher(SqlCatalogAgentRepository(session)),
                # ⚠️ **会话缓冲** ✓（**L1 表退役后的唯一来源** ✓ —— M-46 ✓）
                # —— 管理端看的「L1」现在就是它 ✓（决策 #5 ✓）。
                buffer=SqlMemoryBufferRepository(session),
                # ⚠️ **会话的展示信息** ✓（「谁 ↔ 哪个 agent」✓）—— 窄端口 ✓
                # （Memory 不查会话表 ✓）。
                session_info=PostgresSessionInfo(session),
            )

        def __call__(self, session):  # type: ignore[no-untyped-def]
            return self.for_session(session)

    # ⚠️ **两个平面各一个工厂** ✓（Memory Stage 0 的平面分离 ✓ 台账 X16 ✓）
    # —— 对话路径只看得到**运行面** ✓。
    app.state.memory_runtime_service_factory = _MemoryRuntimeFactory()
    app.state.memory_admin_service_factory = _MemoryAdminFactory()

    class _DataSubjectFactory:
        """**数据主体请求**的工厂 ✓（C9 ✓ —— 决策 #8 ✓）。

        ⚠️ **治理域只认 scope** ✓ —— 它**不认识**记忆表 ✗✗ → 记忆域自己
        实现一个 scope ✓（``scope = "memory"`` ✓）—— 这里只负责**注册** ✓。
        """

        def for_session(self, session):  # type: ignore[no-untyped-def]
            from qzdap.modules.governance.application.data_subject import (
                DataSubjectService,
            )
            from qzdap.modules.memory.adapter.persistence.buffer_repository import (
                SqlMemoryBufferRepository,
            )
            from qzdap.modules.memory.application.governance import (
                MemoryDataSubjectScope,
            )

            return DataSubjectService(
                scopes=[
                    MemoryDataSubjectScope(
                        catalog=SqlMemoryCatalogRepository(session),
                        vectors=memory_vectors,
                        buffer=SqlMemoryBufferRepository(session),
                    )
                ]
            )

        def __call__(self, session):  # type: ignore[no-untyped-def]
            return self.for_session(session)

    app.state.data_subject_service_factory = _DataSubjectFactory()

    # ── per-request knowledge factory ───────────────────────────────────
    from qzdap.modules.knowledge.adapter.persistence.repositories import (
        SqlKnowledgeCatalogRepository,
        SqlKnowledgeDocUserStateRepository,
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
            dim=EMBEDDING_DIM,
        )
    )
    knowledge_embedding = container.memory_embedding_adapter()

    class _KnowledgeFactory:
        def for_session(self, session):  # type: ignore[no-untyped-def]
            return KnowledgeService(
                SqlKnowledgeCatalogRepository(session),
                embedding=knowledge_embedding,
                vectors=knowledge_vectors,
                user_state=SqlKnowledgeDocUserStateRepository(session),
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

        def for_session(self, session) -> EvaluationService:  # type: ignore[no-untyped-def]
            ds_repo = SqlEvalDatasetRepository(session)
            run_repo = SqlEvalRunRepository(session)
            # 评测跑的是**唯一 turn 实现**（copilot 链 ✓）—— 没有它就退到桩 ✓。
            sub_agent_factory = getattr(app.state, "copilot_factory", None)
            sub_agent = _sub_agent_for_evaluation(sub_agent_factory)
            runner = EvalRunner(
                run_repo=run_repo,
                dataset_repo=ds_repo,
                sub_agent=sub_agent,
                publisher=self._publisher,
                scoring_threshold=(container.settings.agent_factory_eval_score_min),
                concurrency=container.settings.evaluation_runner_concurrency,
                case_timeout_seconds=(container.settings.evaluation_case_default_timeout_seconds),
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

        Wire to the real ``RealSubAgentPort`` when the copilot factory
        (the **唯一 turn 实现**) is available; fall back to the deterministic
        stub when it is not (legacy dev shells, missing
        ``QZDAP_MODEL_MASTER_KEY``, boot in a slim test harness). Heuristic
        scoring against the stub will fail most cases — the gate wiring
        (pass / fail / no_eval) still validates the lifecycle.
        """
        if ar_factory is None:
            from qzdap.modules.evaluation.adapter.sub_agent_stub import (
                StubSubAgentPort,
            )

            return StubSubAgentPort()

        class _AgentVersionQuery:
            """**评测要读的 agent 版本** ✓ —— 从 agent_factory 的版本表读 ✓。

            ⚠️ **跨模块的读放在组合根** ✓ —— 评测模块只声明端口 ✓（不引
            agent_factory 的持久化 ✓）。

            ⚠️ **返回字典而不是领域对象** ✓ —— 评测模块不引 agent_factory 的
            领域 ✓ → 消费方按键取值 ✓（`model_id` / `version_tag` ✓）。
            """

            def __init__(self, repo) -> None:  # type: ignore[no-untyped-def]
                self._repo = repo

            async def get_agent_version(  # type: ignore[no-untyped-def]
                self, *, tenant_id, template_id, version_id
            ):
                version = await self._repo.get(tenant_id=tenant_id, version_id=version_id)
                if version is None or version.template_id != template_id:
                    return None
                return {
                    "model_id": version.model_id,
                    "version_tag": version.version_tag,
                    "status": version.status.value,
                }

        from qzdap.modules.agent_factory.adapter.persistence.repositories import (
            SqlAgentVersionRepository,
        )

        sf_for_query = container.session_factory().maker()
        agent_factory = _AgentVersionQuery(SqlAgentVersionRepository(sf_for_query))
        return _PerCaseRealSubAgent(
            container=container,
            agent_factory=agent_factory,
        )

    class _PerCaseRealSubAgent:
        """每个评测用例装配一个**请求级**的服务（隔离的会话 + 连接 ✓）。

        ⚠️ 走的是 **copilot 链**（唯一 turn 实现 ✓）—— 旧的 ``AgentRuntimeService``
        门面已删（Session Stage 5b ✓）。
        """

        def __init__(self, *, container, agent_factory) -> None:  # type: ignore[no-untyped-def]
            self._container = container
            self._agent_factory = agent_factory

        async def run_turn_to_completion(self, **kwargs):  # type: ignore[no-untyped-def]
            from qzdap.modules.agent_runtime.adapter.events import (
                AgentRuntimeEventPublisher,
            )
            from qzdap.modules.agent_runtime.adapter.persistence.repositories import (
                SqlSessionRepository,
            )
            from qzdap.modules.agent_runtime.application.one_shot_turn import (
                OneShotTurnService,
            )
            from qzdap.modules.agent_runtime.application.use_cases.create_session import (
                CreateSessionUseCase,
            )
            from qzdap.modules.evaluation.adapter.sub_agent_real import (
                RealSubAgentPort,
            )

            sf = self._container.session_factory().maker()
            # ⚠️ **唯一 turn 实现**（Session Stage 5b）—— 与 web / IM 同一条链路 ✓
            copilot = _CopilotFactory().for_session(sf)
            one_shot = OneShotTurnService(
                create_session=CreateSessionUseCase(
                    SqlSessionRepository(sf),
                    AgentRuntimeEventPublisher(self._container.bus()),
                ),
                copilot=copilot,
                # ⚠️ **跑一轮**走模块侧入口 ✓（S-21b ✓）。
                turn_entry=copilot.turn_entry,
            )
            adapter = RealSubAgentPort(
                one_shot=one_shot,
                agent_factory=self._agent_factory,
            )
            try:
                return await adapter.run_turn_to_completion(**kwargs)
            finally:
                # 评测这一轮的轮次行 / 消息要落库 ✓（不提交 = 白跑 ✓）。
                await sf.commit()

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

        def for_session(self, session) -> AgentFactoryService:  # type: ignore[no-untyped-def]
            evaluation_query = _build_evaluation_query(session)
            return AgentFactoryService.from_parts(
                template_repository=SqlAgentTemplateRepository(session),
                version_repository=SqlAgentVersionRepository(session),
                release_repository=SqlReleaseRepository(session),
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
        def for_session(self, session) -> PlatformService:  # type: ignore[no-untyped-def]
            return PlatformService.from_parts(
                plan_repo=PlatformSqlPlanRepository(session),
                subscription_repo=SqlSubscriptionRepository(session),
                setting_repo=SqlTenantSettingRepository(session),
                publisher=None,
                # Bridge into observability's SqlCostRecordRepository
                # so ``aggregate_costs`` actually reads tenant spend.
                cost_repo=ObservabilityCostRepositoryBridge(session),
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
    channel_service_obj = getattr(app.state, "channel_service", None)
    if channel_service_obj is not None:
        from qzdap.modules.agent_runtime.adapter.persistence.outbox_repository import (
            PostgresOutboxRepository,
        )
        from qzdap.modules.channel.adapter.dispatch.channel_turn_dispatcher import (
            ChannelTurnDispatcher,
        )

        dispatch = ChannelTurnDispatcher(
            channel_repository=channel_service_obj.channel_repo,
            # 跑一轮 —— **唯一 turn 实现**（Session 层）✓（台账 X2 的终结点）。
            turn_factory=app.state.channel_turn_factory,
            # 出站 —— 统一编码 + 投递（Gateway ① 的出站，§6）。
            sink=container.channel_result_sink(),
            open_session=container.session_factory().maker,
            # 出站队列 —— **回复先入队、投递失败可重试** ✓（Session 方案 §7）。
            outbox=PostgresOutboxRepository(container.session_factory()),
        )
        await dispatch.install(bus)
        app.state.channel_turn_dispatcher = dispatch
        _log.info("channel turn dispatcher active")
    else:
        _log.info("channel turn dispatcher skipped (channel_service missing)")

    # ── Phase 19: agent_factory.version.released → agent_runtime catalog ──
    # factory 发布时, 若 catalog 里有 id == template_id 的行, 把它推到 published.
    # 条件: catalog 仓储可用 (adapters admin side wired).
    catalog_factory = getattr(app.state, "agent_catalog_factory", None)
    if catalog_factory is not None:
        from qzdap.modules.agent_runtime.adapter.subscribers import (
            agent_factory_release_subscriber,
        )

        session_factory_obj = container.session_factory()
        await agent_factory_release_subscriber.install(bus, session_factory_obj)
        _log.info("agent_factory release subscriber active")
    else:
        _log.info("agent_factory release subscriber skipped (catalog_factory absent)")

    # ── seed default resources ───────────────────────────────────────────
    await ensure_default_resources(container)

    # ── redis client (for /readyz) ───────────────────────────────────────
    try:
        app.state.redis = container.redis_client()
    except Exception:
        _log.warning("redis client not attached; /readyz will report redis=skipped")

    # ── Session 生命周期（Session Stage 0/1）─────────────────────────────
    # ① 超时清扫器 —— **幂等键过期是 Gateway 的硬依赖**（过期行留在表里，
    #    同一个键重发仍会命中冲突 → 表无限膨胀）✓
    app.state.session_sweeper_stop = await _start_session_sweeper(container, app)
    # ③ 出站队列 worker —— **IM 的回复先入队、投递失败可重试** ✓
    #    （Session 方案 §7；台账 S-24 / S-26）
    app.state.outbox_worker_stop = await _start_outbox_worker(container)
    # ④ 向量补写 worker —— **落库后异步补向量** ✓（C5 ✓ —— Memory §5.4 ✓）
    app.state.memory_vector_stop = _start_memory_vector_worker(app)

    # ⚠️ **checkpoint saver 已退役** ✓（Session S-14 ✓）—— 它唯一的消费者是
    # 那张 19 节点的 LangGraph 图 ✓（**已随 Agent Stage 7 删除** ✓）——
    # 新的循环用**会话 metadata + 轮次行**续传 ✓（不需要 LangGraph 的
    # checkpoint ✓）→ **不再起它** ✓（省一个连接池 ✓ —— 台账 X3 ✓）。

    try:
        yield
    finally:
        # Phase 14: 关停 health sampler
        stop_sampler = getattr(app.state, "health_sampler_stop", None)
        if stop_sampler is not None:
            await stop_sampler()
        # Session：先停清扫器，再关 saver（saver 的连接要在任务停后才关 ✓）
        stop_sweeper = getattr(app.state, "session_sweeper_stop", None)
        if stop_sweeper is not None:
            await stop_sweeper()
        stop_outbox = getattr(app.state, "outbox_worker_stop", None)
        if stop_outbox is not None:
            await stop_outbox()
        stop_vector = getattr(app.state, "memory_vector_stop", None)
        if stop_vector is not None:
            await stop_vector()
        await bus.stop()
        sandbox = getattr(app.state, "sandbox", None)
        if sandbox is not None:
            await sandbox.shutdown()


def _start_memory_vector_worker(app: Any) -> Callable[[], Awaitable[None]]:
    """起**向量补写**的后台任务 ✓（C5 ✓ —— Memory 方案 §5.4 ✓）。

    ⚠️ **写路径不等它** ✓ —— 队列是应用级的 ✓（每请求一个队列 = 队列就没了 ✗✗）。
    ⚠️ **补不上由兜底补写捡回来** ✓（worker 自己定期扫「最近更新过的」✓）。
    """
    worker = getattr(app.state, "memory_vector_worker", None)
    if worker is None:

        async def _noop() -> None:
            return None

        return _noop

    interval = max(1, int(os.environ.get("QZDAP_MEMORY_VECTOR_INTERVAL", "30")))

    async def _loop() -> None:
        await worker.run(interval_s=interval)

    task = asyncio.create_task(_loop())
    _log.info("memory_vector_worker_started interval=%ds", interval)

    async def _stop() -> None:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task

    return _stop


def _expire_due_approvals(container: Container) -> Callable[[datetime], Awaitable[int]]:
    """**审批过期的清扫回调** ✓（Session 方案 §3.3 ✓）。

    ⚠️ **判定在治理域** ✓ —— 这里只做接线 ✓（清扫器不引治理模块 ✓）。
    """

    async def _expire(now: datetime) -> int:
        service = container.approval_service()
        return int(await service.expire_due(now=now))

    return _expire


async def _refine_memory_buffers(app: Any, container: Container) -> None:
    """**会话缓冲的提炼** ✓（M-29 ✓ —— 由 sweeper 触发 ✓）。

    ⚠️ **失败不拖垮清扫** ✓ —— 提炼失败下一轮再来 ✓。
    """
    if app is None:
        return
    factory = getattr(app.state, "memory_runtime_service_factory", None)
    if factory is None:
        return
    try:
        async with container.session_factory().session() as session:
            service = factory.for_session(session)
            now = datetime.now(UTC)
            report = await service.refine_buffers(now=now)
            # ⚠️ **淘汰器与清扫器同批调度** ✓（Memory 方案 Stage 6 ✓ ——
            # 「淘汰器与 sweeper 一起调度」✓）—— **策略第一次有执行者** ✓。
            evicted = await service.evict(now=now)
            await session.commit()
    except Exception:
        _log.exception("memory buffer refinement failed; will retry next tick")
        return
    if report.total:
        _log.info("memory buffer refine: %s", report)
    if evicted.total:
        _log.info("memory eviction: %s", evicted)


async def _start_session_sweeper(
    container: Container, app: Any = None
) -> Callable[[], Awaitable[None]]:
    """起超时清扫的后台任务 —— **幂等键过期**是 Gateway 的硬依赖 ✓。

    ⚠️ 清扫**四类**（Session 方案 §3.3 ✓）：僵尸轮次 ✓ + 幂等键过期 ✓ +
    审批过期 ✓（判定归治理域 ✓）+ **会话空闲** ✓（30 天 ✓ —— 只关「有
    复活路径」的 ✓ —— 方案 §3.4 ✓）。
    """
    from qzdap.modules.agent_runtime.adapter.persistence.idempotency_store import (
        PostgresIdempotencyStore,
    )
    from qzdap.modules.agent_runtime.adapter.persistence.session_sweeper import (
        PostgresSessionSweeper,
    )

    interval = max(1, int(os.environ.get("QZDAP_SESSION_SWEEPER_INTERVAL", "300")))
    sweeper = PostgresSessionSweeper(
        session_factory=container.session_factory(),
        idempotency_store=PostgresIdempotencyStore(container.session_factory()),
        # ⚠️ **审批过期归治理域** ✓（Session 方案 §3.3 的第 2 类 ✓ —— 判定
        # 只有一份 ✓ —— 治理域的 ``expire_if_due`` ✓）。
        expire_approvals=_expire_due_approvals(container),
        # ⚠️ **会话空闲阈值可配** ✓（决策 #7 ✓ —— 默认 30 天 ✓）。
        idle_timeout_days=container.settings.session_idle_timeout_days,
    )

    async def _loop() -> None:
        while True:
            await asyncio.sleep(interval)
            try:
                report = await sweeper.sweep(now=datetime.now(UTC))
            except asyncio.CancelledError:
                raise
            except Exception:
                _log.exception("session sweep failed; will retry next tick")
                continue
            if report.total:
                _log.info("session sweep: %s", report)
            # ⚠️ **会话缓冲的提炼** ✓（M-29 ✓）—— **同批调度** ✓
            # （Memory 方案 Stage 5 ✓ —— 「由 sweeper 触发」✓ —— 没有触发者
            # = 这个能力不存在 ✗✗）。
            await _refine_memory_buffers(app, container)

    task = asyncio.create_task(_loop())
    _log.info("session_sweeper_started interval=%ds", interval)

    async def _stop() -> None:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task

    return _stop


async def _start_outbox_worker(
    container: Container,
    *,
    repo: Any | None = None,
    dispatcher: Any | None = None,
) -> Callable[[], Awaitable[None]]:
    """起**出站队列**的后台任务 —— 重试与死信 ✓。

    ⚠️ **队列里只有「出站消息」**（``im_reply`` 那一类 ✓）—— 轮次里的 chunk
    事件是**事件日志**（供重放 ✓），不是队列 ✗（混在一起会把 web 的 chunk
    投到 IM 渠道 ✗✗）。

    ⚠️ **投递失败不炸主链路** ✓ —— 那一轮已经成功；回复晚到一步，比丢掉好 ✓。
    """
    from qzdap.modules.agent_runtime.adapter.persistence.outbox_repository import (
        PostgresOutboxRepository,
    )
    from qzdap.modules.channel.adapter.outbound.channel_outbox_dispatcher import (
        ChannelOutboxDispatcher,
    )
    from qzdap_agent_runtime.outbox import OutboxWorker

    interval = max(1, int(os.environ.get("QZDAP_OUTBOX_INTERVAL", "10")))
    # ⚠️ **可注入**（repo / dispatcher）—— 接线层要能**离线**测 ✓
    # （「接了但没跑」是静默的 ✗✗）。
    worker = OutboxWorker(
        repo=repo or PostgresOutboxRepository(container.session_factory()),
        dispatcher=dispatcher or ChannelOutboxDispatcher(sink=container.channel_result_sink()),
    )

    async def _loop() -> None:
        while True:
            await asyncio.sleep(interval)
            try:
                processed = await worker.tick()
            except asyncio.CancelledError:
                raise
            except Exception:
                _log.exception("outbox tick failed; will retry next tick")
                continue
            if processed:
                _log.info("outbox tick: %s", worker.stats)

    task = asyncio.create_task(_loop())
    _log.info("outbox_worker_started interval=%ds", interval)

    async def _stop() -> None:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task

    return _stop


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
    except Exception:
        _log.exception("seed_default_plans failed; continuing boot")


async def _seed_builtin_eval_datasets(app: FastAPI, container: Container) -> None:
    """Seed the 50-case golden dataset for every existing tenant.

    Idempotent: skips tenants that already have a ``golden-default``
    dataset.  Called once at lifespan start so the dataset is ready
    by the time HTTP requests land.
    """
    from uuid import uuid4

    from sqlalchemy import select

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
    from qzdap_kernel.ids import TenantId, UserId, WorkspaceId

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
    except Exception:
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
    """按 ``QZDAP_ENV`` 种对应那一套种子数据.

    * ``demo``        → demo 租户 + demo 账号（演示库）
    * ``development`` → dev 租户 + dev 账号（开发库）
    * ``test``        → 同 development, 但不种给 CI 用
    * 其它 env        → 不种（staging / production 需要时显式跑
      ``backend/scripts/seed_dev_data.py``）

    关键约束: **开发环境不种 demo 数据**. 之前这里对 development 和 test
    都种 ``Demo Tenant`` + ``admin@acme.com``, 而真正的 ``demo`` env 反而
    什么都不种 —— 正好与需求相反. 现在两套数据各有各的租户和账号.

    ``QZDAP_DEV_SEED_DEFAULT_RESOURCES=1`` 只影响 dev 那套, 不会把 demo
    账号种进非演示环境.
    """
    import os

    from qzdap.composition.seeds import (
        profile_for_env,
        seed_builtin_tools,
        seed_demo_content,
        seed_identity,
    )

    settings = container.settings
    profile = profile_for_env(settings)
    if profile is None:
        if os.environ.get("QZDAP_DEV_SEED_DEFAULT_RESOURCES", "0") != "1":
            return
        # 显式要求种 —— 但仍然只种 dev 那套, 演示数据不进非演示环境.
        from qzdap.composition.seeds import dev_profile

        profile = dev_profile(settings)

    sf = container.session_factory()
    try:
        async with sf.session() as session:
            result = await seed_identity(session, container.hasher(), profile)
            await seed_builtin_tools(session, result["tenant_id"], result["workspace_id"])
            # 演示内容 (智能体/技能/工作流/知识库) —— 内部按 profile.label
            # 判断, dev 那套直接跳过.
            await seed_demo_content(
                session,
                profile,
                tenant_id=result["tenant_id"],
                workspace_id=result["workspace_id"],
            )
    except Exception:
        _log.exception("ensure_default_resources failed; continuing boot")
