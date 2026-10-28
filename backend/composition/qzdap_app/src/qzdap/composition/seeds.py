"""种子数据 —— 演示数据与开发测试数据**严格分开**。

两套数据各有独立的租户、账号、密码, 落在各自的库里:

===============  ======================  =========================
环境             QZDAP_ENV              种子
===============  ======================  =========================
演示             ``demo``                demo 租户 + admin@acme.com / user@acme.com
开发             ``development``         dev 租户 + admin@dev.qzdap.dev
===============  ======================  =========================

规则:

* 开发环境**不种 demo 数据** —— 开发库里不该出现 ``Demo Tenant`` 或
  ``admin@acme.com``. 开发要用的数据由 dev 种子提供, 名字里带 ``dev``.
* 演示环境**不种 dev 数据** —— 演示库里只有 demo 租户和 demo 账号.
* 两者不共用租户、账号、密码, 也不共用库. 哪套数据由 ``QZDAP_ENV``
  决定, 没有旁路开关 —— 之前的 ``QZDAP_DEV_SEED_DEFAULT_RESOURCES``
  只影响 dev 那套, 且不会种 demo 账号.

内置工具 (``echo`` / ``bash`` / …) 是**平台参考数据**而不是演示内容 ——
每个租户都需要一份, 所以两套种子都会注册. 名字与参数契约的单一来源是
``qzdap.modules.tool.application.tool_catalog.BUILTIN_TOOL_SPECS``.

演示智能体 (``DEMO_AGENT_SPECS``) 是**演示内容** —— 只在 demo 那套里种.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

_log = logging.getLogger(__name__)


@dataclass(frozen=True)
class SeedProfile:
    """一套种子数据的身份 —— 租户 / 工作区 / 账号 / 密码."""

    #: ``demo`` / ``dev`` —— 只用于日志和 metadata, 决定数据"长什么样".
    label: str
    tenant_id: UUID
    tenant_slug: str
    tenant_display_name: str
    workspace_slug: str
    workspace_display_name: str
    #: (email, display_name, role) —— role 是 workspace 角色.
    accounts: tuple[tuple[str, str, str], ...]
    password: str


def demo_profile(settings: Any) -> SeedProfile:
    """演示环境用的那套数据."""
    return SeedProfile(
        label="demo",
        tenant_id=UUID(settings.demo_tenant_id),
        tenant_slug=settings.demo_tenant_slug,
        tenant_display_name=settings.demo_tenant_display_name,
        workspace_slug="default",
        workspace_display_name="Default Workspace",
        accounts=(
            (settings.demo_admin_email, "Demo Admin", "admin"),
            (settings.demo_user_email, "Demo User", "member"),
        ),
        password=settings.demo_password,
    )


def dev_profile(settings: Any) -> SeedProfile:
    """开发环境用的那套数据 —— 名字里带 dev, 跟 demo 区分得开."""
    return SeedProfile(
        label="dev",
        tenant_id=uuid4(),
        tenant_slug=settings.dev_tenant_slug,
        tenant_display_name=settings.dev_tenant_display_name,
        workspace_slug="default",
        workspace_display_name="Default Workspace",
        accounts=((settings.dev_admin_email, "Dev Admin", "admin"),),
        password=settings.dev_admin_password,
    )


def profile_for_env(settings: Any) -> SeedProfile | None:
    """按 ``QZDAP_ENV`` 选对应那套种子.

    ``staging`` / ``production`` 返回 ``None`` —— 那两个环境不种任何
    租户/账号, 需要的话走 ``backend/scripts/seed_dev_data.py`` 显式跑.
    """
    env = str(getattr(settings, "env", "development"))
    if env == "demo":
        return demo_profile(settings)
    if env in {"development", "test"}:
        return dev_profile(settings)
    return None


async def seed_identity(
    session: Any,
    hasher: Any,
    profile: SeedProfile,
) -> dict[str, Any]:
    """种租户 / 工作区 / 账号 / 工作区成员关系. 幂等.

    已经有同名租户时**复用**它而不是新建 —— 免得重复跑种子脚本把库里
    塞满同名租户.
    """
    from qzdap.modules.identity.adapter.persistence.models import (
        TenantORM,
        UserWorkspaceORM,
        WorkspaceORM,
    )
    from qzdap.modules.identity.adapter.persistence.repositories import (
        SqlTenantRepository,
        SqlUserRepository,
        SqlWorkspaceRepository,
    )
    from qzdap.modules.identity.domain import Tenant, User, Workspace
    from sqlalchemy import select

    existing_tenant = (
        await session.execute(
            select(TenantORM).where(TenantORM.slug == profile.tenant_slug).limit(1)
        )
    ).scalar_one_or_none()
    if existing_tenant is not None:
        tenant_id = existing_tenant.id
        workspace_id = (
            await session.execute(
                select(WorkspaceORM.id)
                .where(
                    WorkspaceORM.tenant_id == tenant_id,
                    WorkspaceORM.status == "active",
                )
                .limit(1)
            )
        ).scalars().first()
        created_tenant = False
    else:
        tenant_id = profile.tenant_id
        tenant = Tenant.create(
            id=tenant_id,
            slug=profile.tenant_slug,
            display_name=profile.tenant_display_name,
            metadata={"seeded": True, "seed_profile": profile.label},
        )
        workspace = Workspace.create(
            id=uuid4(),
            tenant_id=tenant_id,
            slug=profile.workspace_slug,
            display_name=profile.workspace_display_name,
        )
        await SqlTenantRepository(session).add(tenant)
        await SqlWorkspaceRepository(session).add(workspace)
        await session.commit()
        workspace_id = workspace.id
        created_tenant = True
        _log.info(
            "seeded %s tenant/workspace",
            profile.label,
            extra={
                "tenant_id": str(tenant_id),
                "workspace_id": str(workspace_id),
                "slug": profile.tenant_slug,
            },
        )

    users_repo = SqlUserRepository(session)
    hashed = hasher.hash(profile.password)
    seeded_logins: list[str] = []
    seeded_memberships: list[str] = []
    for email, display_name, role in profile.accounts:
        user = await users_repo.get_by_email_global(email)
        if user is None:
            user = User.create(
                id=uuid4(),
                tenant_id=tenant_id,
                email=email,
                display_name=display_name,
                hashed_password=hashed,
            )
            await users_repo.add(user)
            seeded_logins.append(email)
        # 工作区成员关系 —— 没有这行, 需要 workspace_access 的端点会 403.
        if workspace_id is not None:
            membership = await session.scalar(
                select(UserWorkspaceORM).where(
                    UserWorkspaceORM.user_id == user.id,
                    UserWorkspaceORM.workspace_id == workspace_id,
                )
            )
            if membership is None:
                session.add(
                    UserWorkspaceORM(
                        tenant_id=tenant_id,
                        user_id=user.id,
                        workspace_id=workspace_id,
                        role=role,
                    )
                )
                seeded_memberships.append(email)
    if seeded_logins:
        await session.commit()
        _log.info(
            "seeded %s login accounts", profile.label, extra={"emails": seeded_logins}
        )
    if seeded_memberships:
        await session.commit()
        _log.info(
            "seeded %s workspace memberships",
            profile.label,
            extra={"emails": seeded_memberships, "workspace_id": str(workspace_id)},
        )
    return {
        "tenant_id": tenant_id,
        "workspace_id": workspace_id,
        "created_tenant": created_tenant,
        "seeded_logins": seeded_logins,
    }


async def seed_builtin_tools(
    session: Any,
    tenant_id: UUID,
    workspace_id: UUID | None,
) -> list[str]:
    """给租户注册内置工具. 幂等 —— 已存在的名字直接跳过.

    内置工具是**平台参考数据**（每个租户都要一份, 才能让模型调得到）,
    不是演示内容, 所以 demo 和 dev 两套种子都会注册它.
    """
    from qzdap.modules.tool.adapter.persistence.models import ToolORM
    from qzdap.modules.tool.application.tool_catalog import BUILTIN_TOOL_SPECS
    from sqlalchemy import select

    existing = {
        str(name)
        for (name,) in (
            await session.execute(
                select(ToolORM.name).where(ToolORM.tenant_id == tenant_id)
            )
        ).all()
    }
    added: list[str] = []
    for name, spec in sorted(BUILTIN_TOOL_SPECS.items()):
        if name in existing:
            continue
        session.add(
            ToolORM(
                id=uuid4(),
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                name=name,
                description=spec["description"],
                protocol="custom",
                spec={},
                spec_operations=[],
                auth_config=None,
                rate_limit_per_minute=None,
                enabled=True,
                version=1,
            )
        )
        added.append(name)
    if added:
        await session.commit()
        _log.info(
            "seeded built-in tools", extra={"tenant_id": str(tenant_id), "count": len(added)}
        )
    return added


#: 演示智能体的上游模型 id —— 演示环境没配供应商前聊天会返回 503,
#: 运营在 ``/admin/models`` 建供应商时把 upstream model 建成这个名字,
#: 这些智能体就能直接对话 (见 ``SqlCatalogModelResolver.resolve``).
DEMO_AGENT_MODEL = "deepseek-chat"

#: 演示智能体清单. body 用的是 **前端 camelCase 契约** —— 跟
#: ``AgentCatalogService.create`` 收的形状一模一样, 所以种出来的
#: 智能体跟管理端手工建的没有区别.
#:
#: ``prompts.user`` 里以 ``-`` 开头的行会被 ``to_catalog_dict`` 取成
#: 开场示例 (Copilot 空态的"常用开场"). ``tools`` 里的名字必须存在于
#: 工具目录 (``BUILTIN_TOOL_SPECS``) —— 内置工具种子已经把它们注册好了.
DEMO_AGENT_SPECS: tuple[dict[str, Any], ...] = (
    {
        "name": "销售线索洞察助手",
        "description": "从线索表里找出值得优先跟进的客户，给出跟进动作与话术建议。",
        "category": "销售支持",
        "tags": ["线索分析", "客户跟进"],
        "tone": "brand",
        "dataAccess": "CRM 线索表与客户跟进记录",
        "tools": ["csv_query", "json_query", "calculator"],
        "prompts": {
            "soul": "你是一名资深销售运营分析师，说话直接、有结论、有下一步动作。",
            "prompt": (
                "职责：从线索数据里识别高价值客户，输出优先级排序、跟进理由和下一步动作。\n"
                "要求：先给结论再给依据；所有数字都要标明来源字段；不确定的地方明说。"
            ),
            "user": (
                "- 帮我看看本周新增线索里哪些值得优先跟进\n"
                "- 按行业统计转化率，并指出掉得最厉害的一环"
            ),
        },
    },
    {
        "name": "客服应答助手",
        "description": "基于产品知识库起草标准应答，必要时引用外部资料并提醒人工介入。",
        "category": "客服应答",
        "tags": ["工单应答", "知识检索"],
        "tone": "info",
        "dataAccess": "产品知识库与历史工单",
        "tools": ["web_search", "http_fetch", "notify_user"],
        "prompts": {
            "soul": "你是一名资深客服支持工程师，语气耐心、条理清楚。",
            "prompt": (
                "职责：根据知识库内容起草可直接发送的回复。\n"
                "要求：先给一段可直接复制的答复，再列出引用的资料要点；"
                "知识库覆盖不到、或者涉及退款与合同条款时，标注需要人工确认。"
            ),
            "user": (
                "- 客户反馈导出功能偶发失败，帮我起草一段回复\n"
                "- 把这份工单整理成一页 FAQ"
            ),
        },
    },
    {
        "name": "经营数据分析",
        "description": "拉通订单、成本与渠道数据，算清关键指标并指出异常。",
        "category": "数据分析",
        "tags": ["指标分析", "经营看板"],
        "tone": "success",
        "dataAccess": "订单、成本与渠道投放数据",
        "tools": ["csv_query", "json_query", "calculator", "bash"],
        "prompts": {
            "soul": "你是一名经营分析师，擅长把数据变成可执行的判断。",
            "prompt": (
                "职责：计算核心经营指标，定位异常并给出解释与建议。\n"
                "要求：每个指标写清口径与时间范围；异常要区分是数据问题还是业务问题；"
                "不要编造没有的数据。"
            ),
            "user": (
                "- 算一下上月各渠道的毛利率并排出好坏\n"
                "- 本周转化率突然掉了，帮我定位可能的原因"
            ),
        },
    },
    {
        "name": "营销文案创作",
        "description": "把卖点与客群信息改写成多渠道可用的营销文案。",
        "category": "文案创作",
        "tags": ["文案生成", "多渠道改写"],
        "tone": "purple",
        "dataAccess": "产品卖点与目标客群画像",
        "tools": ["convert_format", "write_file", "echo"],
        "prompts": {
            "soul": "你是一名资深品牌文案，讲究节奏、画面感和克制的夸张。",
            "prompt": (
                "职责：把给定的卖点与客群写成可直接投放的文案。\n"
                "要求：一版一个角度；不编造用户证言或数据；"
                "同时给出标题、正文和行动号召三段。"
            ),
            "user": (
                "- 给新款企业版写一段发布公告\n"
                "- 把这段介绍改写成适合公众号推文和短信的版本"
            ),
        },
    },
    {
        "name": "企智搭平台向导",
        "description": "讲清楚平台能做什么，并帮忙把任务拆成可执行的步骤。",
        "category": "企业通用",
        "tags": ["平台导览", "任务拆解"],
        "tone": "brand",
        "dataAccess": "平台能力与当前工作空间配置",
        "tools": ["todo_write", "plan_submit"],
        "prompts": {
            "soul": "你是企智搭平台的向导，熟悉平台的每一条能力边界。",
            "prompt": (
                "职责：回答平台用法问题，并把模糊目标拆成可执行步骤。\n"
                "要求：先给一句话答案，再给步骤；平台做不到的事直说，"
                "不要含糊过去。"
            ),
            "user": (
                "- 企智搭能接哪些类型的知识库？\n"
                "- 我想把每周的数据周报自动化，帮我拆成步骤"
            ),
        },
    },
)


async def seed_demo_agents(
    session: Any,
    profile: SeedProfile,
    *,
    tenant_id: UUID,
    workspace_id: UUID | None,
) -> list[str]:
    """种**演示智能体** —— 只有 demo 那套才会种.

    开发环境 (``profile.label != "demo"``) 直接返回空列表: 演示智能体是
    **演示内容**, 开发库里不该出现. 这个判断在函数内部, 不靠调用方自觉.

    幂等: 已经存在同名智能体就跳过 —— 重复跑种子脚本不会塞出一堆同名
    智能体 (数据库上还有 ``(tenant_id, workspace_id, name)`` 唯一约束兜底).
    """
    if profile.label != "demo":
        return []
    if workspace_id is None:
        _log.warning("demo agent seed skipped: no workspace")
        return []

    from qzdap.modules.agent_runtime.adapter.persistence.catalog_repositories import (
        SqlCatalogAgentRepository,
        SqlCatalogAgentUserStateRepository,
    )
    from qzdap.modules.agent_runtime.application.catalog import AgentCatalogService

    repo = SqlCatalogAgentRepository(session)
    service = AgentCatalogService(
        repo, user_state=SqlCatalogAgentUserStateRepository(session)
    )
    existing = {agent.name for agent in await repo.list_for_workspace(workspace_id)}

    created: list[str] = []
    owner = profile.accounts[0][1] if profile.accounts else "演示管理员"
    for spec in DEMO_AGENT_SPECS:
        if spec["name"] in existing:
            continue
        body: dict[str, Any] = {
            **spec,
            "owner": owner,
            "status": "published",
            "model": DEMO_AGENT_MODEL,
            "maxSteps": 8,
            "visibleScope": ["公开"],
            "tools": [{"name": name, "enabled": True} for name in spec.get("tools", [])],
        }
        await service.create(tenant_id=tenant_id, workspace_id=workspace_id, body=body)
        created.append(str(spec["name"]))
    if created:
        await session.commit()
        _log.info(
            "seeded demo agents",
            extra={"tenant_id": str(tenant_id), "names": created},
        )
    return created


#: 演示技能. body 是 ``SkillService.create`` 收的 camelCase 形状.
DEMO_SKILL_SPECS: tuple[dict[str, Any], ...] = (
    {
        "name": "会议纪要归档",
        "description": "把会议录音转写稿整理成纪要：议题、结论、待办与责任人。",
        "type": "Skill",
        "risk": "low",
        "needConfirm": False,
        "tags": ["会议", "纪要"],
        "visibleScope": ["公开"],
        "inputSchema": [
            {"name": "transcript", "type": "string", "required": True, "description": "会议转写全文"},
            {"name": "attendees", "type": "string", "required": False, "description": "参会人名单"},
        ],
        "outputSchema": [
            {"name": "minutes", "type": "string", "required": True, "description": "结构化会议纪要"},
        ],
    },
    {
        "name": "差旅报销核算",
        "description": "按差旅政策核对报销单，标出超标项并算出应补/应退金额。",
        "type": "Skill",
        "risk": "medium",
        "needConfirm": True,
        "tags": ["财务", "合规"],
        "visibleScope": ["部门"],
        "inputSchema": [
            {"name": "claim", "type": "string", "required": True, "description": "报销单明细"},
        ],
        "outputSchema": [
            {"name": "verdict", "type": "string", "required": True, "description": "核算结论与超标项"},
        ],
    },
    {
        "name": "客户反馈聚类",
        "description": "把客服工单按问题类型聚类，给出高频问题与建议优先级。",
        "type": "Skill",
        "risk": "low",
        "needConfirm": False,
        "tags": ["客服", "分析"],
        "visibleScope": ["公开"],
        "inputSchema": [
            {"name": "tickets", "type": "string", "required": True, "description": "工单列表"},
        ],
        "outputSchema": [
            {"name": "clusters", "type": "string", "required": True, "description": "聚类结果与优先级"},
        ],
    },
)

#: 演示工作流. ``boundAgentNames`` 是**智能体名字** —— 种子时会解析成 id,
#: 这样演示库里的工作流是绑在真智能体上的, 不是悬空的 id.
DEMO_WORKFLOW_SPECS: tuple[dict[str, Any], ...] = (
    {
        "name": "每周经营周报",
        "description": "拉数据 → 算指标 → 出结论 → 生成周报，全程无人值守。",
        "scene": "经营分析",
        "trigger": "定时触发",
        "status": "published",
        "boundAgentNames": ["经营数据分析"],
    },
    {
        "name": "新线索自动分派",
        "description": "新线索进来后打分、分派负责人、生成跟进话术。",
        "scene": "销售支持",
        "trigger": "事件触发",
        "status": "published",
        "boundAgentNames": ["销售线索洞察助手"],
    },
    {
        "name": "知识库周更",
        "description": "收集本周新增文档、归类入库、更新检索索引。",
        "scene": "知识运营",
        "trigger": "手动触发",
        "status": "draft",
        "boundAgentNames": ["企智搭平台向导"],
    },
)

#: 演示知识库. ``docs`` 是往库里放的文档（走真实的 ingest 路径）.
DEMO_KB_SPECS: tuple[dict[str, Any], ...] = (
    {
        "name": "差旅与报销指南",
        "description": "出差审批、报销标准、超标处理与常见驳回原因。",
        "scope": "部门",
        "retrieval": "hybrid",
        "topK": 8,
        "docs": [
            {
                "name": "差旅报销标准（2026 版）",
                "type": "manual",
                "content": (
                    "住宿标准：一线城市每晚上限 600 元，其他城市 400 元。\n"
                    "市内交通：按实际发生额报销，需附行程单。\n"
                    "超标处理：超出标准的部分需由部门负责人书面说明，"
                    "在报销单备注栏注明原因。\n"
                    "提交时限：返程后 15 个工作日内提交，逾期需附部门说明。"
                ),
            },
            {
                "name": "常见驳回原因清单",
                "type": "manual",
                "content": (
                    "1. 发票抬头与公司名称不一致。\n"
                    "2. 缺少行程单或行程单与发票日期对不上。\n"
                    "3. 超标项没有负责人说明。\n"
                    "4. 同一笔费用在两个单子里重复提交。"
                ),
            },
        ],
    },
    {
        "name": "产品答疑手册",
        "description": "常见问题、配置说明与故障自查步骤。",
        "scope": "公开",
        "retrieval": "hybrid",
        "topK": 6,
        "docs": [
            {
                "name": "企业知识库接入说明",
                "type": "manual",
                "content": (
                    "支持的文件类型：PDF、Markdown、Word、网页链接。\n"
                    "同步方式：手动上传，或配置来源后按天增量同步。\n"
                    "检索：默认混合检索（语义 + 关键词），Top K 默认 8。"
                ),
            }
        ],
    },
)


async def seed_demo_skills(
    session: Any,
    profile: SeedProfile,
    *,
    tenant_id: UUID,
    workspace_id: UUID | None,
) -> list[str]:
    """种**演示技能** —— 只有 demo 那套才会种."""
    if profile.label != "demo" or workspace_id is None:
        return []

    from qzdap.modules.skill.adapter.persistence.repositories import (
        SqlSkillRepository,
        SqlSkillUserStateRepository,
    )
    from qzdap.modules.skill.application.services import SkillService

    repo = SqlSkillRepository(session)
    service = SkillService(repo, user_state=SqlSkillUserStateRepository(session))
    owner = profile.accounts[0][1] if profile.accounts else "演示管理员"

    created: list[str] = []
    republished = False
    for spec in DEMO_SKILL_SPECS:
        existing = await repo.get_by_name(workspace_id=workspace_id, name=spec["name"])
        if existing is not None:
            # 已经在了 —— 但如果是草稿就补一次发布 (早期种的数据是 draft).
            if existing.status != "published":
                await service.update(
                    skill_id=existing.id,
                    body={"status": "published"},
                    actor=owner,
                )
                republished = True
            continue
        skill = await service.create(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            body={**spec, "owner": owner},
        )
        # Skill.create 强制 status="draft" —— 用户侧目录只放 published /
        # graying 的, 不发布的话"技能"页是空的.
        await service.update(
            skill_id=UUID(str(skill["id"])),
            body={"status": "published"},
            actor=owner,
        )
        created.append(str(spec["name"]))
    if created or republished:
        await session.commit()
        _log.info(
            "seeded demo skills",
            extra={"names": created, "republished": republished},
        )
    return created


async def seed_demo_workflows(
    session: Any,
    profile: SeedProfile,
    *,
    tenant_id: UUID,
    workspace_id: UUID | None,
) -> list[str]:
    """种**演示工作流** —— 绑在真智能体上."""
    if profile.label != "demo" or workspace_id is None:
        return []

    from qzdap.modules.agent_runtime.adapter.persistence.catalog_repositories import (
        SqlCatalogAgentRepository,
    )
    from qzdap.modules.orchestration.adapter.persistence.repositories import (
        SqlWorkflowRepository,
        SqlWorkflowRunRepository,
        SqlWorkflowUserStateRepository,
    )
    from qzdap.modules.orchestration.application.services import OrchestrationService

    agent_repo = SqlCatalogAgentRepository(session)
    agents = await agent_repo.list_for_workspace(workspace_id)
    agent_ids = {agent.name: str(agent.id) for agent in agents}

    repo = SqlWorkflowRepository(session)
    service = OrchestrationService(
        repo,
        user_state=SqlWorkflowUserStateRepository(session),
        runs=SqlWorkflowRunRepository(session),
    )
    existing = {flow["name"] for flow in await service.list_admin(workspace_id=workspace_id)}
    owner = profile.accounts[0][1] if profile.accounts else "演示管理员"

    created: list[str] = []
    for spec in DEMO_WORKFLOW_SPECS:
        if spec["name"] in existing:
            continue
        bound = [
            agent_ids[name] for name in spec.get("boundAgentNames", []) if name in agent_ids
        ]
        await service.create(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            body={
                "name": spec["name"],
                "description": spec["description"],
                "owner": owner,
                "scene": spec["scene"],
                "trigger": spec["trigger"],
                "status": spec["status"],
                "boundAgents": bound,
            },
        )
        created.append(str(spec["name"]))
    if created:
        await session.commit()
        _log.info("seeded demo workflows", extra={"names": created})
    return created


async def seed_demo_knowledge(
    session: Any,
    profile: SeedProfile,
    *,
    tenant_id: UUID,
    workspace_id: UUID | None,
) -> list[str]:
    """种**演示知识库 + 文档** —— 走真实的 ingest 路径（本地切块, 不用模型）."""
    if profile.label != "demo" or workspace_id is None:
        return []

    from qzdap.modules.knowledge.adapter.persistence.repositories import (
        SqlKnowledgeCatalogRepository,
    )
    from qzdap.modules.knowledge.application.services import KnowledgeService

    # embedding / vectors 传 None: 演示环境没配嵌入供应商, 切块和检索
    # 向量留到运营真配了嵌入服务再说 —— 不能拿假向量糊弄.
    service = KnowledgeService(SqlKnowledgeCatalogRepository(session))
    owner = profile.accounts[0][1] if profile.accounts else "演示管理员"

    existing = {kb["name"] for kb in await service.list_kbs(workspace_id=workspace_id)}
    doc_names = {doc["name"] for doc in await service.list_docs(workspace_id=workspace_id)}

    created: list[str] = []
    for spec in DEMO_KB_SPECS:
        if spec["name"] in existing:
            continue
        kb = await service.create_kb(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            body={
                "name": spec["name"],
                "description": spec["description"],
                "scope": spec["scope"],
                "retrieval": spec["retrieval"],
                "topK": spec["topK"],
                "boundSources": [],
            },
            owner=owner,
        )
        for doc in spec.get("docs", []):
            if doc["name"] in doc_names:
                continue
            await service.ingest_doc(
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                body={
                    "kbId": kb["id"],
                    "name": doc["name"],
                    "type": doc["type"],
                    "content": doc["content"],
                },
            )
        created.append(str(spec["name"]))
    if created:
        await session.commit()
        _log.info("seeded demo knowledge bases", extra={"names": created})
    return created


#: 演示用的**多轮对话** —— 模拟数据, 不需要真的接模型.
#:
#: 演示环境不配 LLM 供应商也能有"聊过的记录": 演示时点开就能看到完整的
#: 多轮问答 (含一次工具调用), 不用现场等模型回话.
#:
#: 每条消息是 ``(role, content)`` 或 ``(role, tool_name, content)``;
#: role ∈ user / assistant / tool. ``title`` 会显示在会话列表里,
#: ``owner`` 决定这条对话挂在哪个演示账号名下.
DEMO_CONVERSATION_SPECS: tuple[dict[str, Any], ...] = (
    {
        "agent": "经营数据分析",
        "owner": "user@acme.com",
        "title": "上周各渠道毛利对比",
        "messages": [
            ("user", "帮我拉一下上周各渠道的毛利额，排个名，顺便看看毛利率。"),
            (
                "tool",
                "csv_query",
                "已读取渠道订单明细 128 行，字段：渠道、订单额、成本额、订单数。",
            ),
            (
                "assistant",
                (
                    "按毛利额排序（上周一至周日）：\n"
                    "1. 直营门店 —— 毛利额 82.4 万，毛利率 31.2%\n"
                    "2. 企业直销 —— 毛利额 61.7 万，毛利率 27.8%\n"
                    "3. 线上商城 —— 毛利额 24.9 万，毛利率 22.4%\n"
                    "4. 渠道分销 —— 毛利额 11.3 万，毛利率 14.1%\n\n"
                    "分销的毛利率明显偏低，订单数只有直营的 6%，但折扣率是最高的。"
                ),
            ),
            ("user", "渠道分销为什么毛利这么低？"),
            (
                "assistant",
                (
                    "两个原因，都能在刚才那份数据里对上：\n"
                    "1. 折扣 —— 分销渠道平均折扣 8.5 折，其它渠道在 9 折以上。\n"
                    "2. 结构 —— 分销的订单里 63% 是小批量备货，单均履约成本高。\n\n"
                    "要压缩的话，先看折扣：把 8.5 折收回到 9 折，按上周单量估算能补回约 6 万毛利。"
                ),
            ),
        ],
    },
    {
        "agent": "销售线索洞察助手",
        "owner": "admin@acme.com",
        "title": "本周新线索分派",
        "messages": [
            ("user", "本周新增线索有 40 多条，能按价值分一下吗？"),
            (
                "tool",
                "csv_query",
                "已读取本周新增线索 43 条，字段：来源、行业、预算区间、跟进状态。",
            ),
            (
                "assistant",
                (
                    "按「预算 × 行业匹配度」打了分，分三档：\n"
                    "· 高优先（15 条）：制造业 + 预算 50 万以上，建议今天就分派。\n"
                    "· 中优先（19 条）：预算 20~50 万，本周内分派即可。\n"
                    "· 低优先（9 条）：预算 20 万以下或行业不匹配，先进培育池。\n\n"
                    "高优先里有一条来自汽车零配件、预算 80 万，值得优先跟进。"
                ),
            ),
            ("user", "那条 80 万的帮我起个跟进话术。"),
            (
                "assistant",
                (
                    "可以直接用这一版：\n\n"
                    "「王总您好，看到贵司在汽车零配件这块有新的产线规划。我们这季度有 3 家同类客户"
                    "把供应商切换周期压到了 6 周以内，可以约 30 分钟聊聊贵司现在的交付瓶颈在哪，"
                    "我们按那条链路给个初步方案。」\n\n"
                    "避开的：别一上来就报价，这条线索还没确认预算归属。"
                ),
            ),
        ],
    },
    {
        "agent": "客服应答助手",
        "owner": "user@acme.com",
        "title": "导出功能偶发失败的标准回复",
        "messages": [
            ("user", "客户反馈批量导出偶尔失败，帮我写一段可以直接发的回复。"),
            (
                "tool",
                "web_search",
                "检索到 3 条相关工单，均为「导出任务排队超时」，集中在月末高峰时段。",
            ),
            (
                "assistant",
                (
                    "这段可以直接发：\n\n"
                    "「您好，导出失败的情况我们已经在排查了。目前确认是月末导出任务集中排队导致的，"
                    "不是您的数据有问题。临时处理办法：把导出时间拆成两批（上午/下午各一次），"
                    "基本都能成功。我们会在本周内发布扩容版本，之后不需要再拆分了。给您带来不便很抱歉。」\n\n"
                    "如果客户追问具体时间，可以补一句「本周五前上线」，别承诺具体到小时。"
                ),
            ),
            ("user", "那要不要提到具体原因？排队这个词会不会显得我们在甩锅？"),
            (
                "assistant",
                (
                    "建议提，但换说法。「排队」容易读成「怪你导多了」——改成：\n\n"
                    "「导出功能我们做了扩容，目前正在分批发布。今天遇到问题的朋友可以先用「分批导出」"
                    "绕开，扩容完成后就不需要了。」\n\n"
                    "先给办法、再给原因，顺序反过来体验会好很多。"
                ),
            ),
        ],
    },
)


async def seed_demo_conversations(
    session: Any,
    profile: SeedProfile,
    *,
    tenant_id: UUID,
    workspace_id: UUID | None,
) -> list[str]:
    """种**演示用的多轮对话** —— 模拟数据, 不调用模型.

    演示环境没配 LLM 供应商时, 对话入口会返回 503; 但"聊过的记录"应该
    还在 —— 所以这里直接写会话与消息, 演示时点开就能看到多轮问答.
    """
    if profile.label != "demo" or workspace_id is None:
        return []

    from qzdap.modules.agent_runtime.adapter.persistence.catalog_repositories import (
        SqlCatalogAgentRepository,
        SqlSessionMessageRepository,
    )
    from qzdap.modules.agent_runtime.adapter.persistence.models import SessionORM
    from qzdap.modules.agent_runtime.adapter.persistence.repositories import (
        SqlSessionRepository,
    )
    from qzdap.modules.agent_runtime.domain.entities import Session
    from qzdap.modules.identity.adapter.persistence.models import UserORM
    from qzdap_schema.ids import AgentId, SessionId, TenantId, UserId, WorkspaceId
    from sqlalchemy import select

    agent_repo = SqlCatalogAgentRepository(session)
    agents = {agent.name: agent for agent in await agent_repo.list_for_workspace(workspace_id)}
    session_repo = SqlSessionRepository(session)
    message_repo = SqlSessionMessageRepository(session)

    users = {
        str(email): user
        for user, email in (
            (row, str(row.email))
            for row in (
                await session.execute(select(UserORM).where(UserORM.tenant_id == tenant_id))
            )
            .scalars()
            .all()
        )
    }

    created: list[str] = []
    for spec in DEMO_CONVERSATION_SPECS:
        agent = agents.get(spec["agent"])
        owner = users.get(spec["owner"])
        if agent is None or owner is None:
            _log.warning(
                "demo conversation skipped (agent or owner missing)",
                extra={"title": spec["title"]},
            )
            continue
        # 幂等: 同一个 owner 下同名标题的会话不重复种.
        existing_titles = {
            str((row.metadata_ or {}).get("title") or "")
            for row in (
                await session.execute(
                    select(SessionORM).where(
                        SessionORM.tenant_id == tenant_id,
                        SessionORM.owner_id == owner.id,
                    )
                )
            )
            .scalars()
            .all()
        }
        if spec["title"] in existing_titles:
            continue

        messages = spec["messages"]
        first_reply = next(
            (m[-1] for m in messages if m[0] == "assistant"), ""
        )
        conversation = Session.create(
            id=SessionId(uuid4()),
            tenant_id=TenantId(tenant_id),
            workspace_id=WorkspaceId(workspace_id),
            owner_id=UserId(owner.id),
            agent_id=AgentId(agent.id),
            agent_version=agent.version or "v1",
            metadata={
                "title": spec["title"],
                "preview": first_reply[:80],
                "agentName": agent.name,
                "model": agent.model,
                "rolling_summary": "",
                "title_auto": False,
            },
        )
        await session_repo.add(conversation)

        for seq, message in enumerate(messages):
            role = message[0]
            if role == "tool":
                tool_name, content = message[1], message[2]
            else:
                tool_name, content = "", message[1]
            await message_repo.append(
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                session_id=conversation.id,
                turn_id=None,
                seq=seq,
                role=role,
                content=content,
                tool_name=tool_name,
            )
        created.append(str(spec["title"]))

    if created:
        await session.commit()
        _log.info("seeded demo conversations", extra={"titles": created})
    return created


#: 演示用的**三层记忆** —— 让 /admin/memory 有东西可看, 可 flush / 可晋升.
#:
#: 真实记忆是聊天时提炼出来的; 演示环境不配模型就没有这些行, 记忆管理页
#: 会是一片空白. 这里直接按领域模型造一批, 让演示能点得到.
DEMO_MEMORY_SPECS: dict[str, tuple[dict[str, Any], ...]] = {
    "l1": (
        {
            "user": "Demo User",
            "agent": "客服应答助手",
            "buffer": "客户问的是退款进度, 订单号 SO-20240517, 已查过物流.",
            "tokens": 4820,
            "ttl_remain": 38,
            "status": "active",
        },
        {
            "user": "Demo User",
            "agent": "销售线索洞察助手",
            "buffer": "客户是华东区的连锁零售, 关注续约周期和门店数.",
            "tokens": 3140,
            "ttl_remain": 12,
            "status": "active",
        },
        {
            "user": "Demo Admin",
            "agent": "经营数据分析",
            "buffer": "本周要看的指标: 渠道毛利额、订单数、退款率.",
            "tokens": 2180,
            "ttl_remain": 45,
            "status": "active",
        },
    ),
    "l2": (
        {
            "user": "Demo User",
            "key": "答复风格",
            "value": "喜欢精简答复, 3 行内给结论",
            "category": "preference",
            "confidence": 0.96,
            "status": "confirmed",
        },
        {
            "user": "Demo User",
            "key": "负责领域",
            "value": "负责客户成功团队, 日常对接 SaaS 客户",
            "category": "fact",
            "confidence": 0.92,
            "status": "confirmed",
        },
        {
            "user": "Demo User",
            "key": "退款口径",
            "value": "退款需在 7 天内申请, 超时走人工工单",
            "category": "context",
            "confidence": 0.88,
            "status": "confirmed",
        },
        {
            "user": "Demo Admin",
            "key": "数据单位偏好",
            "value": "金额一律使用 ¥, 保留两位小数",
            "category": "preference",
            "confidence": 0.89,
            "status": "confirmed",
        },
        {
            "user": "Demo Admin",
            "key": "关注指标",
            "value": "日活、留存、转化漏斗",
            "category": "fact",
            "confidence": 0.84,
            "status": "pending",
        },
    ),
    "l3": (
        {
            "team": "客服团队",
            "title": "退款话术模板",
            "summary": "5 类退款场景的标准回复模板, 带情绪分级.",
            "category": "话术",
            "contributor": "客服一组",
            "status": "published",
            "hits": 524,
        },
        {
            "team": "产品团队",
            "title": "业务术语对照表",
            "summary": "内部术语、缩写、产品代号的官方解释, 所有智能体引用时优先检索.",
            "category": "术语表",
            "contributor": "产品团队",
            "status": "published",
            "hits": 1280,
        },
        {
            "team": "研发团队",
            "title": "API 设计规范",
            "summary": "REST 命名、错误码、版本策略; 新智能体工程助手输出代码需符合.",
            "category": "规范",
            "contributor": "研发架构组",
            "status": "draft",
            "hits": 612,
        },
    ),
}


async def seed_demo_memory(
    session: Any,
    profile: SeedProfile,
    *,
    tenant_id: UUID,
    workspace_id: UUID | None,
) -> dict[str, int]:
    """种演示用的三层记忆 —— 让记忆管理页不是空的.

    幂等: 工作区里已经有记忆行就整体跳过 —— 记忆是聊天时**累积**出来的,
    跟智能体/技能那种"看一眼有没有"的不一样, 重复种会把真实记忆冲掉.
    """
    if profile.label != "demo" or workspace_id is None:
        return {}

    from qzdap.modules.memory.adapter.persistence.repositories import (
        SqlMemoryCatalogRepository,
    )
    from qzdap.modules.memory.domain.entities import (
        L1Session,
        L2Fact,
        L3Entry,
        PromotionEvent,
    )

    catalog = SqlMemoryCatalogRepository(session)
    if await catalog.list_l1(workspace_id) or await catalog.list_l2(workspace_id):
        return {}

    now = datetime.now(UTC)
    counts = {"l1": 0, "l2": 0, "l3": 0, "promotions": 0}

    l1_ids: list[str] = []
    for spec in DEMO_MEMORY_SPECS["l1"]:
        session_row = L1Session(
            id=uuid4(),
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            user_name=spec["user"],
            agent_name=spec["agent"],
            buffer_size=len(spec["buffer"]) // 4,
            tokens_used=spec["tokens"],
            ttl_minutes=60,
            ttl_remain_min=spec["ttl_remain"],
            status=spec["status"],
            updated_at=now,
            created_at=now,
            buffer_text=spec["buffer"],
        )
        await catalog.add_l1(session_row)
        l1_ids.append(str(session_row.id))
        counts["l1"] += 1

    l2_ids: list[str] = []
    for index, spec in enumerate(DEMO_MEMORY_SPECS["l2"]):
        fact = L2Fact(
            id=uuid4(),
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            user_name=spec["user"],
            key=spec["key"],
            value=spec["value"],
            category=spec["category"],
            source_session=l1_ids[index % len(l1_ids)],
            confidence=spec["confidence"],
            status=spec["status"],
            promoted_to_l3=False,
            updated_at=now,
            created_at=now,
            usage_history=["刚刚", "1 小时前", "昨天"],
        )
        await catalog.add_l2(fact)
        l2_ids.append(str(fact.id))
        counts["l2"] += 1
        await catalog.add_promotion(
            PromotionEvent(
                id=uuid4(),
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                layer="l1→l2",
                label=f"{fact.user_name} · {fact.key}: {fact.value[:24]}",
                operator="系统自动提炼",
                target_id=str(fact.id),
                created_at=now,
            )
        )
        counts["promotions"] += 1

    for spec in DEMO_MEMORY_SPECS["l3"]:
        entry = L3Entry.create(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            team=spec["team"],
            title=spec["title"],
            summary=spec["summary"],
            category=spec["category"],
            contributor=spec["contributor"],
            status=spec["status"],
        )
        entry.hits = spec["hits"]
        entry.hits_trend = [spec["hits"] // 2, spec["hits"] - spec["hits"] // 4, spec["hits"]]
        await catalog.add_l3(entry)
        counts["l3"] += 1

    # 一条 l2→l3 的晋升记录, 让"晋升"这条链路在演示里有来龙去脉.
    promoted_fact = await catalog.get_l2(UUID(l2_ids[2]))
    promoted_entry = (await catalog.list_l3(workspace_id))[0]
    if promoted_fact is not None:
        promoted_fact.promoted_to_l3 = True
        promoted_fact.updated_at = now
        await catalog.update_l2(promoted_fact)
        promoted_entry.promoted_from_l2_ids = [str(promoted_fact.id)]
        await catalog.update_l3(promoted_entry)
    await catalog.add_promotion(
        PromotionEvent(
            id=uuid4(),
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            layer="l2→l3",
            label=f"{promoted_entry.team} · {promoted_entry.title}发布",
            operator="演示管理员",
            target_id=str(promoted_entry.id),
            created_at=now,
        )
    )
    counts["promotions"] += 1

    await session.commit()
    _log.info("seeded demo memory", extra={"counts": counts})
    return counts


async def seed_demo_content(
    session: Any,
    profile: SeedProfile,
    *,
    tenant_id: UUID,
    workspace_id: UUID | None,
) -> dict[str, Any]:
    """把演示内容一次种齐 —— 智能体 → 技能 → 工作流 → 知识库 → 对话 → 记忆.

    顺序有讲究: 工作流要绑智能体, 所以智能体必须先种.
    """
    agents = await seed_demo_agents(
        session, profile, tenant_id=tenant_id, workspace_id=workspace_id
    )
    skills = await seed_demo_skills(
        session, profile, tenant_id=tenant_id, workspace_id=workspace_id
    )
    workflows = await seed_demo_workflows(
        session, profile, tenant_id=tenant_id, workspace_id=workspace_id
    )
    knowledge = await seed_demo_knowledge(
        session, profile, tenant_id=tenant_id, workspace_id=workspace_id
    )
    conversations = await seed_demo_conversations(
        session, profile, tenant_id=tenant_id, workspace_id=workspace_id
    )
    memory = await seed_demo_memory(
        session, profile, tenant_id=tenant_id, workspace_id=workspace_id
    )
    return {
        "agents": agents,
        "skills": skills,
        "workflows": workflows,
        "knowledge": knowledge,
        "conversations": conversations,
        "memory": memory,
    }


def _children_first(
    tables: list[str], child_to_parent: dict[str, set[str]]
) -> list[str]:
    """按外键依赖排删除顺序 —— **子表先删**, 父表后删.

    ``child_to_parent[child]`` 是 child 引用的父表. 删的时候反过来:
    一张表只有在"引用它的那些表"都删完之后才能删 —— 否则父行还被子行
    指着, 外键会拦下来 (``agent_versions`` → ``agent_templates`` 就是
    这种关系).

    只在给定的 ``tables`` 里排序; 引用了不在集合里的表时忽略那条边
    (那些行不属于 demo 租户, 不会挡路).
    """
    parent_to_children: dict[str, set[str]] = {}
    for child, parents in child_to_parent.items():
        for parent in parents:
            parent_to_children.setdefault(parent, set()).add(child)

    remaining = list(tables)
    known = set(remaining)
    ordered: list[str] = []
    placed: set[str] = set()
    while remaining:
        progressed = False
        for table in list(remaining):
            children = parent_to_children.get(table, set()) & known
            # 引用它的表还没删 → 这张表现在不能删.
            if any(child not in placed for child in children):
                continue
            ordered.append(table)
            placed.add(table)
            remaining.remove(table)
            progressed = True
        if not progressed:
            # 有环 —— 剩下的按原顺序追加, 让 DB 自己报约束错误.
            ordered.extend(remaining)
            break
    return ordered


async def prune_demo_data(session: Any) -> dict[str, Any]:
    """把开发库里残留的 demo 数据清掉.

    早期的启动种子会给 development 环境种一套 ``Demo Tenant`` +
    ``admin@acme.com``, 后来改成分离之后那些行还留在老库里. 这个函数
    把它们删掉 —— 开发环境不该有 demo 数据.

    做法: 找出 demo 租户 (slug='demo') 和 demo 账号, 然后

    1. 扫一遍库里所有带 ``tenant_id`` 列的表, 删掉属于 demo 租户的行
       —— 各模块的数据都是 tenant-scoped 的, 一次扫干净.
    2. 删掉 demo 账号 (``*@acme.com``) 和它的工作区成员关系.

    只在**显式跑 dev 种子脚本**时调用, 不会在启动时自动删数据.
    """
    from qzdap.modules.identity.adapter.persistence.models import (
        APIKeyORM,
        TenantORM,
        UserORM,
        UserSessionORM,
        UserWorkspaceORM,
        WorkspaceORM,
    )
    from sqlalchemy import bindparam, delete, select, text

    demo_tenant_ids = [
        row
        for (row,) in (
            await session.execute(
                select(TenantORM.id).where(TenantORM.slug == "demo")
            )
        ).all()
    ]
    demo_user_ids = [
        row
        for (row,) in (
            await session.execute(
                select(UserORM.id).where(UserORM.email.like("%@acme.com"))
            )
        ).all()
    ]
    if not demo_tenant_ids and not demo_user_ids:
        return {"tenants": 0, "users": 0, "tables": 0}

    # 1. 各模块的 tenant-scoped 行 —— 挨个表扫.
    #    删除顺序必须尊重外键 (子表先删), 所以先按 information_schema 里的
    #    外键关系排个拓扑序 —— agent_templates ← agent_versions 就是这种.
    fk_rows = (
        await session.execute(
            text(
                "SELECT tc.table_name, ccu.table_name "
                "FROM information_schema.table_constraints tc "
                "JOIN information_schema.key_column_usage kcu "
                "  ON tc.constraint_name = kcu.constraint_name "
                "JOIN information_schema.constraint_column_usage ccu "
                "  ON ccu.constraint_name = tc.constraint_name "
                "WHERE tc.constraint_type = 'FOREIGN KEY' "
                "AND tc.table_schema = current_schema() "
                "AND ccu.table_schema = current_schema()"
            )
        )
    ).all()
    child_to_parent: dict[str, set[str]] = {}
    for child, parent in fk_rows:
        child_to_parent.setdefault(str(child), set()).add(str(parent))

    tables = [
        str(name)
        for (name,) in (
            await session.execute(
                text(
                    "SELECT table_name FROM information_schema.columns "
                    "WHERE column_name = 'tenant_id' "
                    "AND table_schema = current_schema() "
                    "ORDER BY table_name"
                )
            )
        ).all()
    ]
    swept = 0
    if demo_tenant_ids:
        for table in _children_first(tables, child_to_parent):
            # 表名来自 information_schema, 不是外部输入; 再挡一层只允许标识符字符.
            if not table.replace("_", "").isalnum():
                continue
            result = await session.execute(
                text(f'DELETE FROM "{table}" WHERE tenant_id IN :ids').bindparams(
                    bindparam("ids", expanding=True)
                ),
                {"ids": list(demo_tenant_ids)},
            )
            swept += int(result.rowcount or 0)

    # 2. demo 账号 —— 它的成员关系 / API key / 会话跟着级联删.
    if demo_user_ids:
        await session.execute(
            delete(UserWorkspaceORM).where(UserWorkspaceORM.user_id.in_(demo_user_ids))
        )
        await session.execute(
            delete(UserSessionORM).where(UserSessionORM.user_id.in_(demo_user_ids))
        )
        await session.execute(
            delete(APIKeyORM).where(APIKeyORM.owner_user_id.in_(demo_user_ids))
        )
        await session.execute(delete(UserORM).where(UserORM.id.in_(demo_user_ids)))
    if demo_tenant_ids:
        await session.execute(
            delete(UserWorkspaceORM).where(
                UserWorkspaceORM.tenant_id.in_(demo_tenant_ids)
            )
        )
        await session.execute(
            delete(WorkspaceORM).where(WorkspaceORM.tenant_id.in_(demo_tenant_ids))
        )
        await session.execute(
            delete(TenantORM).where(TenantORM.id.in_(demo_tenant_ids))
        )
    await session.commit()
    _log.info(
        "pruned demo data from dev database",
        extra={
            "tenants": len(demo_tenant_ids),
            "users": len(demo_user_ids),
            "rows": swept,
        },
    )
    return {
        "tenants": len(demo_tenant_ids),
        "users": len(demo_user_ids),
        "tables": swept,
    }


__all__ = [
    "DEMO_AGENT_MODEL",
    "DEMO_AGENT_SPECS",
    "DEMO_CONVERSATION_SPECS",
    "DEMO_KB_SPECS",
    "DEMO_SKILL_SPECS",
    "DEMO_WORKFLOW_SPECS",
    "SeedProfile",
    "demo_profile",
    "dev_profile",
    "profile_for_env",
    "prune_demo_data",
    "seed_builtin_tools",
    "seed_demo_agents",
    "seed_demo_content",
    "seed_demo_conversations",
    "seed_demo_knowledge",
    "seed_demo_skills",
    "seed_demo_workflows",
    "seed_identity",
]
